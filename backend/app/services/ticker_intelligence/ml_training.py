import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import sqrt

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import (
    ComparativeMetricResponse,
    ModelComparisonRowResponse,
    PriceBackfillResponse,
    PriceFeatureBuildCreate,
    PriceFeatureBuildResponse,
    PortfolioFitResponse,
    PredictiveModelPredictCreate,
    PredictiveModelPredictionResponse,
    PredictiveModelTrainCreate,
    PredictiveModelTrainResponse,
    TickerAnalysisCreate,
    TickerComparativeResponse,
    TickerDatasetRowResponse,
    TickerMLReportResponse,
    TrainingLabelGenerateCreate,
    TrainingLabelResponse,
    YahooPriceBackfillCreate,
)
from app.models import CashLedgerEntry, Instrument, MarketPriceBar, ModelVersion, Portfolio, Position, TickerFeatureSnapshot, TickerTrainingLabel
from app.services.portfolio.operating_core import DEFAULT_PORTFOLIO_NAME, upsert_instrument

logger = logging.getLogger(__name__)

FEATURE_VERSION = "ticker_features_v1"
PRICE_FEATURE_VERSION = "price_features_v1"
LABEL_VERSION = "forward_returns_v1"
PREDICTIVE_MODEL_NAME = "Ticker Relative Return ML"
PREDICTIVE_MODEL_POD = "Quantitative Equity Pod"
PRICE_FEATURE_NAMES = [
    "return_21d_pct",
    "return_63d_pct",
    "return_126d_pct",
    "price_vs_200d_pct",
    "realized_volatility_21d_pct",
    "realized_volatility_63d_pct",
    "max_drawdown_63d_pct",
]
FUNDAMENTAL_FEATURE_NAMES = [
    "market_cap_billion",
    "pe_ratio",
    "forward_pe",
    "revenue_growth_pct",
    "earnings_growth_pct",
    "free_cash_flow_yield_pct",
    "net_margin_pct",
    "debt_to_equity",
]


class MLTrainingDataUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class PriceBarPoint:
    bar_date: date
    close_price: Decimal
    adjusted_close_price: Decimal | None = None
    open_price: Decimal | None = None
    high_price: Decimal | None = None
    low_price: Decimal | None = None
    volume: int | None = None
    raw_payload: dict | None = None

    @property
    def label_price(self) -> Decimal:
        return self.adjusted_close_price or self.close_price


@dataclass(frozen=True)
class ForwardTrainingLabel:
    as_of_date: date
    horizon_days: int
    forward_return_pct: Decimal
    benchmark_forward_return_pct: Decimal | None
    relative_return_pct: Decimal | None
    max_drawdown_pct: Decimal | None
    realized_volatility_pct: Decimal | None
    raw_payload: dict


async def backfill_yahoo_prices(
    session: AsyncSession,
    payload: YahooPriceBackfillCreate,
) -> PriceBackfillResponse:
    instrument = await upsert_instrument(
        session,
        InstrumentCreate(
            ticker=payload.ticker,
            name=payload.name or payload.ticker.upper(),
            asset_class=payload.asset_class,
            exchange=payload.exchange,
            currency=payload.currency.upper(),
        ),
    )
    yahoo_symbol = payload.yahoo_symbol or payload.ticker
    bars = await fetch_yahoo_daily_bars(
        yahoo_symbol,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    rows_saved = await upsert_price_bars(
        session,
        instrument=instrument,
        bars=bars,
        source="yahoo",
    )
    await session.commit()

    logger.info(
        "yahoo_price_backfill_completed",
        extra={
            "ticker": instrument.ticker,
            "yahoo_symbol": yahoo_symbol,
            "rows_fetched": len(bars),
            "rows_saved": rows_saved,
        },
    )

    return PriceBackfillResponse(
        ticker=instrument.ticker,
        source="yahoo",
        start_date=payload.start_date,
        end_date=payload.end_date,
        rows_fetched=len(bars),
        rows_saved=rows_saved,
    )


async def generate_training_labels(
    session: AsyncSession,
    payload: TrainingLabelGenerateCreate,
) -> TrainingLabelResponse:
    instrument = await _get_instrument(session, payload.ticker)
    if instrument is None:
        raise MLTrainingDataUnavailableError(f"{payload.ticker.upper()} is not in the instrument table.")

    bars = await _load_price_points(session, instrument.id, payload.source)
    if not bars:
        raise MLTrainingDataUnavailableError(f"No {payload.source} price bars found for {instrument.ticker}.")

    benchmark = None
    benchmark_bars = None
    if payload.benchmark_ticker:
        benchmark = await _get_instrument(session, payload.benchmark_ticker)
        if benchmark is None:
            raise MLTrainingDataUnavailableError(
                f"Benchmark {payload.benchmark_ticker.upper()} is not in the instrument table."
            )
        benchmark_bars = await _load_price_points(session, benchmark.id, payload.source)
        if not benchmark_bars:
            raise MLTrainingDataUnavailableError(
                f"No {payload.source} price bars found for benchmark {benchmark.ticker}."
            )

    labels = compute_forward_labels(
        bars,
        horizons=payload.horizons,
        benchmark_bars=benchmark_bars,
    )
    if benchmark is not None and not any(label.relative_return_pct is not None for label in labels):
        raise MLTrainingDataUnavailableError(
            f"No benchmark-aligned labels could be generated for {instrument.ticker} vs {benchmark.ticker}."
        )
    rows_saved = await upsert_training_labels(
        session,
        instrument=instrument,
        benchmark=benchmark,
        labels=labels,
        source=payload.source,
    )
    await session.commit()

    logger.info(
        "ticker_training_labels_generated",
        extra={
            "ticker": instrument.ticker,
            "benchmark_ticker": benchmark.ticker if benchmark is not None else None,
            "rows_saved": rows_saved,
        },
    )

    return TrainingLabelResponse(
        ticker=instrument.ticker,
        benchmark_ticker=benchmark.ticker if benchmark is not None else None,
        horizons=payload.horizons,
        labels_generated=rows_saved,
        first_as_of_date=labels[0].as_of_date if labels else None,
        last_as_of_date=labels[-1].as_of_date if labels else None,
    )


async def build_price_feature_snapshots(
    session: AsyncSession,
    payload: PriceFeatureBuildCreate,
) -> PriceFeatureBuildResponse:
    normalized_tickers = sorted(
        {ticker.strip().upper() for ticker in payload.tickers if ticker.strip()}
    )
    if not normalized_tickers:
        raise MLTrainingDataUnavailableError("At least one ticker is required.")

    snapshots_saved = 0
    first_as_of_date = None
    last_as_of_date = None

    for ticker in normalized_tickers:
        instrument = await _get_instrument(session, ticker)
        if instrument is None:
            raise MLTrainingDataUnavailableError(f"{ticker} is not in the instrument table.")

        bars = await _load_price_points(session, instrument.id, payload.source)
        snapshots = compute_price_feature_snapshots(
            bars,
            feature_version=payload.feature_version,
        )
        snapshots_saved += await upsert_price_feature_snapshots(
            session,
            instrument=instrument,
            snapshots=snapshots,
        )
        if snapshots:
            first_as_of_date = min(
                snapshots[0]["as_of_date"],
                first_as_of_date or snapshots[0]["as_of_date"],
            )
            last_as_of_date = max(
                snapshots[-1]["as_of_date"],
                last_as_of_date or snapshots[-1]["as_of_date"],
            )

    await session.commit()

    logger.info(
        "price_feature_snapshots_built",
        extra={
            "ticker_count": len(normalized_tickers),
            "feature_version": payload.feature_version,
            "snapshots_saved": snapshots_saved,
        },
    )

    return PriceFeatureBuildResponse(
        feature_version=payload.feature_version,
        source=payload.source,
        tickers=normalized_tickers,
        snapshots_saved=snapshots_saved,
        first_as_of_date=first_as_of_date,
        last_as_of_date=last_as_of_date,
    )


async def train_predictive_model(
    session: AsyncSession,
    payload: PredictiveModelTrainCreate,
) -> PredictiveModelTrainResponse:
    import numpy as np

    dataset = await _load_model_dataset(session, payload)
    if len(dataset) < 30:
        raise MLTrainingDataUnavailableError(
            f"At least 30 labeled rows are required to train. Found {len(dataset)}."
        )

    feature_names = _model_feature_names(dataset)
    x = np.array([[float(row["features"][name]) for name in feature_names] for row in dataset])
    y = np.array([float(row["label"]) for row in dataset])
    y_direction = np.array([1.0 if value > 0 else 0.0 for value in y])

    train_indexes, validation_indexes = _chronological_split_indexes(len(dataset))
    x_train = x[train_indexes]
    y_train = y[train_indexes]
    x_validation = x[validation_indexes]
    y_validation = y[validation_indexes]
    y_direction_train = y_direction[train_indexes]
    y_direction_validation = y_direction[validation_indexes]

    standardized = _standardize_train_validation(x_train, x_validation)
    ridge = _fit_ridge(standardized["train"], y_train, alpha=float(payload.ridge_alpha))
    train_prediction = _predict_linear(standardized["train"], ridge)
    validation_prediction = _predict_linear(standardized["validation"], ridge)

    logistic = _fit_logistic(standardized["train"], y_direction_train)
    validation_probability = _predict_logistic(standardized["validation"], logistic)
    validation_direction = (validation_probability >= 0.5).astype(float)

    residuals = y_validation - validation_prediction
    if len(residuals) == 0:
        residuals = y_train - train_prediction

    metrics = {
        "train_mae": _float4(_mean_absolute_error(y_train, train_prediction)),
        "validation_mae": _float4(_mean_absolute_error(y_validation, validation_prediction)),
        "validation_r2": _float4(_r2_score(y_validation, validation_prediction)),
        "validation_directional_accuracy": _float4(
            _accuracy(y_direction_validation, validation_direction)
        ),
        "residual_p05_pct": _float4(float(np.percentile(residuals, 5))),
        "training_rows": int(len(train_indexes)),
        "validation_rows": int(len(validation_indexes)),
        "validation_policy": "chronological_80_20",
    }
    artifact = {
        "feature_version": payload.feature_version,
        "feature_names": feature_names,
        "horizon_days": payload.horizon_days,
        "benchmark_ticker": payload.benchmark_ticker,
        "label_source": payload.label_source,
        "standardization": {
            "mean": {
                name: _float8(value)
                for name, value in zip(feature_names, standardized["mean"])
            },
            "std": {
                name: _float8(value)
                for name, value in zip(feature_names, standardized["std"])
            },
        },
        "ridge_regression": {
            "alpha": str(payload.ridge_alpha),
            "intercept": _float8(ridge["intercept"]),
            "coefficients": {
                name: _float8(value)
                for name, value in zip(feature_names, ridge["coefficients"])
            },
        },
        "logistic_regression": {
            "intercept": _float8(logistic["intercept"]),
            "coefficients": {
                name: _float8(value)
                for name, value in zip(feature_names, logistic["coefficients"])
            },
        },
        "residual_p05_pct": metrics["residual_p05_pct"],
    }
    model_version = ModelVersion(
        name=PREDICTIVE_MODEL_NAME,
        version=_model_version_label(payload.horizon_days),
        pod=PREDICTIVE_MODEL_POD,
        purpose="Predict ticker relative return and outperformance probability from historical price features.",
        training_data={
            "tickers": [ticker.strip().upper() for ticker in payload.tickers],
            "rows": len(dataset),
            "label_version": LABEL_VERSION,
            "label_source": payload.label_source,
            "benchmark_ticker": payload.benchmark_ticker,
        },
        features=artifact,
        metrics=metrics,
        assumptions="Historical price behavior contains useful signal for future benchmark-relative returns.",
        limitations="Price-first model. It includes point-in-time fundamentals when enough aligned rows exist, but does not yet include macro regime, liquidity, or transaction costs.",
        approved_use="Research forecasting, model comparison, and analyst decision support.",
        prohibited_use="Automatic trading, unrestricted sizing, or production deployment without out-of-sample review.",
        shutdown_criteria="Disable if validation accuracy deteriorates, residuals become unstable, or model disagrees persistently with realized outcomes.",
    )
    session.add(model_version)
    await session.commit()
    await session.refresh(model_version)

    logger.info(
        "ticker_predictive_model_trained",
        extra={
            "model_version_id": str(model_version.id),
            "horizon_days": payload.horizon_days,
            "training_rows": len(train_indexes),
            "validation_rows": len(validation_indexes),
        },
    )

    return PredictiveModelTrainResponse(
        model_version_id=model_version.id,
        model_name=model_version.name,
        model_version=model_version.version,
        horizon_days=payload.horizon_days,
        feature_version=payload.feature_version,
        training_rows=len(train_indexes),
        validation_rows=len(validation_indexes),
        feature_names=feature_names,
        metrics=metrics,
    )


async def predict_with_latest_model(
    session: AsyncSession,
    payload: PredictiveModelPredictCreate,
) -> PredictiveModelPredictionResponse:
    import numpy as np

    instrument = await _get_instrument(session, payload.ticker)
    if instrument is None:
        raise MLTrainingDataUnavailableError(f"{payload.ticker.upper()} is not in the instrument table.")

    model_version = await _load_model_version(
        session,
        model_version_id=payload.model_version_id,
        horizon_days=payload.horizon_days,
    )
    if model_version is None:
        raise MLTrainingDataUnavailableError(
            f"No predictive model found for {payload.horizon_days}-day horizon."
        )

    artifact = model_version.features or {}
    feature_names = artifact.get("feature_names") or PRICE_FEATURE_NAMES
    snapshot = await session.scalar(
        select(TickerFeatureSnapshot)
        .where(TickerFeatureSnapshot.instrument_id == instrument.id)
        .where(TickerFeatureSnapshot.feature_version == payload.feature_version)
        .order_by(TickerFeatureSnapshot.as_of_date.desc())
    )
    if snapshot is None:
        raise MLTrainingDataUnavailableError(
            f"No {payload.feature_version} snapshot found for {instrument.ticker}."
        )

    latest_fundamental_snapshot = await session.scalar(
        select(TickerFeatureSnapshot)
        .where(TickerFeatureSnapshot.instrument_id == instrument.id)
        .where(TickerFeatureSnapshot.feature_version == FEATURE_VERSION)
        .where(TickerFeatureSnapshot.as_of_date <= snapshot.as_of_date)
        .order_by(TickerFeatureSnapshot.as_of_date.desc())
    )
    prediction_features = dict(snapshot.features)
    if latest_fundamental_snapshot is not None:
        prediction_features.update(
            _extract_fundamental_features(latest_fundamental_snapshot.features)
        )

    missing_features = [
        name for name in feature_names if prediction_features.get(name) is None
    ]
    if missing_features:
        raise MLTrainingDataUnavailableError(
            f"Latest feature snapshot is missing model features: {', '.join(missing_features)}."
        )

    vector = np.array([float(prediction_features[name]) for name in feature_names])
    mean = np.array([float(artifact["standardization"]["mean"][name]) for name in feature_names])
    std = np.array([float(artifact["standardization"]["std"][name]) for name in feature_names])
    standardized_vector = (vector - mean) / std
    ridge = {
        "intercept": float(artifact["ridge_regression"]["intercept"]),
        "coefficients": np.array([
            float(artifact["ridge_regression"]["coefficients"][name])
            for name in feature_names
        ]),
    }
    logistic = {
        "intercept": float(artifact["logistic_regression"]["intercept"]),
        "coefficients": np.array([
            float(artifact["logistic_regression"]["coefficients"][name])
            for name in feature_names
        ]),
    }
    expected_relative_return = float(
        ridge["intercept"] + np.dot(standardized_vector, ridge["coefficients"])
    )
    probability_outperform = float(
        _sigmoid(logistic["intercept"] + np.dot(standardized_vector, logistic["coefficients"]))
    )
    residual_p05 = float(artifact.get("residual_p05_pct", 0))
    confidence = _prediction_confidence(model_version.metrics or {}, probability_outperform)

    return PredictiveModelPredictionResponse(
        ticker=instrument.ticker,
        model_version_id=model_version.id,
        model_version=model_version.version,
        as_of_date=snapshot.as_of_date,
        horizon_days=payload.horizon_days,
        expected_relative_return_pct=_decimal4(expected_relative_return),
        downside_p05_relative_return_pct=_decimal4(expected_relative_return + residual_p05),
        probability_outperform=_decimal4(probability_outperform),
        confidence_score=_decimal4(confidence),
        feature_version=payload.feature_version,
        drivers=_prediction_drivers(feature_names, standardized_vector, ridge["coefficients"]),
    )


async def build_ticker_ml_report(
    session: AsyncSession,
    ticker: str,
    horizon_days: int = 63,
) -> TickerMLReportResponse:
    normalized_ticker = ticker.strip().upper()
    warnings: list[str] = []

    comparative = await build_comparative_analysis(session, normalized_ticker)
    if comparative is None:
        warnings.append("Comparative analysis needs price feature snapshots.")

    prediction = None
    try:
        prediction = await predict_with_latest_model(
            session,
            PredictiveModelPredictCreate(
                ticker=normalized_ticker,
                horizon_days=horizon_days,
            ),
        )
    except MLTrainingDataUnavailableError as exc:
        warnings.append(str(exc))

    portfolio_fit = await build_portfolio_fit(
        session,
        normalized_ticker,
        prediction=prediction,
    )
    if portfolio_fit is None:
        warnings.append("Portfolio fit needs an instrument record and portfolio state.")

    model_comparison = await list_predictive_model_comparison(session)

    return TickerMLReportResponse(
        ticker=normalized_ticker,
        comparative=comparative,
        prediction=prediction,
        portfolio_fit=portfolio_fit,
        model_comparison=model_comparison,
        warnings=warnings,
    )


async def build_comparative_analysis(
    session: AsyncSession,
    ticker: str,
    feature_version: str = PRICE_FEATURE_VERSION,
) -> TickerComparativeResponse | None:
    instrument = await _get_instrument(session, ticker)
    if instrument is None:
        return None

    current_snapshot = await session.scalar(
        select(TickerFeatureSnapshot)
        .where(TickerFeatureSnapshot.instrument_id == instrument.id)
        .where(TickerFeatureSnapshot.feature_version == feature_version)
        .order_by(TickerFeatureSnapshot.as_of_date.desc())
    )
    if current_snapshot is None:
        return None

    history_snapshots = list(
        await session.scalars(
            select(TickerFeatureSnapshot)
            .where(TickerFeatureSnapshot.instrument_id == instrument.id)
            .where(TickerFeatureSnapshot.feature_version == feature_version)
            .order_by(TickerFeatureSnapshot.as_of_date)
        )
    )
    latest_universe = await _latest_universe_snapshots(session, feature_version)
    sector_snapshots = [
        row
        for row in latest_universe
        if row["sector"] and row["sector"] == instrument.sector
    ]

    metrics = []
    for feature_name in PRICE_FEATURE_NAMES:
        value = _decimal(current_snapshot.features.get(feature_name))
        if value is None:
            continue
        history_values = [
            item
            for item in (_decimal(snapshot.features.get(feature_name)) for snapshot in history_snapshots)
            if item is not None
        ]
        sector_values = [
            item
            for item in (_decimal(row["features"].get(feature_name)) for row in sector_snapshots)
            if item is not None
        ]
        universe_values = [
            item
            for item in (_decimal(row["features"].get(feature_name)) for row in latest_universe)
            if item is not None
        ]
        metrics.append(
            ComparativeMetricResponse(
                metric=feature_name,
                value=value,
                history_percentile=_percentile_rank(value, history_values),
                sector_percentile=_percentile_rank(value, sector_values),
                universe_percentile=_percentile_rank(value, universe_values),
                peer_count=max(len(sector_values) - 1, 0),
            )
        )

    return TickerComparativeResponse(
        ticker=instrument.ticker,
        as_of_date=current_snapshot.as_of_date,
        feature_version=feature_version,
        sector=instrument.sector,
        metrics=metrics,
    )


async def build_portfolio_fit(
    session: AsyncSession,
    ticker: str,
    prediction: PredictiveModelPredictionResponse | None,
) -> PortfolioFitResponse | None:
    instrument = await _get_instrument(session, ticker)
    if instrument is None:
        return None

    portfolio = await session.scalar(
        select(Portfolio).where(Portfolio.name == DEFAULT_PORTFOLIO_NAME)
    )
    if portfolio is None:
        return None
    cash_balance = await session.scalar(
        select(func.sum(CashLedgerEntry.amount)).where(
            CashLedgerEntry.portfolio_id == portfolio.id
        )
    )
    cash_balance = cash_balance or Decimal("0")
    positions = list(
        await session.scalars(
            select(Position)
            .options(selectinload(Position.instrument))
            .join(Position.instrument)
            .where(Position.portfolio_id == portfolio.id)
            .where(Position.quantity > 0)
        )
    )
    invested_value = sum((position.market_value for position in positions), Decimal("0"))
    nav = cash_balance + invested_value
    if nav <= 0:
        nav = Decimal("1")

    current_position_value = sum(
        (
            position.market_value
            for position in positions
            if position.instrument_id == instrument.id
        ),
        Decimal("0"),
    )
    sector_value = sum(
        (
            position.market_value
            for position in positions
            if position.instrument.sector == instrument.sector and instrument.sector is not None
        ),
        Decimal("0"),
    )
    current_weight = _quantize((current_position_value / nav) * Decimal("100"))
    proposed_weight = _proposed_weight_from_prediction(prediction, instrument.asset_class)
    pro_forma_weight = _quantize(current_weight + proposed_weight)
    sector_exposure_after = _quantize((sector_value / nav) * Decimal("100") + proposed_weight)
    concentration_after = max(
        [pro_forma_weight]
        + [_quantize((position.market_value / nav) * Decimal("100")) for position in positions]
    )
    expected_return = (
        prediction.expected_relative_return_pct
        if prediction is not None
        else Decimal("0")
    )
    downside = (
        prediction.downside_p05_relative_return_pct
        if prediction is not None
        else Decimal("-10")
    )
    confidence = (
        prediction.confidence_score
        if prediction is not None
        else Decimal("25")
    )
    score = compute_portfolio_fit_score(
        expected_relative_return_pct=expected_return,
        downside_p05_relative_return_pct=downside,
        confidence_score=confidence,
        concentration_after_pct=concentration_after,
        sector_exposure_after_pct=sector_exposure_after,
    )
    notes = _portfolio_fit_notes(
        expected_return,
        downside,
        confidence,
        concentration_after,
        sector_exposure_after,
    )

    return PortfolioFitResponse(
        ticker=instrument.ticker,
        portfolio_fit_score=score,
        improves_portfolio=score >= Decimal("60.0000") and proposed_weight > 0,
        current_position_weight=current_weight,
        proposed_weight=proposed_weight,
        pro_forma_weight=pro_forma_weight,
        concentration_after=concentration_after,
        sector_exposure_after=sector_exposure_after,
        notes=notes,
    )


async def list_predictive_model_comparison(
    session: AsyncSession,
    limit: int = 20,
) -> list[ModelComparisonRowResponse]:
    result = await session.scalars(
        select(ModelVersion)
        .where(ModelVersion.name == PREDICTIVE_MODEL_NAME)
        .order_by(ModelVersion.created_at.desc())
        .limit(limit)
    )
    rows = []
    for model_version in result:
        artifact = model_version.features or {}
        metrics = model_version.metrics or {}
        rows.append(
            ModelComparisonRowResponse(
                model_version_id=model_version.id,
                model_name=model_version.name,
                model_version=model_version.version,
                horizon_days=_optional_int_value(artifact.get("horizon_days")),
                feature_version=_optional_string(artifact.get("feature_version")),
                training_rows=_optional_int_value(metrics.get("training_rows")),
                validation_rows=_optional_int_value(metrics.get("validation_rows")),
                validation_mae=_optional_decimal(metrics.get("validation_mae")),
                validation_r2=_optional_decimal(metrics.get("validation_r2")),
                validation_directional_accuracy=_optional_decimal(
                    metrics.get("validation_directional_accuracy")
                ),
                residual_p05_pct=_optional_decimal(metrics.get("residual_p05_pct")),
                created_at=model_version.created_at,
            )
        )
    return rows


async def save_ticker_feature_snapshot(
    session: AsyncSession,
    instrument: Instrument,
    payload: TickerAnalysisCreate,
    scores: dict,
) -> TickerFeatureSnapshot:
    features = {
        "instrument": payload.instrument.model_dump(mode="json"),
        "metrics": payload.metrics.model_dump(mode="json"),
        "scores": scores,
        "time_horizon": payload.time_horizon,
        "investment_question": payload.investment_question,
    }
    quality_score = _feature_quality_score(payload)

    existing = await session.scalar(
        select(TickerFeatureSnapshot).where(
            TickerFeatureSnapshot.instrument_id == instrument.id,
            TickerFeatureSnapshot.as_of_date == payload.memo_date,
            TickerFeatureSnapshot.feature_version == FEATURE_VERSION,
        )
    )
    if existing is not None:
        existing.source_reference = payload.source_reference
        existing.features = features
        existing.quality_score = quality_score
        return existing

    snapshot = TickerFeatureSnapshot(
        instrument_id=instrument.id,
        as_of_date=payload.memo_date,
        feature_version=FEATURE_VERSION,
        source_reference=payload.source_reference,
        features=features,
        quality_score=quality_score,
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def list_ticker_dataset_rows(
    session: AsyncSession,
    ticker: str,
    limit: int = 100,
) -> list[TickerDatasetRowResponse]:
    instrument = await _get_instrument(session, ticker)
    if instrument is None:
        return []

    snapshots = list(
        await session.scalars(
            select(TickerFeatureSnapshot)
            .where(TickerFeatureSnapshot.instrument_id == instrument.id)
            .order_by(TickerFeatureSnapshot.as_of_date.desc())
            .limit(limit)
        )
    )
    if not snapshots:
        return []

    label_result = await session.scalars(
        select(TickerTrainingLabel)
        .where(TickerTrainingLabel.instrument_id == instrument.id)
        .where(
            TickerTrainingLabel.as_of_date.in_(
                [snapshot.as_of_date for snapshot in snapshots]
            )
        )
        .order_by(TickerTrainingLabel.as_of_date.desc(), TickerTrainingLabel.horizon_days)
    )
    labels_by_date: dict[date, list[dict]] = {}
    for label in label_result:
        labels_by_date.setdefault(label.as_of_date, []).append(
            {
                "horizon_days": label.horizon_days,
                "forward_return_pct": str(label.forward_return_pct),
                "benchmark_forward_return_pct": _optional_decimal_string(
                    label.benchmark_forward_return_pct
                ),
                "relative_return_pct": _optional_decimal_string(label.relative_return_pct),
                "max_drawdown_pct": _optional_decimal_string(label.max_drawdown_pct),
                "realized_volatility_pct": _optional_decimal_string(
                    label.realized_volatility_pct
                ),
                "source": label.source,
                "label_version": label.label_version,
            }
        )

    return [
        TickerDatasetRowResponse(
            as_of_date=snapshot.as_of_date,
            feature_version=snapshot.feature_version,
            features=snapshot.features,
            labels=labels_by_date.get(snapshot.as_of_date, []),
        )
        for snapshot in snapshots
    ]


async def fetch_yahoo_daily_bars(
    yahoo_symbol: str,
    start_date: date,
    end_date: date,
) -> list[PriceBarPoint]:
    if start_date > end_date:
        raise MLTrainingDataUnavailableError("Start date must be before end date.")

    try:
        import yfinance as yf
    except ImportError as exc:
        raise MLTrainingDataUnavailableError(
            "yfinance is not installed. Run `pip install -r backend/requirements.txt`."
        ) from exc

    def load_history():
        ticker = yf.Ticker(yahoo_symbol)
        return ticker.history(
            start=start_date.isoformat(),
            end=(end_date + _one_day()).isoformat(),
            auto_adjust=False,
            actions=False,
        )

    frame = await asyncio.to_thread(load_history)
    if frame is None or frame.empty:
        raise MLTrainingDataUnavailableError(f"Yahoo returned no rows for {yahoo_symbol}.")

    bars: list[PriceBarPoint] = []
    for index, row in frame.iterrows():
        bar_date = index.date()
        close_price = _decimal(row.get("Close"))
        if close_price is None:
            continue
        bars.append(
            PriceBarPoint(
                bar_date=bar_date,
                open_price=_decimal(row.get("Open")),
                high_price=_decimal(row.get("High")),
                low_price=_decimal(row.get("Low")),
                close_price=close_price,
                adjusted_close_price=_decimal(row.get("Adj Close")),
                volume=_optional_int(row.get("Volume")),
                raw_payload={
                    "yahoo_symbol": yahoo_symbol,
                    "open": _optional_string(row.get("Open")),
                    "high": _optional_string(row.get("High")),
                    "low": _optional_string(row.get("Low")),
                    "close": _optional_string(row.get("Close")),
                    "adjusted_close": _optional_string(row.get("Adj Close")),
                    "volume": _optional_string(row.get("Volume")),
                },
            )
        )
    return bars


async def upsert_price_bars(
    session: AsyncSession,
    instrument: Instrument,
    bars: list[PriceBarPoint],
    source: str,
) -> int:
    if not bars:
        return 0

    rows = [
        {
            "instrument_id": instrument.id,
            "bar_date": bar.bar_date,
            "source": source,
            "open_price": bar.open_price,
            "high_price": bar.high_price,
            "low_price": bar.low_price,
            "close_price": bar.close_price,
            "adjusted_close_price": bar.adjusted_close_price,
            "volume": bar.volume,
            "currency": instrument.currency,
            "raw_payload": bar.raw_payload or {},
        }
        for bar in bars
    ]
    statement = insert(MarketPriceBar).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_market_price_bars_instrument_date_source",
        set_={
            "open_price": statement.excluded.open_price,
            "high_price": statement.excluded.high_price,
            "low_price": statement.excluded.low_price,
            "close_price": statement.excluded.close_price,
            "adjusted_close_price": statement.excluded.adjusted_close_price,
            "volume": statement.excluded.volume,
            "currency": statement.excluded.currency,
            "raw_payload": statement.excluded.raw_payload,
        },
    )
    await session.execute(statement)
    return len(rows)


async def upsert_training_labels(
    session: AsyncSession,
    instrument: Instrument,
    benchmark: Instrument | None,
    labels: list[ForwardTrainingLabel],
    source: str,
) -> int:
    if not labels:
        return 0

    rows = [
        {
            "instrument_id": instrument.id,
            "benchmark_instrument_id": benchmark.id if benchmark is not None else None,
            "as_of_date": label.as_of_date,
            "horizon_days": label.horizon_days,
            "forward_return_pct": label.forward_return_pct,
            "benchmark_forward_return_pct": label.benchmark_forward_return_pct,
            "relative_return_pct": label.relative_return_pct,
            "max_drawdown_pct": label.max_drawdown_pct,
            "realized_volatility_pct": label.realized_volatility_pct,
            "label_version": LABEL_VERSION,
            "source": source,
            "raw_payload": label.raw_payload,
        }
        for label in labels
    ]
    statement = insert(TickerTrainingLabel).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_ticker_training_labels_identity",
        set_={
            "forward_return_pct": statement.excluded.forward_return_pct,
            "benchmark_forward_return_pct": statement.excluded.benchmark_forward_return_pct,
            "relative_return_pct": statement.excluded.relative_return_pct,
            "max_drawdown_pct": statement.excluded.max_drawdown_pct,
            "realized_volatility_pct": statement.excluded.realized_volatility_pct,
            "raw_payload": statement.excluded.raw_payload,
        },
    )
    await session.execute(statement)
    return len(rows)


async def upsert_price_feature_snapshots(
    session: AsyncSession,
    instrument: Instrument,
    snapshots: list[dict],
) -> int:
    if not snapshots:
        return 0

    rows = [
        {
            "instrument_id": instrument.id,
            "as_of_date": snapshot["as_of_date"],
            "feature_version": snapshot["feature_version"],
            "source_reference": snapshot["source_reference"],
            "features": snapshot["features"],
            "quality_score": snapshot["quality_score"],
        }
        for snapshot in snapshots
    ]
    statement = insert(TickerFeatureSnapshot).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_ticker_feature_snapshots_instrument_date_version",
        set_={
            "source_reference": statement.excluded.source_reference,
            "features": statement.excluded.features,
            "quality_score": statement.excluded.quality_score,
        },
    )
    await session.execute(statement)
    return len(rows)


def compute_forward_labels(
    bars: list[PriceBarPoint],
    horizons: list[int],
    benchmark_bars: list[PriceBarPoint] | None = None,
) -> list[ForwardTrainingLabel]:
    sorted_bars = sorted(bars, key=lambda bar: bar.bar_date)
    benchmark_by_date = (
        {bar.bar_date: bar for bar in benchmark_bars} if benchmark_bars else {}
    )
    labels: list[ForwardTrainingLabel] = []

    for horizon in sorted(set(horizons)):
        if horizon <= 0:
            continue
        for index, start_bar in enumerate(sorted_bars):
            future_index = index + horizon
            if future_index >= len(sorted_bars):
                continue

            future_bar = sorted_bars[future_index]
            path = sorted_bars[index : future_index + 1]
            forward_return = _return_pct(start_bar.label_price, future_bar.label_price)
            benchmark_return = _benchmark_return_pct(
                benchmark_by_date,
                start_bar.bar_date,
                future_bar.bar_date,
            )
            labels.append(
                ForwardTrainingLabel(
                    as_of_date=start_bar.bar_date,
                    horizon_days=horizon,
                    forward_return_pct=forward_return,
                    benchmark_forward_return_pct=benchmark_return,
                    relative_return_pct=(
                        _quantize(forward_return - benchmark_return)
                        if benchmark_return is not None
                        else None
                    ),
                    max_drawdown_pct=_max_drawdown_pct(path),
                    realized_volatility_pct=_realized_volatility_pct(path),
                    raw_payload={
                        "start_date": start_bar.bar_date.isoformat(),
                        "end_date": future_bar.bar_date.isoformat(),
                        "start_price": str(start_bar.label_price),
                        "end_price": str(future_bar.label_price),
                    },
                )
            )
    return labels


def compute_price_feature_snapshots(
    bars: list[PriceBarPoint],
    feature_version: str = PRICE_FEATURE_VERSION,
) -> list[dict]:
    sorted_bars = sorted(bars, key=lambda bar: bar.bar_date)
    snapshots: list[dict] = []

    for index, bar in enumerate(sorted_bars):
        if index < 200:
            continue
        path_to_date = sorted_bars[: index + 1]
        features = {
            "return_21d_pct": _lookback_return_pct(path_to_date, 21),
            "return_63d_pct": _lookback_return_pct(path_to_date, 63),
            "return_126d_pct": _lookback_return_pct(path_to_date, 126),
            "price_vs_200d_pct": _price_vs_average_pct(path_to_date, 200),
            "realized_volatility_21d_pct": _realized_volatility_pct(path_to_date[-22:]),
            "realized_volatility_63d_pct": _realized_volatility_pct(path_to_date[-64:]),
            "max_drawdown_63d_pct": _max_drawdown_pct(path_to_date[-64:]),
        }
        if any(value is None for value in features.values()):
            continue
        snapshots.append(
            {
                "as_of_date": bar.bar_date,
                "feature_version": feature_version,
                "source_reference": f"price-bars:{feature_version}:{bar.bar_date.isoformat()}",
                "features": {
                    key: str(value)
                    for key, value in features.items()
                    if value is not None
                },
                "quality_score": Decimal("100.00"),
            }
        )
    return snapshots


async def _get_instrument(session: AsyncSession, ticker: str) -> Instrument | None:
    normalized_ticker = ticker.strip().upper()
    return await session.scalar(
        select(Instrument).where(Instrument.ticker == normalized_ticker)
    )


async def _load_price_points(
    session: AsyncSession,
    instrument_id,
    source: str,
) -> list[PriceBarPoint]:
    result = await session.scalars(
        select(MarketPriceBar)
        .where(MarketPriceBar.instrument_id == instrument_id)
        .where(MarketPriceBar.source == source)
        .order_by(MarketPriceBar.bar_date)
    )
    return [
        PriceBarPoint(
            bar_date=bar.bar_date,
            open_price=bar.open_price,
            high_price=bar.high_price,
            low_price=bar.low_price,
            close_price=bar.close_price,
            adjusted_close_price=bar.adjusted_close_price,
            volume=bar.volume,
            raw_payload=bar.raw_payload,
        )
        for bar in result
    ]


async def _load_model_dataset(
    session: AsyncSession,
    payload: PredictiveModelTrainCreate,
) -> list[dict]:
    normalized_tickers = sorted(
        {ticker.strip().upper() for ticker in payload.tickers if ticker.strip()}
    )
    instruments = list(
        await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(normalized_tickers))
        )
    )
    instrument_ids = {instrument.id for instrument in instruments}
    if not instrument_ids:
        return []
    benchmark = (
        await _get_instrument(session, payload.benchmark_ticker)
        if payload.benchmark_ticker
        else None
    )

    snapshots = list(
        await session.scalars(
            select(TickerFeatureSnapshot)
            .where(TickerFeatureSnapshot.instrument_id.in_(instrument_ids))
            .where(TickerFeatureSnapshot.feature_version == payload.feature_version)
            .order_by(TickerFeatureSnapshot.as_of_date)
        )
    )
    fundamental_snapshots = list(
        await session.scalars(
            select(TickerFeatureSnapshot)
            .where(TickerFeatureSnapshot.instrument_id.in_(instrument_ids))
            .where(TickerFeatureSnapshot.feature_version == FEATURE_VERSION)
            .order_by(TickerFeatureSnapshot.as_of_date)
        )
    )
    snapshot_by_key = {
        (snapshot.instrument_id, snapshot.as_of_date): snapshot
        for snapshot in snapshots
        if _has_model_features(snapshot.features)
    }
    fundamentals_by_instrument = _group_fundamentals_by_instrument(fundamental_snapshots)
    label_query = (
        select(TickerTrainingLabel)
        .where(TickerTrainingLabel.instrument_id.in_(instrument_ids))
        .where(TickerTrainingLabel.horizon_days == payload.horizon_days)
        .where(TickerTrainingLabel.source == payload.label_source)
        .where(TickerTrainingLabel.label_version == LABEL_VERSION)
        .order_by(TickerTrainingLabel.as_of_date)
    )
    if payload.benchmark_ticker and benchmark is not None:
        label_query = label_query.where(
            TickerTrainingLabel.benchmark_instrument_id == benchmark.id
        )
    elif payload.benchmark_ticker:
        return []
    else:
        label_query = label_query.where(TickerTrainingLabel.benchmark_instrument_id.is_(None))

    labels = list(await session.scalars(label_query))

    dataset = []
    for label in labels:
        if label.relative_return_pct is None:
            continue
        snapshot = snapshot_by_key.get((label.instrument_id, label.as_of_date))
        if snapshot is None:
            continue
        fundamental_features = _latest_fundamental_features_as_of(
            fundamentals_by_instrument.get(label.instrument_id, []),
            label.as_of_date,
        )
        features = {
            **snapshot.features,
            **fundamental_features,
        }
        dataset.append(
            {
                "as_of_date": label.as_of_date,
                "instrument_id": str(label.instrument_id),
                "features": features,
                "label": label.relative_return_pct,
            }
        )
    return dataset


async def _load_model_version(
    session: AsyncSession,
    model_version_id,
    horizon_days: int,
) -> ModelVersion | None:
    if model_version_id is not None:
        return await session.get(ModelVersion, model_version_id)

    return await session.scalar(
        select(ModelVersion)
        .where(ModelVersion.name == PREDICTIVE_MODEL_NAME)
        .where(ModelVersion.features["horizon_days"].as_integer() == horizon_days)
        .order_by(ModelVersion.created_at.desc())
    )


def _has_model_features(features: dict) -> bool:
    return all(features.get(name) is not None for name in PRICE_FEATURE_NAMES)


async def _latest_universe_snapshots(
    session: AsyncSession,
    feature_version: str,
) -> list[dict]:
    rows = await session.execute(
        select(TickerFeatureSnapshot, Instrument)
        .join(Instrument, TickerFeatureSnapshot.instrument_id == Instrument.id)
        .where(TickerFeatureSnapshot.feature_version == feature_version)
        .order_by(
            TickerFeatureSnapshot.instrument_id,
            TickerFeatureSnapshot.as_of_date.desc(),
        )
    )
    latest: dict[str, dict] = {}
    for snapshot, instrument in rows:
        instrument_id = str(instrument.id)
        if instrument_id in latest:
            continue
        latest[instrument_id] = {
            "ticker": instrument.ticker,
            "sector": instrument.sector,
            "features": snapshot.features,
            "as_of_date": snapshot.as_of_date,
        }
    return list(latest.values())


def _extract_fundamental_features(snapshot_features: dict) -> dict[str, str]:
    metrics = snapshot_features.get("metrics")
    if not isinstance(metrics, dict):
        return {}

    extracted = {}
    for feature_name in FUNDAMENTAL_FEATURE_NAMES:
        value = metrics.get(feature_name)
        if _decimal(value) is not None:
            extracted[feature_name] = str(value)
    return extracted


def _group_fundamentals_by_instrument(
    snapshots: list[TickerFeatureSnapshot],
) -> dict:
    grouped: dict = {}
    for snapshot in snapshots:
        grouped.setdefault(snapshot.instrument_id, []).append(snapshot)
    for instrument_snapshots in grouped.values():
        instrument_snapshots.sort(key=lambda snapshot: snapshot.as_of_date)
    return grouped


def _latest_fundamental_features_as_of(
    snapshots: list[TickerFeatureSnapshot],
    as_of_date: date,
) -> dict[str, str]:
    latest = None
    for snapshot in snapshots:
        if snapshot.as_of_date > as_of_date:
            break
        latest = snapshot
    if latest is None:
        return {}
    return _extract_fundamental_features(latest.features)


def _model_feature_names(dataset: list[dict]) -> list[str]:
    feature_names = list(PRICE_FEATURE_NAMES)
    for name in FUNDAMENTAL_FEATURE_NAMES:
        values = [
            _decimal(row["features"].get(name))
            for row in dataset
            if row["features"].get(name) is not None
        ]
        if len(values) == len(dataset) and len(set(values)) > 1:
            feature_names.append(name)
    return feature_names


def _benchmark_return_pct(
    benchmark_by_date: dict[date, PriceBarPoint],
    start_date: date,
    end_date: date,
) -> Decimal | None:
    start_bar = benchmark_by_date.get(start_date)
    end_bar = benchmark_by_date.get(end_date)
    if start_bar is None or end_bar is None:
        return None
    return _return_pct(start_bar.label_price, end_bar.label_price)


def _percentile_rank(value: Decimal, values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    below_or_equal = sum(1 for item in values if item <= value)
    return _quantize((Decimal(below_or_equal) / Decimal(len(values))) * Decimal("100"))


def _proposed_weight_from_prediction(
    prediction: PredictiveModelPredictionResponse | None,
    asset_class: str,
) -> Decimal:
    if prediction is None:
        return Decimal("0.0000")
    if prediction.expected_relative_return_pct <= 0:
        return Decimal("0.0000")
    if prediction.probability_outperform < Decimal("0.5500"):
        return Decimal("0.0000")

    max_weight = Decimal("5.0000")
    if asset_class in {"etf", "bond", "cash_equivalent"}:
        max_weight = Decimal("15.0000")
    if asset_class == "commodity":
        max_weight = Decimal("7.5000")

    edge_component = min(
        prediction.expected_relative_return_pct / Decimal("10"),
        Decimal("1"),
    )
    confidence_component = prediction.confidence_score / Decimal("100")
    probability_component = min(
        (prediction.probability_outperform - Decimal("0.5000")) / Decimal("0.2500"),
        Decimal("1"),
    )
    return _quantize(max_weight * edge_component * confidence_component * probability_component)


def compute_portfolio_fit_score(
    *,
    expected_relative_return_pct: Decimal,
    downside_p05_relative_return_pct: Decimal,
    confidence_score: Decimal,
    concentration_after_pct: Decimal,
    sector_exposure_after_pct: Decimal,
) -> Decimal:
    score = Decimal("50")
    score += max(min(expected_relative_return_pct * Decimal("2.0"), Decimal("25")), Decimal("-25"))
    score += max(min(confidence_score - Decimal("50"), Decimal("20")), Decimal("-20")) / Decimal("2")
    if downside_p05_relative_return_pct < Decimal("-15"):
        score -= min(abs(downside_p05_relative_return_pct + Decimal("15")), Decimal("25"))
    if concentration_after_pct > Decimal("20"):
        score -= min(concentration_after_pct - Decimal("20"), Decimal("25"))
    if sector_exposure_after_pct > Decimal("35"):
        score -= min(sector_exposure_after_pct - Decimal("35"), Decimal("25"))
    return _quantize(max(min(score, Decimal("100")), Decimal("0")))


def _portfolio_fit_notes(
    expected_return: Decimal,
    downside: Decimal,
    confidence: Decimal,
    concentration_after: Decimal,
    sector_exposure_after: Decimal,
) -> list[str]:
    notes = []
    if expected_return > 0:
        notes.append("Positive expected relative return supports inclusion.")
    else:
        notes.append("Expected relative return does not support new allocation.")
    if downside < Decimal("-15"):
        notes.append("Downside estimate is large enough to require tighter sizing.")
    else:
        notes.append("Downside estimate is within the initial research tolerance.")
    if confidence < Decimal("55"):
        notes.append("Model confidence is still modest.")
    else:
        notes.append("Model confidence is usable for research triage.")
    if concentration_after > Decimal("20"):
        notes.append("Pro forma concentration is above the phase-one comfort band.")
    if sector_exposure_after > Decimal("35"):
        notes.append("Pro forma sector exposure is high.")
    return notes


def _chronological_split_indexes(row_count: int):
    import numpy as np

    split_index = max(int(row_count * 0.8), 1)
    if row_count - split_index < 10 and row_count >= 40:
        split_index = row_count - 10
    if split_index >= row_count:
        split_index = row_count - 1
    indexes = np.arange(row_count)
    return indexes[:split_index], indexes[split_index:]


def _standardize_train_validation(x_train, x_validation):
    import numpy as np

    mean = x_train.mean(axis=0)
    std = x_train.std(axis=0)
    std = np.where(std == 0, 1.0, std)
    return {
        "train": (x_train - mean) / std,
        "validation": (x_validation - mean) / std,
        "mean": mean,
        "std": std,
    }


def _fit_ridge(x, y, alpha: float):
    import numpy as np

    x_with_intercept = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(x_with_intercept.shape[1]) * alpha
    penalty[0, 0] = 0
    coefficients = np.linalg.pinv(
        x_with_intercept.T @ x_with_intercept + penalty
    ) @ x_with_intercept.T @ y
    return {
        "intercept": float(coefficients[0]),
        "coefficients": coefficients[1:],
    }


def _predict_linear(x, model: dict):
    return model["intercept"] + x @ model["coefficients"]


def _fit_logistic(
    x,
    y,
    epochs: int = 800,
    learning_rate: float = 0.05,
    alpha: float = 0.01,
):
    import numpy as np

    weights = np.zeros(x.shape[1])
    intercept = 0.0
    for _ in range(epochs):
        logits = intercept + x @ weights
        predictions = _sigmoid(logits)
        errors = predictions - y
        intercept -= learning_rate * float(errors.mean())
        weights -= learning_rate * ((x.T @ errors) / len(x) + alpha * weights)
    return {"intercept": intercept, "coefficients": weights}


def _predict_logistic(x, model: dict):
    return _sigmoid(model["intercept"] + x @ model["coefficients"])


def _sigmoid(value):
    import numpy as np

    clipped = np.clip(value, -35, 35)
    return 1 / (1 + np.exp(-clipped))


def _mean_absolute_error(actual, predicted) -> float:
    import numpy as np

    if len(actual) == 0:
        return 0.0
    return float(np.mean(np.abs(actual - predicted)))


def _r2_score(actual, predicted) -> float:
    import numpy as np

    if len(actual) < 2:
        return 0.0
    total = float(np.sum((actual - np.mean(actual)) ** 2))
    if total == 0:
        return 0.0
    residual = float(np.sum((actual - predicted) ** 2))
    return 1 - (residual / total)


def _accuracy(actual, predicted) -> float:
    if len(actual) == 0:
        return 0.0
    return float((actual == predicted).mean())


def _prediction_confidence(metrics: dict, probability_outperform: float) -> float:
    row_component = min(float(metrics.get("training_rows", 0)) / 500, 1) * 35
    accuracy_component = float(metrics.get("validation_directional_accuracy", 0)) * 45
    probability_component = abs(probability_outperform - 0.5) * 40
    return min(20 + row_component + accuracy_component + probability_component, 100)


def _prediction_drivers(feature_names: list[str], standardized_vector, coefficients) -> list[dict]:
    contributions = [
        {
            "feature": feature_name,
            "value_zscore": _float4(float(value)),
            "contribution_pct": _float4(float(value * coefficient)),
        }
        for feature_name, value, coefficient in zip(
            feature_names,
            standardized_vector,
            coefficients,
        )
    ]
    return sorted(
        contributions,
        key=lambda item: abs(item["contribution_pct"]),
        reverse=True,
    )[:5]


def _lookback_return_pct(path: list[PriceBarPoint], lookback: int) -> Decimal | None:
    if len(path) <= lookback:
        return None
    return _return_pct(path[-lookback - 1].label_price, path[-1].label_price)


def _price_vs_average_pct(path: list[PriceBarPoint], lookback: int) -> Decimal | None:
    if len(path) < lookback:
        return None
    average = sum((bar.label_price for bar in path[-lookback:]), Decimal("0")) / Decimal(lookback)
    if average == 0:
        return None
    return _quantize(((path[-1].label_price - average) / average) * Decimal("100"))


def _model_version_label(horizon_days: int) -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"rr-{horizon_days}d-{timestamp}"


def _return_pct(start_price: Decimal, end_price: Decimal) -> Decimal:
    if start_price == 0:
        return Decimal("0.0000")
    return _quantize(((end_price - start_price) / start_price) * Decimal("100"))


def _max_drawdown_pct(path: list[PriceBarPoint]) -> Decimal | None:
    if len(path) < 2:
        return None
    peak = path[0].label_price
    worst = Decimal("0")
    for bar in path[1:]:
        price = bar.label_price
        if price > peak:
            peak = price
        if peak == 0:
            continue
        drawdown = ((price - peak) / peak) * Decimal("100")
        if drawdown < worst:
            worst = drawdown
    return _quantize(worst)


def _realized_volatility_pct(path: list[PriceBarPoint]) -> Decimal | None:
    prices = [bar.label_price for bar in path]
    if len(prices) < 3:
        return None
    returns: list[float] = []
    for previous, current in zip(prices, prices[1:]):
        if previous == 0:
            continue
        returns.append(float((current - previous) / previous))
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return _quantize(Decimal(str(sqrt(variance) * sqrt(252) * 100)))


def _feature_quality_score(payload: TickerAnalysisCreate) -> Decimal:
    values = payload.metrics.model_dump().values()
    provided = sum(1 for value in values if value is not None)
    total = len(payload.metrics.model_fields)
    if total == 0:
        return Decimal("0.00")
    return _quantize((Decimal(provided) / Decimal(total)) * Decimal("100"))


def _decimal(value: object) -> Decimal | None:
    if value is None or str(value) == "nan":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _optional_int(value: object) -> int | None:
    decimal_value = _decimal(value)
    if decimal_value is None:
        return None
    return int(decimal_value)


def _optional_int_value(value: object) -> int | None:
    return _optional_int(value)


def _optional_decimal(value: object) -> Decimal | None:
    value_as_decimal = _decimal(value)
    if value_as_decimal is None:
        return None
    return _quantize(value_as_decimal)


def _optional_string(value: object) -> str | None:
    if value is None or str(value) == "nan":
        return None
    return str(value)


def _optional_decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal4(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _float4(value: float) -> float:
    return round(float(value), 4)


def _float8(value: float) -> float:
    return round(float(value), 8)


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

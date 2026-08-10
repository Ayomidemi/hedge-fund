import asyncio
import logging
import uuid
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
    BacktestPeriodResponse,
    BacktestRunCreate,
    BacktestRunResponse,
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
    PipelineStepResponse,
    RegimeModelFitCreate,
    RegimeModelResponse,
    RegimeStateResponse,
    ResearchPipelineRunCreate,
    ResearchPipelineRunResponse,
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
HMM_REGIME_MODEL_NAME = "HMM Market Regime Model"
HMM_REGIME_MODEL_POD = "Macro Regime Pod"
BACKTEST_ENGINE_VERSION = "factor_backtest_v1"
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


async def run_research_data_pipeline(
    session: AsyncSession,
    payload: ResearchPipelineRunCreate,
) -> ResearchPipelineRunResponse:
    normalized_tickers = sorted(
        {ticker.strip().upper() for ticker in payload.tickers if ticker.strip()}
    )
    benchmark_ticker = payload.benchmark_ticker.strip().upper()
    price_tickers = sorted(set(normalized_tickers + [benchmark_ticker]))
    steps: list[PipelineStepResponse] = []
    warnings: list[str] = []
    successful_price_tickers: list[str] = []

    for ticker in price_tickers:
        try:
            backfill = await backfill_yahoo_prices(
                session,
                YahooPriceBackfillCreate(
                    ticker=ticker,
                    name=ticker,
                    yahoo_symbol=ticker,
                    start_date=payload.start_date,
                    end_date=payload.end_date,
                ),
            )
            successful_price_tickers.append(ticker)
            steps.append(
                PipelineStepResponse(
                    name=f"price_backfill:{ticker}",
                    status="completed",
                    message=f"Saved {backfill.rows_saved} daily bars.",
                    rows=backfill.rows_saved,
                )
            )
        except Exception as exc:
            message = f"{ticker} price backfill failed: {exc}"
            warnings.append(message)
            steps.append(
                PipelineStepResponse(
                    name=f"price_backfill:{ticker}",
                    status="failed",
                    message=message,
                )
            )

    label_ready_tickers = [
        ticker
        for ticker in normalized_tickers
        if ticker in successful_price_tickers and benchmark_ticker in successful_price_tickers
    ]
    for ticker in label_ready_tickers:
        try:
            labels = await generate_training_labels(
                session,
                TrainingLabelGenerateCreate(
                    ticker=ticker,
                    benchmark_ticker=benchmark_ticker,
                    horizons=[payload.horizon_days],
                    source=payload.source,
                ),
            )
            steps.append(
                PipelineStepResponse(
                    name=f"labels:{ticker}",
                    status="completed",
                    message=f"Saved {labels.labels_generated} forward labels.",
                    rows=labels.labels_generated,
                )
            )
        except Exception as exc:
            message = f"{ticker} label generation failed: {exc}"
            warnings.append(message)
            steps.append(
                PipelineStepResponse(
                    name=f"labels:{ticker}",
                    status="failed",
                    message=message,
                )
            )

    if successful_price_tickers:
        try:
            features = await build_price_feature_snapshots(
                session,
                PriceFeatureBuildCreate(
                    tickers=successful_price_tickers,
                    source=payload.source,
                ),
            )
            steps.append(
                PipelineStepResponse(
                    name="price_features",
                    status="completed",
                    message=f"Saved {features.snapshots_saved} feature snapshots.",
                    rows=features.snapshots_saved,
                )
            )
        except Exception as exc:
            message = f"Price feature build failed: {exc}"
            warnings.append(message)
            steps.append(
                PipelineStepResponse(
                    name="price_features",
                    status="failed",
                    message=message,
                )
            )

    model_version_id = None
    if payload.train_model and label_ready_tickers:
        try:
            trained = await train_predictive_model(
                session,
                PredictiveModelTrainCreate(
                    tickers=label_ready_tickers,
                    benchmark_ticker=benchmark_ticker,
                    horizon_days=payload.horizon_days,
                    label_source=payload.source,
                ),
            )
            model_version_id = trained.model_version_id
            steps.append(
                PipelineStepResponse(
                    name="predictive_model",
                    status="completed",
                    message=(
                        f"Trained {trained.model_version} with "
                        f"{trained.training_rows + trained.validation_rows} rows."
                    ),
                    rows=trained.training_rows + trained.validation_rows,
                )
            )
        except Exception as exc:
            message = f"Predictive model training failed: {exc}"
            warnings.append(message)
            steps.append(
                PipelineStepResponse(
                    name="predictive_model",
                    status="failed",
                    message=message,
                )
            )

    logger.info(
        "research_data_pipeline_completed",
        extra={
            "ticker_count": len(normalized_tickers),
            "benchmark_ticker": benchmark_ticker,
            "step_count": len(steps),
            "warning_count": len(warnings),
        },
    )

    return ResearchPipelineRunResponse(
        tickers=normalized_tickers,
        benchmark_ticker=benchmark_ticker,
        start_date=payload.start_date,
        end_date=payload.end_date,
        horizon_days=payload.horizon_days,
        steps=steps,
        model_version_id=model_version_id,
        warnings=warnings,
    )


async def fit_market_regime_model(
    session: AsyncSession,
    payload: RegimeModelFitCreate,
) -> RegimeModelResponse:
    instrument = await _get_instrument(session, payload.ticker)
    if instrument is None:
        raise MLTrainingDataUnavailableError(f"{payload.ticker.upper()} is not in the instrument table.")

    bars = await _load_price_points(session, instrument.id, payload.source)
    if len(bars) < payload.lookback_days:
        bars = bars[-len(bars):]
    else:
        bars = bars[-payload.lookback_days:]

    artifact = compute_hmm_regime_artifact(
        instrument.ticker,
        bars,
        state_count=payload.state_count,
    )
    model_version = ModelVersion(
        name=HMM_REGIME_MODEL_NAME,
        version=_regime_model_version_label(instrument.ticker),
        pod=HMM_REGIME_MODEL_POD,
        purpose="Classify the current market regime from price return and volatility states.",
        training_data={
            "ticker": instrument.ticker,
            "source": payload.source,
            "lookback_days": payload.lookback_days,
            "state_count": payload.state_count,
            "observation_count": artifact["observation_count"],
        },
        features=artifact,
        metrics={
            "current_regime": artifact["current_regime"],
            "confidence_score": artifact["confidence_score"],
            "as_of_date": artifact["as_of_date"],
        },
        assumptions="Daily returns and realized volatility expose persistent market states.",
        limitations="Lightweight phase-one Gaussian HMM approximation; not macro-data enriched yet.",
        approved_use="Research regime context, risk discussion, and model diagnostics.",
        prohibited_use="Automatic defensive mode or trading halt without central risk review.",
        shutdown_criteria="Disable if state assignments become unstable or conflict with validated macro evidence.",
    )
    session.add(model_version)
    await session.commit()
    await session.refresh(model_version)

    logger.info(
        "market_regime_model_fit",
        extra={
            "model_version_id": str(model_version.id),
            "ticker": instrument.ticker,
            "current_regime": artifact["current_regime"],
            "confidence_score": artifact["confidence_score"],
        },
    )

    return _regime_response_from_artifact(model_version, artifact)


async def get_latest_market_regime_model(
    session: AsyncSession,
) -> RegimeModelResponse:
    model_version = await session.scalar(
        select(ModelVersion)
        .where(ModelVersion.name == HMM_REGIME_MODEL_NAME)
        .order_by(ModelVersion.created_at.desc())
    )
    if model_version is None:
        raise MLTrainingDataUnavailableError("No HMM market-regime model has been fit yet.")

    return _regime_response_from_artifact(model_version, model_version.features or {})


async def run_factor_backtest(
    session: AsyncSession,
    payload: BacktestRunCreate,
) -> BacktestRunResponse:
    dataset = await _load_backtest_dataset(session, payload)
    if not dataset:
        raise MLTrainingDataUnavailableError("No labeled feature rows are available for this backtest.")

    rows_by_date: dict[date, list[dict]] = {}
    for row in dataset:
        rows_by_date.setdefault(row["as_of_date"], []).append(row)

    periods: list[BacktestPeriodResponse] = []
    previous_selection: set[str] = set()
    warnings: list[str] = []
    selected_counts: list[int] = []

    for as_of_date in sorted(rows_by_date):
        candidates = rows_by_date[as_of_date]
        if len(candidates) < payload.min_names_per_period:
            warnings.append(
                f"{as_of_date.isoformat()} skipped; only {len(candidates)} candidates."
            )
            continue

        ranked = sorted(
            candidates,
            key=lambda item: _backtest_signal_score(item["features"]),
            reverse=True,
        )
        selected = ranked[: payload.top_n]
        selected_tickers = [item["ticker"] for item in selected]
        selection_set = set(selected_tickers)
        turnover = _selection_turnover(previous_selection, selection_set)
        cost_drag = _cost_drag_pct(turnover, payload.transaction_cost_bps)
        gross_return = _average_decimal(
            [item["forward_return_pct"] for item in selected]
        )
        strategy_return = _quantize(gross_return - cost_drag)
        benchmark_return = _period_benchmark_return(selected)
        alpha = (
            _quantize(strategy_return - benchmark_return)
            if benchmark_return is not None
            else None
        )
        periods.append(
            BacktestPeriodResponse(
                as_of_date=as_of_date,
                selected_tickers=selected_tickers,
                strategy_return_pct=strategy_return,
                benchmark_return_pct=benchmark_return,
                alpha_pct=alpha,
                turnover_pct=turnover,
                cost_drag_pct=cost_drag,
            )
        )
        selected_counts.append(len(selected))
        previous_selection = selection_set

    if not periods:
        raise MLTrainingDataUnavailableError("No rebalance periods met the backtest requirements.")

    strategy_returns = [period.strategy_return_pct for period in periods]
    benchmark_returns = [
        period.benchmark_return_pct
        for period in periods
        if period.benchmark_return_pct is not None
    ]
    cumulative_return = _compound_return_pct(strategy_returns)
    benchmark_cumulative = (
        _compound_return_pct(benchmark_returns)
        if len(benchmark_returns) == len(periods)
        else None
    )
    alpha = (
        _quantize(cumulative_return - benchmark_cumulative)
        if benchmark_cumulative is not None
        else None
    )
    annualized_return = _annualized_return_pct(
        cumulative_return,
        len(periods),
        payload.horizon_days,
    )
    annualized_volatility = _annualized_volatility_pct(
        strategy_returns,
        payload.horizon_days,
    )
    sharpe = (
        _quantize(annualized_return / annualized_volatility)
        if annualized_volatility != 0
        else Decimal("0.0000")
    )
    hit_rate = _backtest_hit_rate(periods)
    turnover = _average_decimal([period.turnover_pct for period in periods])
    cost_drag = sum((period.cost_drag_pct for period in periods), Decimal("0"))

    logger.info(
        "factor_backtest_completed",
        extra={
            "ticker_count": len(payload.tickers),
            "rebalance_count": len(periods),
            "horizon_days": payload.horizon_days,
            "cumulative_return_pct": str(cumulative_return),
        },
    )

    return BacktestRunResponse(
        backtest_id=uuid.uuid4(),
        name=f"{BACKTEST_ENGINE_VERSION}:{payload.horizon_days}d",
        start_date=periods[0].as_of_date,
        end_date=periods[-1].as_of_date,
        horizon_days=payload.horizon_days,
        rebalance_count=len(periods),
        selected_count_avg=_average_decimal([Decimal(count) for count in selected_counts]),
        cumulative_return_pct=cumulative_return,
        benchmark_return_pct=benchmark_cumulative,
        alpha_pct=alpha,
        annualized_return_pct=annualized_return,
        annualized_volatility_pct=annualized_volatility,
        sharpe_ratio=sharpe,
        max_drawdown_pct=_max_drawdown_from_returns(strategy_returns),
        hit_rate_pct=hit_rate,
        turnover_pct=turnover,
        cost_drag_pct=_quantize(cost_drag),
        periods=periods,
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


def compute_hmm_regime_artifact(
    ticker: str,
    bars: list[PriceBarPoint],
    state_count: int = 4,
) -> dict:
    observations = _regime_observations(bars)
    if len(observations) < state_count * 8:
        raise MLTrainingDataUnavailableError(
            f"At least {state_count * 8} regime observations are required. Found {len(observations)}."
        )

    import numpy as np

    points = np.array(
        [
            [
                float(observation["daily_return_pct"]),
                float(observation["realized_volatility_pct"]),
            ]
            for observation in observations
        ]
    )
    assignments, means, standard_deviations = _cluster_regime_points(points, state_count)
    transition_matrix = _regime_transition_matrix(assignments, state_count)
    previous_state = int(assignments[-2]) if len(assignments) > 1 else None
    probabilities = _regime_state_probabilities(
        points[-1],
        previous_state,
        means,
        standard_deviations,
        transition_matrix,
    )
    labels = _regime_labels(means)
    observation_counts = {
        state_id: int((assignments == state_id).sum())
        for state_id in range(state_count)
    }
    states = []
    for state_id in range(state_count):
        states.append(
            {
                "state_id": state_id,
                "label": labels[state_id],
                "probability": str(_decimal4(float(probabilities[state_id]))),
                "mean_return_pct": str(_decimal4(float(means[state_id][0]))),
                "volatility_pct": str(_decimal4(float(means[state_id][1]))),
                "observation_count": observation_counts[state_id],
            }
        )

    current_state = int(np.argmax(probabilities))
    confidence = _decimal4(float(probabilities[current_state] * 100))

    return {
        "ticker": ticker,
        "as_of_date": observations[-1]["as_of_date"].isoformat(),
        "current_regime": labels[current_state],
        "confidence_score": str(confidence),
        "state_probabilities": states,
        "transition_matrix": [
            [str(_decimal4(float(value))) for value in row]
            for row in transition_matrix
        ],
        "observation_count": len(observations),
        "warnings": [
            "Phase-one HMM uses price and volatility only; macro variables are not included yet."
        ],
    }


def _regime_observations(bars: list[PriceBarPoint]) -> list[dict]:
    sorted_bars = sorted(bars, key=lambda bar: bar.bar_date)
    observations: list[dict] = []
    for index in range(21, len(sorted_bars)):
        previous = sorted_bars[index - 1]
        current = sorted_bars[index]
        volatility = _realized_volatility_pct(sorted_bars[index - 21 : index + 1])
        if volatility is None:
            continue
        observations.append(
            {
                "as_of_date": current.bar_date,
                "daily_return_pct": _return_pct(previous.label_price, current.label_price),
                "realized_volatility_pct": volatility,
            }
        )
    return observations


def _cluster_regime_points(points, state_count: int):
    import numpy as np

    mean = points.mean(axis=0)
    standard_deviation = points.std(axis=0)
    standard_deviation = np.where(standard_deviation == 0, 1.0, standard_deviation)
    standardized = (points - mean) / standard_deviation
    risk_score = standardized[:, 0] - standardized[:, 1]
    ordered_indexes = np.argsort(risk_score)
    seed_positions = np.linspace(0, len(ordered_indexes) - 1, state_count).astype(int)
    centroids = standardized[ordered_indexes[seed_positions]]
    assignments = np.zeros(len(points), dtype=int)

    for _ in range(40):
        distances = np.linalg.norm(
            standardized[:, None, :] - centroids[None, :, :],
            axis=2,
        )
        next_assignments = np.argmin(distances, axis=1)
        if np.array_equal(assignments, next_assignments):
            break
        assignments = next_assignments
        for state_id in range(state_count):
            state_points = standardized[assignments == state_id]
            if len(state_points) > 0:
                centroids[state_id] = state_points.mean(axis=0)

    raw_means = np.zeros((state_count, points.shape[1]))
    raw_standard_deviations = np.ones((state_count, points.shape[1]))
    for state_id in range(state_count):
        state_points = points[assignments == state_id]
        if len(state_points) == 0:
            raw_means[state_id] = mean
            raw_standard_deviations[state_id] = standard_deviation
            continue
        raw_means[state_id] = state_points.mean(axis=0)
        raw_standard_deviations[state_id] = np.where(
            state_points.std(axis=0) == 0,
            standard_deviation,
            state_points.std(axis=0),
        )
    return assignments, raw_means, raw_standard_deviations


def _regime_transition_matrix(assignments, state_count: int):
    import numpy as np

    matrix = np.ones((state_count, state_count)) * 0.1
    for previous, current in zip(assignments[:-1], assignments[1:]):
        matrix[int(previous), int(current)] += 1
    row_sums = matrix.sum(axis=1)
    return matrix / row_sums[:, None]


def _regime_state_probabilities(
    latest_point,
    previous_state: int | None,
    means,
    standard_deviations,
    transition_matrix,
):
    import numpy as np

    safe_deviations = np.where(standard_deviations <= 1e-6, 1.0, standard_deviations)
    z_scores = (latest_point - means) / safe_deviations
    likelihood = np.exp(-0.5 * np.sum(z_scores**2, axis=1)) / np.prod(
        safe_deviations,
        axis=1,
    )
    if previous_state is None:
        prior = np.ones(len(means)) / len(means)
    else:
        prior = transition_matrix[previous_state]
    posterior = prior * likelihood
    total = posterior.sum()
    if total <= 0:
        return np.ones(len(means)) / len(means)
    return posterior / total


def _regime_labels(means) -> dict[int, str]:
    labels_by_count = {
        2: ["risk-on", "stress"],
        3: ["risk-on", "fragile", "stress"],
        4: ["risk-on", "constructive", "fragile", "stress"],
        5: ["risk-on", "constructive", "neutral", "fragile", "stress"],
        6: ["risk-on", "constructive", "neutral", "fragile", "stress", "shock"],
    }
    state_count = len(means)
    ordered_states = sorted(
        range(state_count),
        key=lambda state_id: means[state_id][0] - (means[state_id][1] * 0.20),
        reverse=True,
    )
    rank_labels = labels_by_count.get(state_count, labels_by_count[4])
    return {
        state_id: rank_labels[rank]
        for rank, state_id in enumerate(ordered_states)
    }


def _regime_response_from_artifact(
    model_version: ModelVersion,
    artifact: dict,
) -> RegimeModelResponse:
    return RegimeModelResponse(
        model_version_id=model_version.id,
        model_name=model_version.name,
        model_version=model_version.version,
        ticker=str(artifact.get("ticker") or ""),
        as_of_date=date.fromisoformat(str(artifact.get("as_of_date"))),
        current_regime=str(artifact.get("current_regime") or "unknown"),
        confidence_score=_required_decimal(artifact.get("confidence_score")),
        state_probabilities=[
            RegimeStateResponse(
                state_id=int(state["state_id"]),
                label=str(state["label"]),
                probability=_required_decimal(state["probability"]),
                mean_return_pct=_required_decimal(state["mean_return_pct"]),
                volatility_pct=_required_decimal(state["volatility_pct"]),
                observation_count=int(state["observation_count"]),
            )
            for state in artifact.get("state_probabilities", [])
        ],
        transition_matrix=[
            [_required_decimal(value) for value in row]
            for row in artifact.get("transition_matrix", [])
        ],
        warnings=[
            str(warning)
            for warning in artifact.get("warnings", [])
        ],
    )


def _regime_model_version_label(ticker: str) -> str:
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"hmm-{ticker.lower()}-{timestamp}"


async def _load_backtest_dataset(
    session: AsyncSession,
    payload: BacktestRunCreate,
) -> list[dict]:
    normalized_tickers = sorted(
        {ticker.strip().upper() for ticker in payload.tickers if ticker.strip()}
    )
    instruments = list(
        await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(normalized_tickers))
        )
    )
    if not instruments:
        return []

    benchmark = None
    if payload.benchmark_ticker:
        benchmark = await _get_instrument(session, payload.benchmark_ticker)
        if benchmark is None:
            raise MLTrainingDataUnavailableError(
                f"Benchmark {payload.benchmark_ticker.upper()} is not in the instrument table."
            )

    instruments_by_id = {instrument.id: instrument for instrument in instruments}
    instrument_ids = set(instruments_by_id)
    snapshots = list(
        await session.scalars(
            select(TickerFeatureSnapshot)
            .where(TickerFeatureSnapshot.instrument_id.in_(instrument_ids))
            .where(TickerFeatureSnapshot.feature_version == payload.feature_version)
            .order_by(TickerFeatureSnapshot.as_of_date)
        )
    )
    snapshots_by_key = {
        (snapshot.instrument_id, snapshot.as_of_date): snapshot
        for snapshot in snapshots
        if _has_model_features(snapshot.features)
    }

    label_query = (
        select(TickerTrainingLabel)
        .where(TickerTrainingLabel.instrument_id.in_(instrument_ids))
        .where(TickerTrainingLabel.horizon_days == payload.horizon_days)
        .where(TickerTrainingLabel.source == payload.label_source)
        .where(TickerTrainingLabel.label_version == LABEL_VERSION)
        .order_by(TickerTrainingLabel.as_of_date)
    )
    if benchmark is not None:
        label_query = label_query.where(
            TickerTrainingLabel.benchmark_instrument_id == benchmark.id
        )
    else:
        label_query = label_query.where(TickerTrainingLabel.benchmark_instrument_id.is_(None))

    rows = []
    for label in await session.scalars(label_query):
        snapshot = snapshots_by_key.get((label.instrument_id, label.as_of_date))
        if snapshot is None:
            continue
        instrument = instruments_by_id[label.instrument_id]
        rows.append(
            {
                "as_of_date": label.as_of_date,
                "ticker": instrument.ticker,
                "features": snapshot.features,
                "forward_return_pct": label.forward_return_pct,
                "benchmark_return_pct": label.benchmark_forward_return_pct,
            }
        )
    return rows


def _backtest_signal_score(features: dict) -> float:
    return_63d = float(_decimal(features.get("return_63d_pct")) or Decimal("0"))
    return_126d = float(_decimal(features.get("return_126d_pct")) or Decimal("0"))
    trend = float(_decimal(features.get("price_vs_200d_pct")) or Decimal("0"))
    volatility = float(_decimal(features.get("realized_volatility_63d_pct")) or Decimal("0"))
    drawdown = float(_decimal(features.get("max_drawdown_63d_pct")) or Decimal("0"))
    return (return_63d * 0.35) + (return_126d * 0.25) + (trend * 0.25) + (drawdown * 0.10) - (volatility * 0.15)


def _selection_turnover(
    previous_selection: set[str],
    current_selection: set[str],
) -> Decimal:
    if not current_selection:
        return Decimal("0.0000")
    if not previous_selection:
        return Decimal("100.0000")
    overlap = Decimal(len(previous_selection & current_selection)) / Decimal(len(current_selection))
    return _quantize((Decimal("1") - overlap) * Decimal("100"))


def _cost_drag_pct(turnover_pct: Decimal, transaction_cost_bps: Decimal) -> Decimal:
    return _quantize((turnover_pct / Decimal("100")) * (transaction_cost_bps / Decimal("100")))


def _average_decimal(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal("0.0000")
    return _quantize(sum(values, Decimal("0")) / Decimal(len(values)))


def _period_benchmark_return(rows: list[dict]) -> Decimal | None:
    values = [
        row["benchmark_return_pct"]
        for row in rows
        if row["benchmark_return_pct"] is not None
    ]
    if not values:
        return None
    return _average_decimal(values)


def _compound_return_pct(returns: list[Decimal]) -> Decimal:
    equity = Decimal("1")
    for value in returns:
        equity *= Decimal("1") + (value / Decimal("100"))
    return _quantize((equity - Decimal("1")) * Decimal("100"))


def _annualized_return_pct(
    cumulative_return_pct: Decimal,
    period_count: int,
    horizon_days: int,
) -> Decimal:
    if period_count <= 0:
        return Decimal("0.0000")
    annual_factor = 252 / horizon_days
    cumulative = 1 + (float(cumulative_return_pct) / 100)
    annualized = (cumulative ** (annual_factor / period_count) - 1) * 100
    return _decimal4(annualized)


def _annualized_volatility_pct(
    returns: list[Decimal],
    horizon_days: int,
) -> Decimal:
    if len(returns) < 2:
        return Decimal("0.0000")
    mean = sum(returns, Decimal("0")) / Decimal(len(returns))
    variance = sum((value - mean) ** 2 for value in returns) / Decimal(len(returns) - 1)
    annualized = sqrt(float(variance)) * sqrt(252 / horizon_days)
    return _decimal4(annualized)


def _max_drawdown_from_returns(returns: list[Decimal]) -> Decimal:
    equity = Decimal("1")
    peak = Decimal("1")
    worst = Decimal("0")
    for value in returns:
        equity *= Decimal("1") + (value / Decimal("100"))
        if equity > peak:
            peak = equity
        if peak == 0:
            continue
        drawdown = ((equity - peak) / peak) * Decimal("100")
        if drawdown < worst:
            worst = drawdown
    return _quantize(worst)


def _backtest_hit_rate(periods: list[BacktestPeriodResponse]) -> Decimal:
    if not periods:
        return Decimal("0.0000")
    wins = 0
    for period in periods:
        if period.alpha_pct is not None:
            wins += int(period.alpha_pct > 0)
        else:
            wins += int(period.strategy_return_pct > 0)
    return _quantize((Decimal(wins) / Decimal(len(periods))) * Decimal("100"))


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


def _required_decimal(value: object) -> Decimal:
    decimal_value = _decimal(value)
    if decimal_value is None:
        return Decimal("0.0000")
    return _quantize(decimal_value)


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

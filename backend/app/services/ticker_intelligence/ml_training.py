import asyncio
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import sqrt

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import (
    PriceBackfillResponse,
    TickerAnalysisCreate,
    TickerDatasetRowResponse,
    TrainingLabelGenerateCreate,
    TrainingLabelResponse,
    YahooPriceBackfillCreate,
)
from app.models import Instrument, MarketPriceBar, TickerFeatureSnapshot, TickerTrainingLabel
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)

FEATURE_VERSION = "ticker_features_v1"
LABEL_VERSION = "forward_returns_v1"


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
        if benchmark is not None:
            benchmark_bars = await _load_price_points(session, benchmark.id, payload.source)

    labels = compute_forward_labels(
        bars,
        horizons=payload.horizons,
        benchmark_bars=benchmark_bars,
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


def _optional_string(value: object) -> str | None:
    if value is None or str(value) == "nan":
        return None
    return str(value)


def _optional_decimal_string(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _one_day():
    from datetime import timedelta

    return timedelta(days=1)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

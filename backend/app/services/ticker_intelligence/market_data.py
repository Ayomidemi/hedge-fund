import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import sqrt
from urllib.parse import urlsplit

import httpx

from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import TickerMetricsInput, TickerPrefillResponse
from app.core.config import settings

logger = logging.getLogger(__name__)


class MarketDataUnavailableError(RuntimeError):
    pass


@dataclass
class ProviderResult:
    payload: dict | None = None
    warning: str | None = None


@dataclass
class PrefillBuildContext:
    ticker: str
    details: dict = field(default_factory=dict)
    ratios: dict = field(default_factory=dict)
    bars: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def prefill_ticker(ticker: str) -> TickerPrefillResponse:
    if settings.market_data_provider != "polygon":
        raise MarketDataUnavailableError("Market data provider is not configured.")
    if not settings.hf_polygon_api_key:
        raise MarketDataUnavailableError("Polygon/Massive API key is missing.")

    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        raise MarketDataUnavailableError("Ticker is required.")

    async with httpx.AsyncClient(
        base_url=settings.polygon_base_url,
        timeout=httpx.Timeout(10.0),
        headers={"Authorization": f"Bearer {settings.hf_polygon_api_key}"},
    ) as client:
        context = PrefillBuildContext(ticker=normalized_ticker)
        details = await _safe_get(client, f"/v3/reference/tickers/{normalized_ticker}")
        ratios = await _safe_get(
            client,
            "/stocks/financials/v1/ratios",
            params={"ticker": normalized_ticker, "limit": "1", "sort": "date.desc"},
        )
        bars = await _safe_get(
            client,
            _bars_path(normalized_ticker),
            params={"adjusted": "true", "sort": "asc", "limit": "50000"},
        )

    context.details = _first_result(details.payload)
    context.ratios = _first_result(ratios.payload)
    context.bars = _results(bars.payload)
    context.warnings = [
        warning
        for warning in [details.warning, ratios.warning, bars.warning]
        if warning is not None
    ]

    response = _build_prefill_response(context)
    logger.info(
        "ticker_prefill_loaded",
        extra={
            "ticker": normalized_ticker,
            "provider": response.provider,
            "warning_count": len(response.source_warnings),
            "bar_count": len(context.bars),
        },
    )
    return response


def normalize_massive_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized in {"https://massive.com", "http://massive.com"}:
        return "https://api.massive.com"
    return normalized


async def _safe_get(
    client: httpx.AsyncClient,
    path: str,
    params: dict[str, str] | None = None,
) -> ProviderResult:
    try:
        response = await client.get(path, params=params)
        response.raise_for_status()
        return ProviderResult(payload=response.json())
    except httpx.HTTPStatusError as exc:
        return ProviderResult(warning=_provider_warning(path, exc.response))
    except (httpx.HTTPError, ValueError) as exc:
        return ProviderResult(warning=f"{path} unavailable: {exc}")


def _provider_warning(path: str, response: httpx.Response) -> str:
    detail = response.text[:160].strip()
    if response.status_code in {401, 403}:
        return f"{path} not available for this API key or plan."
    if response.status_code == 429:
        return f"{path} rate limited by provider."
    if detail:
        return f"{path} returned {response.status_code}: {detail}"
    return f"{path} returned {response.status_code}."


def _bars_path(ticker: str) -> str:
    today = date.today()
    start = today - timedelta(days=430)
    return f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{today.isoformat()}"


def _build_prefill_response(context: PrefillBuildContext) -> TickerPrefillResponse:
    instrument = InstrumentCreate(
        ticker=context.ticker,
        name=str(context.details.get("name") or context.ticker),
        asset_class=_asset_class(context.details),
        exchange=_optional_string(context.details.get("primary_exchange")),
        currency=_currency(context.details),
        sector=_optional_string(
            context.details.get("sic_description")
            or context.details.get("sector")
            or context.details.get("market")
        ),
        industry=_optional_string(
            context.details.get("industry")
            or context.details.get("type")
        ),
    )
    metrics = TickerMetricsInput(
        current_price=_latest_price(context),
        market_cap_billion=_market_cap_billion(context),
        pe_ratio=_decimal(context.ratios.get("price_to_earnings")),
        forward_pe=None,
        revenue_growth_pct=None,
        earnings_growth_pct=None,
        free_cash_flow_yield_pct=_free_cash_flow_yield(context),
        net_margin_pct=_net_margin(context),
        debt_to_equity=_decimal(context.ratios.get("debt_to_equity")),
        price_vs_200d_pct=_price_vs_200d(context.bars),
        relative_strength_6m_pct=_relative_strength(context.bars),
        volatility_30d_pct=_volatility_30d(context.bars),
    )

    return TickerPrefillResponse(
        instrument=instrument,
        metrics=metrics,
        provider="polygon",
        source_reference=f"massive:{context.ticker}:{datetime.now(timezone.utc).isoformat()}",
        data_timestamp=datetime.now(timezone.utc),
        source_warnings=context.warnings,
        raw_sources={
            "details": _redact_url_fields(context.details),
            "ratios": context.ratios,
            "bars": {
                "count": len(context.bars),
                "first_date": _bar_date(context.bars[0]) if context.bars else None,
                "last_date": _bar_date(context.bars[-1]) if context.bars else None,
            },
        },
    )


def _first_result(payload: dict | None) -> dict:
    if not payload:
        return {}
    results = payload.get("results")
    if isinstance(results, list):
        return results[0] if results else {}
    if isinstance(results, dict):
        return results
    return {}


def _results(payload: dict | None) -> list[dict]:
    if not payload:
        return []
    results = payload.get("results")
    return results if isinstance(results, list) else []


def _asset_class(details: dict) -> str:
    ticker_type = str(details.get("type") or "").upper()
    if ticker_type == "ETF":
        return "etf"
    return "equity"


def _currency(details: dict) -> str:
    value = str(details.get("currency_name") or "USD").upper()
    if value == "USD":
        return "USD"
    return value[:3]


def _latest_price(context: PrefillBuildContext) -> Decimal | None:
    ratio_price = _decimal(context.ratios.get("price"))
    if ratio_price is not None:
        return ratio_price
    if context.bars:
        return _decimal(context.bars[-1].get("c"))
    return None


def _market_cap_billion(context: PrefillBuildContext) -> Decimal | None:
    market_cap = _decimal(context.ratios.get("market_cap"))
    if market_cap is None:
        market_cap = _decimal(context.details.get("market_cap"))
    if market_cap is None:
        return None
    return _quantize_pct(market_cap / Decimal("1000000000"))


def _free_cash_flow_yield(context: PrefillBuildContext) -> Decimal | None:
    market_cap = _decimal(context.ratios.get("market_cap"))
    free_cash_flow = _decimal(context.ratios.get("free_cash_flow"))
    if market_cap is None or free_cash_flow is None or market_cap == 0:
        return None
    return _quantize_pct((free_cash_flow / market_cap) * Decimal("100"))


def _net_margin(context: PrefillBuildContext) -> Decimal | None:
    value = context.ratios.get("net_margin") or context.ratios.get("profit_margin")
    decimal_value = _decimal(value)
    if decimal_value is None:
        return None
    if abs(decimal_value) <= 1:
        return _quantize_pct(decimal_value * Decimal("100"))
    return decimal_value


def _price_vs_200d(bars: list[dict]) -> Decimal | None:
    closes = _closes(bars)
    if len(closes) < 200:
        return None
    latest = closes[-1]
    average = sum(closes[-200:], Decimal("0")) / Decimal("200")
    if average == 0:
        return None
    return _quantize_pct(((latest - average) / average) * Decimal("100"))


def _relative_strength(bars: list[dict]) -> Decimal | None:
    closes = _closes(bars)
    if len(closes) < 126:
        return None
    start = closes[-126]
    latest = closes[-1]
    if start == 0:
        return None
    return _quantize_pct(((latest - start) / start) * Decimal("100"))


def _volatility_30d(bars: list[dict]) -> Decimal | None:
    closes = _closes(bars)
    if len(closes) < 31:
        return None
    returns: list[float] = []
    recent = closes[-31:]
    for previous, current in zip(recent, recent[1:]):
        if previous == 0:
            continue
        returns.append(float((current - previous) / previous))
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    annualized = sqrt(variance) * sqrt(252) * 100
    return _quantize_pct(Decimal(str(annualized)))


def _closes(bars: list[dict]) -> list[Decimal]:
    closes: list[Decimal] = []
    for bar in bars:
        close = _decimal(bar.get("c"))
        if close is not None:
            closes.append(close)
    return closes


def _bar_date(bar: dict) -> str | None:
    timestamp = bar.get("t")
    if not isinstance(timestamp, int):
        return None
    return datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date().isoformat()


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _quantize_pct(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _redact_url_fields(payload: dict) -> dict:
    redacted = dict(payload)
    for key in ["logo_url", "icon_url"]:
        value = redacted.get(key)
        if isinstance(value, str):
            parsed = urlsplit(value)
            redacted[key] = parsed.path
    return redacted

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from math import sqrt
from urllib.parse import urlsplit

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.operating_core import InstrumentCreate
from app.api.schemas.ticker_intelligence import (
    TickerMetricsInput,
    TickerPrefillResponse,
    TickerSuggestionResponse,
)
from app.core.config import settings
from app.models import Instrument
from app.services.ticker_intelligence.sec_fundamentals import (
    SecFundamentals,
    calculate_sec_fundamentals,
)

logger = logging.getLogger(__name__)


class MarketDataUnavailableError(RuntimeError):
    pass


@dataclass
class ProviderResult:
    payload: dict | list | None = None
    warning: str | None = None


@dataclass(frozen=True)
class TickerResolution:
    requested_ticker: str
    ticker: str
    provider_symbol: str
    market: str


@dataclass
class PrefillBuildContext:
    ticker: str
    requested_ticker: str = ""
    provider_symbol: str = ""
    market: str = "US"
    details: dict = field(default_factory=dict)
    ratios: dict = field(default_factory=dict)
    bars: list[dict | list] = field(default_factory=list)
    sec_fundamentals: SecFundamentals = field(default_factory=SecFundamentals)
    sec_facts_summary: dict = field(default_factory=dict)
    fmp_profile: dict = field(default_factory=dict)
    fmp_quote: dict = field(default_factory=dict)
    fmp_ratios: dict = field(default_factory=dict)
    fmp_key_metrics: dict = field(default_factory=dict)
    tiingo_meta: dict = field(default_factory=dict)
    ngn_company: dict = field(default_factory=dict)
    ngn_etf: dict = field(default_factory=dict)
    providers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


async def prefill_ticker(
    ticker: str,
    market_hint: str | None = None,
) -> TickerPrefillResponse:
    if settings.market_data_provider == "disabled":
        raise MarketDataUnavailableError("Market data provider is not configured.")

    resolution = resolve_ticker(ticker, market_hint=market_hint)
    if not resolution.provider_symbol:
        raise MarketDataUnavailableError("Ticker is required.")
    if not _has_market_data_key(resolution.market):
        raise MarketDataUnavailableError(
            f"No {resolution.market} market data API keys are configured."
        )

    context = PrefillBuildContext(
        ticker=resolution.ticker,
        requested_ticker=resolution.requested_ticker,
        provider_symbol=resolution.provider_symbol,
        market=resolution.market,
    )

    if resolution.market == "NG":
        await _load_ngn_market_sources(context)
    else:
        await _load_us_sources(context)

    response = _build_prefill_response(context)
    logger.info(
        "ticker_prefill_loaded",
        extra={
            "ticker_symbol": response.instrument.ticker,
            "market": context.market,
            "provider": response.provider,
            "warning_count": len(response.source_warnings),
            "bar_count": len(context.bars),
        },
    )
    return response


async def search_ticker_suggestions(
    session: AsyncSession,
    query: str,
    *,
    limit: int = 8,
) -> list[TickerSuggestionResponse]:
    normalized_query = query.strip().upper()
    if len(normalized_query) < 1:
        return []

    pattern = f"%{normalized_query}%"
    rows = await session.scalars(
        select(Instrument)
        .where(or_(Instrument.ticker.ilike(pattern), Instrument.name.ilike(pattern)))
        .order_by(
            Instrument.ticker.ilike(f"{normalized_query}%").desc(),
            Instrument.ticker.asc(),
        )
        .limit(limit)
    )

    return [
        TickerSuggestionResponse(
            ticker=instrument.ticker,
            name=instrument.name,
            asset_class=instrument.asset_class,
            exchange=instrument.exchange,
            currency=instrument.currency,
            sector=instrument.sector,
            industry=instrument.industry,
        )
        for instrument in rows
    ]


def resolve_ticker(ticker: str, market_hint: str | None = None) -> TickerResolution:
    requested_ticker = ticker.strip()
    normalized_ticker = requested_ticker.upper().replace(" ", "")
    normalized_market = (market_hint or "").strip().upper()

    if normalized_ticker.startswith("NGX:"):
        symbol = normalized_ticker.split(":", 1)[1]
        return TickerResolution(requested_ticker, f"{symbol}.NG", symbol, "NG")

    if normalized_ticker.endswith(".NG"):
        symbol = normalized_ticker.removesuffix(".NG")
        return TickerResolution(requested_ticker, f"{symbol}.NG", symbol, "NG")

    if normalized_market in {"NG", "NIGERIA", "NGX"}:
        return TickerResolution(
            requested_ticker,
            f"{normalized_ticker}.NG",
            normalized_ticker,
            "NG",
        )

    return TickerResolution(
        requested_ticker, normalized_ticker, normalized_ticker, "US"
    )


def normalize_massive_base_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized in {"https://massive.com", "http://massive.com"}:
        return "https://api.massive.com"
    return normalized


async def _load_us_sources(context: PrefillBuildContext) -> None:
    await _load_polygon_sources(context)
    await _fetch_sec_fundamentals(context)
    await _load_fmp_sources(context)
    await _load_tiingo_sources(context)


async def _load_polygon_sources(context: PrefillBuildContext) -> None:
    if not settings.hf_polygon_api_key:
        return

    async with httpx.AsyncClient(
        base_url=settings.polygon_base_url,
        timeout=httpx.Timeout(10.0),
        headers={"Authorization": f"Bearer {settings.hf_polygon_api_key}"},
    ) as client:
        details = await _safe_get(
            client,
            f"/v3/reference/tickers/{context.provider_symbol}",
        )
        ratios = await _safe_get(
            client,
            "/stocks/financials/v1/ratios",
            params={
                "ticker": context.provider_symbol,
                "limit": "1",
                "sort": "date.desc",
            },
        )
        bars = await _safe_get(
            client,
            _bars_path(context.provider_symbol),
            params={"adjusted": "true", "sort": "asc", "limit": "50000"},
        )

    context.details = _first_result(details.payload)
    context.ratios = _first_result(ratios.payload)
    context.bars = _results(bars.payload) or context.bars
    _record_provider(context, "massive", [details, ratios, bars])


async def _load_fmp_sources(context: PrefillBuildContext) -> None:
    if not settings.hf_fmp_api_key:
        return

    symbol = context.provider_symbol
    base_params = {"apikey": settings.hf_fmp_api_key}
    async with httpx.AsyncClient(
        base_url=settings.fmp_base_url,
        timeout=httpx.Timeout(10.0),
    ) as client:
        profile = await _safe_get(client, f"/v3/profile/{symbol}", params=base_params)
        quote = await _safe_get(client, f"/v3/quote/{symbol}", params=base_params)
        ratios = await _safe_get(client, f"/v3/ratios-ttm/{symbol}", params=base_params)
        key_metrics = await _safe_get(
            client,
            f"/v3/key-metrics-ttm/{symbol}",
            params=base_params,
        )

    context.fmp_profile = _first_list_item(profile.payload)
    context.fmp_quote = _first_list_item(quote.payload)
    context.fmp_ratios = _first_list_item(ratios.payload)
    context.fmp_key_metrics = _first_list_item(key_metrics.payload)
    _record_provider(context, "fmp", [profile, quote, ratios, key_metrics])


async def _load_tiingo_sources(context: PrefillBuildContext) -> None:
    if not settings.hf_tiingo_api_key:
        return

    today = date.today()
    start = today - timedelta(days=430)
    async with httpx.AsyncClient(
        base_url=settings.tiingo_base_url,
        timeout=httpx.Timeout(10.0),
        headers={"Authorization": f"Token {settings.hf_tiingo_api_key}"},
    ) as client:
        meta = await _safe_get(
            client, f"/tiingo/daily/{context.provider_symbol.lower()}"
        )
        prices = await _safe_get(
            client,
            f"/tiingo/daily/{context.provider_symbol.lower()}/prices",
            params={"startDate": start.isoformat(), "endDate": today.isoformat()},
        )

    context.tiingo_meta = meta.payload if isinstance(meta.payload, dict) else {}
    tiingo_bars = _list_payload(prices.payload)
    if tiingo_bars and not context.bars:
        context.bars = tiingo_bars
    _record_provider(context, "tiingo", [meta, prices])


async def _load_ngn_market_sources(context: PrefillBuildContext) -> None:
    if not settings.hf_ngnmarket_api_key:
        context.warnings.append("NGN Market API key is missing.")
        return

    symbol = context.provider_symbol
    async with httpx.AsyncClient(
        base_url=settings.ngnmarket_base_url,
        timeout=httpx.Timeout(10.0),
        headers={"Authorization": f"Bearer {settings.hf_ngnmarket_api_key}"},
    ) as client:
        companies = await _safe_get(
            client,
            "/companies",
            params={"search": symbol, "limit": "25"},
        )
        identifiers = await _safe_get(client, "/companies/identifiers")
        etfs = await _safe_get(client, "/etfs")
        company = await _safe_get(client, f"/companies/{symbol}")
        company_chart = await _safe_get(
            client,
            f"/companies/{symbol}/chart",
            params={"period": "1y", "format": "ohlcv"},
        )
        etf = await _safe_get(client, f"/etfs/{symbol}")
        etf_chart = await _safe_get(
            client,
            f"/etfs/{symbol}/chart",
            params={"period": "1y", "format": "ohlcv"},
        )

    context.ngn_company = (
        _payload_object(company.payload)
        or _find_symbol_payload(
            companies.payload,
            symbol,
        )
        or _find_symbol_payload(identifiers.payload, symbol)
    )
    context.ngn_etf = _payload_object(etf.payload) or _find_symbol_payload(
        etfs.payload,
        symbol,
    )
    ngn_bars = _chart_points(company_chart.payload) or _chart_points(etf_chart.payload)
    if ngn_bars:
        context.bars = ngn_bars
    _record_provider(
        context,
        "ngnmarket",
        [companies, identifiers, etfs, company, company_chart, etf, etf_chart],
    )


async def _fetch_sec_fundamentals(context: PrefillBuildContext) -> None:
    cik = _cik(context.details)
    if cik is None:
        return

    headers = {
        "User-Agent": settings.hf_sec_user_agent,
        "Accept-Encoding": "gzip, deflate",
    }
    async with httpx.AsyncClient(
        base_url=settings.hf_sec_base_url.rstrip("/"),
        timeout=httpx.Timeout(10.0),
        headers=headers,
    ) as client:
        result = await _safe_get(client, f"/api/xbrl/companyfacts/CIK{cik}.json")

    if result.warning is not None:
        context.warnings.append(result.warning)
    if not isinstance(result.payload, dict):
        return

    market_cap = _market_cap(context)
    fundamentals = calculate_sec_fundamentals(result.payload, market_cap)
    context.sec_fundamentals = fundamentals
    context.sec_facts_summary = {
        "cik": cik,
        "entity_name": result.payload.get("entityName"),
        "source_period": fundamentals.source_period,
        "used_tags": fundamentals.used_tags or {},
    }
    if "sec" not in context.providers:
        context.providers.append("sec")


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
    if response.status_code == 404:
        return f"{path} was not found by provider."
    if response.status_code == 429:
        return f"{path} rate limited by provider."
    if detail:
        return f"{path} returned {response.status_code}: {detail}"
    return f"{path} returned {response.status_code}."


def _build_prefill_response(context: PrefillBuildContext) -> TickerPrefillResponse:
    fundamentals = context.sec_fundamentals
    instrument = InstrumentCreate(
        ticker=context.ticker,
        name=_instrument_name(context),
        asset_class=_asset_class(context),
        exchange=_exchange(context),
        currency=_currency(context),
        sector=_sector(context),
        industry=_industry(context),
    )
    metrics = TickerMetricsInput(
        current_price=_latest_price(context),
        market_cap_billion=_market_cap_billion(context),
        pe_ratio=_price_to_earnings(context) or fundamentals.pe_ratio,
        forward_pe=_decimal_from_keys(context.fmp_ratios, "forwardPERatioTTM"),
        revenue_growth_pct=fundamentals.revenue_growth_pct,
        earnings_growth_pct=fundamentals.earnings_growth_pct,
        free_cash_flow_yield_pct=_free_cash_flow_yield(context)
        or fundamentals.free_cash_flow_yield_pct,
        net_margin_pct=_net_margin(context) or fundamentals.net_margin_pct,
        debt_to_equity=_debt_to_equity(context) or fundamentals.debt_to_equity,
        price_vs_200d_pct=_price_vs_200d(context.bars),
        relative_strength_6m_pct=_relative_strength(context.bars),
        volatility_30d_pct=_volatility_30d(context.bars),
    )
    source_warnings = _client_source_warnings(context, instrument, metrics)

    return TickerPrefillResponse(
        instrument=instrument,
        metrics=metrics,
        provider=_provider_label(context),
        source_reference=_source_reference(context),
        data_timestamp=datetime.now(timezone.utc),
        source_warnings=source_warnings,
        raw_sources={
            "massive_details": _redact_url_fields(context.details),
            "massive_ratios": context.ratios,
            "fmp_profile": context.fmp_profile,
            "fmp_quote": context.fmp_quote,
            "fmp_ratios": context.fmp_ratios,
            "fmp_key_metrics": context.fmp_key_metrics,
            "tiingo_meta": context.tiingo_meta,
            "ngn_company": context.ngn_company,
            "ngn_etf": context.ngn_etf,
            "bars": {
                "count": len(context.bars),
                "first_date": _bar_date(context.bars[0]) if context.bars else None,
                "last_date": _bar_date(context.bars[-1]) if context.bars else None,
            },
            "sec_companyfacts": context.sec_facts_summary,
        },
    )


def _bars_path(ticker: str) -> str:
    today = date.today()
    start = today - timedelta(days=430)
    return (
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start.isoformat()}/{today.isoformat()}"
    )


def _record_provider(
    context: PrefillBuildContext,
    provider: str,
    results: list[ProviderResult],
) -> None:
    if provider not in context.providers:
        context.providers.append(provider)
    context.warnings.extend(
        result.warning for result in results if result.warning is not None
    )


def _client_source_warnings(
    context: PrefillBuildContext,
    instrument: InstrumentCreate,
    metrics: TickerMetricsInput,
) -> list[str]:
    warnings = list(dict.fromkeys(context.warnings))
    if not _has_prefill_coverage(context, instrument, metrics):
        return warnings
    return [
        warning
        for warning in warnings
        if not _is_non_actionable_provider_warning(warning)
    ]


def _has_prefill_coverage(
    context: PrefillBuildContext,
    instrument: InstrumentCreate,
    metrics: TickerMetricsInput,
) -> bool:
    ticker = context.ticker.strip().upper()
    name = instrument.name.strip().upper()
    has_identity = bool(name and name != ticker)
    has_classification = any(
        [instrument.exchange, instrument.sector, instrument.industry]
    )
    has_metric = any(
        getattr(metrics, field_name) is not None
        for field_name in TickerMetricsInput.model_fields
    )
    return has_identity or has_classification or has_metric


def _is_non_actionable_provider_warning(warning: str) -> bool:
    normalized = warning.strip().lower()
    if "not available for this api key or plan" in normalized:
        return True
    if "was not found by provider" in normalized:
        return True
    if "sec companyfacts skipped" in normalized:
        return True
    if " returned 404" in normalized and normalized.startswith(
        ("/v2/", "/v3/", "/stocks/", "/tiingo/", "/companies", "/etfs")
    ):
        return True
    return False


def _has_market_data_key(market: str) -> bool:
    if market == "NG":
        return bool(settings.hf_ngnmarket_api_key)
    return any(
        [
            settings.hf_polygon_api_key,
            settings.hf_fmp_api_key,
            settings.hf_tiingo_api_key,
        ]
    )


def _source_reference(context: PrefillBuildContext) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    return f"{_provider_label(context)}:{context.ticker}:{timestamp}"


def _provider_label(context: PrefillBuildContext) -> str:
    if context.providers:
        return "+".join(context.providers)
    if context.market == "NG":
        return "ngnmarket"
    return "market-data"


def _instrument_name(context: PrefillBuildContext) -> str:
    return (
        _string_from_keys(
            context.details,
            "name",
            "company_name",
            "companyName",
            "securityName",
        )
        or _string_from_keys(
            context.fmp_profile, "companyName", "companyNameLong", "name"
        )
        or _string_from_keys(context.tiingo_meta, "name")
        or _string_from_keys(
            context.ngn_company,
            "name",
            "companyName",
            "company_name",
            "securityName",
        )
        or _string_from_keys(context.ngn_etf, "name", "fundName", "fund_name")
        or context.ticker
    )


def _asset_class(context: PrefillBuildContext) -> str:
    ticker_type = str(context.details.get("type") or "").upper()
    if ticker_type == "ETF":
        return "etf"

    fmp_type = str(
        context.fmp_profile.get("type")
        or context.fmp_profile.get("assetType")
        or context.fmp_profile.get("securityType")
        or ""
    ).upper()
    if fmp_type == "ETF" or context.fmp_profile.get("isEtf") is True:
        return "etf"

    if context.ngn_etf and not context.ngn_company:
        return "etf"

    return "equity"


def _exchange(context: PrefillBuildContext) -> str | None:
    if context.market == "NG":
        return (
            _string_from_keys(context.ngn_company, "exchange", "exchangeCode")
            or _string_from_keys(context.ngn_etf, "exchange", "exchangeCode")
            or "NGX"
        )
    return (
        _optional_string(context.details.get("primary_exchange"))
        or _string_from_keys(context.fmp_profile, "exchangeShortName", "exchange")
        or _string_from_keys(context.fmp_quote, "exchange")
        or _string_from_keys(context.tiingo_meta, "exchangeCode")
    )


def _currency(context: PrefillBuildContext) -> str:
    if context.market == "NG":
        return "NGN"

    value = (
        _string_from_keys(context.details, "currency_name", "currency")
        or _string_from_keys(context.fmp_profile, "currency")
        or "USD"
    )
    value = value.upper()
    if value == "US DOLLAR":
        return "USD"
    return value[:3]


def _sector(context: PrefillBuildContext) -> str | None:
    return (
        _optional_string(
            context.details.get("sic_description")
            or context.details.get("sector")
            or context.details.get("market")
        )
        or _string_from_keys(context.fmp_profile, "sector")
        or _string_from_keys(context.ngn_company, "sector", "sectorName")
        or _string_from_keys(context.ngn_etf, "sector", "sectorName")
    )


def _industry(context: PrefillBuildContext) -> str | None:
    return (
        _optional_string(context.details.get("industry") or context.details.get("type"))
        or _string_from_keys(context.fmp_profile, "industry")
        or _string_from_keys(context.ngn_company, "industry", "subSector", "subsector")
        or _string_from_keys(context.ngn_etf, "industry", "category")
    )


def _latest_price(context: PrefillBuildContext) -> Decimal | None:
    return (
        _decimal(context.ratios.get("price"))
        or _decimal_from_keys(context.fmp_quote, "price")
        or _decimal_from_keys(context.fmp_profile, "price")
        or _decimal_from_keys(
            context.ngn_company,
            "current_price",
            "currentPrice",
            "price",
            "last_price",
            "lastPrice",
        )
        or _decimal_from_keys(
            context.ngn_etf,
            "current_price",
            "currentPrice",
            "price",
            "last_price",
            "lastPrice",
        )
        or _latest_bar_close(context.bars)
    )


def _market_cap(context: PrefillBuildContext) -> Decimal | None:
    return (
        _decimal(context.ratios.get("market_cap"))
        or _decimal(context.details.get("market_cap"))
        or _decimal_from_keys(context.fmp_quote, "marketCap")
        or _decimal_from_keys(context.fmp_profile, "mktCap", "marketCap")
        or _decimal_from_keys(
            context.ngn_company,
            "market_cap",
            "marketCap",
            "marketCapitalization",
        )
    )


def _market_cap_billion(context: PrefillBuildContext) -> Decimal | None:
    market_cap = _market_cap(context)
    if market_cap is None:
        return None
    return _quantize_pct(market_cap / Decimal("1000000000"))


def _price_to_earnings(context: PrefillBuildContext) -> Decimal | None:
    direct_value = (
        _decimal(context.ratios.get("price_to_earnings"))
        or _decimal_from_keys(context.fmp_quote, "pe")
        or _decimal_from_keys(context.fmp_profile, "pe")
        or _decimal_from_keys(
            context.fmp_ratios,
            "peRatioTTM",
            "priceEarningsRatioTTM",
            "priceToEarningsRatioTTM",
        )
        or _decimal_from_keys(context.ngn_company, "peRatio", "pe_ratio", "pe")
    )
    if direct_value is not None:
        return direct_value

    price = _latest_price(context)
    eps = _decimal_from_keys(
        context.ngn_company,
        "trailing_eps",
        "trailingEps",
        "eps",
    )
    if price is not None and eps is not None and eps != 0:
        return _quantize_pct(price / eps)
    return None


def _free_cash_flow_yield(context: PrefillBuildContext) -> Decimal | None:
    direct_value = _decimal_from_keys(
        context.fmp_key_metrics,
        "freeCashFlowYieldTTM",
        "freeCashFlowYield",
    )
    if direct_value is not None:
        return _pct_value(direct_value)

    market_cap = _decimal(context.ratios.get("market_cap"))
    free_cash_flow = _decimal(context.ratios.get("free_cash_flow"))
    if market_cap is None or free_cash_flow is None or market_cap == 0:
        return None
    return _quantize_pct((free_cash_flow / market_cap) * Decimal("100"))


def _net_margin(context: PrefillBuildContext) -> Decimal | None:
    value = (
        _decimal(
            context.ratios.get("net_margin") or context.ratios.get("profit_margin")
        )
        or _decimal_from_keys(
            context.fmp_ratios,
            "netProfitMarginTTM",
            "netProfitMargin",
        )
        or _decimal_from_keys(context.ngn_company, "netMargin", "net_margin")
    )
    if value is None:
        return None
    return _pct_value(value)


def _debt_to_equity(context: PrefillBuildContext) -> Decimal | None:
    return (
        _decimal(context.ratios.get("debt_to_equity"))
        or _decimal_from_keys(
            context.fmp_ratios,
            "debtEquityRatioTTM",
            "debtEquityRatio",
        )
        or _decimal_from_keys(context.ngn_company, "debtToEquity", "debt_to_equity")
    )


def _price_vs_200d(bars: list[dict | list]) -> Decimal | None:
    closes = _closes(bars)
    if len(closes) < 200:
        return None
    latest = closes[-1]
    average = sum(closes[-200:], Decimal("0")) / Decimal("200")
    if average == 0:
        return None
    return _quantize_pct(((latest - average) / average) * Decimal("100"))


def _relative_strength(bars: list[dict | list]) -> Decimal | None:
    closes = _closes(bars)
    if len(closes) < 126:
        return None
    start = closes[-126]
    latest = closes[-1]
    if start == 0:
        return None
    return _quantize_pct(((latest - start) / start) * Decimal("100"))


def _volatility_30d(bars: list[dict | list]) -> Decimal | None:
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


def _closes(bars: list[dict | list]) -> list[Decimal]:
    closes: list[Decimal] = []
    for bar in bars:
        close = _bar_close(bar)
        if close is not None:
            closes.append(close)
    return closes


def _latest_bar_close(bars: list[dict | list]) -> Decimal | None:
    if not bars:
        return None
    return _bar_close(bars[-1])


def _bar_close(bar: dict | list) -> Decimal | None:
    if isinstance(bar, dict):
        return _decimal_from_keys(bar, "c", "adjClose", "close", "price")
    if isinstance(bar, list):
        if len(bar) >= 5:
            return _decimal(bar[4])
        if len(bar) >= 2:
            return _decimal(bar[1])
    return None


def _bar_date(bar: dict | list) -> str | None:
    if isinstance(bar, dict):
        timestamp = bar.get("t") or bar.get("timestamp")
        if isinstance(timestamp, int):
            return (
                datetime.fromtimestamp(
                    timestamp / 1000,
                    tz=timezone.utc,
                )
                .date()
                .isoformat()
            )
        value = bar.get("date")
        return str(value)[:10] if value else None

    if isinstance(bar, list) and bar:
        timestamp = _decimal(bar[0])
        if timestamp is None:
            return None
        timestamp_float = float(timestamp)
        if timestamp_float > 10_000_000_000:
            timestamp_float = timestamp_float / 1000
        return (
            datetime.fromtimestamp(timestamp_float, tz=timezone.utc).date().isoformat()
        )

    return None


def _first_result(payload: dict | list | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    results = payload.get("results")
    if isinstance(results, list):
        return results[0] if results else {}
    if isinstance(results, dict):
        return results
    return {}


def _results(payload: dict | list | None) -> list[dict | list]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    return results if isinstance(results, list) else []


def _first_list_item(payload: dict | list | None) -> dict:
    values = _list_payload(payload)
    if values and isinstance(values[0], dict):
        return values[0]
    return payload if isinstance(payload, dict) else {}


def _payload_object(payload: dict | list | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    for key in ["data", "result", "results", "company", "etf"]:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return payload


def _list_payload(payload: dict | list | None) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ["data", "results", "result", "prices", "chart"]:
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _chart_points(payload: dict | list | None) -> list[dict | list]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ["data", "results", "result", "prices", "chart"]:
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _chart_points(value)
            if nested:
                return nested
    return []


def _find_symbol_payload(payload: dict | list | None, symbol: str) -> dict:
    target = symbol.strip().upper()
    for item in _walk_payload_items(payload):
        if not isinstance(item, dict):
            continue
        candidates = [
            item.get("symbol"),
            item.get("ticker"),
            item.get("tickerSymbol"),
            item.get("securityCode"),
            item.get("code"),
        ]
        if any(
            str(candidate or "").strip().upper() == target for candidate in candidates
        ):
            return item
    return {}


def _walk_payload_items(payload: dict | list | None) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    items: list = []
    for key in ["data", "results", "result", "companies", "identifiers", "etfs"]:
        value = payload.get(key)
        if isinstance(value, list):
            items.extend(value)
        elif isinstance(value, dict):
            items.extend(_walk_payload_items(value))
    return items


def _decimal_from_keys(payload: dict, *keys: str) -> Decimal | None:
    for key in keys:
        value = _decimal(payload.get(key))
        if value is not None:
            return value
    return None


def _string_from_keys(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = _optional_string(payload.get(key))
        if value is not None:
            return value
    return None


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _cik(details: dict) -> str | None:
    cik_value = details.get("cik")
    if cik_value is None:
        return None
    digits = "".join(character for character in str(cik_value) if character.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def _pct_value(value: Decimal) -> Decimal:
    if abs(value) <= 1:
        return _quantize_pct(value * Decimal("100"))
    return value


def _quantize_pct(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _redact_url_fields(payload: dict) -> dict:
    redacted = dict(payload)
    for key in ["logo_url", "icon_url", "image", "website"]:
        value = redacted.get(key)
        if isinstance(value, str):
            parsed = urlsplit(value)
            redacted[key] = parsed.path or parsed.netloc
    return redacted

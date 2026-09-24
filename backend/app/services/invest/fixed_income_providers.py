from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.core.config import settings

QUOTE_QUALITY_EXECUTABLE = "executable_quote"
QUOTE_QUALITY_TRADE_PRINT = "trade_print"
QUOTE_QUALITY_EVALUATED = "evaluated_price"
QUOTE_QUALITY_OFFICIAL_AUCTION = "official_auction"
QUOTE_QUALITY_CURVE_MODEL = "curve_model"
QUOTE_QUALITY_PROXY_MARKET = "proxy_market"
QUOTE_QUALITY_SEED_MODEL = "seed_model"

QUOTE_QUALITY_LABELS: dict[str, str] = {
    QUOTE_QUALITY_EXECUTABLE: "Executable quote",
    QUOTE_QUALITY_TRADE_PRINT: "Trade print",
    QUOTE_QUALITY_EVALUATED: "Evaluated price",
    QUOTE_QUALITY_OFFICIAL_AUCTION: "Official auction",
    QUOTE_QUALITY_CURVE_MODEL: "Curve model",
    QUOTE_QUALITY_PROXY_MARKET: "Listed proxy",
    QUOTE_QUALITY_SEED_MODEL: "Model fallback",
}

QUOTE_QUALITY_RANK: dict[str, int] = {
    QUOTE_QUALITY_EXECUTABLE: 700,
    QUOTE_QUALITY_TRADE_PRINT: 600,
    QUOTE_QUALITY_EVALUATED: 500,
    QUOTE_QUALITY_OFFICIAL_AUCTION: 400,
    QUOTE_QUALITY_CURVE_MODEL: 300,
    QUOTE_QUALITY_PROXY_MARKET: 200,
    QUOTE_QUALITY_SEED_MODEL: 100,
}

QUOTE_QUALITY_FRESHNESS: dict[str, timedelta] = {
    QUOTE_QUALITY_EXECUTABLE: timedelta(minutes=2),
    QUOTE_QUALITY_TRADE_PRINT: timedelta(hours=2),
    QUOTE_QUALITY_EVALUATED: timedelta(hours=8),
    QUOTE_QUALITY_OFFICIAL_AUCTION: timedelta(days=2),
    QUOTE_QUALITY_CURVE_MODEL: timedelta(hours=18),
    QUOTE_QUALITY_PROXY_MARKET: timedelta(minutes=20),
    QUOTE_QUALITY_SEED_MODEL: timedelta(hours=18),
}

LIVE_QUOTE_QUALITIES = frozenset(
    {
        QUOTE_QUALITY_EXECUTABLE,
        QUOTE_QUALITY_TRADE_PRINT,
        QUOTE_QUALITY_PROXY_MARKET,
    }
)


@dataclass(frozen=True)
class FixedIncomeProviderCapability:
    provider: str
    label: str
    source: str
    quote_quality: str
    freshness: timedelta
    markets: frozenset[str] = frozenset()
    instrument_types: frozenset[str] = frozenset()
    credential_settings: tuple[str, ...] = ()
    requires_proxy_ticker: bool = False
    implemented: bool = False
    notes: tuple[str, ...] = ()

    def supports(self, product: Any) -> bool:
        market = str(getattr(product, "market", "") or "").upper()
        instrument_type = str(getattr(product, "instrument_type", "") or "").lower()
        proxy_ticker = str(getattr(product, "proxy_ticker", "") or "").strip()
        if self.markets and market not in self.markets:
            return False
        if self.instrument_types and instrument_type not in self.instrument_types:
            return False
        if self.requires_proxy_ticker and not proxy_ticker:
            return False
        return True

    @property
    def configured(self) -> bool:
        if not self.credential_settings:
            return True
        return all(
            bool(getattr(settings, key, None)) for key in self.credential_settings
        )

    @property
    def enabled(self) -> bool:
        return self.implemented and self.configured

    @property
    def status(self) -> str:
        if self.enabled:
            return "enabled"
        if not self.implemented:
            return "planned"
        return "credentials_missing"


IMPLEMENTED_MODEL_PROVIDER = FixedIncomeProviderCapability(
    provider="internal_model",
    label="Internal pricing model",
    source="model_seed",
    quote_quality=QUOTE_QUALITY_SEED_MODEL,
    freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_SEED_MODEL],
    implemented=True,
    notes=(
        "Fallback mark from the product shelf when no provider quote is available.",
    ),
)

FIXED_INCOME_PROVIDER_CAPABILITIES: tuple[FixedIncomeProviderCapability, ...] = (
    FixedIncomeProviderCapability(
        provider="alpaca_fixed_income",
        label="Alpaca fixed income",
        source="alpaca_broker_api",
        quote_quality=QUOTE_QUALITY_EXECUTABLE,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_EXECUTABLE],
        markets=frozenset({"US"}),
        instrument_types=frozenset(
            {"treasury_bill", "treasury_note", "government_bond", "corporate_bond"}
        ),
        credential_settings=(
            "hf_alpaca_broker_api_key",
            "hf_alpaca_broker_api_secret",
        ),
        notes=("Candidate source for US Treasury and corporate executable quotes.",),
    ),
    FixedIncomeProviderCapability(
        provider="finra_trace",
        label="FINRA TRACE",
        source="finra_trace_api",
        quote_quality=QUOTE_QUALITY_TRADE_PRINT,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_TRADE_PRINT],
        markets=frozenset({"US"}),
        instrument_types=frozenset({"corporate_bond", "agency_bond"}),
        notes=("Post-trade tape; useful as context, not executable liquidity.",),
    ),
    FixedIncomeProviderCapability(
        provider="treasury_fiscal_data",
        label="Treasury/Fiscal Data",
        source="treasury_official",
        quote_quality=QUOTE_QUALITY_OFFICIAL_AUCTION,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_OFFICIAL_AUCTION],
        markets=frozenset({"US"}),
        instrument_types=frozenset(
            {"treasury_bill", "treasury_note", "government_bond"}
        ),
        notes=("Official US auction and reference data.",),
    ),
    FixedIncomeProviderCapability(
        provider="fred_curve",
        label="FRED yield curve",
        source="fred_curve",
        quote_quality=QUOTE_QUALITY_CURVE_MODEL,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_CURVE_MODEL],
        markets=frozenset({"US"}),
        instrument_types=frozenset(
            {"treasury_bill", "treasury_note", "government_bond"}
        ),
        notes=("Curve inputs for modeled US Treasury marks.",),
    ),
    FixedIncomeProviderCapability(
        provider="fmdq",
        label="FMDQ",
        source="fmdq_market_data",
        quote_quality=QUOTE_QUALITY_EXECUTABLE,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_EXECUTABLE],
        markets=frozenset({"NG"}),
        instrument_types=frozenset(
            {"treasury_bill", "government_bond", "commercial_paper"}
        ),
        credential_settings=("hf_fmdq_api_key",),
        notes=("Candidate source for Nigerian fixed-income market data.",),
    ),
    FixedIncomeProviderCapability(
        provider="cbn",
        label="CBN",
        source="cbn_official",
        quote_quality=QUOTE_QUALITY_OFFICIAL_AUCTION,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_OFFICIAL_AUCTION],
        markets=frozenset({"NG"}),
        instrument_types=frozenset({"treasury_bill"}),
        notes=("Official Nigerian auction and rates context.",),
    ),
    FixedIncomeProviderCapability(
        provider="dmo",
        label="DMO Nigeria",
        source="dmo_official",
        quote_quality=QUOTE_QUALITY_OFFICIAL_AUCTION,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_OFFICIAL_AUCTION],
        markets=frozenset({"NG"}),
        instrument_types=frozenset({"government_bond"}),
        notes=("Official Nigerian sovereign bond issuance context.",),
    ),
    FixedIncomeProviderCapability(
        provider="tiingo_proxy",
        label="Tiingo listed proxy",
        source="tiingo_proxy_market",
        quote_quality=QUOTE_QUALITY_PROXY_MARKET,
        freshness=QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_PROXY_MARKET],
        credential_settings=("hf_tiingo_api_key",),
        requires_proxy_ticker=True,
        notes=("Listed ETF proxy context; not a direct cash-bond quote.",),
    ),
    IMPLEMENTED_MODEL_PROVIDER,
)


def fixed_income_provider_plan(
    product: Any,
) -> tuple[FixedIncomeProviderCapability, ...]:
    """Return the provider ladder that can plausibly support this product."""
    supported = [
        capability
        for capability in FIXED_INCOME_PROVIDER_CAPABILITIES
        if capability.supports(product)
    ]
    return tuple(
        sorted(
            supported,
            key=lambda item: (
                not item.enabled,
                -QUOTE_QUALITY_RANK.get(item.quote_quality, 0),
                item.provider,
            ),
        )
    )


def implemented_provider_for_source(source: str) -> FixedIncomeProviderCapability:
    normalized = source.strip().lower()
    for capability in FIXED_INCOME_PROVIDER_CAPABILITIES:
        if capability.source == normalized or capability.provider == normalized:
            return capability
    return IMPLEMENTED_MODEL_PROVIDER


def provider_label(provider: str | None) -> str:
    normalized = (provider or "").strip().lower()
    for capability in FIXED_INCOME_PROVIDER_CAPABILITIES:
        if capability.provider == normalized or capability.source == normalized:
            return capability.label
    return normalized.replace("_", " ").title() if normalized else "Unknown provider"


def quote_quality_label(quality: str | None) -> str:
    normalized = (quality or "").strip().lower()
    return QUOTE_QUALITY_LABELS.get(
        normalized,
        normalized.replace("_", " ").title() if normalized else "Unknown quality",
    )


def quote_quality_is_live(quality: str | None) -> bool:
    return (quality or "").strip().lower() in LIVE_QUOTE_QUALITIES


def stale_after_for_quality(quality: str | None, as_of: datetime) -> datetime:
    normalized = (quality or "").strip().lower()
    freshness = QUOTE_QUALITY_FRESHNESS.get(
        normalized,
        QUOTE_QUALITY_FRESHNESS[QUOTE_QUALITY_SEED_MODEL],
    )
    return as_of + freshness

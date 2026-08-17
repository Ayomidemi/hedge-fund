"""Tuning constants for the live price platform.

These are deliberately code constants, not environment variables. The only
env-driven knob is HF_PRICE_REFRESH_INTERVAL_SECONDS (see config.py).
"""

# Max tickers per provider HTTP request.
PRICE_BATCH_SIZE = 50

# Skip quote ingestion outside US regular trading hours. Flip to False when
# testing off-hours (e.g. penny stocks in extended sessions).
PRICE_MARKET_HOURS_ONLY = True

# A quote older than this is flagged stale and excluded from marking.
PRICE_STALE_AFTER_SECONDS = 600

# Always kept in the price universe for benchmarking (risk, attribution).
BENCHMARK_TICKERS = ("SPY",)

# HTTP timeout for provider quote calls.
QUOTE_HTTP_TIMEOUT_SECONDS = 15.0

# Model recommendations newer than this stay in the price universe.
RECOMMENDATION_UNIVERSE_DAYS = 30

# Redis pub/sub channel all platform events flow through.
PLATFORM_EVENTS_CHANNEL = "platform:events"

# --- Market radar ---
# Human attention budget for the daily working set (holdings + movers).
RADAR_WORKING_SET_SIZE = 100

# Celery cadence. The task still no-ops closed jurisdictions, so this is an
# upper bound on how often an *open* market is scanned — not a request to
# poll vendors overnight.
RADAR_SCAN_INTERVAL_SECONDS = 1800

# How long after the cash session we still allow one discovery scan using
# that day's session data, without treating the market as open for live quotes.
RADAR_POST_CLOSE_WINDOW_HOURS = 2

# Max names pulled from each US discovery list (gainers / losers / actives).
RADAR_MOVER_LIST_LIMIT = 15

# Max NGX discovery names beyond always-watched holdings.
RADAR_NG_DISCOVERY_LIMIT = 25

# Quotes already refreshed by the live-price platform can be reused by Radar if
# they are from the current UTC day or no older than this live-cache window.
RADAR_QUOTE_CACHE_TTL_SECONDS = 900

# Radar may fill missing catalog/always-watched prices during open sessions, but
# these caps keep NGX per-symbol calls and US fallback calls bounded.
RADAR_US_QUOTE_REFRESH_LIMIT = 60
RADAR_NG_QUOTE_REFRESH_LIMIT = 12

# Historical context window used for anomaly scoring and sparklines.
RADAR_HISTORY_LOOKBACK_DAYS = 90
RADAR_SPARKLINE_POINTS = 24

# Sector / market ETFs always watched as industry pulse (US only).
RADAR_SECTOR_ETFS: tuple[tuple[str, str, str], ...] = (
    ("SPY", "Broad Market", "ETF"),
    ("QQQ", "Technology", "ETF"),
    ("IWM", "Broad Market", "ETF"),
    ("XLK", "Technology", "ETF"),
    ("XLF", "Financial Services", "ETF"),
    ("XLE", "Energy", "ETF"),
    ("XLV", "Healthcare", "ETF"),
    ("XLI", "Industrials", "ETF"),
    ("XLY", "Consumer Cyclical", "ETF"),
    ("XLP", "Consumer Defensive", "ETF"),
    ("XLB", "Basic Materials", "ETF"),
    ("XLU", "Utilities", "ETF"),
    ("XLC", "Communication Services", "ETF"),
    ("XLRE", "Real Estate", "ETF"),
    ("TLT", "Bonds", "ETF"),
    ("GLD", "Commodity", "ETF"),
)


def _sector_benchmarks() -> dict[str, str]:
    """Map a GICS-style sector to the ETF used as its pulse.

    Dedicated XL* funds win over QQQ. Broad market stays on SPY, not IWM.
    """
    mapping: dict[str, str] = {}
    for ticker, sector, _asset_class in RADAR_SECTOR_ETFS:
        if sector not in mapping or ticker.startswith("XL"):
            mapping[sector] = ticker
    return mapping


RADAR_SECTOR_BENCHMARKS = _sector_benchmarks()

RADAR_VENDOR_QUOTE_SOURCES = frozenset({"fmp", "tiingo", "polygon", "ngnmarket"})

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

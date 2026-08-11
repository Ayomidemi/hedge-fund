"""FX conversion helpers used when marking Nigerian positions into USD."""

import logging
from decimal import Decimal

from app.models import FxRate, Instrument, InstrumentQuote

logger = logging.getLogger(__name__)

_NG_EXCHANGES = {"NG", "NGX"}


def is_nigerian_instrument(instrument: Instrument) -> bool:
    ticker = instrument.ticker.upper()
    exchange = (instrument.exchange or "").strip().upper()
    return ticker.endswith(".NG") or exchange in _NG_EXCHANGES


def convert_to_usd(
    amount: Decimal,
    currency: str,
    fx_rates: dict[tuple[str, str], FxRate],
) -> Decimal | None:
    """Convert an amount to USD using stored FX rates.

    Returns None if conversion is required but no rate is available.
    """
    normalized = currency.strip().upper()
    if normalized == "USD":
        return amount

    if normalized == "NGN":
        rate_row = fx_rates.get(("USD", "NGN"))
        if rate_row is None or rate_row.rate <= 0:
            return None
        return amount / rate_row.rate

    logger.warning("fx_conversion_unsupported", extra={"currency": normalized})
    return None


def mark_price_for_position(
    *,
    quote: InstrumentQuote,
    instrument: Instrument,
    portfolio_base_currency: str,
    fx_rates: dict[tuple[str, str], FxRate],
) -> Decimal | None:
    """Resolve the mark price in the portfolio's base currency.

    Nigerian instruments quoted in NGN are converted to USD (or whatever the
    portfolio base is) using the latest FX rate. Same-currency quotes pass
    through unchanged.
    """
    base = portfolio_base_currency.strip().upper()
    quote_currency = quote.currency.strip().upper()
    instrument_currency = instrument.currency.strip().upper()

    # Nigerian quote → always convert to portfolio base, even if the
    # instrument row has the wrong currency label (common data issue).
    if quote_currency == "NGN" and (
        is_nigerian_instrument(instrument) or instrument_currency == "NGN"
    ):
        return convert_to_usd(quote.price, "NGN", fx_rates)

    if quote_currency == base:
        return quote.price

    if quote_currency != instrument_currency:
        logger.warning(
            "mark_skipped_currency_mismatch",
            extra={
                "ticker_symbol": instrument.ticker,
                "instrument_currency": instrument_currency,
                "quote_currency": quote_currency,
                "portfolio_base": base,
            },
        )
        return None

    return quote.price

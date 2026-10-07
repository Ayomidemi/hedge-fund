"""Keep active orders supplied with quotes independently of slow research jobs."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.models import Instrument, InstrumentQuote, PaperFundRun, PaperOrder
from app.services.market_data.ingestion import ingest_quotes
from app.services.market_radar.execution import quote_rejection
from app.services.paper_fund.calendar import market_blocker
from app.services.paper_fund.engine import utc


async def refresh_order_quotes(session, *, now: datetime | None = None) -> int:
    now = utc(now or datetime.now(timezone.utc))
    if market_blocker(now):
        return 0
    rows = await session.execute(
        select(Instrument, InstrumentQuote, PaperOrder)
        .join(PaperOrder, PaperOrder.instrument_id == Instrument.id)
        .join(PaperFundRun, PaperFundRun.id == PaperOrder.run_id)
        .outerjoin(InstrumentQuote, InstrumentQuote.instrument_id == Instrument.id)
        .where(PaperFundRun.status != "completed", PaperOrder.status.in_(["pending", "open"]))
    )
    universe = {}
    for instrument, quote, order in rows:
        # A pending order needs a later observation; a healthy stream usually
        # supplies it. REST takes over when the stream is missing or delayed.
        needs_later_trade = order.status == "pending" and (
            quote is None or utc(quote.as_of) <= utc(order.submitted_at)
        )
        if (quote_rejection(quote, now) or needs_later_trade
                or (now - utc(quote.as_of)).total_seconds() >= 60):
            universe.setdefault(instrument.ticker, set()).add(instrument.id)
    if not universe:
        return 0
    result = await ingest_quotes(session, {ticker: list(ids) for ticker, ids in universe.items()})
    await session.commit()
    return result.success_count

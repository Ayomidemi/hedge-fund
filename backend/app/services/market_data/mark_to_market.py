"""Mark-to-market: apply latest quotes to every open position.

This is the only writer of position.market_value / unrealized_pnl outside of
trade booking. Nigerian (NGN) quotes are converted to the portfolio base
currency (USD) via the fx_rates table before marking.
"""

import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import CashLedgerEntry, InstrumentQuote, Portfolio, Position
from app.services.market_data.fx_convert import mark_price_for_position
from app.services.market_data.fx_refresh import load_fx_rates
from app.services.portfolio.calculations import money

logger = logging.getLogger(__name__)


@dataclass
class MarkedPortfolio:
    portfolio_id: uuid.UUID
    owner_user_id: str
    nav: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    position_count: int


@dataclass
class MarkResult:
    positions_marked: int = 0
    positions_skipped: int = 0
    portfolios: list[MarkedPortfolio] = field(default_factory=list)


async def mark_open_positions(session: AsyncSession) -> MarkResult:
    positions = list(
        await session.scalars(
            select(Position)
            .options(
                selectinload(Position.portfolio),
                selectinload(Position.instrument),
            )
            .where(Position.quantity > 0)
            .where(Position.closed_at.is_(None))
        )
    )
    if not positions:
        return MarkResult()

    instrument_ids = {position.instrument_id for position in positions}
    quotes = {
        quote.instrument_id: quote
        for quote in await session.scalars(
            select(InstrumentQuote)
            .where(InstrumentQuote.instrument_id.in_(instrument_ids))
            .where(InstrumentQuote.is_stale.is_(False))
        )
    }
    fx_rates = await load_fx_rates(session)

    marked = 0
    skipped = 0
    touched_portfolios: dict[uuid.UUID, Portfolio] = {}
    for position in positions:
        quote = quotes.get(position.instrument_id)
        if quote is None:
            skipped += 1
            continue

        mark_price = mark_price_for_position(
            quote=quote,
            instrument=position.instrument,
            portfolio_base_currency=position.portfolio.base_currency,
            fx_rates=fx_rates,
        )
        if mark_price is None:
            skipped += 1
            continue

        position.market_value = money(position.quantity * mark_price)
        position.unrealized_pnl = money(
            (mark_price - position.average_cost) * position.quantity
        )
        marked += 1
        touched_portfolios[position.portfolio_id] = position.portfolio

    await session.flush()

    portfolios = await _portfolio_snapshots(session, touched_portfolios)
    logger.info(
        "positions_marked_to_market",
        extra={
            "positions_marked": marked,
            "positions_skipped": skipped,
            "portfolio_count": len(portfolios),
        },
    )
    return MarkResult(
        positions_marked=marked,
        positions_skipped=skipped,
        portfolios=portfolios,
    )


async def _portfolio_snapshots(
    session: AsyncSession,
    portfolios: dict[uuid.UUID, Portfolio],
) -> list[MarkedPortfolio]:
    if not portfolios:
        return []

    portfolio_ids = list(portfolios)

    cash_rows = await session.execute(
        select(
            CashLedgerEntry.portfolio_id,
            func.coalesce(func.sum(CashLedgerEntry.amount), 0),
        )
        .where(CashLedgerEntry.portfolio_id.in_(portfolio_ids))
        .group_by(CashLedgerEntry.portfolio_id)
    )
    cash_by_portfolio = {row[0]: money(Decimal(str(row[1]))) for row in cash_rows}

    invested_rows = await session.execute(
        select(
            Position.portfolio_id,
            func.coalesce(func.sum(Position.market_value), 0),
            func.count(Position.id),
        )
        .where(Position.portfolio_id.in_(portfolio_ids))
        .where(Position.quantity > 0)
        .where(Position.closed_at.is_(None))
        .group_by(Position.portfolio_id)
    )

    snapshots: list[MarkedPortfolio] = []
    for portfolio_id, invested_value, position_count in invested_rows:
        portfolio = portfolios[portfolio_id]
        cash_balance = cash_by_portfolio.get(portfolio_id, Decimal("0.00"))
        invested = money(Decimal(str(invested_value)))
        snapshots.append(
            MarkedPortfolio(
                portfolio_id=portfolio_id,
                owner_user_id=portfolio.owner_user_id,
                nav=money(cash_balance + invested),
                cash_balance=cash_balance,
                invested_value=invested,
                position_count=int(position_count),
            )
        )
    return snapshots

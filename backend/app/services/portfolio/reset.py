"""Owner-scoped Capital reset, with an atomic transaction and private backup.

The caller owns the transaction. No live broker or retail Invest records are
modified. Paper starts and existing execution workers share the locks below.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.locks import lock_idempotency_scope
from app.models import (
    CashLedgerEntry,
    Opportunity,
    PaperEquitySnapshot,
    PaperFundRun,
    PaperOrder,
    Portfolio,
    PortfolioRiskSnapshot,
    Position,
    PositionRiskSnapshot,
    PreTradeRiskCheck,
    ReportSnapshot,
    RiskCheck,
    RiskLimit,
    RiskMeasurement,
    StrategyPod,
    StrategyPodSnapshot,
    StressTestResult,
    SystemLogEntry,
    Trade,
)


RESET_CAPITAL = Decimal("10000.00")


class CapitalResetError(ValueError):
    pass


@dataclass(frozen=True)
class CapitalResetSummary:
    owner_user_id: str
    portfolio_id: str
    portfolio_name: str
    currency: str
    previous_initial_capital: str
    opening_cash: str
    cash_by_currency: dict[str, str]
    rows_to_delete: dict[str, int]
    executed: bool = False
    reset_id: str | None = None
    backup_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _targets(owner: str, portfolio_id: UUID) -> list[tuple[type, object]]:
    """Deletion order follows FK children before their parent records."""
    owned_trades = select(Trade.id).where(Trade.portfolio_id == portfolio_id)
    owned_limits = select(RiskLimit.id).where(RiskLimit.portfolio_id == portfolio_id)
    owned_runs = select(PaperFundRun.id).where(PaperFundRun.owner_user_id == owner)
    owned_pods = select(StrategyPod.id).where(StrategyPod.owner_user_id == owner)
    return [
        (Opportunity, Opportunity.owner_user_id == owner),
        (RiskCheck, or_(
            RiskCheck.portfolio_id == portfolio_id,
            and_(RiskCheck.portfolio_id.is_(None), or_(
                RiskCheck.trade_id.in_(owned_trades),
                RiskCheck.risk_limit_id.in_(owned_limits),
            )),
        )),
        (Trade, Trade.portfolio_id == portfolio_id),
        (Position, Position.portfolio_id == portfolio_id),
        (CashLedgerEntry, CashLedgerEntry.portfolio_id == portfolio_id),
        (PreTradeRiskCheck, and_(PreTradeRiskCheck.portfolio_id == portfolio_id,
                                 PreTradeRiskCheck.owner_user_id == owner)),
        (PositionRiskSnapshot, PositionRiskSnapshot.portfolio_id == portfolio_id),
        (RiskMeasurement, RiskMeasurement.portfolio_id == portfolio_id),
        (StressTestResult, StressTestResult.portfolio_id == portfolio_id),
        (PortfolioRiskSnapshot, PortfolioRiskSnapshot.portfolio_id == portfolio_id),
        (ReportSnapshot, and_(ReportSnapshot.portfolio_id == portfolio_id,
                              ReportSnapshot.owner_user_id == owner)),
        (StrategyPodSnapshot, StrategyPodSnapshot.strategy_pod_id.in_(owned_pods)),
        (PaperOrder, PaperOrder.run_id.in_(owned_runs)),
        (PaperEquitySnapshot, PaperEquitySnapshot.run_id.in_(owned_runs)),
        (PaperFundRun, PaperFundRun.owner_user_id == owner),
    ]


async def _portfolio(
    session: AsyncSession,
    owner: str,
    *,
    expected_portfolio_id: UUID | None = None,
    lock: bool = False,
) -> Portfolio:
    if not owner or owner != owner.strip():
        raise CapitalResetError("An exact, non-empty owner user ID is required.")
    if lock:
        # start_run takes this same owner lock before creating a new paper run.
        await lock_idempotency_scope(session, "paper-fund-start", owner)
    statement = select(Portfolio).where(Portfolio.owner_user_id == owner)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    portfolio = await session.scalar(statement)
    if portfolio is None:
        raise CapitalResetError("No Capital portfolio exists for the specified owner.")
    if expected_portfolio_id is not None and portfolio.id != expected_portfolio_id:
        raise CapitalResetError("Portfolio ID does not match the specified owner; nothing was reset.")
    if portfolio.base_currency != "USD":
        raise CapitalResetError("The $10,000 reset requires a USD Capital portfolio.")
    if lock:
        # cycle/control hold FOR UPDATE on the run while reading or changing its
        # orders. Wait for those transactions before deleting their records.
        await session.scalars(
            select(PaperFundRun)
            .where(PaperFundRun.owner_user_id == owner)
            .order_by(PaperFundRun.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    return portfolio


async def _summary(session: AsyncSession, portfolio: Portfolio) -> CapitalResetSummary:
    owner = portfolio.owner_user_id
    counts = {}
    for model, predicate in _targets(owner, portfolio.id):
        counts[model.__tablename__] = int(await session.scalar(
            select(func.count()).select_from(model).where(predicate)
        ) or 0)
    cash_by_currency = {
        currency: str(amount)
        for currency, amount in (await session.execute(
            select(CashLedgerEntry.currency, func.sum(CashLedgerEntry.amount))
            .where(CashLedgerEntry.portfolio_id == portfolio.id)
            .group_by(CashLedgerEntry.currency)
        )).all()
    }
    return CapitalResetSummary(
        owner_user_id=owner,
        portfolio_id=str(portfolio.id),
        portfolio_name=portfolio.name,
        currency=portfolio.base_currency,
        previous_initial_capital=str(portfolio.initial_capital),
        opening_cash=str(RESET_CAPITAL),
        cash_by_currency=cash_by_currency,
        rows_to_delete=counts,
    )


async def preview_capital_reset(
    session: AsyncSession,
    owner_user_id: str,
    *,
    expected_portfolio_id: UUID | None = None,
) -> CapitalResetSummary:
    """Read-only count of exactly the owner's Capital records to be removed."""
    portfolio = await _portfolio(session, owner_user_id, expected_portfolio_id=expected_portfolio_id)
    return await _summary(session, portfolio)


def _json_value(value):
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"Unsupported backup value: {type(value).__name__}")


async def export_reset_state(
    session: AsyncSession,
    portfolio: Portfolio,
    *,
    reset_id: UUID,
    summary: CapitalResetSummary,
) -> dict:
    """Export full row values while reset's owner and portfolio locks are held."""
    tables = {}
    for model, predicate in _targets(portfolio.owner_user_id, portfolio.id):
        rows = (await session.execute(select(model.__table__).where(predicate))).mappings().all()
        tables[model.__tablename__] = [dict(row) for row in rows]
    portfolio_row = (await session.execute(
        select(Portfolio.__table__).where(Portfolio.id == portfolio.id)
    )).mappings().one()
    return {
        "format": "capital-reset-backup-v1",
        "reset_id": str(reset_id),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary.to_dict(),
        "portfolio": dict(portfolio_row),
        "tables": tables,
    }


def write_private_backup(path: Path, data: dict) -> None:
    """Never overwrite a previous backup, and grant read/write only to owner."""
    contents = json.dumps(data, default=_json_value, indent=2, sort_keys=True) + "\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        handle.write(contents)
        handle.flush()
        os.fsync(handle.fileno())


async def reset_capital(
    session: AsyncSession,
    owner_user_id: str,
    *,
    expected_portfolio_id: UUID,
    backup_path: Path,
    now: datetime | None = None,
) -> CapitalResetSummary:
    """Reset inside the caller's transaction; commit/rollback is their decision.

    A private full-row backup is mandatory and is fsynced before any deletion.
    A failed deletion or later failure leaves all database records unchanged on
    transaction rollback. The backup remains available for inspection.
    """
    if not session.in_transaction():
        raise CapitalResetError("Capital reset must run inside an explicit transaction.")
    portfolio = await _portfolio(
        session, owner_user_id, expected_portfolio_id=expected_portfolio_id, lock=True
    )
    summary = await _summary(session, portfolio)
    reset_id = uuid4()
    backup = await export_reset_state(session, portfolio, reset_id=reset_id, summary=summary)
    write_private_backup(backup_path, backup)
    for model, predicate in _targets(owner_user_id, portfolio.id):
        await session.execute(delete(model).where(predicate).execution_options(synchronize_session=False))
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    portfolio.initial_capital = RESET_CAPITAL
    session.add(CashLedgerEntry(
        portfolio_id=portfolio.id,
        entry_date=now.date(),
        amount=RESET_CAPITAL,
        currency="USD",
        entry_type="initial_capital",
        platform="paper",
        description="Fresh $10,000 Capital paper-testing balance after an owner-requested reset.",
        source_reference=f"capital_reset:{reset_id}",
        idempotency_key=f"capital-reset:{reset_id}",
    ))
    session.add(SystemLogEntry(
        owner_user_id=owner_user_id,
        level="info",
        category="portfolio",
        event="capital_reset",
        message="Capital trading history reset; opening paper cash is $10,000.00.",
        context={"reset_id": str(reset_id), "portfolio_id": str(portfolio.id),
                 "deleted_rows": summary.rows_to_delete, "opening_cash": str(RESET_CAPITAL)},
    ))
    await session.flush()
    return CapitalResetSummary(**{
        **summary.to_dict(), "executed": True, "reset_id": str(reset_id),
        "backup_path": str(backup_path.resolve()),
    })

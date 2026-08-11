import calendar
import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.api.schemas.reporting import (
    MonthlyReportMemo,
    MonthlyReportMetric,
    MonthlyReportPosition,
    MonthlyReportResponse,
)
from app.models import CashLedgerEntry, Trade
from app.services.portfolio.calculations import percent
from app.services.portfolio.operating_core import get_dashboard
from app.services.ticker_intelligence.analysis import list_recent_ticker_memos
from app.services.ticker_intelligence.ml_training import (
    list_predictive_model_comparison,
)

logger = logging.getLogger(__name__)


async def build_monthly_report(
    session: AsyncSession,
    user: AuthenticatedUser,
    year: int | None = None,
    month: int | None = None,
) -> MonthlyReportResponse:
    today = date.today()
    report_year = year or today.year
    report_month = month or today.month
    period_start = date(report_year, report_month, 1)
    period_end = _next_month(period_start)

    dashboard = await get_dashboard(session, user)
    monthly_cash_flow = await _monthly_cash_flow(
        session, dashboard.portfolio.id, period_start, period_end
    )
    monthly_trade_count = await _monthly_trade_count(
        session, dashboard.portfolio.id, period_start, period_end
    )
    memos = [
        memo
        for memo in await list_recent_ticker_memos(session, user, limit=50)
        if period_start <= memo.memo_date < period_end
    ]
    model_rows = await list_predictive_model_comparison(session, limit=5)
    risk_warnings = [
        check.message for check in dashboard.risk_checks if not check.passed
    ]

    top_positions = [
        MonthlyReportPosition(
            ticker=position.instrument.ticker,
            name=position.instrument.name,
            asset_class=position.instrument.asset_class,
            market_value=position.market_value,
            portfolio_weight_pct=percent(position.market_value, dashboard.nav),
            unrealized_pnl=position.unrealized_pnl,
        )
        for position in sorted(
            dashboard.positions,
            key=lambda item: item.market_value,
            reverse=True,
        )[:8]
    ]
    recent_memos = [
        MonthlyReportMemo(
            ticker=memo.ticker,
            memo_date=memo.memo_date.isoformat(),
            classification=memo.classification,
            action=memo.action,
            composite_score=memo.composite_score,
        )
        for memo in memos[:10]
    ]
    month_label = f"{calendar.month_name[report_month]} {report_year}"

    logger.info(
        "monthly_report_generated",
        extra={
            "month": month_label,
            "owner_user_id": user.id,
            "nav": str(dashboard.nav),
            "trade_count": monthly_trade_count,
            "memo_count": len(memos),
            "risk_warning_count": len(risk_warnings),
        },
    )

    return MonthlyReportResponse(
        month=month_label,
        generated_at=datetime.now(timezone.utc),
        portfolio_name=dashboard.portfolio.name,
        nav=dashboard.nav,
        cash_balance=dashboard.cash_balance,
        invested_value=dashboard.invested_value,
        monthly_cash_flow=monthly_cash_flow,
        monthly_trade_count=monthly_trade_count,
        monthly_memo_count=len(memos),
        risk_warning_count=len(risk_warnings),
        metrics=[
            MonthlyReportMetric(label="NAV", value=f"{dashboard.nav}"),
            MonthlyReportMetric(label="Cash", value=f"{dashboard.cash_balance}"),
            MonthlyReportMetric(label="Invested", value=f"{dashboard.invested_value}"),
            MonthlyReportMetric(
                label="Open positions", value=str(dashboard.open_position_count)
            ),
            MonthlyReportMetric(label="Risk warnings", value=str(len(risk_warnings))),
        ],
        top_positions=top_positions,
        recent_memos=recent_memos,
        risk_warnings=risk_warnings,
        model_registry_summary=[
            MonthlyReportMetric(
                label=row.model_version,
                value=(
                    f"{row.validation_directional_accuracy} direction accuracy"
                    if row.validation_directional_accuracy is not None
                    else "validation pending"
                ),
            )
            for row in model_rows
        ],
        commentary=_monthly_commentary(
            month_label=month_label,
            nav=dashboard.nav,
            cash_balance=dashboard.cash_balance,
            invested_value=dashboard.invested_value,
            trade_count=monthly_trade_count,
            memo_count=len(memos),
            risk_warning_count=len(risk_warnings),
        ),
    )


async def _monthly_cash_flow(
    session: AsyncSession,
    portfolio_id,
    period_start: date,
    period_end: date,
) -> Decimal:
    value = await session.scalar(
        select(func.sum(CashLedgerEntry.amount)).where(
            CashLedgerEntry.portfolio_id == portfolio_id,
            CashLedgerEntry.entry_date >= period_start,
            CashLedgerEntry.entry_date < period_end,
        )
    )
    return value or Decimal("0")


async def _monthly_trade_count(
    session: AsyncSession,
    portfolio_id,
    period_start: date,
    period_end: date,
) -> int:
    value = await session.scalar(
        select(func.count(Trade.id)).where(
            Trade.portfolio_id == portfolio_id,
            Trade.trade_date
            >= datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc),
            Trade.trade_date
            < datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc),
        )
    )
    return int(value or 0)


def _monthly_commentary(
    *,
    month_label: str,
    nav: Decimal,
    cash_balance: Decimal,
    invested_value: Decimal,
    trade_count: int,
    memo_count: int,
    risk_warning_count: int,
) -> str:
    risk_text = (
        "Risk checks are clear."
        if risk_warning_count == 0
        else f"{risk_warning_count} risk warning(s) require review."
    )
    return (
        f"{month_label} report: NAV is {nav}, with {cash_balance} in cash and "
        f"{invested_value} invested. The fund recorded {trade_count} trade(s) and "
        f"{memo_count} ticker memo(s) during the month. {risk_text}"
    )


def _next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)

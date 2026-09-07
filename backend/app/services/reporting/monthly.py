import calendar
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.reporting import (
    MonthlyReportAttributionRow,
    MonthlyReportAttributionSummary,
    MonthlyReportMemo,
    MonthlyReportMetric,
    MonthlyReportPosition,
    MonthlyReportResponse,
    ReportBenchmarkSummary,
    ReportCompactSection,
    ReportKind,
    ReportSnapshotResponse,
)
from app.core.auth import AuthenticatedUser
from app.models import (
    CashLedgerEntry,
    Instrument,
    MarketPriceBar,
    Opportunity,
    ReportSnapshot,
    StrategyPod,
    StrategyPodSnapshot,
    TickerMemo,
    Trade,
)
from app.services.attribution.performance import build_attribution_report
from app.services.portfolio.calculations import percent
from app.services.portfolio.operating_core import get_dashboard
from app.services.ticker_intelligence.ml_training import (
    list_predictive_model_comparison,
)

logger = logging.getLogger(__name__)

REPORT_KINDS: set[str] = {"daily", "weekly", "monthly", "quarterly", "annual"}
BENCHMARK_CANDIDATES = (
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("VOO", "Vanguard S&P 500 ETF"),
    ("IVV", "iShares Core S&P 500 ETF"),
    ("QQQ", "Invesco QQQ Trust"),
)
COMPACT_ITEM_LIMIT = 4


@dataclass(frozen=True)
class ReportPeriod:
    kind: ReportKind
    key: str
    label: str
    title: str
    start: date
    end_exclusive: date
    display_end: date
    reporting_mode: str


async def build_monthly_report(
    session: AsyncSession,
    user: AuthenticatedUser,
    year: int | None = None,
    month: int | None = None,
) -> MonthlyReportResponse:
    return await build_report(
        session,
        user,
        report_kind="monthly",
        year=year,
        month=month,
    )


async def build_report(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    report_kind: str = "monthly",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    as_of: date | None = None,
) -> MonthlyReportResponse:
    period = _resolve_period(
        report_kind,
        year=year,
        month=month,
        quarter=quarter,
        as_of=as_of,
    )

    dashboard = await get_dashboard(session, user)
    period_cash_flow = await _period_cash_flow(
        session, dashboard.portfolio.id, period.start, period.end_exclusive
    )
    period_trade_count = await _period_trade_count(
        session, dashboard.portfolio.id, period.start, period.end_exclusive
    )
    memos = await _period_memos(session, user, period.start, period.end_exclusive)
    model_rows = await list_predictive_model_comparison(session, limit=5)
    attribution_report = await build_attribution_report(
        session,
        user,
        period_start=period.start,
        period_end=period.end_exclusive,
    )
    attribution = _monthly_attribution_summary(attribution_report)
    cumulative_report = await build_attribution_report(session, user)
    cumulative_return_pct = cumulative_report.summary.total_return_pct
    benchmark_summary = await _benchmark_summary(
        session,
        period=period,
        fund_period_return_pct=(
            attribution.total_return_pct if attribution is not None else None
        ),
    )
    opportunity_counts = await _opportunity_counts(session, user)
    strategy_snapshot_count = await _strategy_snapshot_count(
        session,
        user,
        period.start,
        period.end_exclusive,
    )
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
            ticker=memo.instrument.ticker,
            memo_date=memo.memo_date.isoformat(),
            classification=memo.classification,
            action=_optional_string((memo.scores or {}).get("action")),
            composite_score=_optional_decimal((memo.scores or {}).get("composite_score")),
        )
        for memo in memos[:10]
    ]

    logger.info(
        "report_generated",
        extra={
            "report_kind": period.kind,
            "period": period.label,
            "owner_user_id": user.id,
            "nav": str(dashboard.nav),
            "trade_count": period_trade_count,
            "memo_count": len(memos),
            "risk_warning_count": len(risk_warnings),
        },
    )

    commentary = _report_commentary(
        period=period,
        nav=dashboard.nav,
        cash_balance=dashboard.cash_balance,
        invested_value=dashboard.invested_value,
        trade_count=period_trade_count,
        memo_count=len(memos),
        risk_warning_count=len(risk_warnings),
        attribution=attribution,
        benchmark_summary=benchmark_summary,
    )

    return MonthlyReportResponse(
        report_kind=period.kind,
        report_title=period.title,
        period_key=period.key,
        period_label=period.label,
        month=period.label,
        portfolio_id=dashboard.portfolio.id,
        period_start=period.start,
        period_end=period.display_end,
        reporting_mode=period.reporting_mode,
        generated_at=datetime.now(timezone.utc),
        portfolio_name=dashboard.portfolio.name,
        nav=dashboard.nav,
        cash_balance=dashboard.cash_balance,
        invested_value=dashboard.invested_value,
        period_cash_flow=period_cash_flow,
        period_trade_count=period_trade_count,
        period_memo_count=len(memos),
        monthly_cash_flow=period_cash_flow,
        monthly_trade_count=period_trade_count,
        monthly_memo_count=len(memos),
        risk_warning_count=len(risk_warnings),
        cumulative_return_pct=cumulative_return_pct,
        metrics=[
            MonthlyReportMetric(label="NAV", value=f"{dashboard.nav}"),
            MonthlyReportMetric(label="Cash", value=f"{dashboard.cash_balance}"),
            MonthlyReportMetric(label="Invested", value=f"{dashboard.invested_value}"),
            MonthlyReportMetric(
                label="Open positions", value=str(dashboard.open_position_count)
            ),
            MonthlyReportMetric(
                label="Period trades", value=str(period_trade_count)
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
        research_summary=_research_summary(memos),
        attribution=attribution,
        attribution_detail=attribution_report,
        benchmark_summary=benchmark_summary,
        ai_overview=_ai_overview_section(
            attribution=attribution,
            benchmark_summary=benchmark_summary,
            risk_warning_count=len(risk_warnings),
            trade_count=period_trade_count,
            memo_count=len(memos),
        ),
        portfolio_positioning=_portfolio_positioning_section(
            nav=dashboard.nav,
            cash_balance=dashboard.cash_balance,
            invested_value=dashboard.invested_value,
            top_positions=top_positions,
            attribution_report=attribution_report,
        ),
        market_commentary=_market_commentary_section(
            attribution=attribution,
            benchmark_summary=benchmark_summary,
            risk_warning_count=len(risk_warnings),
        ),
        strategy_changes=_strategy_changes_section(
            period_trade_count=period_trade_count,
            risk_warning_count=len(risk_warnings),
            model_count=len(model_rows),
            strategy_snapshot_count=strategy_snapshot_count,
        ),
        research_pipeline=_research_pipeline_section(
            memos=memos,
            opportunity_counts=opportunity_counts,
        ),
        commentary=commentary,
    )


async def save_report_snapshot(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    report_kind: str = "monthly",
    year: int | None = None,
    month: int | None = None,
    quarter: int | None = None,
    as_of: date | None = None,
) -> ReportSnapshotResponse:
    report = await build_report(
        session,
        user,
        report_kind=report_kind,
        year=year,
        month=month,
        quarter=quarter,
        as_of=as_of,
    )
    payload = report.model_dump(mode="json")
    payload["payload_version"] = 1
    snapshot = ReportSnapshot(
        owner_user_id=user.id,
        portfolio_id=report.portfolio_id,
        report_kind=report.report_kind,
        period_start=report.period_start,
        period_end=report.period_end,
        period_label=report.period_label,
        title=f"{report.portfolio_name} - {report.period_label} {report.report_title}",
        nav=report.nav,
        return_pct=(
            report.attribution.total_return_pct
            if report.attribution is not None
            else None
        ),
        payload=payload,
    )
    session.add(snapshot)
    await session.commit()
    await session.refresh(snapshot)
    return _snapshot_response(snapshot, include_payload=True)


async def list_report_snapshots(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 20,
) -> list[ReportSnapshotResponse]:
    rows = await session.scalars(
        select(ReportSnapshot)
        .where(ReportSnapshot.owner_user_id == user.id)
        .order_by(ReportSnapshot.created_at.desc())
        .limit(limit)
    )
    return [_snapshot_response(snapshot, include_payload=False) for snapshot in rows]


async def get_report_snapshot(
    session: AsyncSession,
    user: AuthenticatedUser,
    snapshot_id: UUID,
) -> ReportSnapshotResponse | None:
    snapshot = await session.scalar(
        select(ReportSnapshot).where(
            ReportSnapshot.id == snapshot_id,
            ReportSnapshot.owner_user_id == user.id,
        )
    )
    if snapshot is None:
        return None
    return _snapshot_response(snapshot, include_payload=True)


async def update_report_snapshot(
    session: AsyncSession,
    user: AuthenticatedUser,
    snapshot_id: UUID,
    title: str,
) -> ReportSnapshotResponse | None:
    snapshot = await session.scalar(
        select(ReportSnapshot).where(
            ReportSnapshot.id == snapshot_id,
            ReportSnapshot.owner_user_id == user.id,
        )
    )
    if snapshot is None:
        return None
    snapshot.title = title.strip()
    await session.commit()
    await session.refresh(snapshot)
    return _snapshot_response(snapshot, include_payload=True)


async def delete_report_snapshot(
    session: AsyncSession,
    user: AuthenticatedUser,
    snapshot_id: UUID,
) -> bool:
    snapshot = await session.scalar(
        select(ReportSnapshot).where(
            ReportSnapshot.id == snapshot_id,
            ReportSnapshot.owner_user_id == user.id,
        )
    )
    if snapshot is None:
        return False
    await session.delete(snapshot)
    await session.commit()
    return True


async def _period_cash_flow(
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


async def _period_trade_count(
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


async def _period_memos(
    session: AsyncSession,
    user: AuthenticatedUser,
    period_start: date,
    period_end: date,
) -> list[TickerMemo]:
    return list(
        await session.scalars(
            select(TickerMemo)
            .options(selectinload(TickerMemo.instrument))
            .where(
                TickerMemo.owner_user_id == user.id,
                TickerMemo.memo_date >= period_start,
                TickerMemo.memo_date < period_end,
            )
            .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
        )
    )


async def _opportunity_counts(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> dict[str, int]:
    rows = await session.execute(
        select(Opportunity.status, func.count(Opportunity.id))
        .where(Opportunity.owner_user_id == user.id)
        .group_by(Opportunity.status)
    )
    return {str(status): int(count or 0) for status, count in rows.all()}


async def _strategy_snapshot_count(
    session: AsyncSession,
    user: AuthenticatedUser,
    period_start: date,
    period_end: date,
) -> int:
    value = await session.scalar(
        select(func.count(StrategyPodSnapshot.id))
        .join(StrategyPod, StrategyPod.id == StrategyPodSnapshot.strategy_pod_id)
        .where(
            StrategyPod.owner_user_id == user.id,
            StrategyPodSnapshot.captured_at
            >= datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc),
            StrategyPodSnapshot.captured_at
            < datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc),
        )
    )
    return int(value or 0)


async def _benchmark_summary(
    session: AsyncSession,
    *,
    period: ReportPeriod,
    fund_period_return_pct: Decimal | None,
) -> ReportBenchmarkSummary:
    benchmark = await _benchmark_instrument(session)
    if benchmark is None:
        return ReportBenchmarkSummary(
            benchmark_symbol="SPY",
            benchmark_name="S&P 500 proxy",
            status="unavailable",
            notes=[
                "No local benchmark price bars are available yet; benchmark comparison is waiting on market-data history."
            ],
        )

    period_return = await _price_return_pct(
        session,
        benchmark.id,
        start=period.start,
        end=period.display_end,
    )
    cumulative_return = await _price_return_pct(
        session,
        benchmark.id,
        start=None,
        end=period.display_end,
    )
    relative_return = (
        fund_period_return_pct - period_return
        if fund_period_return_pct is not None and period_return is not None
        else None
    )
    notes = [
        "Benchmark uses locally stored daily price bars; no external vendor call is made during report generation."
    ]
    status = "available" if period_return is not None else "partial"
    if period_return is None:
        notes.append("Benchmark bars do not cover this report period yet.")

    return ReportBenchmarkSummary(
        benchmark_symbol=benchmark.ticker,
        benchmark_name=benchmark.name,
        period_return_pct=period_return,
        cumulative_return_pct=cumulative_return,
        relative_return_pct=relative_return,
        status=status,
        notes=notes,
    )


async def _benchmark_instrument(session: AsyncSession) -> Instrument | None:
    for ticker, _name in BENCHMARK_CANDIDATES:
        instrument = await session.scalar(
            select(Instrument).where(Instrument.ticker == ticker).limit(1)
        )
        if instrument is not None:
            return instrument
    return None


async def _price_return_pct(
    session: AsyncSession,
    instrument_id,
    *,
    start: date | None,
    end: date,
) -> Decimal | None:
    if start is not None and start > end:
        return None

    start_query = select(MarketPriceBar).where(
        MarketPriceBar.instrument_id == instrument_id,
        MarketPriceBar.bar_date <= end,
    )
    if start is not None:
        start_query = start_query.where(MarketPriceBar.bar_date >= start)
    start_bar = await session.scalar(start_query.order_by(MarketPriceBar.bar_date.asc()).limit(1))
    end_bar = await session.scalar(
        select(MarketPriceBar)
        .where(
            MarketPriceBar.instrument_id == instrument_id,
            MarketPriceBar.bar_date <= end,
        )
        .order_by(MarketPriceBar.bar_date.desc())
        .limit(1)
    )
    if start_bar is None or end_bar is None:
        return None

    start_price = start_bar.adjusted_close_price or start_bar.close_price
    end_price = end_bar.adjusted_close_price or end_bar.close_price
    if start_price <= 0:
        return None
    return percent(end_price - start_price, start_price)


def _portfolio_positioning_section(
    *,
    nav: Decimal,
    cash_balance: Decimal,
    invested_value: Decimal,
    top_positions: list[MonthlyReportPosition],
    attribution_report,
) -> ReportCompactSection:
    top_position = top_positions[0] if top_positions else None
    top_sector = attribution_report.by_sector[0] if attribution_report.by_sector else None
    items = [
        MonthlyReportMetric(label="Cash weight", value=f"{percent(cash_balance, nav)}%"),
        MonthlyReportMetric(
            label="Invested weight", value=f"{percent(invested_value, nav)}%"
        ),
        MonthlyReportMetric(
            label="Largest position",
            value=(
                f"{top_position.ticker} / {top_position.portfolio_weight_pct}%"
                if top_position is not None
                else "-"
            ),
        ),
    ]
    if top_sector is not None:
        items.append(
            MonthlyReportMetric(
                label="Largest sector",
                value=f"{top_sector.name} / {top_sector.exposure_pct}%",
            )
        )
    return ReportCompactSection(
        title="Portfolio Positioning",
        items=items[:COMPACT_ITEM_LIMIT],
        note="Current positioning snapshot; historical exposure snapshots can deepen this later.",
    )


def _market_commentary_section(
    *,
    attribution: MonthlyReportAttributionSummary | None,
    benchmark_summary: ReportBenchmarkSummary | None,
    risk_warning_count: int,
) -> ReportCompactSection:
    items = [
        MonthlyReportMetric(
            label="Fund return",
            value=f"{attribution.total_return_pct}%" if attribution is not None else "-",
        ),
        MonthlyReportMetric(
            label="Benchmark",
            value=(
                f"{benchmark_summary.period_return_pct}%"
                if benchmark_summary is not None
                and benchmark_summary.period_return_pct is not None
                else "-"
            ),
        ),
        MonthlyReportMetric(
            label="Relative",
            value=(
                f"{benchmark_summary.relative_return_pct}%"
                if benchmark_summary is not None
                and benchmark_summary.relative_return_pct is not None
                else "-"
            ),
        ),
        MonthlyReportMetric(
            label="Risk tape",
            value="Clear" if risk_warning_count == 0 else f"{risk_warning_count} warning(s)",
        ),
    ]
    note = None
    if benchmark_summary is not None and benchmark_summary.notes:
        note = benchmark_summary.notes[0]
    return ReportCompactSection(
        title="Market Commentary",
        items=items,
        note=note,
    )


def _strategy_changes_section(
    *,
    period_trade_count: int,
    risk_warning_count: int,
    model_count: int,
    strategy_snapshot_count: int,
) -> ReportCompactSection:
    items = [
        MonthlyReportMetric(label="Trade decisions", value=str(period_trade_count)),
        MonthlyReportMetric(label="Risk exceptions", value=str(risk_warning_count)),
        MonthlyReportMetric(label="Pod reviews", value=str(strategy_snapshot_count)),
        MonthlyReportMetric(label="Models tracked", value=str(model_count)),
    ]
    changed = any(
        value > 0 for value in (period_trade_count, risk_warning_count, strategy_snapshot_count)
    )
    return ReportCompactSection(
        title="Strategy Changes",
        items=items,
        note=(
            "Recorded changes exist for this period."
            if changed
            else "No recorded strategy changes this period."
        ),
    )


def _research_pipeline_section(
    *,
    memos: list[TickerMemo],
    opportunity_counts: dict[str, int],
) -> ReportCompactSection:
    active_statuses = {
        "discovered",
        "screening",
        "research",
        "parked",
        "candidate",
        "investment_candidate",
        "approved",
    }
    active_count = sum(
        count
        for status, count in opportunity_counts.items()
        if status in active_statuses
    )
    items = [
        MonthlyReportMetric(label="Period memos", value=str(len(memos))),
        MonthlyReportMetric(label="Active opportunities", value=str(active_count)),
        MonthlyReportMetric(
            label="In research", value=str(opportunity_counts.get("research", 0))
        ),
        MonthlyReportMetric(
            label="Parked", value=str(opportunity_counts.get("parked", 0))
        ),
    ]
    classifications = Counter(memo.classification or "unclassified" for memo in memos)
    note = None
    if classifications:
        label, count = classifications.most_common(1)[0]
        note = f"Most common memo type: {_format_label(label)} ({count})."
    return ReportCompactSection(
        title="Current Research Pipeline",
        items=items,
        note=note or "No new memo cluster this period.",
    )


def _ai_overview_section(
    *,
    attribution: MonthlyReportAttributionSummary | None,
    benchmark_summary: ReportBenchmarkSummary | None,
    risk_warning_count: int,
    trade_count: int,
    memo_count: int,
) -> ReportCompactSection:
    period_return = attribution.total_return_pct if attribution is not None else None
    benchmark_return = (
        benchmark_summary.period_return_pct
        if benchmark_summary is not None
        else None
    )
    relative_return = (
        benchmark_summary.relative_return_pct
        if benchmark_summary is not None
        else None
    )

    if period_return is None:
        driver = "Performance attribution is still forming."
    elif period_return > Decimal("0"):
        driver = "Positive period P/L is the main headline."
    elif period_return < Decimal("0"):
        driver = "Drawdown control is the main headline."
    else:
        driver = "Flat performance keeps risk and research quality in focus."

    benchmark_text = "Benchmark comparison is pending."
    if relative_return is not None:
        benchmark_text = (
            "Ahead of benchmark"
            if relative_return > Decimal("0")
            else "Behind benchmark"
            if relative_return < Decimal("0")
            else "In line with benchmark"
        )

    risk_text = "No active risk warnings" if risk_warning_count == 0 else "Risk review needed"
    activity_text = (
        "Research-led"
        if memo_count > trade_count
        else "Execution-led"
        if trade_count > memo_count
        else "Balanced activity"
    )
    data_confidence = (
        "Partial"
        if benchmark_return is None
        else "Caution"
        if risk_warning_count > 0
        else "Normal"
    )

    return ReportCompactSection(
        title="AI Overview",
        items=[
            MonthlyReportMetric(label="Main read", value=driver),
            MonthlyReportMetric(label="Benchmark read", value=benchmark_text),
            MonthlyReportMetric(label="Risk read", value=risk_text),
            MonthlyReportMetric(label="Activity read", value=activity_text),
        ],
        note=(
            f"Data confidence: {data_confidence}. This overview is generated from "
            "verified ledger, position, attribution, benchmark, and research fields."
        ),
    )


def _report_commentary(
    *,
    period: ReportPeriod,
    nav: Decimal,
    cash_balance: Decimal,
    invested_value: Decimal,
    trade_count: int,
    memo_count: int,
    risk_warning_count: int,
    attribution: MonthlyReportAttributionSummary | None,
    benchmark_summary: ReportBenchmarkSummary | None,
) -> str:
    risk_text = (
        "Risk checks are clear."
        if risk_warning_count == 0
        else f"{risk_warning_count} risk warning(s) require review."
    )
    attribution_text = ""
    if attribution is not None:
        attribution_text = (
            f" Recorded net P/L is {attribution.net_pnl} "
            f"({attribution.total_return_pct}% period return on the current capital base), "
            f"with {attribution.total_fees} in fees."
        )
    benchmark_text = ""
    if benchmark_summary is not None and benchmark_summary.period_return_pct is not None:
        benchmark_text = (
            f" The {benchmark_summary.benchmark_symbol} benchmark returned "
            f"{benchmark_summary.period_return_pct}% over the same local-data window."
        )
    return (
        f"{period.label} {period.title.lower()}: NAV is {nav}, with {cash_balance} "
        f"in cash and {invested_value} invested. The fund recorded {trade_count} "
        f"trade(s) and {memo_count} ticker memo(s) during the period."
        f"{attribution_text}{benchmark_text} {risk_text}"
    )


def _research_summary(memos) -> list[MonthlyReportMetric]:
    if not memos:
        return []
    classifications = Counter(memo.classification or "unclassified" for memo in memos)
    actions = Counter(
        _optional_string((memo.scores or {}).get("action")) or "no action"
        for memo in memos
    )
    rows = [
        MonthlyReportMetric(
            label=f"{_format_label(label)} memos",
            value=str(count),
        )
        for label, count in classifications.most_common(4)
    ]
    rows.extend(
        MonthlyReportMetric(
            label=f"{_format_label(label)} actions",
            value=str(count),
        )
        for label, count in actions.most_common(4)
    )
    return rows[:6]


def _monthly_attribution_summary(report) -> MonthlyReportAttributionSummary:
    rows = [row for row in report.by_ticker if row.net_pnl != Decimal("0")]
    contributors = sorted(rows, key=lambda row: row.net_pnl, reverse=True)
    detractors = sorted(rows, key=lambda row: row.net_pnl)
    return MonthlyReportAttributionSummary(
        net_pnl=report.summary.net_pnl,
        total_return_pct=report.summary.total_return_pct,
        total_fees=report.summary.total_fees,
        turnover_pct=report.summary.turnover_pct,
        hit_rate_pct=report.summary.hit_rate_pct,
        top_contributors=[
            _attribution_row_response(row)
            for row in contributors
            if row.net_pnl > Decimal("0")
        ][:5],
        top_detractors=[
            _attribution_row_response(row)
            for row in detractors
            if row.net_pnl < Decimal("0")
        ][:5],
        notes=report.notes,
    )


def _attribution_row_response(row) -> MonthlyReportAttributionRow:
    return MonthlyReportAttributionRow(
        ticker=row.instrument.ticker,
        name=row.instrument.name,
        net_pnl=row.net_pnl,
        contribution_pct_nav=row.contribution_pct_nav,
        portfolio_weight_pct=row.portfolio_weight_pct,
    )


def _snapshot_response(
    snapshot: ReportSnapshot,
    *,
    include_payload: bool,
) -> ReportSnapshotResponse:
    payload = snapshot.payload if include_payload else None
    return ReportSnapshotResponse(
        id=snapshot.id,
        report_kind=snapshot.report_kind,
        period_label=snapshot.period_label,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        title=snapshot.title,
        nav=snapshot.nav,
        return_pct=snapshot.return_pct,
        created_at=snapshot.created_at,
        updated_at=snapshot.updated_at,
        payload_version=_payload_version(snapshot.payload),
        payload=payload,
    )


def _resolve_period(
    report_kind: str,
    *,
    year: int | None,
    month: int | None,
    quarter: int | None,
    as_of: date | None,
) -> ReportPeriod:
    kind = _normalize_report_kind(report_kind)
    today = date.today()
    anchor = as_of or today

    if kind == "daily":
        start = anchor
        end = start + timedelta(days=1)
        key = start.isoformat()
        label = _format_date_label(start)
        title = "Daily Internal Report"
    elif kind == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
        key = f"{start.isoformat()}-week"
        label = f"Week of {_format_date_label(start)}"
        title = "Weekly Investment Review"
    elif kind == "monthly":
        report_year = year or today.year
        report_month = month or today.month
        start = date(report_year, report_month, 1)
        end = _add_months(start, 1)
        key = f"{report_year}-{report_month:02d}"
        label = f"{calendar.month_name[report_month]} {report_year}"
        title = "Monthly Investor Letter"
    elif kind == "quarterly":
        report_year = year or today.year
        report_quarter = quarter or ((today.month - 1) // 3) + 1
        start = date(report_year, ((report_quarter - 1) * 3) + 1, 1)
        end = _add_months(start, 3)
        key = f"{report_year}-Q{report_quarter}"
        label = f"Q{report_quarter} {report_year}"
        title = "Quarterly Strategy Review"
    else:
        report_year = year or today.year
        start = date(report_year, 1, 1)
        end = date(report_year + 1, 1, 1)
        key = str(report_year)
        label = str(report_year)
        title = "Annual Report"

    period_last_day = end - timedelta(days=1)
    if today < start:
        display_end = period_last_day
        reporting_mode = "scheduled_period"
    elif today <= period_last_day:
        display_end = today
        reporting_mode = _to_date_mode(kind)
    else:
        display_end = period_last_day
        reporting_mode = _full_period_mode(kind)

    return ReportPeriod(
        kind=kind,
        key=key,
        label=label,
        title=title,
        start=start,
        end_exclusive=end,
        display_end=display_end,
        reporting_mode=reporting_mode,
    )


def _normalize_report_kind(value: str) -> ReportKind:
    normalized = value.strip().lower()
    if normalized not in REPORT_KINDS:
        raise ValueError(f"Unsupported report kind: {value}")
    return normalized  # type: ignore[return-value]


def _payload_version(payload: dict | None) -> int:
    if not payload:
        return 1
    value = payload.get("payload_version")
    try:
        version = int(value)
    except (TypeError, ValueError):
        return 1
    return max(version, 1)


def _to_date_mode(kind: ReportKind) -> str:
    return {
        "daily": "intraday",
        "weekly": "week_to_date",
        "monthly": "month_to_date",
        "quarterly": "quarter_to_date",
        "annual": "year_to_date",
    }[kind]


def _full_period_mode(kind: ReportKind) -> str:
    return {
        "daily": "full_day",
        "weekly": "full_week",
        "monthly": "full_month",
        "quarterly": "full_quarter",
        "annual": "full_year",
    }[kind]


def _format_date_label(value: date) -> str:
    return value.strftime("%b %d, %Y").replace(" 0", " ")


def _format_label(value: str) -> str:
    return value.replace("_", " ").title()


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = (month_index % 12) + 1
    return date(year, month, 1)

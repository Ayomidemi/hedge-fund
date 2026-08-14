from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.research_lab import (
    ResearchExperimentRecordResponse,
    ResearchLabOverviewResponse,
    ResearchNoteCreate,
    ResearchNoteResponse,
    SavedBacktestRunResponse,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.models import BacktestRun
from app.services.research_lab.experiments import list_experiments
from app.services.research_lab.lab import build_research_lab_overview
from app.services.research_lab.notes import (
    create_research_note,
    delete_research_note,
    list_research_notes,
)

router = APIRouter(prefix="/research-lab")


@router.get("/overview", response_model=ResearchLabOverviewResponse)
async def read_research_lab_overview(
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ResearchLabOverviewResponse:
    return await build_research_lab_overview(session, user)


@router.get("/experiments", response_model=list[ResearchExperimentRecordResponse])
async def read_research_experiments(
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[ResearchExperimentRecordResponse]:
    experiments = await list_experiments(session, user, limit=limit)
    return [
        ResearchExperimentRecordResponse(
            id=experiment.id,
            name=experiment.name,
            experiment_type=experiment.experiment_type,
            status=experiment.status,
            hypothesis=experiment.hypothesis,
            parameters=experiment.parameters or {},
            metrics=experiment.metrics or {},
            primary_metric=experiment.primary_metric,
            primary_value=experiment.primary_value,
            model_version_id=experiment.model_version_id,
            backtest_run_id=experiment.backtest_run_id,
            created_at=experiment.created_at,
        )
        for experiment in experiments
    ]


@router.get("/backtests", response_model=list[SavedBacktestRunResponse])
async def read_saved_backtests(
    limit: int = Query(default=25, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[SavedBacktestRunResponse]:
    runs = await session.scalars(
        select(BacktestRun)
        .where(BacktestRun.owner_user_id == user.id)
        .order_by(BacktestRun.created_at.desc())
        .limit(limit)
    )
    return [_saved_backtest_response(run, include_periods=False) for run in runs]


@router.get("/backtests/{backtest_id}", response_model=SavedBacktestRunResponse)
async def read_saved_backtest(
    backtest_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> SavedBacktestRunResponse:
    run = await session.scalar(
        select(BacktestRun)
        .where(BacktestRun.id == backtest_id)
        .where(BacktestRun.owner_user_id == user.id)
    )
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backtest run not found.",
        )
    return _saved_backtest_response(run, include_periods=True)


@router.get("/notes", response_model=list[ResearchNoteResponse])
async def read_research_notes(
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> list[ResearchNoteResponse]:
    return await list_research_notes(session, user)


@router.post(
    "/notes",
    response_model=ResearchNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    payload: ResearchNoteCreate,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> ResearchNoteResponse:
    return await create_research_note(session, user, payload)


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> None:
    deleted = await delete_research_note(session, user, note_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research note not found.",
        )


def _saved_backtest_response(
    run: BacktestRun,
    *,
    include_periods: bool,
) -> SavedBacktestRunResponse:
    return SavedBacktestRunResponse(
        id=run.id,
        name=run.name,
        status=run.status,
        engine_version=run.engine_version,
        parameters=run.parameters or {},
        start_date=run.start_date,
        end_date=run.end_date,
        horizon_days=run.horizon_days,
        rebalance_count=run.rebalance_count,
        cumulative_return_pct=run.cumulative_return_pct,
        benchmark_return_pct=run.benchmark_return_pct,
        alpha_pct=run.alpha_pct,
        annualized_return_pct=run.annualized_return_pct,
        annualized_volatility_pct=run.annualized_volatility_pct,
        sharpe_ratio=run.sharpe_ratio,
        max_drawdown_pct=run.max_drawdown_pct,
        hit_rate_pct=run.hit_rate_pct,
        turnover_pct=run.turnover_pct,
        cost_drag_pct=run.cost_drag_pct,
        regime_filter_applied=run.regime_filter_applied,
        skipped_by_regime=run.skipped_by_regime,
        created_at=run.created_at,
        periods=list(run.periods or []) if include_periods else [],
        warnings=list(run.warnings or []),
    )

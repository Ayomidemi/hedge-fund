import logging
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.models import ResearchExperiment

logger = logging.getLogger(__name__)


async def record_experiment(
    session: AsyncSession,
    *,
    owner_user_id: str,
    name: str,
    experiment_type: str,
    hypothesis: str,
    parameters: dict[str, Any],
    metrics: dict[str, Any],
    status: str = "completed",
    primary_metric: str | None = None,
    primary_value: Decimal | None = None,
    model_version_id: uuid.UUID | None = None,
    backtest_run_id: uuid.UUID | None = None,
) -> ResearchExperiment:
    experiment = ResearchExperiment(
        owner_user_id=owner_user_id,
        name=name,
        experiment_type=experiment_type,
        status=status,
        hypothesis=hypothesis,
        parameters=parameters,
        metrics=metrics,
        primary_metric=primary_metric,
        primary_value=primary_value,
        model_version_id=model_version_id,
        backtest_run_id=backtest_run_id,
    )
    session.add(experiment)
    await session.flush()
    logger.info(
        "research_experiment_recorded",
        extra={
            "experiment_id": str(experiment.id),
            "experiment_type": experiment_type,
            "owner_user_id": owner_user_id,
        },
    )
    return experiment


async def list_experiments(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 50,
) -> list[ResearchExperiment]:
    return list(
        await session.scalars(
            select(ResearchExperiment)
            .where(ResearchExperiment.owner_user_id == user.id)
            .order_by(ResearchExperiment.created_at.desc())
            .limit(limit)
        )
    )

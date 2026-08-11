import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.research_lab import (
    ResearchActionItemResponse,
    ResearchBacktestResponse,
    ResearchDatasetResponse,
    ResearchExperimentResponse,
    ResearchFeatureSetResponse,
    ResearchLabOverviewResponse,
    ResearchLabSummaryResponse,
    ResearchModelResponse,
    ResearchNotebookResponse,
    ResearchPipelineStageResponse,
    ResearchValidationCheckResponse,
)
from app.core.auth import AuthenticatedUser
from app.models import (
    Instrument,
    MarketPriceBar,
    ModelRecommendation,
    ModelVersion,
    Opportunity,
    TickerFeatureSnapshot,
    TickerMemo,
    TickerTrainingLabel,
)
from app.services.portfolio.operating_core import get_dashboard
from app.services.ticker_intelligence.ml_training import list_predictive_model_comparison

logger = logging.getLogger(__name__)

ACTIVE_OPPORTUNITY_STATUSES = {
    "discovered",
    "screening",
    "research",
    "watchlist",
    "candidate",
    "approved",
    "active_position",
}


async def build_research_lab_overview(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> ResearchLabOverviewResponse:
    dashboard = await get_dashboard(session, user)
    datasets = await _build_datasets(session, user)
    feature_sets = await _build_feature_sets(session)
    notebooks = await _build_notebooks(session, user)
    models = await _build_models(session)
    experiments = await _build_experiments(session)
    backtests = _build_backtests(models, feature_sets)
    active_opportunity_count = await _active_opportunity_count(session, user)
    validation_checks = _build_validation_checks(
        datasets=datasets,
        feature_sets=feature_sets,
        models=models,
        notebooks=notebooks,
    )
    action_items = _build_action_items(
        datasets=datasets,
        feature_sets=feature_sets,
        models=models,
        notebooks=notebooks,
        active_opportunity_count=active_opportunity_count,
    )
    warning_count = len(
        [check for check in validation_checks if check.status in {"warning", "failed"}]
    )

    logger.info(
        "research_lab_overview_generated",
        extra={
            "owner_user_id": user.id,
            "dataset_count": len(datasets),
            "feature_set_count": len(feature_sets),
            "model_count": len(models),
            "notebook_count": len(notebooks),
            "warning_count": warning_count,
        },
    )

    return ResearchLabOverviewResponse(
        generated_at=datetime.now(timezone.utc),
        summary=ResearchLabSummaryResponse(
            portfolio_name=dashboard.portfolio.name,
            nav=dashboard.nav,
            research_memo_count=len(notebooks),
            active_opportunity_count=active_opportunity_count,
            dataset_count=len(datasets),
            feature_set_count=len(feature_sets),
            model_count=len(models),
            backtest_count=len(backtests),
            warning_count=warning_count,
        ),
        pipeline=_build_pipeline(
            memo_count=len(notebooks),
            opportunity_count=active_opportunity_count,
            experiment_count=len(experiments),
            backtest_count=len(backtests),
            model_count=len(models),
        ),
        datasets=datasets,
        feature_sets=feature_sets,
        notebooks=notebooks,
        experiments=experiments,
        backtests=backtests,
        models=models,
        validation_checks=validation_checks,
        action_items=action_items,
        notes=[
            "Research Lab is a live read model over the current research system.",
            "Datasets and models are shared research infrastructure; memos and opportunities are scoped to the signed-in user.",
            "Backtest runs are executable through the ticker-intelligence ML endpoints; persistent run history can be added next.",
        ],
    )


async def _build_datasets(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> list[ResearchDatasetResponse]:
    return [
        ResearchDatasetResponse(
            key="market_price_bars",
            name="Market price bars",
            source="Yahoo / market-data pipeline",
            row_count=await _count(session, MarketPriceBar.id),
            instrument_count=await _count_distinct(session, MarketPriceBar.instrument_id),
            latest_observation=await session.scalar(select(func.max(MarketPriceBar.bar_date))),
            frequency="Daily",
            status=_dataset_status(await _count(session, MarketPriceBar.id)),
            validation_summary="Point-in-time OHLCV rows used for features, labels, regimes, and backtests.",
        ),
        ResearchDatasetResponse(
            key="ticker_feature_snapshots",
            name="Ticker feature snapshots",
            source="Feature engineering pipeline",
            row_count=await _count(session, TickerFeatureSnapshot.id),
            instrument_count=await _count_distinct(
                session, TickerFeatureSnapshot.instrument_id
            ),
            latest_observation=await session.scalar(
                select(func.max(TickerFeatureSnapshot.as_of_date))
            ),
            frequency="Daily / as generated",
            status=_dataset_status(await _count(session, TickerFeatureSnapshot.id)),
            validation_summary="Stores model-ready feature vectors by ticker, date, and feature version.",
        ),
        ResearchDatasetResponse(
            key="ticker_training_labels",
            name="Training labels",
            source="Forward-return label generator",
            row_count=await _count(session, TickerTrainingLabel.id),
            instrument_count=await _count_distinct(
                session, TickerTrainingLabel.instrument_id
            ),
            latest_observation=await session.scalar(
                select(func.max(TickerTrainingLabel.as_of_date))
            ),
            frequency="Horizon based",
            status=_dataset_status(await _count(session, TickerTrainingLabel.id)),
            validation_summary="Forward returns, downside, volatility, and relative-return labels for ML validation.",
        ),
        ResearchDatasetResponse(
            key="ticker_memos",
            name="Ticker research memos",
            source="Ticker Analyst",
            row_count=await _count_owned_memos(session, user),
            instrument_count=await _count_distinct_owned_memos(session, user),
            latest_observation=await session.scalar(
                select(func.max(TickerMemo.memo_date)).where(
                    TickerMemo.owner_user_id == user.id
                )
            ),
            frequency="Event driven",
            status=_dataset_status(await _count_owned_memos(session, user)),
            validation_summary="User-owned investment memos with thesis, cases, risk notes, and model scores.",
        ),
        ResearchDatasetResponse(
            key="model_recommendations",
            name="Model recommendations",
            source="Ticker scoring and predictive layer",
            row_count=await _count_owned_recommendations(session, user),
            instrument_count=await _count_distinct_owned_recommendations(session, user),
            latest_observation=await session.scalar(
                select(func.max(ModelRecommendation.generated_at)).where(
                    ModelRecommendation.owner_user_id == user.id
                )
            ),
            frequency="Event driven",
            status=_dataset_status(await _count_owned_recommendations(session, user)),
            validation_summary="User-owned recommendation records attached to ticker memos and opportunity review.",
        ),
    ]


async def _build_feature_sets(
    session: AsyncSession,
) -> list[ResearchFeatureSetResponse]:
    rows = (
        await session.execute(
            select(
                TickerFeatureSnapshot.feature_version,
                func.count(TickerFeatureSnapshot.id),
                func.count(distinct(TickerFeatureSnapshot.instrument_id)),
                func.min(TickerFeatureSnapshot.as_of_date),
                func.max(TickerFeatureSnapshot.as_of_date),
                func.avg(TickerFeatureSnapshot.quality_score),
            )
            .group_by(TickerFeatureSnapshot.feature_version)
            .order_by(func.max(TickerFeatureSnapshot.as_of_date).desc())
        )
    ).all()

    responses: list[ResearchFeatureSetResponse] = []
    for (
        feature_version,
        snapshot_count,
        instrument_count,
        first_as_of_date,
        last_as_of_date,
        average_quality_score,
    ) in rows:
        sample = await session.scalar(
            select(TickerFeatureSnapshot)
            .where(TickerFeatureSnapshot.feature_version == feature_version)
            .order_by(TickerFeatureSnapshot.as_of_date.desc())
        )
        feature_count = len(sample.features) if sample is not None else 0
        responses.append(
            ResearchFeatureSetResponse(
                feature_version=feature_version,
                snapshot_count=int(snapshot_count or 0),
                instrument_count=int(instrument_count or 0),
                feature_count=feature_count,
                first_as_of_date=first_as_of_date,
                last_as_of_date=last_as_of_date,
                average_quality_score=_optional_decimal(average_quality_score),
                status=_feature_status(
                    snapshot_count=int(snapshot_count or 0),
                    instrument_count=int(instrument_count or 0),
                    feature_count=feature_count,
                ),
                notes=_feature_notes(
                    snapshot_count=int(snapshot_count or 0),
                    instrument_count=int(instrument_count or 0),
                    feature_count=feature_count,
                ),
            )
        )

    return responses


async def _build_notebooks(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> list[ResearchNotebookResponse]:
    memos = list(
        await session.scalars(
            select(TickerMemo)
            .options(selectinload(TickerMemo.instrument))
            .where(TickerMemo.owner_user_id == user.id)
            .order_by(TickerMemo.memo_date.desc(), TickerMemo.created_at.desc())
            .limit(12)
        )
    )

    return [
        ResearchNotebookResponse(
            id=memo.id,
            title=f"{memo.instrument.ticker} investment memo",
            ticker=memo.instrument.ticker,
            classification=memo.classification,
            memo_date=memo.memo_date,
            status=_memo_status(memo),
            linked_recommendation_id=memo.recommendation_id,
            summary=memo.executive_view,
        )
        for memo in memos
    ]


async def _build_models(session: AsyncSession) -> list[ResearchModelResponse]:
    comparison_rows = await list_predictive_model_comparison(session, limit=50)
    responses: list[ResearchModelResponse] = []
    for row in comparison_rows:
        responses.append(
            ResearchModelResponse(
                model_version_id=row.model_version_id,
                model_name=row.model_name,
                model_version=row.model_version,
                purpose="Predict ticker relative return and outperformance probability.",
                feature_version=row.feature_version,
                horizon_days=row.horizon_days,
                training_rows=row.training_rows,
                validation_rows=row.validation_rows,
                validation_directional_accuracy=row.validation_directional_accuracy,
                validation_r2=row.validation_r2,
                status=_model_status(
                    row.validation_rows,
                    row.validation_directional_accuracy,
                    row.validation_r2,
                ),
                created_at=row.created_at,
            )
        )

    return responses


async def _build_experiments(session: AsyncSession) -> list[ResearchExperimentResponse]:
    model_versions = list(
        await session.scalars(
            select(ModelVersion).order_by(ModelVersion.created_at.desc()).limit(12)
        )
    )
    experiments: list[ResearchExperimentResponse] = []
    for model_version in model_versions:
        metrics = model_version.metrics or {}
        validation_value = _first_decimal(
            metrics.get("validation_directional_accuracy"),
            metrics.get("directional_accuracy"),
            metrics.get("validation_r2"),
        )
        experiments.append(
            ResearchExperimentResponse(
                id=model_version.id,
                name=f"{model_version.name} {model_version.version}",
                experiment_type=model_version.pod,
                status=_model_version_status(metrics),
                hypothesis=model_version.purpose,
                feature_version=_string_or_none(metrics.get("feature_version")),
                horizon_days=_int_or_none(metrics.get("horizon_days")),
                validation_metric=_primary_metric_name(metrics),
                validation_value=validation_value,
                created_at=model_version.created_at,
            )
        )

    return experiments


def _build_backtests(
    models: list[ResearchModelResponse],
    feature_sets: list[ResearchFeatureSetResponse],
) -> list[ResearchBacktestResponse]:
    responses = [
        ResearchBacktestResponse(
            id="factor-ranker-walk-forward",
            name="Factor ranker walk-forward",
            status="ready" if feature_sets else "blocked",
            strategy="Rank model-ready feature snapshots and rebalance into top names.",
            benchmark="SPY",
            cost_model="Configurable bps per rebalance",
            latest_run_at=models[0].created_at if models else None,
            primary_metric=(
                "Directional accuracy"
                if models and models[0].validation_directional_accuracy is not None
                else None
            ),
            notes=(
                "Run through /api/ticker-intelligence/ml/backtests/factor."
                if feature_sets
                else "Needs feature snapshots and training labels before it can run."
            ),
        ),
        ResearchBacktestResponse(
            id="regime-filter-review",
            name="Regime filter review",
            status="design",
            strategy="Compare model signals with the latest market-regime state before allocation.",
            benchmark="SPY",
            cost_model="No trading costs until a portfolio rule is defined",
            latest_run_at=None,
            primary_metric=None,
            notes="Uses HMM regime context once regime snapshots are captured.",
        ),
    ]
    return responses


def _build_pipeline(
    *,
    memo_count: int,
    opportunity_count: int,
    experiment_count: int,
    backtest_count: int,
    model_count: int,
) -> list[ResearchPipelineStageResponse]:
    return [
        ResearchPipelineStageResponse(
            key="memos",
            label="Research memos",
            count=memo_count,
            description="Completed analyst work from Ticker Analyst.",
        ),
        ResearchPipelineStageResponse(
            key="opportunities",
            label="Opportunity review",
            count=opportunity_count,
            description="Ideas promoted into the queue for follow-up.",
        ),
        ResearchPipelineStageResponse(
            key="experiments",
            label="Experiments",
            count=experiment_count,
            description="Model versions and research trials available for review.",
        ),
        ResearchPipelineStageResponse(
            key="backtests",
            label="Backtests",
            count=backtest_count,
            description="Executable validation templates and saved research runs.",
        ),
        ResearchPipelineStageResponse(
            key="models",
            label="Model registry",
            count=model_count,
            description="Validated models available for analyst decision support.",
        ),
    ]


def _build_validation_checks(
    *,
    datasets: list[ResearchDatasetResponse],
    feature_sets: list[ResearchFeatureSetResponse],
    models: list[ResearchModelResponse],
    notebooks: list[ResearchNotebookResponse],
) -> list[ResearchValidationCheckResponse]:
    price_dataset = _dataset_by_key(datasets, "market_price_bars")
    label_dataset = _dataset_by_key(datasets, "ticker_training_labels")
    checks = [
        ResearchValidationCheckResponse(
            key="price_data",
            label="Price data availability",
            status="passed" if price_dataset and price_dataset.row_count > 0 else "warning",
            detail=(
                f"{price_dataset.row_count} price rows across {price_dataset.instrument_count} instruments."
                if price_dataset
                else "No price bars have been loaded."
            ),
        ),
        ResearchValidationCheckResponse(
            key="feature_coverage",
            label="Feature coverage",
            status="passed" if feature_sets else "warning",
            detail=(
                f"{len(feature_sets)} feature version(s) available."
                if feature_sets
                else "No feature snapshots are available."
            ),
        ),
        ResearchValidationCheckResponse(
            key="label_coverage",
            label="Training label coverage",
            status="passed" if label_dataset and label_dataset.row_count > 0 else "warning",
            detail=(
                f"{label_dataset.row_count} labels generated."
                if label_dataset
                else "No training labels are available."
            ),
        ),
        ResearchValidationCheckResponse(
            key="model_registry",
            label="Model registry",
            status="passed" if models else "warning",
            detail=(
                f"{len(models)} model version(s) available."
                if models
                else "No trained predictive models are registered."
            ),
        ),
        ResearchValidationCheckResponse(
            key="memo_review",
            label="Research memo review",
            status="passed" if notebooks else "warning",
            detail=(
                f"{len(notebooks)} recent memo(s) available."
                if notebooks
                else "No user-owned ticker memos yet."
            ),
        ),
    ]
    return checks


def _build_action_items(
    *,
    datasets: list[ResearchDatasetResponse],
    feature_sets: list[ResearchFeatureSetResponse],
    models: list[ResearchModelResponse],
    notebooks: list[ResearchNotebookResponse],
    active_opportunity_count: int,
) -> list[ResearchActionItemResponse]:
    actions: list[ResearchActionItemResponse] = []
    price_dataset = _dataset_by_key(datasets, "market_price_bars")
    label_dataset = _dataset_by_key(datasets, "ticker_training_labels")

    if not price_dataset or price_dataset.row_count == 0:
        actions.append(
            ResearchActionItemResponse(
                key="backfill_prices",
                label="Backfill research price history",
                priority="high",
                owner_area="Data infrastructure",
                detail="Load Yahoo price bars for the phase-one ticker universe.",
                action_path="/ticker-analyst",
            )
        )
    if not feature_sets:
        actions.append(
            ResearchActionItemResponse(
                key="build_features",
                label="Build price feature snapshots",
                priority="high",
                owner_area="Feature engineering",
                detail="Convert price bars into model-ready feature vectors.",
                action_path="/research-lab",
            )
        )
    if not label_dataset or label_dataset.row_count == 0:
        actions.append(
            ResearchActionItemResponse(
                key="generate_labels",
                label="Generate forward-return labels",
                priority="high",
                owner_area="ML training",
                detail="Create supervised labels before training or backtesting.",
                action_path="/research-lab",
            )
        )
    if not models:
        actions.append(
            ResearchActionItemResponse(
                key="train_model",
                label="Train baseline predictive model",
                priority="medium",
                owner_area="Model development",
                detail="Train the baseline ridge model and compare it with simple alternatives.",
                action_path="/research-lab",
            )
        )
    if active_opportunity_count > 0:
        actions.append(
            ResearchActionItemResponse(
                key="review_opportunities",
                label="Convert queued opportunities into experiments",
                priority="medium",
                owner_area="Research process",
                detail=f"{active_opportunity_count} active opportunity item(s) need research follow-up.",
                action_path="/opportunity-queue",
            )
        )
    if notebooks:
        actions.append(
            ResearchActionItemResponse(
                key="post_memo_validation",
                label="Validate recent ticker memos with model evidence",
                priority="medium",
                owner_area="Analyst review",
                detail="Compare memo conclusions against latest comparative and predictive model outputs.",
                action_path="/ticker-analyst",
            )
        )

    if not actions:
        actions.append(
            ResearchActionItemResponse(
                key="run_backtest",
                label="Run a factor backtest on the current feature set",
                priority="medium",
                owner_area="Backtesting",
                detail="The research data pipeline is ready for walk-forward validation.",
                action_path="/research-lab",
            )
        )

    return actions[:6]


async def _active_opportunity_count(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> int:
    return int(
        await session.scalar(
            select(func.count(Opportunity.id)).where(
                Opportunity.owner_user_id == user.id,
                Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
            )
        )
        or 0
    )


async def _count(session: AsyncSession, column) -> int:
    return int(await session.scalar(select(func.count(column))) or 0)


async def _count_distinct(session: AsyncSession, column) -> int:
    return int(await session.scalar(select(func.count(distinct(column)))) or 0)


async def _count_owned_memos(session: AsyncSession, user: AuthenticatedUser) -> int:
    return int(
        await session.scalar(
            select(func.count(TickerMemo.id)).where(TickerMemo.owner_user_id == user.id)
        )
        or 0
    )


async def _count_distinct_owned_memos(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> int:
    return int(
        await session.scalar(
            select(func.count(distinct(TickerMemo.instrument_id))).where(
                TickerMemo.owner_user_id == user.id
            )
        )
        or 0
    )


async def _count_owned_recommendations(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> int:
    return int(
        await session.scalar(
            select(func.count(ModelRecommendation.id)).where(
                ModelRecommendation.owner_user_id == user.id
            )
        )
        or 0
    )


async def _count_distinct_owned_recommendations(
    session: AsyncSession,
    user: AuthenticatedUser,
) -> int:
    return int(
        await session.scalar(
            select(func.count(distinct(ModelRecommendation.instrument_id))).where(
                ModelRecommendation.owner_user_id == user.id
            )
        )
        or 0
    )


def _dataset_status(row_count: int) -> str:
    if row_count <= 0:
        return "warning"
    return "passed"


def _feature_status(
    *,
    snapshot_count: int,
    instrument_count: int,
    feature_count: int,
) -> str:
    if snapshot_count <= 0 or feature_count <= 0:
        return "warning"
    if instrument_count < 5:
        return "warning"
    return "passed"


def _feature_notes(
    *,
    snapshot_count: int,
    instrument_count: int,
    feature_count: int,
) -> str:
    if snapshot_count <= 0:
        return "No feature snapshots are available for this version."
    if instrument_count < 5:
        return "Coverage is thin; add more instruments before relying on cross-sectional comparisons."
    return f"{feature_count} feature(s) available across {instrument_count} instruments."


def _memo_status(memo: TickerMemo) -> str:
    scores = memo.scores or {}
    composite = _optional_decimal(scores.get("composite_score"))
    if composite is not None and composite >= Decimal("70"):
        return "candidate"
    if memo.classification in {"avoid", "rejected"}:
        return "archived"
    return "review"


def _model_status(
    validation_rows: int | None,
    directional_accuracy: Decimal | None,
    validation_r2: Decimal | None,
) -> str:
    if not validation_rows:
        return "training"
    if directional_accuracy is not None and directional_accuracy >= Decimal("55"):
        return "validated"
    if validation_r2 is not None and validation_r2 > Decimal("0"):
        return "review"
    return "needs_review"


def _model_version_status(metrics: dict) -> str:
    validation_rows = _int_or_none(metrics.get("validation_rows"))
    directional_accuracy = _optional_decimal(
        metrics.get("validation_directional_accuracy")
    )
    r2 = _optional_decimal(metrics.get("validation_r2"))
    return _model_status(validation_rows, directional_accuracy, r2)


def _primary_metric_name(metrics: dict) -> str | None:
    if metrics.get("validation_directional_accuracy") is not None:
        return "Directional accuracy"
    if metrics.get("validation_r2") is not None:
        return "Validation R2"
    if metrics.get("validation_mae") is not None:
        return "Validation MAE"
    return None


def _dataset_by_key(
    datasets: list[ResearchDatasetResponse],
    key: str,
) -> ResearchDatasetResponse | None:
    return next((dataset for dataset in datasets if dataset.key == key), None)


def _optional_decimal(value) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _first_decimal(*values) -> Decimal | None:
    for value in values:
        if value is not None:
            return _optional_decimal(value)
    return None


def _int_or_none(value) -> int | None:
    if value is None:
        return None
    return int(value)


def _string_or_none(value) -> str | None:
    if value is None:
        return None
    return str(value)

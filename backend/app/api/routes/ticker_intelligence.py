from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.ticker_intelligence import (
    BacktestRunCreate,
    BacktestRunResponse,
    PriceBackfillResponse,
    PriceFeatureBuildCreate,
    PriceFeatureBuildResponse,
    ModelComparisonRowResponse,
    PredictiveModelPredictCreate,
    PredictiveModelPredictionResponse,
    PredictiveModelTrainCreate,
    PredictiveModelTrainResponse,
    RegimeModelFitCreate,
    RegimeModelResponse,
    ResearchPipelineRunCreate,
    ResearchPipelineRunResponse,
    TickerAIDraftCreate,
    TickerAIDraftResponse,
    TickerAnalysisCreate,
    TickerAnalysisResponse,
    TickerDatasetRowResponse,
    TickerDeskResponse,
    TickerMLReportResponse,
    TickerMemoResponse,
    TickerMemoSummaryResponse,
    TickerPrefillResponse,
    TickerSuggestionResponse,
    TrainingLabelGenerateCreate,
    TrainingLabelResponse,
    YahooPriceBackfillCreate,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.ticker_intelligence.ai_draft import (
    AIDraftUnavailableError,
    generate_ticker_ai_draft,
)
from app.services.ticker_intelligence.analysis import (
    analyze_ticker,
    get_ticker_desk,
    get_ticker_memo,
    list_recent_ticker_memos,
    list_ticker_memos,
)
from app.services.market_data.quote_cache import get_cached_quote_price
from app.services.research_lab.experiments import record_experiment
from app.services.ticker_intelligence.market_data import (
    MarketDataUnavailableError,
    prefill_ticker,
    search_ticker_suggestions,
)
from app.services.ticker_intelligence.ml_training import (
    MLTrainingDataUnavailableError,
    backfill_yahoo_prices,
    build_price_feature_snapshots,
    build_ticker_ml_report,
    fit_market_regime_model,
    generate_training_labels,
    get_latest_market_regime_model,
    list_predictive_model_comparison,
    list_ticker_dataset_rows,
    predict_with_latest_model,
    run_factor_backtest,
    run_research_data_pipeline,
    train_predictive_model,
)

router = APIRouter(prefix="/ticker-intelligence")


@router.post(
    "/analyze",
    response_model=TickerAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticker_analysis(
    payload: TickerAnalysisCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TickerAnalysisResponse:
    return await analyze_ticker(session, payload, user)


@router.post("/ai/draft", response_model=TickerAIDraftResponse)
async def create_ticker_ai_draft(
    payload: TickerAIDraftCreate,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
) -> TickerAIDraftResponse:
    try:
        return await generate_ticker_ai_draft(payload)
    except AIDraftUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/prices/yahoo/backfill", response_model=PriceBackfillResponse)
async def create_yahoo_price_backfill(
    payload: YahooPriceBackfillCreate,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PriceBackfillResponse:
    try:
        return await backfill_yahoo_prices(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/pipeline/run", response_model=ResearchPipelineRunResponse)
async def create_research_pipeline_run(
    payload: ResearchPipelineRunCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ResearchPipelineRunResponse:
    result = await run_research_data_pipeline(session, payload)
    failed_steps = [step for step in result.steps if step.status == "failed"]
    await record_experiment(
        session,
        owner_user_id=user.id,
        name=f"Data pipeline run ({len(result.tickers)} tickers, {result.horizon_days}d)",
        experiment_type="pipeline",
        status="needs_review" if failed_steps else "completed",
        hypothesis="Fresh point-in-time prices, labels, and features improve model readiness.",
        parameters={
            "tickers": result.tickers,
            "benchmark_ticker": result.benchmark_ticker,
            "start_date": result.start_date.isoformat(),
            "end_date": result.end_date.isoformat(),
            "horizon_days": result.horizon_days,
            "train_model": payload.train_model,
        },
        metrics={
            "steps_completed": len(
                [step for step in result.steps if step.status == "completed"]
            ),
            "steps_failed": len(failed_steps),
            "warnings": len(result.warnings),
            "model_trained": result.model_version_id is not None,
        },
        primary_metric="steps_failed",
        primary_value=Decimal(len(failed_steps)),
        model_version_id=result.model_version_id,
    )
    await session.commit()
    return result


@router.post("/ml/labels", response_model=TrainingLabelResponse)
async def create_training_labels(
    payload: TrainingLabelGenerateCreate,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TrainingLabelResponse:
    try:
        return await generate_training_labels(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/features/price", response_model=PriceFeatureBuildResponse)
async def create_price_feature_snapshots(
    payload: PriceFeatureBuildCreate,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PriceFeatureBuildResponse:
    try:
        return await build_price_feature_snapshots(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/regime/hmm", response_model=RegimeModelResponse)
async def create_hmm_regime_model(
    payload: RegimeModelFitCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RegimeModelResponse:
    try:
        result = await fit_market_regime_model(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    await record_experiment(
        session,
        owner_user_id=user.id,
        name=f"HMM regime fit ({result.ticker}, {len(result.state_probabilities)} states)",
        experiment_type="regime",
        hypothesis="Return and volatility observations cluster into persistent market regimes.",
        parameters={
            "ticker": result.ticker,
            "state_count": payload.state_count,
            "lookback_days": payload.lookback_days,
            "source": payload.source,
        },
        metrics={
            "current_regime": result.current_regime,
            "confidence_score": str(result.confidence_score),
            "as_of_date": result.as_of_date.isoformat(),
        },
        primary_metric="confidence_score",
        primary_value=result.confidence_score,
        model_version_id=result.model_version_id,
    )
    await session.commit()
    return result


@router.get("/ml/regime/latest", response_model=RegimeModelResponse)
async def read_latest_hmm_regime_model(
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RegimeModelResponse:
    try:
        return await get_latest_market_regime_model(session)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/backtests/factor", response_model=BacktestRunResponse)
async def create_factor_backtest(
    payload: BacktestRunCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestRunResponse:
    try:
        return await run_factor_backtest(session, payload, user)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/train", response_model=PredictiveModelTrainResponse)
async def create_predictive_model_training_run(
    payload: PredictiveModelTrainCreate,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PredictiveModelTrainResponse:
    try:
        result = await train_predictive_model(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    accuracy = _decimal_or_none(
        result.metrics.get("validation_directional_accuracy")
    )
    await record_experiment(
        session,
        owner_user_id=user.id,
        name=f"Model training {result.horizon_days}d ({result.model_version})",
        experiment_type="training",
        hypothesis="Price features carry predictive signal for benchmark-relative forward returns.",
        parameters={
            "tickers": sorted({ticker.strip().upper() for ticker in payload.tickers}),
            "horizon_days": payload.horizon_days,
            "benchmark_ticker": payload.benchmark_ticker,
            "feature_version": payload.feature_version,
            "ridge_alpha": str(payload.ridge_alpha),
        },
        metrics={
            "training_rows": result.training_rows,
            "validation_rows": result.validation_rows,
            **{key: str(value) for key, value in result.metrics.items()},
        },
        primary_metric="validation_directional_accuracy",
        primary_value=accuracy,
        model_version_id=result.model_version_id,
    )
    await session.commit()
    return result


def _decimal_or_none(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


@router.post("/ml/predict", response_model=PredictiveModelPredictionResponse)
async def create_predictive_model_prediction(
    payload: PredictiveModelPredictCreate,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PredictiveModelPredictionResponse:
    try:
        return await predict_with_latest_model(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/ml/models", response_model=list[ModelComparisonRowResponse])
async def read_predictive_model_comparison(
    limit: int = Query(default=20, ge=1, le=100),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[ModelComparisonRowResponse]:
    return await list_predictive_model_comparison(session, limit=limit)


@router.get("/ml/report/{ticker}", response_model=TickerMLReportResponse)
async def read_ticker_ml_report(
    ticker: str,
    horizon_days: int = Query(default=63, ge=1, le=756),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TickerMLReportResponse:
    return await build_ticker_ml_report(
        session,
        ticker,
        horizon_days=horizon_days,
        user=user,
    )


@router.get("/ml/dataset/{ticker}", response_model=list[TickerDatasetRowResponse])
async def read_ticker_dataset_rows(
    ticker: str,
    limit: int = Query(default=100, ge=1, le=500),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[TickerDatasetRowResponse]:
    return await list_ticker_dataset_rows(session, ticker, limit=limit)


@router.get("/memos", response_model=list[TickerMemoSummaryResponse])
async def read_recent_ticker_memos(
    limit: int = Query(default=12, ge=1, le=50),
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[TickerMemoSummaryResponse]:
    return await list_recent_ticker_memos(session, user, limit=limit)


@router.get("/memos/{memo_id}", response_model=TickerMemoResponse)
async def read_ticker_memo(
    memo_id: UUID,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TickerMemoResponse:
    memo = await get_ticker_memo(session, memo_id, user)
    if memo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticker memo not found.",
        )
    return memo


@router.get("/suggestions", response_model=list[TickerSuggestionResponse])
async def read_ticker_suggestions(
    query: str = Query(min_length=1, max_length=64),
    market: str = Query(default="US", min_length=2, max_length=16),
    limit: int = Query(default=8, ge=1, le=20),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[TickerSuggestionResponse]:
    return await search_ticker_suggestions(
        session,
        query,
        market_hint=market,
        limit=limit,
    )


@router.get("/{ticker}/desk", response_model=TickerDeskResponse)
async def read_ticker_desk(
    ticker: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TickerDeskResponse:
    return await get_ticker_desk(session, ticker, user)


@router.get("/{ticker}/prefill", response_model=TickerPrefillResponse)
async def read_ticker_prefill(
    ticker: str,
    market: str | None = Query(default=None, max_length=16),
    scope: str = Query(default="identity", max_length=16),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TickerPrefillResponse:
    try:
        response = await prefill_ticker(ticker, market_hint=market, scope=scope)
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    # Prefer the platform's live mark over the provider snapshot so the
    # analyst sees the same price the portfolio is marked at.
    live_price = await get_cached_quote_price(session, response.instrument.ticker)
    if live_price is not None:
        response.metrics.current_price = live_price
    return response


@router.get("/{ticker}/memos", response_model=list[TickerMemoResponse])
async def read_ticker_memos(
    ticker: str,
    user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> list[TickerMemoResponse]:
    return await list_ticker_memos(session, ticker, user)

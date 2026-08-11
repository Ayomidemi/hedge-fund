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
    TickerMLReportResponse,
    TickerMemoResponse,
    TickerMemoSummaryResponse,
    TickerPrefillResponse,
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
    get_ticker_memo,
    list_recent_ticker_memos,
    list_ticker_memos,
)
from app.services.market_data.quote_cache import get_cached_quote_price
from app.services.ticker_intelligence.market_data import (
    MarketDataUnavailableError,
    prefill_ticker,
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
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> ResearchPipelineRunResponse:
    return await run_research_data_pipeline(session, payload)


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
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> RegimeModelResponse:
    try:
        return await fit_market_regime_model(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestRunResponse:
    try:
        return await run_factor_backtest(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/ml/train", response_model=PredictiveModelTrainResponse)
async def create_predictive_model_training_run(
    payload: PredictiveModelTrainCreate,
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> PredictiveModelTrainResponse:
    try:
        return await train_predictive_model(session, payload)
    except MLTrainingDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


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


@router.get("/{ticker}/prefill", response_model=TickerPrefillResponse)
async def read_ticker_prefill(
    ticker: str,
    market: str | None = Query(default=None, max_length=16),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
    session: AsyncSession = Depends(get_session),
) -> TickerPrefillResponse:
    try:
        response = await prefill_ticker(ticker, market_hint=market)
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

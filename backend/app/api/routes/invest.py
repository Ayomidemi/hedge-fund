from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestAccountResponse,
    InvestCashRequest,
    InvestDiscoverResponse,
    InvestFixedIncomeProductResponse,
    InvestHolding,
    InvestHomeResponse,
    InvestInstrumentResponse,
    InvestMarketsResponse,
    InvestOrderCreate,
    InvestOrderResponse,
    InvestTransactionResponse,
    InvestWatchlistCreate,
    InvestWatchlistItemResponse,
)
from app.core.auth import AuthenticatedUser, require_invest_user
from app.db.session import get_session
from app.services.invest import accounts as invest
from app.services.invest.fixed_income import (
    ensure_fixed_income_instrument,
    fixed_income_response,
    get_fixed_income_product,
    search_fixed_income_products,
)
from app.services.invest.discover import build_invest_discover
from app.services.invest.markets import build_invest_markets

router = APIRouter(prefix="/invest")


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, invest.InvestNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, invest.InvestValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Invest request failed.",
    )


@router.get("/account", response_model=InvestAccountResponse)
async def read_account(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestAccountResponse:
    response = await invest.get_account_response(session, user)
    await session.commit()
    return response


@router.post("/account", response_model=InvestAccountResponse)
async def create_account(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestAccountResponse:
    response = await invest.get_account_response(session, user)
    await session.commit()
    return response


@router.get("/home", response_model=InvestHomeResponse)
async def read_home(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestHomeResponse:
    response = await invest.get_home(session, user)
    await session.commit()
    return response


@router.get("/portfolio", response_model=InvestHomeResponse)
async def read_portfolio(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestHomeResponse:
    response = await invest.get_home(session, user)
    await session.commit()
    return response


@router.get("/positions", response_model=list[InvestHolding])
async def read_positions(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> list[InvestHolding]:
    rows = await invest.list_positions(session, user)
    await session.commit()
    return rows


@router.post("/orders", response_model=InvestOrderResponse)
async def create_order(
    payload: InvestOrderCreate,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestOrderResponse:
    try:
        return await invest.submit_order(session, user, payload)
    except invest.InvestError as exc:
        raise _http_error(exc) from exc


@router.get("/orders", response_model=list[InvestOrderResponse])
async def read_orders(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> list[InvestOrderResponse]:
    rows = await invest.list_orders(session, user)
    await session.commit()
    return rows


@router.get("/orders/{order_id}", response_model=InvestOrderResponse)
async def read_order(
    order_id: UUID,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestOrderResponse:
    try:
        response = await invest.get_order(session, user, order_id)
    except invest.InvestError as exc:
        raise _http_error(exc) from exc
    await session.commit()
    return response


@router.post("/orders/{order_id}/cancel", response_model=InvestOrderResponse)
async def cancel_order(
    order_id: UUID,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestOrderResponse:
    try:
        return await invest.cancel_order(session, user, order_id)
    except invest.InvestError as exc:
        raise _http_error(exc) from exc


@router.get("/transactions", response_model=list[InvestTransactionResponse])
async def read_transactions(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> list[InvestTransactionResponse]:
    rows = await invest.list_transactions(session, user)
    await session.commit()
    return rows


@router.get("/cash", response_model=InvestAccountResponse)
async def read_cash(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestAccountResponse:
    response = await invest.get_account_response(session, user)
    await session.commit()
    return response


@router.post("/paper/deposit", response_model=InvestAccountResponse)
async def add_paper_cash(
    payload: InvestCashRequest,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestAccountResponse:
    try:
        return await invest.add_paper_cash(session, user, payload)
    except invest.InvestError as extra:
        raise _http_error(extra) from extra


@router.post("/paper/reset", response_model=InvestAccountResponse)
async def reset_paper_account(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestAccountResponse:
    try:
        return await invest.reset_paper_account(session, user)
    except invest.InvestError as extra:
        raise _http_error(extra) from extra


@router.get("/watchlist", response_model=list[InvestWatchlistItemResponse])
async def read_watchlist(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> list[InvestWatchlistItemResponse]:
    return await invest.list_watchlist(session, user)


@router.post("/watchlist", response_model=InvestWatchlistItemResponse)
async def create_watchlist_item(
    payload: InvestWatchlistCreate,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestWatchlistItemResponse:
    return await invest.add_watchlist_item(session, user, payload.ticker, payload.notes)


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist_item(
    ticker: str,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await invest.remove_watchlist_item(session, user, ticker)


@router.get("/instruments/search", response_model=list[InvestInstrumentResponse])
async def search_instruments(
    query: str = Query(min_length=1, max_length=64),
    market: str = Query(default="US", max_length=8),
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> list[InvestInstrumentResponse]:
    return await invest.search_instruments(session, query, market)


@router.get("/instruments/{ticker}", response_model=InvestInstrumentResponse)
async def read_instrument(
    ticker: str,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestInstrumentResponse:
    response = await invest.get_instrument(session, ticker)
    await session.commit()
    return response


@router.get("/markets", response_model=InvestMarketsResponse)
async def read_markets(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestMarketsResponse:
    response = await build_invest_markets(session)
    await session.commit()
    return response


@router.get("/fixed-income", response_model=list[InvestFixedIncomeProductResponse])
async def read_fixed_income_products(
    query: str = Query(default="", max_length=64),
    market: str = Query(default="ALL", max_length=8),
    user: AuthenticatedUser = Depends(require_invest_user),
) -> list[InvestFixedIncomeProductResponse]:
    return [
        fixed_income_response(product)
        for product in search_fixed_income_products(query, market=market)
    ]


@router.get(
    "/fixed-income/{ticker}",
    response_model=InvestFixedIncomeProductResponse,
)
async def read_fixed_income_product(
    ticker: str,
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestFixedIncomeProductResponse:
    product = get_fixed_income_product(ticker)
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Fixed-income product was not found.",
        )
    await ensure_fixed_income_instrument(session, product)
    await session.commit()
    return fixed_income_response(product)


@router.get("/discover", response_model=InvestDiscoverResponse)
async def read_discover(
    user: AuthenticatedUser = Depends(require_invest_user),
    session: AsyncSession = Depends(get_session),
) -> InvestDiscoverResponse:
    return await build_invest_discover(session, user)

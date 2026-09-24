from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Instrument,
    RetailAccount,
    RetailOrder,
    RetailPosition,
    RetailTransaction,
)
from app.services.brokerage.protocol import (
    BrokerAccount,
    BrokerBalances,
    BrokerError,
    BrokerOrder,
    BrokerPosition,
    BrokerTransaction,
    BrokerValidationError,
    CashRequest,
    SubmitOrderRequest,
)
from app.services.invest.fixed_income import (
    ensure_fixed_income_instrument,
    fixed_income_price_per_face_db,
    fixed_income_products_by_tickers_db,
    get_fixed_income_product_db,
)
from app.services.invest.configuration import get_typed_paper_broker_policy
from app.services.market_data.fx_convert import amount_in_base, convert_amount_to_base
from app.services.market_data.fx_refresh import load_fx_rates
from app.services.market_data.quote_cache import (
    get_cached_quote_price,
    get_or_fetch_quote_price,
)

QTY = Decimal("0.00000001")
MONEY = Decimal("0.01")
PRICE = Decimal("0.000001")


class PaperBrokerProvider:
    provider_code = "PAPER"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_account(
        self, *, user_id: str, currency: str = "USD"
    ) -> BrokerAccount:
        raise BrokerError("Paper accounts are created by the Invest account service.")

    async def get_account(self, broker_account_id: str) -> BrokerAccount:
        account = await self._load_account(broker_account_id)
        return _account_snapshot(account)

    async def get_balances(self, broker_account_id: str) -> BrokerBalances:
        account = await self._load_account(broker_account_id)
        return _balances(account)

    async def get_positions(self, broker_account_id: str) -> list[BrokerPosition]:
        account = await self._load_account(broker_account_id)
        rows = list(
            await self.session.scalars(
                select(RetailPosition)
                .options(selectinload(RetailPosition.instrument))
                .where(RetailPosition.account_id == account.id)
                .where(RetailPosition.quantity > 0)
            )
        )
        products = await fixed_income_products_by_tickers_db(
            self.session, [row.instrument.ticker for row in rows]
        )
        fx_rates = await load_fx_rates(self.session)
        positions: list[BrokerPosition] = []
        for row in rows:
            native_currency = row.instrument.currency or account.base_currency
            fixed_income_product = products.get(row.instrument.ticker.upper())
            native_mark = (
                await fixed_income_price_per_face_db(self.session, fixed_income_product)
                if fixed_income_product is not None
                else await get_cached_quote_price(self.session, row.instrument.ticker)
            )
            mark = native_mark if native_mark is not None else row.average_cost
            cash_mark = amount_in_base(
                mark, native_currency, account.base_currency, fx_rates
            )
            price = cash_mark if cash_mark is not None else mark
            market_value = (row.quantity * price).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
            unrealized = (market_value - row.cost_basis).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
            pct = None
            if row.cost_basis > 0:
                pct = ((unrealized / row.cost_basis) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            positions.append(
                BrokerPosition(
                    symbol=row.instrument.ticker,
                    quantity=row.quantity,
                    average_cost=row.average_cost,
                    market_value=market_value,
                    unrealized_pnl=unrealized,
                    unrealized_pnl_pct=pct,
                )
            )
        return positions

    async def submit_order(
        self, broker_account_id: str, request: SubmitOrderRequest
    ) -> BrokerOrder:
        account = await self._load_account(broker_account_id)
        policy = await get_typed_paper_broker_policy(self.session)
        side = request.side.strip().upper()
        order_type = request.order_type.strip().lower()
        if side not in policy.allowed_sides:
            raise BrokerValidationError("Order side must be BUY or SELL.")
        if order_type not in policy.allowed_order_types:
            raise BrokerValidationError("Paper V1 only accepts market orders.")

        instrument = await self._load_instrument(request.symbol)
        fixed_income_product = await get_fixed_income_product_db(
            self.session, instrument.ticker
        )
        if fixed_income_product is not None:
            instrument = await ensure_fixed_income_instrument(
                self.session, fixed_income_product
            )
            mark = await fixed_income_price_per_face_db(
                self.session, fixed_income_product
            )
            face_increment = fixed_income_product.face_value_increment
        else:
            mark = await get_or_fetch_quote_price(
                self.session, instrument.ticker, instrument_id=instrument.id
            )
            face_increment = None
        if mark is None or mark <= 0:
            raise BrokerValidationError(
                f"No live mark is available for {instrument.ticker}."
            )

        now = datetime.now(timezone.utc)
        broker_order_id = str(uuid4())
        warnings: list[str] = []

        if side == "BUY":
            if fixed_income_product is not None:
                quantity, notional = _fixed_income_buy_size(
                    request,
                    mark,
                    face_increment,
                )
                warnings.append(
                    "Fixed-income paper fill uses stored dirty price; quantity is face value."
                )
            else:
                quantity, notional = _buy_size(request, mark)
            cash_notional = await self._cash_amount(account, instrument, notional)
            if cash_notional > account.cash_balance:
                raise BrokerValidationError("Not enough buying power for this order.")
            equity = await self._equity(account)
            if (
                equity > 0
                and (cash_notional / (equity + cash_notional))
                >= policy.concentration_warn_pct
            ):
                warnings.append(
                    f"This purchase would be a large share of your portfolio "
                    f"({instrument.ticker})."
                )
            native_ccy = (instrument.currency or account.base_currency).upper()
            if native_ccy != account.base_currency.upper():
                warnings.append(
                    f"Paper cash is {account.base_currency}; "
                    f"{native_ccy} converted at the stored FX rate."
                )
            await self._apply_buy(
                account, instrument, quantity, cash_notional, now, broker_order_id
            )
        else:
            quantity, notional = await self._sell_size(
                account,
                instrument,
                request,
                mark,
                quantity_increment=face_increment,
            )
            if fixed_income_product is not None:
                warnings.append(
                    "Fixed-income paper fill uses stored dirty price; quantity is face value."
                )
            cash_notional = await self._cash_amount(account, instrument, notional)
            native_ccy = (instrument.currency or account.base_currency).upper()
            if native_ccy != account.base_currency.upper():
                warnings.append(
                    f"Paper cash is {account.base_currency}; "
                    f"{native_ccy} converted at the stored FX rate."
                )
            await self._apply_sell(
                account, instrument, quantity, cash_notional, now, broker_order_id
            )

        order = RetailOrder(
            user_id=account.user_id,
            account_id=account.id,
            instrument_id=instrument.id,
            side=side,
            order_type="market",
            quantity=quantity,
            notional=notional,
            status="FILLED",
            submitted_at=now,
            filled_at=now,
            average_fill_price=mark.quantize(
                policy.price_precision, rounding=ROUND_HALF_UP
            ),
            filled_quantity=quantity,
            broker_provider=self.provider_code,
            broker_order_id=broker_order_id,
            warnings=warnings,
        )
        self.session.add(order)
        await self.session.flush()
        return _order_snapshot(order, instrument.ticker)

    async def cancel_order(
        self, broker_account_id: str, broker_order_id: str
    ) -> BrokerOrder:
        account = await self._load_account(broker_account_id)
        order = await self.session.scalar(
            select(RetailOrder)
            .options(selectinload(RetailOrder.instrument))
            .where(RetailOrder.account_id == account.id)
            .where(RetailOrder.broker_order_id == broker_order_id)
        )
        if order is None:
            raise BrokerValidationError("Order was not found.")
        if order.status == "FILLED":
            raise BrokerValidationError("Filled paper orders cannot be cancelled.")
        order.status = "CANCELLED"
        await self.session.flush()
        return _order_snapshot(order, order.instrument.ticker)

    async def get_orders(self, broker_account_id: str) -> list[BrokerOrder]:
        account = await self._load_account(broker_account_id)
        rows = list(
            await self.session.scalars(
                select(RetailOrder)
                .options(selectinload(RetailOrder.instrument))
                .where(RetailOrder.account_id == account.id)
                .order_by(RetailOrder.submitted_at.desc())
            )
        )
        return [_order_snapshot(row, row.instrument.ticker) for row in rows]

    async def get_transactions(self, broker_account_id: str) -> list[BrokerTransaction]:
        account = await self._load_account(broker_account_id)
        rows = list(
            await self.session.scalars(
                select(RetailTransaction)
                .options(selectinload(RetailTransaction.instrument))
                .where(RetailTransaction.account_id == account.id)
                .order_by(RetailTransaction.occurred_at.desc())
            )
        )
        return [
            BrokerTransaction(
                broker_reference=row.broker_reference or str(row.id),
                entry_type=row.entry_type,
                amount=row.amount,
                currency=row.currency,
                occurred_at=row.occurred_at,
                symbol=row.instrument.ticker if row.instrument is not None else None,
                description=row.description,
            )
            for row in rows
        ]

    async def deposit(
        self, broker_account_id: str, request: CashRequest
    ) -> BrokerBalances:
        account = await self._load_account(broker_account_id)
        amount = _positive_money(request.amount)
        account.cash_balance = (account.cash_balance + amount).quantize(MONEY)
        self.session.add(
            RetailTransaction(
                account_id=account.id,
                entry_type="DEPOSIT",
                amount=amount,
                currency=account.base_currency,
                occurred_at=datetime.now(timezone.utc),
                source="paper",
                description="Paper cash added.",
            )
        )
        await self.session.flush()
        return _balances(account)

    async def withdraw(
        self, broker_account_id: str, request: CashRequest
    ) -> BrokerBalances:
        account = await self._load_account(broker_account_id)
        amount = _positive_money(request.amount)
        if amount > account.cash_balance:
            raise BrokerValidationError("Not enough cash to withdraw.")
        account.cash_balance = (account.cash_balance - amount).quantize(MONEY)
        self.session.add(
            RetailTransaction(
                account_id=account.id,
                entry_type="WITHDRAWAL",
                amount=-amount,
                currency=account.base_currency,
                occurred_at=datetime.now(timezone.utc),
                source="paper",
                description="Paper cash withdrawn.",
            )
        )
        await self.session.flush()
        return _balances(account)

    async def reset_account(
        self, broker_account_id: str, starting_cash: Decimal
    ) -> BrokerAccount:
        account = await self._load_account(broker_account_id)
        starting_cash = starting_cash.quantize(MONEY)
        adjustment = (starting_cash - account.cash_balance).quantize(MONEY)
        positions = list(
            await self.session.scalars(
                select(RetailPosition).where(RetailPosition.account_id == account.id)
            )
        )
        for position in positions:
            await self.session.delete(position)
        account.cash_balance = starting_cash
        self.session.add(
            RetailTransaction(
                account_id=account.id,
                entry_type="ADJUSTMENT",
                amount=adjustment,
                currency=account.base_currency,
                occurred_at=datetime.now(timezone.utc),
                source="paper",
                description="Paper account reset; positions cleared.",
            )
        )
        await self.session.flush()
        return _account_snapshot(account)

    async def _load_account(self, broker_account_id: str) -> RetailAccount:
        account = await self.session.scalar(
            select(RetailAccount).where(
                RetailAccount.broker_account_id == broker_account_id
            )
        )
        if account is None:
            raise BrokerValidationError("Paper account was not found.")
        return account

    async def _load_instrument(self, symbol: str) -> Instrument:
        ticker = symbol.strip().upper()
        instrument = await self.session.scalar(
            select(Instrument).where(Instrument.ticker == ticker)
        )
        if instrument is None:
            raise BrokerValidationError(f"{ticker} is not available to trade yet.")
        return instrument

    async def _equity(self, account: RetailAccount) -> Decimal:
        positions = await self.get_positions(account.broker_account_id)
        invested = sum((item.market_value for item in positions), Decimal("0"))
        return (account.cash_balance + invested).quantize(MONEY)

    async def _cash_amount(
        self, account: RetailAccount, instrument: Instrument, native_amount: Decimal
    ) -> Decimal:
        currency = instrument.currency or account.base_currency
        converted = await convert_amount_to_base(
            self.session, native_amount, currency, account.base_currency
        )
        if converted is None:
            raise BrokerValidationError(
                f"No {account.base_currency}/{currency} rate available to paper this order."
            )
        return converted.quantize(MONEY, rounding=ROUND_HALF_UP)

    async def _apply_buy(
        self,
        account: RetailAccount,
        instrument: Instrument,
        quantity: Decimal,
        cash_notional: Decimal,
        now: datetime,
        broker_order_id: str,
    ) -> None:
        notional = cash_notional.quantize(MONEY, rounding=ROUND_HALF_UP)
        account.cash_balance = (account.cash_balance - notional).quantize(MONEY)
        position = await self.session.scalar(
            select(RetailPosition)
            .where(RetailPosition.account_id == account.id)
            .where(RetailPosition.instrument_id == instrument.id)
        )
        unit_cost = (notional / quantity).quantize(PRICE, rounding=ROUND_HALF_UP)
        if position is None:
            position = RetailPosition(
                account_id=account.id,
                instrument_id=instrument.id,
                quantity=quantity,
                average_cost=unit_cost,
                cost_basis=notional,
                realized_pnl=Decimal("0.00"),
            )
            self.session.add(position)
        else:
            new_qty = position.quantity + quantity
            new_cost = position.cost_basis + notional
            position.quantity = new_qty
            position.cost_basis = new_cost
            position.average_cost = (new_cost / new_qty).quantize(
                PRICE, rounding=ROUND_HALF_UP
            )
        self.session.add(
            RetailTransaction(
                account_id=account.id,
                entry_type="BUY",
                amount=-notional,
                currency=account.base_currency,
                instrument_id=instrument.id,
                occurred_at=now,
                source="paper",
                broker_reference=broker_order_id,
                description=_transaction_description("Bought", quantity, instrument),
            )
        )

    async def _apply_sell(
        self,
        account: RetailAccount,
        instrument: Instrument,
        quantity: Decimal,
        cash_proceeds: Decimal,
        now: datetime,
        broker_order_id: str,
    ) -> None:
        position = await self.session.scalar(
            select(RetailPosition)
            .where(RetailPosition.account_id == account.id)
            .where(RetailPosition.instrument_id == instrument.id)
        )
        if position is None or position.quantity < quantity:
            raise BrokerValidationError(f"Not enough {instrument.ticker} to sell.")
        proceeds = cash_proceeds.quantize(MONEY, rounding=ROUND_HALF_UP)
        sold_cost = (position.average_cost * quantity).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        realized = (proceeds - sold_cost).quantize(MONEY, rounding=ROUND_HALF_UP)
        position.quantity = (position.quantity - quantity).quantize(QTY)
        position.cost_basis = (position.average_cost * position.quantity).quantize(
            MONEY
        )
        position.realized_pnl = (position.realized_pnl + realized).quantize(MONEY)
        account.cash_balance = (account.cash_balance + proceeds).quantize(MONEY)
        if position.quantity <= 0:
            await self.session.delete(position)
        self.session.add(
            RetailTransaction(
                account_id=account.id,
                entry_type="SELL",
                amount=proceeds,
                currency=account.base_currency,
                instrument_id=instrument.id,
                occurred_at=now,
                source="paper",
                broker_reference=broker_order_id,
                description=_transaction_description("Sold", quantity, instrument),
            )
        )

    async def _sell_size(
        self,
        account: RetailAccount,
        instrument: Instrument,
        request: SubmitOrderRequest,
        price: Decimal,
        *,
        quantity_increment: Decimal | None = None,
    ) -> tuple[Decimal, Decimal]:
        position = await self.session.scalar(
            select(RetailPosition)
            .where(RetailPosition.account_id == account.id)
            .where(RetailPosition.instrument_id == instrument.id)
        )
        held = position.quantity if position is not None else Decimal("0")
        if request.quantity is not None:
            quantity = _order_quantity(request.quantity, quantity_increment)
        elif request.notional is not None:
            quantity = _order_quantity(request.notional / price, quantity_increment)
        else:
            raise BrokerValidationError("Sell orders need a quantity or amount.")
        if quantity <= 0:
            raise BrokerValidationError("Sell quantity must be greater than zero.")
        if quantity > held:
            raise BrokerValidationError(f"Not enough {instrument.ticker} to sell.")
        notional = (quantity * price).quantize(MONEY, rounding=ROUND_HALF_UP)
        return quantity, notional


def _buy_size(request: SubmitOrderRequest, price: Decimal) -> tuple[Decimal, Decimal]:
    if request.notional is not None:
        notional = _positive_money(request.notional)
        quantity = (notional / price).quantize(QTY, rounding=ROUND_DOWN)
        if quantity <= 0:
            raise BrokerValidationError("Amount is too small to buy a share fraction.")
        actual = (quantity * price).quantize(MONEY, rounding=ROUND_HALF_UP)
        return quantity, actual
    if request.quantity is not None:
        quantity = request.quantity.quantize(QTY, rounding=ROUND_DOWN)
        if quantity <= 0:
            raise BrokerValidationError("Quantity must be greater than zero.")
        return quantity, (quantity * price).quantize(MONEY, rounding=ROUND_HALF_UP)
    raise BrokerValidationError("Buy orders need an amount or quantity.")


def _fixed_income_buy_size(
    request: SubmitOrderRequest,
    price_per_face: Decimal,
    face_increment: Decimal,
) -> tuple[Decimal, Decimal]:
    if request.notional is not None:
        cash_budget = _positive_money(request.notional)
        quantity = _order_quantity(cash_budget / price_per_face, face_increment)
        if quantity <= 0:
            raise BrokerValidationError(
                "Amount is too small to buy the minimum fixed-income face value."
            )
        actual = (quantity * price_per_face).quantize(MONEY, rounding=ROUND_HALF_UP)
        return quantity, actual
    if request.quantity is not None:
        quantity = _order_quantity(request.quantity, face_increment)
        if quantity <= 0:
            raise BrokerValidationError("Face value must be greater than zero.")
        return quantity, (quantity * price_per_face).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
    raise BrokerValidationError("Buy orders need an amount or face value.")


def _order_quantity(value: Decimal, increment: Decimal | None = None) -> Decimal:
    quantity = Decimal(str(value))
    if increment is not None and increment > 0:
        units = (quantity / increment).to_integral_value(rounding=ROUND_DOWN)
        return (units * increment).quantize(QTY, rounding=ROUND_DOWN)
    return quantity.quantize(QTY, rounding=ROUND_DOWN)


def _positive_money(amount: Decimal) -> Decimal:
    value = Decimal(str(amount)).quantize(MONEY, rounding=ROUND_HALF_UP)
    if value <= 0:
        raise BrokerValidationError("Amount must be greater than zero.")
    return value


def _balances(account: RetailAccount) -> BrokerBalances:
    cash = account.cash_balance.quantize(MONEY)
    return BrokerBalances(
        cash=cash,
        buying_power=cash,
        currency=account.base_currency,
        pending=Decimal("0.00"),
    )


def _account_snapshot(account: RetailAccount) -> BrokerAccount:
    return BrokerAccount(
        provider=account.broker_provider,
        broker_account_id=account.broker_account_id,
        status=account.status,
        currency=account.base_currency,
        balances=_balances(account),
    )


def _order_snapshot(order: RetailOrder, symbol: str) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=order.broker_order_id,
        symbol=symbol,
        side=order.side,
        order_type=order.order_type,
        quantity=order.quantity,
        notional=order.notional,
        status=order.status,
        submitted_at=order.submitted_at,
        filled_at=order.filled_at,
        average_fill_price=order.average_fill_price,
        filled_quantity=order.filled_quantity,
        reject_reason=order.reject_reason,
        warnings=list(order.warnings or []),
    )


def _transaction_description(
    action: str, quantity: Decimal, instrument: Instrument
) -> str:
    if _looks_like_fixed_income(instrument):
        return f"{action} {quantity} face value of {instrument.ticker}."
    return f"{action} {quantity} {instrument.ticker}."


def _looks_like_fixed_income(instrument: Instrument) -> bool:
    return (instrument.sector or "").strip().lower() == "fixed income" or (
        instrument.asset_class or ""
    ).strip().lower() in {"bond", "cash_equivalent"}

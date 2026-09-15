from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class BrokerError(Exception):
    """Normalized brokerage failure. Provider-specific errors stay behind this."""


class BrokerValidationError(BrokerError):
    pass


class BrokerUnavailableError(BrokerError):
    pass


@dataclass(frozen=True)
class BrokerBalances:
    cash: Decimal
    buying_power: Decimal
    currency: str
    pending: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class BrokerAccount:
    provider: str
    broker_account_id: str
    status: str
    currency: str
    balances: BrokerBalances


@dataclass(frozen=True)
class BrokerPosition:
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal | None = None


@dataclass(frozen=True)
class SubmitOrderRequest:
    symbol: str
    side: str
    order_type: str = "market"
    quantity: Decimal | None = None
    notional: Decimal | None = None
    limit_price: Decimal | None = None


@dataclass(frozen=True)
class BrokerOrder:
    broker_order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal | None
    notional: Decimal | None
    status: str
    submitted_at: datetime
    filled_at: datetime | None = None
    average_fill_price: Decimal | None = None
    filled_quantity: Decimal | None = None
    reject_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BrokerTransaction:
    broker_reference: str
    entry_type: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    symbol: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class CashRequest:
    amount: Decimal
    currency: str = "USD"


class BrokerProvider(Protocol):
    provider_code: str

    async def create_account(self, *, user_id: str, currency: str = "USD") -> BrokerAccount:
        ...

    async def get_account(self, broker_account_id: str) -> BrokerAccount:
        ...

    async def get_balances(self, broker_account_id: str) -> BrokerBalances:
        ...

    async def get_positions(self, broker_account_id: str) -> list[BrokerPosition]:
        ...

    async def submit_order(
        self, broker_account_id: str, request: SubmitOrderRequest
    ) -> BrokerOrder:
        ...

    async def cancel_order(self, broker_account_id: str, broker_order_id: str) -> BrokerOrder:
        ...

    async def get_orders(self, broker_account_id: str) -> list[BrokerOrder]:
        ...

    async def get_transactions(self, broker_account_id: str) -> list[BrokerTransaction]:
        ...

    async def deposit(self, broker_account_id: str, request: CashRequest) -> BrokerBalances:
        ...

    async def withdraw(self, broker_account_id: str, request: CashRequest) -> BrokerBalances:
        ...

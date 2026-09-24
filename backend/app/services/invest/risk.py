from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.api.schemas.invest import InvestOrderCreate
from app.models import Instrument, RetailAccount
from app.services.invest.configuration import InvestRiskPolicy, parse_risk_policy
from app.services.invest.fixed_income import (
    FixedIncomeProduct,
    get_fixed_income_product,
)
from app.services.market_data.sessions import jurisdiction_for_ticker, session_for

MONEY = Decimal("0.01")
_DEFAULT_RISK_POLICY = parse_risk_policy()
SUPPORTED_ASSET_CLASSES = set(_DEFAULT_RISK_POLICY.supported_asset_classes)


@dataclass(frozen=True)
class RetailRiskCheck:
    code: str
    level: str
    message: str
    passed: bool


@dataclass(frozen=True)
class RetailRiskAssessment:
    checks: tuple[RetailRiskCheck, ...]

    @property
    def blockers(self) -> list[RetailRiskCheck]:
        return [check for check in self.checks if not check.passed]

    @property
    def warnings(self) -> list[str]:
        return [
            check.message
            for check in self.checks
            if check.passed and check.level in {"warning", "review"}
        ]


def evaluate_order_risk(
    *,
    account: RetailAccount,
    instrument: Instrument,
    payload: InvestOrderCreate,
    fixed_income_product: FixedIncomeProduct | None = None,
    policy: dict | InvestRiskPolicy | None = None,
    cash_notional: Decimal | None = None,
) -> RetailRiskAssessment:
    checks: list[RetailRiskCheck] = []
    risk_policy = (
        policy if isinstance(policy, InvestRiskPolicy) else parse_risk_policy(policy)
    )
    asset_class = instrument.asset_class.strip().lower()
    side = payload.side.strip().upper()
    order_type = payload.order_type.strip().lower()
    notional = _money(payload.amount) if payload.amount is not None else None

    checks.append(
        _check(
            "product_eligibility",
            asset_class in risk_policy.supported_asset_classes,
            f"{instrument.asset_class} is eligible for Pease Invest paper trading.",
            f"{instrument.asset_class} is not currently eligible for Pease Invest.",
        )
    )
    checks.append(
        _check(
            "order_type",
            order_type in risk_policy.allowed_order_types,
            "Market order accepted for the current paper provider.",
            "Pease Invest paper V1 only accepts market orders.",
        )
    )
    checks.append(
        _check(
            "side",
            side in risk_policy.allowed_sides,
            "Order side accepted.",
            "Order side must be BUY or SELL.",
        )
    )

    buy_cash = cash_notional if cash_notional is not None else notional
    if side == "BUY" and buy_cash is not None:
        checks.append(
            _check(
                "buying_power",
                buy_cash <= account.cash_balance,
                "Cash check passed.",
                "Not enough buying power for this order.",
            )
        )
        if (
            account.cash_balance > 0
            and buy_cash / account.cash_balance
            >= risk_policy.buying_power_concentration_warn_pct
        ):
            checks.append(
                RetailRiskCheck(
                    code="concentration_review",
                    level="warning",
                    message="This paper order uses at least half of available cash.",
                    passed=True,
                )
            )

    product = fixed_income_product or get_fixed_income_product(instrument.ticker)
    if product is None and asset_class not in {"bond", "cash_equivalent"}:
        session_state = session_for(jurisdiction_for_ticker(instrument.ticker))
        if not session_state.is_open:
            checks.append(
                RetailRiskCheck(
                    code="market_hours",
                    level="warning",
                    message=(
                        f"{session_state.label} is closed. Paper still fills at the last mark."
                    ),
                    passed=True,
                )
            )
    if product is not None:
        order_value = notional
        if order_value is None and payload.quantity is not None and side == "BUY":
            order_value = Decimal(str(payload.quantity)).quantize(
                MONEY, rounding=ROUND_HALF_UP
            )
        if order_value is not None and side == "BUY":
            checks.append(
                _check(
                    "minimum_order",
                    order_value >= product.minimum_order_amount,
                    "Fixed-income minimum order check passed.",
                    f"Minimum order for {product.ticker} is {product.currency} {product.minimum_order_amount}.",
                )
            )
        checks.append(
            _check(
                "fixed_income_execution",
                product.trade_status == "paper_tradable",
                "Fixed-income paper execution is enabled.",
                "Fixed-income product is watch-only and cannot be paper-traded yet.",
            )
        )
        checks.append(
            RetailRiskCheck(
                code="fixed_income_quote_price",
                level="review",
                message=(
                    "Paper fill uses the fixed-income quote service mark, including "
                    "settlement and accrued-interest assumptions."
                ),
                passed=True,
            )
        )
        if (
            risk_policy.fixed_income_fx_warning_enabled
            and product.currency != account.base_currency
        ):
            checks.append(
                RetailRiskCheck(
                    code="fx_model_warning",
                    level="warning",
                    message=(
                        f"{product.ticker} is denominated in {product.currency}; "
                        f"paper cash is {account.base_currency} and converts at the stored FX rate."
                    ),
                    passed=True,
                )
            )

    return RetailRiskAssessment(tuple(checks))


def _check(
    code: str, passed: bool, pass_message: str, fail_message: str
) -> RetailRiskCheck:
    return RetailRiskCheck(
        code=code,
        level="info" if passed else "blocker",
        message=pass_message if passed else fail_message,
        passed=passed,
    )


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)

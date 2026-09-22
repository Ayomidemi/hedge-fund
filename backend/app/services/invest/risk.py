from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.api.schemas.invest import InvestOrderCreate
from app.models import Instrument, RetailAccount
from app.services.invest.configuration import default_invest_setting
from app.services.invest.fixed_income import FixedIncomeProduct, get_fixed_income_product

MONEY = Decimal("0.01")
_DEFAULT_RISK_POLICY = default_invest_setting("risk_policy")
SUPPORTED_ASSET_CLASSES = set(_DEFAULT_RISK_POLICY["supported_asset_classes"])


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
    policy: dict | None = None,
) -> RetailRiskAssessment:
    checks: list[RetailRiskCheck] = []
    risk_policy = _risk_policy(policy)
    asset_class = instrument.asset_class.strip().lower()
    side = payload.side.strip().upper()
    order_type = payload.order_type.strip().lower()
    notional = _money(payload.amount) if payload.amount is not None else None

    checks.append(
        _check(
            "product_eligibility",
            asset_class in risk_policy["supported_asset_classes"],
            f"{instrument.asset_class} is eligible for Pease Invest paper trading.",
            f"{instrument.asset_class} is not currently eligible for Pease Invest.",
        )
    )
    checks.append(
        _check(
            "order_type",
            order_type in risk_policy["allowed_order_types"],
            "Market order accepted for the current paper provider.",
            "Pease Invest paper V1 only accepts market orders.",
        )
    )
    checks.append(
        _check(
            "side",
            side in risk_policy["allowed_sides"],
            "Order side accepted.",
            "Order side must be BUY or SELL.",
        )
    )

    if side == "BUY" and notional is not None:
        checks.append(
            _check(
                "buying_power",
                notional <= account.cash_balance,
                "Cash check passed.",
                "Not enough buying power for this order.",
            )
        )
        if (
            account.cash_balance > 0
            and notional / account.cash_balance
            >= risk_policy["buying_power_concentration_warn_pct"]
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
                code="fixed_income_model_price",
                level="review",
                message=(
                    "Paper fill uses an indicative fixed-income model price, including "
                    "settlement and accrued-interest assumptions."
                ),
                passed=True,
            )
        )
        if (
            risk_policy["fixed_income_fx_warning_enabled"]
            and product.currency != account.base_currency
        ):
            checks.append(
                RetailRiskCheck(
                    code="fx_model_warning",
                    level="warning",
                    message=(
                        f"{product.ticker} is denominated in {product.currency}; "
                        f"paper cash remains recorded in {account.base_currency} without live FX conversion."
                    ),
                    passed=True,
                )
            )

    return RetailRiskAssessment(tuple(checks))


def _risk_policy(policy: dict | None) -> dict:
    source = policy or _DEFAULT_RISK_POLICY
    return {
        "supported_asset_classes": {
            str(item).strip().lower()
            for item in source.get("supported_asset_classes", SUPPORTED_ASSET_CLASSES)
        },
        "allowed_sides": {
            str(item).strip().upper()
            for item in source.get("allowed_sides", ["BUY", "SELL"])
        },
        "allowed_order_types": {
            str(item).strip().lower()
            for item in source.get("allowed_order_types", ["market"])
        },
        "buying_power_concentration_warn_pct": Decimal(
            str(source.get("buying_power_concentration_warn_pct", "0.50"))
        ),
        "fixed_income_fx_warning_enabled": bool(
            source.get("fixed_income_fx_warning_enabled", True)
        ),
    }


def _check(code: str, passed: bool, pass_message: str, fail_message: str) -> RetailRiskCheck:
    return RetailRiskCheck(
        code=code,
        level="info" if passed else "blocker",
        message=pass_message if passed else fail_message,
        passed=passed,
    )


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)

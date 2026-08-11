from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


@dataclass(frozen=True)
class SecFundamentals:
    revenue_growth_pct: Decimal | None = None
    earnings_growth_pct: Decimal | None = None
    free_cash_flow_yield_pct: Decimal | None = None
    net_margin_pct: Decimal | None = None
    debt_to_equity: Decimal | None = None
    pe_ratio: Decimal | None = None
    source_period: str | None = None
    used_tags: dict[str, str] | None = None


@dataclass(frozen=True)
class FactValue:
    end: str
    filed: str
    value: Decimal
    tag: str


REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]
NET_INCOME_TAGS = ["NetIncomeLoss", "ProfitLoss"]
OPERATING_CASH_FLOW_TAGS = ["NetCashProvidedByUsedInOperatingActivities"]
CAPEX_TAGS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
]
CURRENT_DEBT_TAGS = [
    "LongTermDebtAndFinanceLeaseObligationsCurrent",
    "LongTermDebtCurrent",
    "DebtCurrent",
    "ShortTermBorrowings",
]
NONCURRENT_DEBT_TAGS = [
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
    "LongTermDebtNoncurrent",
    "LongTermDebt",
]
TOTAL_DEBT_TAGS = [
    "LongTermDebtAndFinanceLeaseObligations",
    "DebtAndFinanceLeaseObligations",
]
EQUITY_TAGS = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
]


def calculate_sec_fundamentals(
    companyfacts: dict,
    market_cap: Decimal | None,
) -> SecFundamentals:
    revenue_values = _annual_values(companyfacts, REVENUE_TAGS, "USD")
    income_values = _annual_values(companyfacts, NET_INCOME_TAGS, "USD")
    operating_cash_flow = _latest_annual(companyfacts, OPERATING_CASH_FLOW_TAGS, "USD")
    capex = _latest_annual(companyfacts, CAPEX_TAGS, "USD")
    current_debt = _latest_instant(companyfacts, CURRENT_DEBT_TAGS, "USD")
    noncurrent_debt = _latest_instant(companyfacts, NONCURRENT_DEBT_TAGS, "USD")
    total_debt = _latest_instant(companyfacts, TOTAL_DEBT_TAGS, "USD")
    equity = _latest_instant(companyfacts, EQUITY_TAGS, "USD")

    latest_revenue = revenue_values[-1] if revenue_values else None
    latest_income = income_values[-1] if income_values else None
    previous_revenue = revenue_values[-2] if len(revenue_values) >= 2 else None
    previous_income = income_values[-2] if len(income_values) >= 2 else None

    debt_value = (
        total_debt.value
        if total_debt is not None
        else _sum_fact_values(
            current_debt,
            noncurrent_debt,
        )
    )
    free_cash_flow = _free_cash_flow(operating_cash_flow, capex)

    used_tags = {
        "revenue": latest_revenue.tag if latest_revenue else "",
        "net_income": latest_income.tag if latest_income else "",
        "operating_cash_flow": operating_cash_flow.tag if operating_cash_flow else "",
        "capex": capex.tag if capex else "",
        "debt": total_debt.tag if total_debt else "current_debt + noncurrent_debt",
        "equity": equity.tag if equity else "",
    }

    return SecFundamentals(
        revenue_growth_pct=_growth_pct(latest_revenue, previous_revenue),
        earnings_growth_pct=_growth_pct(latest_income, previous_income),
        free_cash_flow_yield_pct=_ratio_pct(free_cash_flow, market_cap),
        net_margin_pct=_ratio_pct(
            latest_income.value if latest_income else None,
            latest_revenue.value if latest_revenue else None,
        ),
        debt_to_equity=_ratio(debt_value, equity.value if equity else None),
        pe_ratio=_ratio(market_cap, latest_income.value if latest_income else None),
        source_period=latest_revenue.end if latest_revenue else None,
        used_tags={key: value for key, value in used_tags.items() if value},
    )


def _annual_values(companyfacts: dict, tags: list[str], unit: str) -> list[FactValue]:
    for tag in tags:
        values = _facts_for_tag(companyfacts, tag, unit)
        annual = [
            FactValue(
                end=str(item.get("end") or ""),
                filed=str(item.get("filed") or ""),
                value=value,
                tag=tag,
            )
            for item in values
            if _is_annual_fact(item)
            and (value := _decimal(item.get("val"))) is not None
        ]
        annual = _dedupe_by_period(annual)
        if annual:
            return annual
    return []


def _latest_annual(companyfacts: dict, tags: list[str], unit: str) -> FactValue | None:
    values = _annual_values(companyfacts, tags, unit)
    return values[-1] if values else None


def _latest_instant(companyfacts: dict, tags: list[str], unit: str) -> FactValue | None:
    for tag in tags:
        values = [
            FactValue(
                end=str(item.get("end") or ""),
                filed=str(item.get("filed") or ""),
                value=value,
                tag=tag,
            )
            for item in _facts_for_tag(companyfacts, tag, unit)
            if _is_filed_fact(item) and (value := _decimal(item.get("val"))) is not None
        ]
        values = _dedupe_by_period(values)
        if values:
            return values[-1]
    return None


def _facts_for_tag(companyfacts: dict, tag: str, unit: str) -> list[dict]:
    facts = companyfacts.get("facts", {})
    us_gaap = facts.get("us-gaap", {})
    tag_payload = us_gaap.get(tag, {})
    units = tag_payload.get("units", {})
    values = units.get(unit)
    return values if isinstance(values, list) else []


def _is_annual_fact(item: dict) -> bool:
    form = str(item.get("form") or "")
    fiscal_period = str(item.get("fp") or "")
    return form == "10-K" and fiscal_period == "FY" and _is_filed_fact(item)


def _is_filed_fact(item: dict) -> bool:
    return bool(item.get("end") and item.get("filed"))


def _dedupe_by_period(values: list[FactValue]) -> list[FactValue]:
    by_end: dict[str, FactValue] = {}
    for value in sorted(values, key=lambda item: (item.end, item.filed)):
        by_end[value.end] = value
    return list(sorted(by_end.values(), key=lambda item: item.end))


def _growth_pct(latest: FactValue | None, previous: FactValue | None) -> Decimal | None:
    if latest is None or previous is None or previous.value == 0:
        return None
    return _quantize(
        ((latest.value - previous.value) / abs(previous.value)) * Decimal("100")
    )


def _ratio_pct(
    numerator: Decimal | None, denominator: Decimal | None
) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _quantize((numerator / denominator) * Decimal("100"))


def _ratio(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return _quantize(numerator / denominator)


def _free_cash_flow(
    operating_cash_flow: FactValue | None,
    capex: FactValue | None,
) -> Decimal | None:
    if operating_cash_flow is None or capex is None:
        return None
    return operating_cash_flow.value - abs(capex.value)


def _sum_fact_values(*values: FactValue | None) -> Decimal | None:
    present = [value.value for value in values if value is not None]
    if not present:
        return None
    return sum(present, Decimal("0"))


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

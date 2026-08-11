from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


PERCENT = Decimal("100")
MONEY = Decimal("0.01")


@dataclass(frozen=True)
class PositionSnapshot:
    ticker: str
    asset_class: str
    sector: str | None
    market_value: Decimal


@dataclass(frozen=True)
class RiskLimitSnapshot:
    name: str
    limit_type: str
    threshold_value: Decimal
    unit: str
    scope: str
    severity: str


@dataclass(frozen=True)
class RiskCheckSnapshot:
    name: str
    limit_type: str
    observed_value: Decimal
    threshold_value: Decimal
    unit: str
    passed: bool
    severity: str
    message: str


DEFAULT_RISK_LIMITS = [
    RiskLimitSnapshot(
        name="Maximum single-equity position",
        limit_type="max_single_equity_position_pct",
        threshold_value=Decimal("5"),
        unit="percent",
        scope="position",
        severity="warning",
    ),
    RiskLimitSnapshot(
        name="Maximum ETF position",
        limit_type="max_etf_position_pct",
        threshold_value=Decimal("25"),
        unit="percent",
        scope="position",
        severity="warning",
    ),
    RiskLimitSnapshot(
        name="Maximum sector exposure",
        limit_type="max_sector_exposure_pct",
        threshold_value=Decimal("30"),
        unit="percent",
        scope="portfolio",
        severity="warning",
    ),
    RiskLimitSnapshot(
        name="Minimum cash allocation",
        limit_type="min_cash_allocation_pct",
        threshold_value=Decimal("15"),
        unit="percent",
        scope="portfolio",
        severity="warning",
    ),
    RiskLimitSnapshot(
        name="Uncovered leverage",
        limit_type="max_leverage_pct",
        threshold_value=Decimal("0"),
        unit="percent",
        scope="portfolio",
        severity="halt",
    ),
]


def money(value: Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(value)

    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def percent(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")

    return ((numerator / denominator) * PERCENT).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def calculate_nav(cash_balance: Decimal, positions: list[PositionSnapshot]) -> Decimal:
    return money(cash_balance + sum(position.market_value for position in positions))


def group_exposure_by_asset_class(
    positions: list[PositionSnapshot],
    nav: Decimal,
) -> dict[str, Decimal]:
    exposures: dict[str, Decimal] = {}
    for position in positions:
        exposures[position.asset_class] = (
            exposures.get(position.asset_class, Decimal("0")) + position.market_value
        )

    return {
        asset_class: percent(value, nav)
        for asset_class, value in sorted(exposures.items())
    }


def group_exposure_by_sector(
    positions: list[PositionSnapshot],
    nav: Decimal,
) -> dict[str, Decimal]:
    exposures: dict[str, Decimal] = {}
    for position in positions:
        sector = position.sector or "Unclassified"
        exposures[sector] = exposures.get(sector, Decimal("0")) + position.market_value

    return {sector: percent(value, nav) for sector, value in sorted(exposures.items())}


def evaluate_risk_limits(
    cash_balance: Decimal,
    positions: list[PositionSnapshot],
    nav: Decimal,
    risk_limits: list[RiskLimitSnapshot],
) -> list[RiskCheckSnapshot]:
    checks: list[RiskCheckSnapshot] = []

    for limit in risk_limits:
        if limit.limit_type == "max_single_equity_position_pct":
            equity_positions = [
                position for position in positions if position.asset_class == "equity"
            ]
            if not equity_positions:
                checks.append(
                    _passed_check(limit, Decimal("0"), "No single-equity exposure.")
                )
                continue

            largest = max(equity_positions, key=lambda position: position.market_value)
            observed = percent(largest.market_value, nav)
            checks.append(
                _threshold_check(
                    limit,
                    observed,
                    observed <= limit.threshold_value,
                    f"{largest.ticker} is {observed}% of NAV.",
                )
            )

        elif limit.limit_type == "max_etf_position_pct":
            etf_positions = [
                position for position in positions if position.asset_class == "etf"
            ]
            if not etf_positions:
                checks.append(_passed_check(limit, Decimal("0"), "No ETF exposure."))
                continue

            largest = max(etf_positions, key=lambda position: position.market_value)
            observed = percent(largest.market_value, nav)
            checks.append(
                _threshold_check(
                    limit,
                    observed,
                    observed <= limit.threshold_value,
                    f"{largest.ticker} is {observed}% of NAV.",
                )
            )

        elif limit.limit_type == "max_sector_exposure_pct":
            sector_exposures = group_exposure_by_sector(positions, nav)
            if not sector_exposures:
                checks.append(_passed_check(limit, Decimal("0"), "No sector exposure."))
                continue

            sector, observed = max(sector_exposures.items(), key=lambda item: item[1])
            checks.append(
                _threshold_check(
                    limit,
                    observed,
                    observed <= limit.threshold_value,
                    f"{sector} exposure is {observed}% of NAV.",
                )
            )

        elif limit.limit_type == "min_cash_allocation_pct":
            observed = percent(cash_balance, nav)
            checks.append(
                _threshold_check(
                    limit,
                    observed,
                    observed >= limit.threshold_value,
                    f"Cash is {observed}% of NAV.",
                )
            )

        elif limit.limit_type == "max_leverage_pct":
            observed = (
                Decimal("0") if cash_balance >= 0 else percent(abs(cash_balance), nav)
            )
            checks.append(
                _threshold_check(
                    limit,
                    observed,
                    observed <= limit.threshold_value,
                    f"Implied cash borrowing is {observed}% of NAV.",
                )
            )

    return checks


def _passed_check(
    limit: RiskLimitSnapshot,
    observed_value: Decimal,
    message: str,
) -> RiskCheckSnapshot:
    return RiskCheckSnapshot(
        name=limit.name,
        limit_type=limit.limit_type,
        observed_value=observed_value,
        threshold_value=limit.threshold_value,
        unit=limit.unit,
        passed=True,
        severity=limit.severity,
        message=message,
    )


def _threshold_check(
    limit: RiskLimitSnapshot,
    observed_value: Decimal,
    passed: bool,
    message: str,
) -> RiskCheckSnapshot:
    return RiskCheckSnapshot(
        name=limit.name,
        limit_type=limit.limit_type,
        observed_value=observed_value,
        threshold_value=limit.threshold_value,
        unit=limit.unit,
        passed=passed,
        severity=limit.severity,
        message=message,
    )

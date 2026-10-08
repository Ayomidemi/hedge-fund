"""Versioned Capital profiles. Account limits remain hard ceilings."""
VERSION = 3
COMMON = dict(version=VERSION, stop_loss_pct=3, take_profit_pct=6,
              slippage_bps=10, fee_bps=5, quote_max_age_seconds=120,
              order_ttl_minutes=30, min_history_returns=60,
              max_liquidity_days=1, max_participation_pct=1,
              correlation_threshold=0.8)
PROFILES = {
    "low": dict(max_position_pct=3, max_etf_position_pct=5, risk_per_trade_pct=0.25,
                max_positions=3, cash_reserve_pct=60, max_drawdown_pct=3,
                max_sector_pct=10, max_aggregate_risk_pct=0.75, max_daily_loss_pct=1,
                max_correlated_exposure_pct=6, max_portfolio_volatility_pct=20,
                max_var_95_pct=2, max_expected_shortfall_95_pct=3, max_stress_loss_pct=3),
    "medium": dict(max_position_pct=10, max_etf_position_pct=10, risk_per_trade_pct=0.5,
                   max_positions=5, cash_reserve_pct=20, max_drawdown_pct=5,
                   max_sector_pct=20, max_aggregate_risk_pct=1.5, max_daily_loss_pct=2,
                   max_correlated_exposure_pct=15, max_portfolio_volatility_pct=30,
                   max_var_95_pct=4, max_expected_shortfall_95_pct=6, max_stress_loss_pct=5),
    "high": dict(max_position_pct=15, max_etf_position_pct=20, risk_per_trade_pct=1,
                 max_positions=8, cash_reserve_pct=20, max_drawdown_pct=8,
                 max_sector_pct=25, max_aggregate_risk_pct=3, max_daily_loss_pct=3,
                 max_correlated_exposure_pct=20, max_portfolio_volatility_pct=40,
                 max_var_95_pct=5, max_expected_shortfall_95_pct=8, max_stress_loss_pct=8),
}


def profile_policy(profile="medium"):
    if profile not in PROFILES:
        raise ValueError("Choose low, medium or high risk.")
    return {**COMMON, **PROFILES[profile], "profile": profile}


def apply_account_limits(policy, limits):
    result = dict(policy)
    mapping = {"max_single_equity_position_pct": "max_position_pct",
               "max_etf_position_pct": "max_etf_position_pct",
               "max_sector_exposure_pct": "max_sector_pct",
               "min_cash_allocation_pct": "cash_reserve_pct"}
    for limit in limits:
        key = mapping.get(limit.limit_type, limit.limit_type)
        if key not in result:
            continue
        value = float(limit.threshold_value)
        result[key] = (max if key == "cash_reserve_pct" else min)(result[key], value)
    return result


def position_cap(policy, asset_class):
    return policy.get("max_etf_position_pct", policy["max_position_pct"]) if asset_class == "etf" else policy["max_position_pct"]

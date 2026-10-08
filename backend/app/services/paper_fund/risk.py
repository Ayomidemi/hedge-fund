"""Pure, repeatable checks of proposed exposure; never sends provider requests."""
from decimal import Decimal as D
from app.services.risk.risk_centre import (
    PortfolioRiskState, RiskPosition, compute_portfolio_market_stats,
    standard_stress_scenarios, run_stress_scenario,
)


def entry_risk(run, orders, candidate, instruments, histories, now):
    from app.services.paper_fund.engine import fee
    active = [o for o in orders if o.status in {"open", "pending"} and o is not candidate]
    active += list(getattr(run, "_external_holdings", [])) + [candidate]
    holdings = {}
    pending_cost = D("0")
    for order in active:
        instrument = instruments.get(order.instrument_id)
        if instrument is None:
            return {"approved": False, "reasons": ["Instrument metadata is unavailable."]}
        price = order.limit_price if order.status == "pending" else (order.mark_price or order.entry_price)
        value = price * order.quantity
        if order.status == "pending":
            pending_cost += value + fee(value, run.policy)
        previous = holdings.get(instrument.ticker)
        holdings[instrument.ticker] = RiskPosition(instrument.id, instrument.ticker, instrument.name,
            instrument.asset_class, instrument.sector, D(order.quantity) + (previous.quantity if previous else 0),
            price, value + (previous.market_value if previous else 0), D("0"))
    invested = sum((p.market_value for p in holdings.values()), D("0"))
    cash = run.cash_balance - pending_cost
    state = PortfolioRiskState(run.portfolio_id, "Capital", now, now.date(), cash + invested,
                               cash, invested, list(holdings.values()), effective_policy=run.policy)
    stats = compute_portfolio_market_stats(state, histories)
    reasons = []
    metrics = {"max_portfolio_volatility_pct": stats.portfolio_volatility_pct,
               "max_var_95_pct": stats.var_95_pct, "max_expected_shortfall_95_pct": stats.expected_shortfall_95_pct,
               "max_liquidity_days": stats.liquidity_days}
    labels = {"max_portfolio_volatility_pct": "Portfolio volatility", "max_var_95_pct": "Daily loss estimate (95%)",
              "max_expected_shortfall_95_pct": "Average tail loss (95%)", "max_liquidity_days": "Estimated liquidation time"}
    for key, value in metrics.items():
        if value is None:
            reasons.append(f"{labels[key]}: insufficient current history or volume.")
        elif value > D(str(run.policy[key])):
            unit = " days" if key == "max_liquidity_days" else "%"
            reasons.append(f"{labels[key]}: {value}{unit} exceeds {run.policy[key]}{unit}.")
    # Connected correlation groups capture exposures across sector labels.
    groups = [{ticker} for ticker in holdings]
    for pair in stats.correlation_pairs or []:
        if pair.correlation < D(str(run.policy["correlation_threshold"])):
            continue
        connected = [g for g in groups if pair.ticker_a in g or pair.ticker_b in g]
        groups = [g for g in groups if g not in connected] + [set().union(*connected)]
    for group in groups:
        exposure = sum((holdings[t].market_value for t in group), D("0"))
        if len(group) > 1 and exposure > state.nav * D(str(run.policy["max_correlated_exposure_pct"])) / 100:
            reasons.append("Correlated exposure exceeds the profile limit: " + ", ".join(sorted(group)))
    losses = [-run_stress_scenario(state, scenario).nav_impact_pct
              for scenario in standard_stress_scenarios(state) if scenario["scenario_type"] != "cash"]
    stress_loss = max(losses, default=D("0"))
    if stress_loss > D(str(run.policy["max_stress_loss_pct"])):
        reasons.append(f"Stress loss {stress_loss}% exceeds the profile limit.")
    # Capacity uses observed historical volume, not a claim of executable depth.
    candidate_instrument = instruments[candidate.instrument_id]
    bars = sorted([b for b in histories.get(candidate_instrument.ticker, []) if b.bar_date < now.date()], key=lambda b: b.bar_date)[-20:]
    volumes = [b.volume for b in bars if b.volume is not None and b.volume >= 0]
    capacity = (D(sum(volumes)) / len(volumes) * D(str(run.policy["max_participation_pct"])) / 100) if len(volumes) >= 15 else D("0")
    if candidate.quantity > capacity:
        reasons.append("Order exceeds measured daily volume capacity or volume coverage is incomplete.")
    return {"approved": not reasons, "reasons": reasons, "policy_version": run.policy["version"],
            "limits": dict(run.policy),
            "profile": run.policy["profile"], "checked_at": now.isoformat(),
            "metrics": {k: str(v) if v is not None else None for k, v in metrics.items()},
            "stress_loss_pct": str(stress_loss), "history_notes": stats.notes,
            "event_data": "not available; event-specific risk is not modeled"}

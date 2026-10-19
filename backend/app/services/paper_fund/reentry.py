"""Account-locked attempt policy. One fresh signal authorizes at most one intent."""
from datetime import timedelta
from decimal import Decimal
from app.services.paper_fund.calendar import NEW_YORK


def reentry_rejection(run, orders, instrument_id, snapshot, now, equity):
    prior = [o for o in orders if o.instrument_id == instrument_id]
    if any(o.status in {'pending','open'} for o in prior):
        return 'An entry or position is already active for this instrument.'
    signal_id = str(snapshot.id)
    if any(str(getattr(o, 'signal_id', None) or (o.evidence or {}).get('radar_snapshot_id')) == signal_id for o in prior):
        return 'This radar signal already has an immutable order attempt.'
    closed = [o for o in prior if o.closed_at is not None]
    if closed:
        last = max(o.closed_at for o in closed)
        if now < last + timedelta(minutes=run.policy['reentry_cooldown_minutes']):
            return 'Re-entry cooldown is active after the previous exit.'
        if snapshot.source_as_of is None or snapshot.source_as_of <= last or snapshot.as_of <= last:
            return 'Re-entry requires a new observation after the previous exit.'
    day = now.astimezone(NEW_YORK).date()
    attempts = [o for o in prior if o.submitted_at.astimezone(NEW_YORK).date() == day]
    entries = [o for o in prior if o.opened_at and o.opened_at.astimezone(NEW_YORK).date() == day]
    if len(attempts) >= run.policy['max_symbol_attempts_per_day']:
        return 'Daily order-attempt limit reached for this instrument.'
    if len(entries) >= run.policy['max_symbol_entries_per_day']:
        return 'Daily filled-entry limit reached for this instrument.'
    losses = sum((-min(o.realized_pnl, Decimal(0)) for o in closed
                  if o.closed_at.astimezone(NEW_YORK).date() == day), Decimal(0))
    if losses >= equity * Decimal(str(run.policy['risk_per_trade_pct'])) / 100:
        return 'Daily loss budget reached for this instrument.'
    return None

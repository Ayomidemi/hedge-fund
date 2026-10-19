"""Review-specific performance and observed coverage, separate from lifetime P/L."""
from datetime import timedelta, timezone
from decimal import Decimal
from app.services.paper_fund.calendar import session_bounds


def market_minutes(start, end):
    cursor = start.astimezone(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0)
    seconds = 0
    while cursor.date() <= end.date():
        bounds = session_bounds(cursor)
        if bounds:
            seconds += max(0, (min(end, bounds[1]) - max(start, bounds[0])).total_seconds())
        cursor += timedelta(days=1)
    return seconds / 60


def review_diagnostics(run, book, history, now):
    end = min(now, run.completed_at or now)
    times = [run.started_at, *[s.recorded_at for s in history if run.started_at <= s.recorded_at <= end], end]
    gaps = [market_minutes(a, b) for a, b in zip(times, times[1:]) if (b-a).total_seconds() > 900]
    gaps = [gap for gap in gaps if gap > 15]
    baseline = run.net_contributions_at_start
    pnl = book.state['equity'] - run.starting_cash - (book.net_contributions-baseline) if baseline is not None else None
    return {'review_pnl': str(pnl.quantize(Decimal('.01'))) if pnl is not None else None,
            'review_return_pct': str((pnl/run.starting_cash*100).quantize(Decimal('.0001'))) if pnl is not None else None,
            'invested_value': str((book.state['equity']-book.cash).quantize(Decimal('.01'))),
            'cash_pct': str((book.cash/book.state['equity']*100).quantize(Decimal('.01'))) if book.state['equity']>0 else None,
            'market_gap_count': len(gaps), 'longest_market_gap_minutes': round(max(gaps, default=0), 1),
            'coverage_note': 'Gaps between recorded observations; this is not a precise uptime measure.'}

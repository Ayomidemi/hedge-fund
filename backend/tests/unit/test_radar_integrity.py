from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from app.services.market_radar.scoring import RadarCandidate, score_candidate
from app.services.market_radar.priority import assign_priority
from app.services.market_radar.scan import (
    _apply_historical_evidence, _apply_quotes, _apply_sector_relative,
    _apply_scan_deltas, _assess_observations,
    _merge, _quote_usable_for_radar, _select_working_set,
)

NOW = datetime(2026, 10, 13, 15, tzinfo=timezone.utc)


def candidate(ticker="TEST", **kwargs):
    return RadarCandidate(ticker=ticker, name=ticker, jurisdiction="US", **kwargs)


def bars():
    dates, day = [], NOW.date() - timedelta(days=1)
    while len(dates) < 30:
        if day.weekday() < 5:
            dates.append(day)
        day -= timedelta(days=1)
    return [SimpleNamespace(instrument_id=1, bar_date=day, source="tiingo",
        close_price=D(100 + index % 3), adjusted_close_price=D(100 + index % 3),
        volume=1000, raw_payload={}) for index, day in enumerate(reversed(dates))]


class RadarHistoryIntegrityTests(IsolatedAsyncioTestCase):
    async def evaluate(self, history, **kwargs):
        item = candidate(**kwargs)
        session = SimpleNamespace(scalars=AsyncMock(return_value=history))
        with patch('app.services.market_radar.scan._load_instruments_by_quote_symbol',
                   new=AsyncMock(return_value={'TEST': SimpleNamespace(id=1)})):
            await _apply_historical_evidence(session, [item], now=NOW)
        return item

    async def test_duplicate_sources_and_incomplete_days_do_not_change_baseline(self):
        history = bars()
        clean = await self.evaluate(history, change_pct=D('5'), volume=2000, price=D('105'))
        dirty = []
        for bar in history:
            dirty.extend([bar, SimpleNamespace(**{**vars(bar), 'source':'live', 'close_price':D('20'), 'volume':1})])
        dirty.append(SimpleNamespace(**{**vars(history[-1]), 'bar_date':NOW.date(), 'close_price':D('1000'), 'volume':999999}))
        dirty.append(SimpleNamespace(**{**vars(history[-1]), 'bar_date':NOW.date()+timedelta(days=1), 'close_price':D('9000')}))
        actual = await self.evaluate(dirty, change_pct=D('5'), volume=2000, price=D('105'))
        for key in ('price_return_zscore', 'average_volume', 'avg_dollar_volume', 'bar_count'):
            self.assertEqual(actual.evidence[key], clean.evidence[key], key)

    async def test_split_adjusted_returns_match_unsplit_history(self):
        history = bars()
        clean = await self.evaluate(history, change_pct=D('5'))
        split = [SimpleNamespace(**{**vars(bar), 'close_price':bar.close_price * (2 if index < 15 else 1)})
                 for index, bar in enumerate(history)]
        actual = await self.evaluate(split, change_pct=D('5'))
        self.assertEqual(actual.evidence['price_return_zscore'], clean.evidence['price_return_zscore'])

    async def test_old_daily_return_does_not_become_current_session_change(self):
        item = await self.evaluate(bars())
        self.assertIsNone(item.change_pct)
        self.assertNotIn('price_return_zscore', item.evidence)

    async def test_tiny_history_cannot_produce_anomaly_zscore(self):
        item = await self.evaluate(bars()[-3:], change_pct=D('8'))
        self.assertNotIn('price_return_zscore', item.evidence)
        self.assertIn('history_gap', item.evidence)

    async def test_dollar_volume_uses_historical_prices_and_includes_zero_volume_days(self):
        history = bars()
        for index, bar in enumerate(history):
            bar.volume = 0 if index % 2 else 1000
        item = await self.evaluate(history, price=D('1000'), volume=500)
        expected = sum(bar.close_price * bar.volume for bar in history) / len(history)
        self.assertEqual(D(item.evidence['avg_dollar_volume']), expected)
        self.assertEqual(item.avg_volume, 500)


class RadarObservationIntegrityTests(TestCase):
    def test_assessment_keeps_verified_and_marks_discovery_as_unverified(self):
        verified = candidate(price=D('105'), change_pct=D('5'), source_as_of=NOW,
                             evidence={'quote_as_of':NOW.isoformat()})
        discovery = candidate('DISC', price=D('105'), change_pct=D('5'), source_as_of=NOW)
        _assess_observations([verified, discovery], NOW)
        self.assertIsNone(verified.stale_reason)
        self.assertEqual(verified.evidence['observation_quality'], 'verified_timestamp')
        self.assertEqual(discovery.evidence['observation_quality'], 'unverified')
        self.assertIsNotNone(discovery.stale_reason)

    def test_new_quote_does_not_reuse_old_session_return_or_volume(self):
        item = candidate(price=D('100'), change_pct=D('20'), volume=10000)
        quote = SimpleNamespace(price=D('101'), previous_close=None, change_pct=None,
                                volume=None, source='tiingo', as_of=NOW, currency='USD')
        _apply_quotes({'TEST':item}, {'TEST':quote})
        self.assertIsNone(item.change_pct)
        self.assertIsNone(item.volume)
        quote.previous_close = D('100')
        _apply_quotes({'TEST':item}, {'TEST':quote})
        self.assertEqual(item.change_pct, D('1'))

    def test_scan_return_changes_are_not_compared_across_session_dates(self):
        item = candidate(price=D('100'), change_pct=D('5'), source_as_of=NOW,
            evidence={'prior_scan_as_of':(NOW-timedelta(days=1)).isoformat(),
                      'prior_scan_price':'90', 'prior_scan_change_pct':'-10'})
        _apply_scan_deltas([item])
        self.assertNotIn('scan_delta_change_pct', item.evidence)
        self.assertEqual(item.evidence['scan_comparison_gap'], 'different_session_date')

    def test_discovery_label_cannot_survive_as_measured_volume_confirmation(self):
        item = candidate(change_pct=D('6'), flags=['unusual_volume'])
        score_candidate(item)
        self.assertNotIn('unusual_volume', item.flags)

    def test_unknown_or_stale_observation_cannot_have_active_priority(self):
        for reason in ('stale quote', 'missing current observation'):
            item = candidate(price=D('100'), change_pct=D('15'), volume=10000,
                             avg_volume=1000, stale_reason=reason)
            score_candidate(item)
            assign_priority(item)
            self.assertIsNone(item.radar_priority)

    def test_universe_cache_rejects_old_same_day_and_future_observations(self):
        for at in (NOW-timedelta(hours=2), NOW+timedelta(seconds=1)):
            quote = SimpleNamespace(is_stale=False, as_of=at)
            self.assertFalse(_quote_usable_for_radar(quote, NOW, candidate=candidate()))

    def test_older_quote_cannot_replace_newer_observation(self):
        item = candidate(price=D('100'), source='tiingo', source_as_of=NOW,
                         evidence={'quote_as_of':NOW.isoformat()})
        older = SimpleNamespace(price=D('90'), previous_close=D('90'), change_pct=D('0'),
                                volume=10, source='tiingo', as_of=NOW-timedelta(minutes=5), currency='USD')
        _apply_quotes({'TEST':item}, {'TEST':older})
        self.assertEqual(item.price, D('100'))
        incoming = candidate(price=D('80'), source='tiingo', source_as_of=NOW-timedelta(minutes=10),
                             evidence={'quote_as_of':(NOW-timedelta(minutes=10)).isoformat()})
        _merge({'TEST':item}, [incoming])
        self.assertEqual(item.price, D('100'))
        self.assertEqual(item.evidence['quote_as_of'], NOW.isoformat())

    def test_stale_benchmark_cannot_confirm_a_sector_move(self):
        benchmark = candidate('XLK', change_pct=D('-5'), stale_reason='stale quote', sector='Technology')
        item = candidate(change_pct=D('1'), sector='Technology')
        _apply_sector_relative([benchmark, item])
        self.assertNotIn('sector_relative_return_pct', item.evidence)

    def test_new_discovery_can_displace_old_pinned_names(self):
        old = [candidate(f'OLD{i}', pinned_prior=True, anomaly_score=D('0')) for i in range(110)]
        new = candidate('NEW', anomaly_score=D('40'))
        selected = _select_working_set(old + [new])
        self.assertEqual(len(selected), 100)
        self.assertIn(new, selected)

from datetime import datetime, timezone
from decimal import Decimal
from unittest import TestCase

from audits.capital_week_metrics import exposure, market_seconds, signal_screen


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=timezone.utc)


def trade(ticker, when, side, quantity, price, status='filled'):
    return dict(ticker=ticker, trade_date=when.isoformat(), side=side, quantity=str(quantity),
                executed_price=str(price), executed_price_base=None, status=status)


class CapitalWeekAuditTests(TestCase):
    def test_market_time_excludes_weekend_and_overnight(self):
        self.assertEqual(market_seconds(at(9,13,30), at(12,20)), 13*3600)
        self.assertEqual(market_seconds(at(10,0), at(11,23)), 0)

    def test_concurrent_exposure_and_sale_release_cost_not_sale_proceeds(self):
        trades = [trade('A',at(13,13,30),'buy',10,10),
                  trade('B',at(13,14),'buy',20,10),
                  trade('A',at(13,14,30),'sell',10,20)]
        result = exposure(trades,at(13,13,30),at(13,15,30))
        self.assertEqual(result['average_entry_cost_held'], Decimal('200'))
        self.assertEqual(result['maximum_entry_cost_after_trade'], Decimal('300'))
        self.assertEqual(result['max_names_after_trade'],2)

    def test_holdings_before_window_still_count_without_any_new_fills(self):
        result = exposure([trade('A',at(8,15),'buy',10,100)],at(9,13,30),at(9,20))
        self.assertEqual(result['average_entry_cost_held'], Decimal('1000'))
        self.assertEqual(result['maximum_entry_cost_after_trade'], Decimal('1000'))
        self.assertEqual(result['max_names_after_trade'],1)

    def test_partial_sale_uses_weighted_acquisition_cost(self):
        trades=[trade('A',at(8,14),'buy',10,10),trade('A',at(8,15),'buy',10,20),
                trade('A',at(9,13),'sell',10,50)]
        result=exposure(trades,at(9,13,30),at(9,20))
        self.assertEqual(result['average_entry_cost_held'],Decimal('150'))

    def test_planned_and_future_trades_do_not_affect_exposure(self):
        result=exposure([trade('A',at(9,14),'buy',10,10,'planned'),
                         trade('B',at(12,14),'buy',10,10)],at(9,13,30),at(9,20))
        self.assertEqual(result['average_entry_cost_held'],0)

    def test_incomplete_trade_history_cannot_silently_create_negative_exposure(self):
        with self.assertRaises(ValueError):
            exposure([trade('A',at(9,14),'sell',10,10)],at(9,13,30),at(9,20))

    def test_signal_screen_separates_repeat_observations_from_new_symbols(self):
        row=dict(run_id='radar',ticker='TEST',jurisdiction='US',currency='USD',asset_class='equity',
                 price='10',change_pct='5',volume_ratio='3',volume=10000,avg_volume=3000,
                 radar_priority='P1',as_of=at(13,15).isoformat(),source_as_of=at(13,15).isoformat(),
                 carried_forward=False,stale_reason=None,avg_dollar_volume='1000000',move_scope=None,
                 price_return_zscore=None,volume_zscore=None,sector_relative_return_pct=None)
        data=dict(radar_runs=[dict(id='radar',started_at=at(13,15).isoformat(),finished_at=at(13,15,1).isoformat())],
                  runs=[dict(id='fund',started_at=at(13,13).isoformat(),ends_at=at(20,13).isoformat())],
                  orders=[dict(ticker='TEST',run_id='fund',closed_at=at(13,14).isoformat())],
                  priority_observations=[row,dict(row,ticker='NEW')])
        result=signal_screen(data)
        self.assertEqual(result['passed_symbols'],['NEW','TEST'])
        self.assertEqual(result['passed_observations_after_same_run_close'],{'TEST':1})
        self.assertEqual(result['observations']['Passed stored signal gates; execution unverified'],2)

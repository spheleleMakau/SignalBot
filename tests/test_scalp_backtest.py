import unittest
from unittest.mock import patch

import pandas as pd

from analysis.candle_patterns import candle_confirmation
from backtest.engine import run_scalp_backtest


class ScalpBacktestTests(unittest.TestCase):
    @staticmethod
    def flat_candles(count, seconds):
        return pd.DataFrame([
            {
                'timestamp': index * seconds,
                'open': 100.0,
                'high': 100.5,
                'low': 99.5,
                'close': 100.0,
                'volume': 0,
            }
            for index in range(count)
        ])

    def test_requires_minimum_closed_history(self):
        result = run_scalp_backtest(
            self.flat_candles(219, 60),
            self.flat_candles(60, 300),
        )

        self.assertEqual(result, {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0})

    def test_flat_history_completes_without_inventing_trades(self):
        result = run_scalp_backtest(
            self.flat_candles(220, 60),
            self.flat_candles(60, 300),
        )

        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['trades'], 0)
        self.assertEqual(result['net_result'], 0)
        self.assertIsNone(result['profit_factor'])

    def test_backtest_supplies_three_candles_to_confirmation(self):
        one_minute = pd.DataFrame([
            {
                'timestamp': index * 60,
                'open': 100 + index * 0.05 - 0.02,
                'high': 100 + index * 0.05 + 0.08,
                'low': 100 + index * 0.05 - 0.08,
                'close': 100 + index * 0.05,
                'volume': 0,
            }
            for index in range(220)
        ])
        five_minute = pd.DataFrame([
            {
                'timestamp': index * 300,
                'open': 100 + index * 0.25 - 0.02,
                'high': 100 + index * 0.25 + 0.08,
                'low': 100 + index * 0.25 - 0.08,
                'close': 100 + index * 0.25,
                'volume': 0,
            }
            for index in range(60)
        ])
        confirmation_lengths = []

        def track_confirmation(frame):
            confirmation_lengths.append(len(frame))
            return candle_confirmation(frame)

        with patch('backtest.engine.candle_confirmation', side_effect=track_confirmation):
            run_scalp_backtest(one_minute, five_minute)

        self.assertTrue(confirmation_lengths)
        self.assertTrue(all(length >= 3 for length in confirmation_lengths))

    def test_main_backtest_supplies_three_candles_to_confirmation(self):
        from backtest.engine import run_backtest

        minute = self.flat_candles(2_200, 60)
        five = self.flat_candles(440, 300)
        fifteen = self.flat_candles(147, 900)
        hour = self.flat_candles(37, 3_600)
        four = self.flat_candles(30, 14_400)
        for frame in (minute, five, fifteen, hour, four):
            closes = [100 + index * 0.01 + (-1) ** index * 0.05 for index in range(len(frame))]
            frame['close'] = closes
            frame['open'] = [close - 0.02 for close in closes]
            frame['high'] = [close + 0.1 for close in closes]
            frame['low'] = [close - 0.1 for close in closes]
        confirmation_lengths = []

        def track_confirmation(frame):
            confirmation_lengths.append(len(frame))
            return candle_confirmation(frame)

        with patch('backtest.engine.candle_confirmation', side_effect=track_confirmation), \
            patch('backtest.engine.market_structure', return_value={'bias': 'UNCLEAR'}):
            run_backtest(minute, five, fifteen, hour, four_hour=four)

        self.assertTrue(confirmation_lengths)
        self.assertTrue(all(length >= 3 for length in confirmation_lengths))

    def test_resolver_uses_candle_order_and_conservative_ambiguous_loss(self):
        from backtest.engine import _resolve_exit

        candles = pd.DataFrame([
            {'low': 100, 'high': 100, 'close': 100},
            {'low': 89, 'high': 121, 'close': 100},
            {'low': 100, 'high': 100, 'close': 100},
        ])
        outcome, exit_index, ambiguous = _resolve_exit(
            candles, 0, 1, 100, 90, 120, 10, target_r=2, holding_bars=2
        )

        self.assertEqual((outcome, exit_index, ambiguous), (-1.0, 1, True))

    def test_main_backtest_requires_all_timeframes(self):
        from backtest.engine import run_backtest

        result = run_backtest(self.flat_candles(250, 60))

        self.assertEqual(result, {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0})

    def test_main_backtest_requires_four_hour_history(self):
        from backtest.engine import run_backtest

        result = run_backtest(
            self.flat_candles(250, 60),
            self.flat_candles(60, 300),
            self.flat_candles(40, 900),
            self.flat_candles(40, 3600),
        )

        self.assertEqual(result, {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0})

    def test_main_backtest_replays_full_timeframe_history(self):
        from backtest.engine import run_backtest

        result = run_backtest(
            self.flat_candles(250, 60),
            self.flat_candles(60, 300),
            self.flat_candles(40, 900),
            self.flat_candles(40, 3600),
            four_hour=self.flat_candles(30, 14_400),
        )

        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['trades'], 0)
        self.assertEqual(result['validation_trades'], 0)


if __name__ == '__main__':
    unittest.main()
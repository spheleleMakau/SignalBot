import unittest

from analysis.halftrend import (
    HalfTrendConfig,
    HalfTrendDataError,
    backtest_halftrend,
    calculate_halftrend,
)


def trend_candles():
    closes = (
        list(range(10, 21))
        + list(range(19, 9, -1))
        + list(range(11, 22))
    )
    return [
        {
            'timestamp': index * 60,
            'open': float(close),
            'high': float(close) + 0.5,
            'low': float(close) - 0.5,
            'close': float(close),
        }
        for index, close in enumerate(closes)
    ]


class HalfTrendTests(unittest.TestCase):
    def test_default_inputs_and_wilder_atr_bands(self):
        candles = trend_candles()
        result = calculate_halftrend(
            candles,
            HalfTrendConfig(amplitude=3, atr_period=3),
            timeframe_seconds=60,
        )

        self.assertAlmostEqual(result[2]['atr_100'], 4 / 3)
        self.assertAlmostEqual(result[2]['atr_half'], 2 / 3)
        self.assertAlmostEqual(
            result[2]['band_high'] - result[2]['line'],
            4 / 3,
        )
        self.assertAlmostEqual(
            result[2]['line'] - result[2]['band_low'],
            4 / 3,
        )
        self.assertEqual(HalfTrendConfig().amplitude, 20)
        self.assertEqual(HalfTrendConfig().channel_deviation, 2.0)
        self.assertEqual(HalfTrendConfig().base_risk, 3.0)

    def test_signals_only_mark_closed_trend_flips_and_risk_levels(self):
        result = calculate_halftrend(
            trend_candles(),
            HalfTrendConfig(amplitude=3, atr_period=3),
            timeframe_seconds=60,
        )
        signals = [bar for bar in result if bar['signal']]

        self.assertGreaterEqual(len(signals), 2)
        self.assertEqual(signals[0]['signal'], 'SHORT')
        self.assertEqual(signals[1]['signal'], 'LONG')
        self.assertEqual(
            [bar['timestamp'] for bar in signals],
            sorted({bar['timestamp'] for bar in signals}),
        )
        for bar in signals:
            self.assertEqual(bar['close_timestamp'], bar['timestamp'] + 60)
            self.assertEqual(bar['entry'], trend_candles()[bar['timestamp'] // 60]['close'])
            self.assertIsNotNone(bar['stop_loss'])
            if bar['signal'] == 'LONG':
                self.assertLess(bar['stop_loss'], bar['entry'])
                self.assertGreater(bar['tp1'], bar['entry'])
                self.assertGreater(bar['tp2'], bar['tp1'])
                self.assertGreater(bar['tp3'], bar['tp2'])
            else:
                self.assertGreater(bar['stop_loss'], bar['entry'])
                self.assertLess(bar['tp1'], bar['entry'])
                self.assertLess(bar['tp2'], bar['tp1'])
                self.assertLess(bar['tp3'], bar['tp2'])

    def test_historical_prefix_matches_live_calculation_through_same_closed_bar(self):
        candles = trend_candles()
        complete = calculate_halftrend(
            candles,
            HalfTrendConfig(amplitude=3, atr_period=3),
            timeframe_seconds=60,
        )
        for end in (4, 10, 17, len(candles)):
            with self.subTest(end=end):
                prefix = calculate_halftrend(
                    candles[:end],
                    HalfTrendConfig(amplitude=3, atr_period=3),
                    timeframe_seconds=60,
                )
                self.assertEqual(prefix, complete[:end])

    def test_missing_duplicate_misaligned_and_invalid_candles_are_rejected(self):
        candles = trend_candles()
        with self.assertRaisesRegex(HalfTrendDataError, 'missing timeframe boundary'):
            calculate_halftrend([candles[0], candles[2]], timeframe_seconds=60)
        with self.assertRaisesRegex(HalfTrendDataError, 'strictly increasing'):
            calculate_halftrend([candles[0], candles[0]], timeframe_seconds=60)
        with self.assertRaisesRegex(HalfTrendDataError, 'not aligned'):
            calculate_halftrend([{**candles[0], 'timestamp': 1}], timeframe_seconds=60)
        with self.assertRaisesRegex(HalfTrendDataError, 'OHLC'):
            calculate_halftrend([{**candles[0], 'low': candles[0]['high']}])

    def test_backtest_resolves_target_and_does_not_guess_same_bar_order(self):
        candles = [
            {'timestamp': index * 60, 'open': 100, 'high': high, 'low': low, 'close': close}
            for index, (high, low, close) in enumerate((
                (100.2, 99.8, 100),
                (101.2, 100.2, 101),
                (100.2, 99.8, 100),
                (102.2, 98.8, 101),
            ))
        ]
        bars = [
            {
                'signal': 'LONG', 'entry': 100.0, 'stop_loss': 99.0,
                'tp1': 101.0, 'tp2': 102.0, 'tp3': 103.0, 'timestamp': 0,
            },
            {'signal': None},
            {
                'signal': 'SHORT', 'entry': 100.0, 'stop_loss': 101.0,
                'tp1': 99.0, 'tp2': 98.0, 'tp3': 97.0, 'timestamp': 120,
            },
            {'signal': None},
        ]
        summary = backtest_halftrend(candles, bars)

        self.assertEqual(summary['trades'], 2)
        self.assertEqual(summary['wins'], 1)
        self.assertEqual(summary['losses'], 0)
        self.assertEqual(summary['unresolved'], 1)
        self.assertEqual(summary['outcomes'][0]['status'], 'WIN · TP1')
        self.assertTrue(summary['outcomes'][1]['status'].startswith('UNRESOLVED'))
        self.assertIn('payout are unavailable', summary['cost_assumptions'])

    def test_backtest_exposes_open_trade_at_end_of_available_candles(self):
        candles = [
            {'timestamp': 0, 'open': 100, 'high': 100.2, 'low': 99.8, 'close': 100},
            {'timestamp': 60, 'open': 100, 'high': 100.5, 'low': 99.5, 'close': 100.1},
        ]
        bars = [
            {
                'signal': 'LONG', 'entry': 100.0, 'stop_loss': 99.0,
                'tp1': 101.0, 'tp2': 102.0, 'tp3': 103.0, 'timestamp': 0,
            },
            {'signal': None},
        ]

        summary = backtest_halftrend(candles, bars)

        self.assertEqual(summary['unresolved'], 1)
        self.assertEqual(summary['active_trade']['direction'], 'LONG')
        self.assertEqual(summary['active_trade']['entry'], 100.0)

    def test_backtest_rejects_mismatched_inputs_and_invalid_configuration(self):
        with self.assertRaisesRegex(ValueError, 'matching lengths'):
            backtest_halftrend([{}], [])
        with self.assertRaisesRegex(ValueError, 'Amplitude'):
            HalfTrendConfig(amplitude=1.5)
        with self.assertRaisesRegex(ValueError, 'Channel deviation'):
            HalfTrendConfig(channel_deviation=0)


if __name__ == '__main__':
    unittest.main()

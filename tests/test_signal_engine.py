import unittest
from unittest.mock import patch

import pandas as pd

from analysis.signal_engine import (
    REQUIRED_SIGNAL_TIMEFRAMES,
    SignalEngine,
    _swing_volume_confirmation,
    _live_entry_price,
    _timeframe_alignment,
)
from analysis.candle_patterns import breakout_confirmation


class SignalAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.frames = {
            timeframe: {'available': True, 'bias': 'BULLISH', 'structure': {'bias': 'BULLISH'}}
            for timeframe in REQUIRED_SIGNAL_TIMEFRAMES
        }

    def test_all_timeframes_must_agree(self):
        self.assertEqual(_timeframe_alignment(self.frames), 'BUY')

        bearish = {
            timeframe: {**frame, 'bias': 'BEARISH'}
            for timeframe, frame in self.frames.items()
        }
        self.assertEqual(_timeframe_alignment(bearish), 'SELL')

        conflicting = {**self.frames, '4h': {**self.frames['4h'], 'bias': 'BEARISH'}}
        self.assertIsNone(_timeframe_alignment(conflicting))

    def test_breakout_confirmation_requires_a_closed_break_of_previous_extreme(self):
        candles = pd.DataFrame([
            {'high': 101.0, 'low': 99.0, 'close': 100.0},
            {'high': 102.0, 'low': 99.5, 'close': 101.0},
        ])
        self.assertFalse(breakout_confirmation(candles, 'BUY'))
        self.assertFalse(breakout_confirmation(candles, 'SELL'))

        candles.loc[1, 'close'] = 101.1
        self.assertTrue(breakout_confirmation(candles, 'BUY'))
        self.assertFalse(breakout_confirmation(candles, 'SELL'))

        candles.loc[1, 'close'] = 98.9
        self.assertFalse(breakout_confirmation(candles, 'BUY'))
        self.assertTrue(breakout_confirmation(candles, 'SELL'))

    def test_conflicting_four_hour_bias_returns_wait(self):
        frames = {**self.frames, '4h': {**self.frames['4h'], 'bias': 'BEARISH'}}

        with patch('analysis.signal_engine.multi_timeframe', return_value=frames):
            signal = SignalEngine('TEST').evaluate(object(), connected=True)

        self.assertEqual(signal['status'], 'WAIT — TIMEFRAMES NOT ALIGNED')
        self.assertIsNone(signal['direction'])
        self.assertIsNone(signal['id'])
        self.assertIn('4H BEARISH', signal['reasons'][1])

    def test_missing_timeframe_data_returns_wait(self):
        frames = {**self.frames, '4h': {'available': False, 'bias': 'UNCLEAR'}}

        with patch('analysis.signal_engine.multi_timeframe', return_value=frames):
            signal = SignalEngine('TEST').evaluate(object(), connected=True)

        self.assertEqual(signal['status'], 'WAIT — TIMEFRAMES NOT ALIGNED')
        self.assertIsNone(signal['direction'])
        self.assertIn('4H NO DATA', signal['reasons'][1])

    def test_live_entry_requires_fresh_price_near_signal_close(self):
        candle = type('Candle', (), {'timestamp': 600, 'close': 100.0})()
        store = type('Store', (), {'last_tick': {'timestamp': 665, 'price': 100.2}})()

        self.assertEqual(_live_entry_price(store, candle, atr=1.0), (100.2, None))

    def test_late_or_chased_entries_return_wait_reasons(self):
        candle = type('Candle', (), {'timestamp': 600, 'close': 100.0})()
        late_store = type('Store', (), {'last_tick': {'timestamp': 720, 'price': 100.0}})()
        moved_store = type('Store', (), {'last_tick': {'timestamp': 665, 'price': 100.3}})()

        self.assertEqual(_live_entry_price(late_store, candle, atr=1.0), (None, 'WAIT — ENTRY WINDOW EXPIRED'))
        self.assertEqual(_live_entry_price(moved_store, candle, atr=1.0), (None, 'WAIT — PRICE MOVED'))

    def test_swing_volume_context_reports_poc_and_direction_alignment(self):
        candles = pd.DataFrame([
            {'high': price + 0.1, 'low': price - 0.1, 'close': price, 'volume': volume}
            for price, volume in [(100.0, 5)] * 7 + [(101.0, 1)] * 3
        ])
        structure = {
            'bias': 'BULLISH',
            'swing_highs': [{'high': 102.0}],
            'swing_lows': [{'low': 98.0}],
        }

        result = _swing_volume_confirmation(candles, structure, current_price=100.5)

        self.assertAlmostEqual(result['poc'], 100.0)
        self.assertEqual(result['swing_high'], 102.0)
        self.assertEqual(result['swing_low'], 98.0)
        self.assertEqual(result['price_vs_poc'], 'ABOVE POC')
        self.assertTrue(result['direction_poc_aligned'])
        self.assertIn('Advisory only', result['entry_context'])

        at_poc = _swing_volume_confirmation(candles, structure, current_price=100.0)
        self.assertEqual(at_poc['price_vs_poc'], 'AT POC')
        self.assertIsNone(at_poc['direction_poc_aligned'])

    def test_swing_volume_context_waits_for_enough_live_volume(self):
        candles = pd.DataFrame([
            {'high': 100.1, 'low': 99.9, 'close': 100.0, 'volume': 1}
            for _ in range(9)
        ])

        result = _swing_volume_confirmation(candles, {'bias': 'BEARISH'}, current_price=99.0)

        self.assertIsNone(result['poc'])
        self.assertIsNone(result['direction_poc_aligned'])
        self.assertEqual(result['volume_candles'], 9)
        self.assertIn('WAITING', result['status'])


if __name__ == '__main__':
    unittest.main()
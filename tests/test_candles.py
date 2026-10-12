import unittest

from market.candles import CandleGapError, CandleStore


class CandleStoreTests(unittest.TestCase):
    def test_gap_is_rejected_without_mutating_history(self):
        store = CandleStore()
        store.add_tick(1_000, 100.0)
        before = store.snapshot()
        previous_tick = store.last_tick

        with self.assertRaises(CandleGapError):
            store.add_tick(1_180, 101.0)

        self.assertEqual(store.snapshot(), before)
        self.assertEqual(store.last_tick, previous_tick)

    def test_same_candle_ticks_update_ohlc(self):
        store = CandleStore()
        store.add_tick(1_000, 100.0)
        store.add_tick(1_010, 102.0)
        store.add_tick(1_019, 99.0)

        candle = store.snapshot()['1m'][0]
        self.assertEqual(
            (candle['open'], candle['high'], candle['low'], candle['close']),
            (100.0, 102.0, 99.0, 99.0),
        )

    def test_four_hour_candles_follow_utc_boundaries(self):
        store = CandleStore()
        for timestamp in range(0, 14_401, 60):
            store.add_tick(timestamp, 100.0 + timestamp / 60)

        candles = store.snapshot()['4h']
        self.assertEqual([candle['timestamp'] for candle in candles], [0, 14_400])
        self.assertEqual((candles[-1]['open'], candles[-1]['close']), (340.0, 340.0))

    def test_multi_timeframe_analysis_includes_four_hour_context(self):
        from analysis.timeframe import multi_timeframe

        store = CandleStore()
        store.load_candles('4h', [
            {'epoch': index * 14_400, 'open': 100, 'high': 101, 'low': 99, 'close': 100}
            for index in range(30)
        ])

        result = multi_timeframe(store)

        self.assertTrue(result['4h']['available'])
        self.assertFalse(result['1h']['available'])

    def test_out_of_order_tick_is_rejected(self):
        store = CandleStore()
        store.add_tick(1_000, 100.0)
        before = store.snapshot()

        with self.assertRaises(CandleGapError):
            store.add_tick(999, 101.0)

        self.assertEqual(store.snapshot(), before)

    def test_invalid_tick_price_is_rejected(self):
        store = CandleStore()

        with self.assertRaises(ValueError):
            store.add_tick(1_000, float('nan'))

        self.assertIsNone(store.last_tick)
        self.assertTrue(all(not candles for candles in store.snapshot().values()))

    def test_invalid_history_does_not_replace_existing_candles(self):
        store = CandleStore()
        store.load_candles('1m', [{'epoch': 0, 'open': 100, 'high': 101, 'low': 99, 'close': 100}])
        before = store.snapshot()

        with self.assertRaises(ValueError):
            store.load_candles('1m', [{'epoch': 60, 'open': 100, 'high': 99, 'low': 98, 'close': 100}])

        self.assertEqual(store.snapshot(), before)


if __name__ == '__main__':
    unittest.main()
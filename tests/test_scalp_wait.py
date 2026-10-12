import unittest

from analysis.signal_engine import SignalEngine
from market.candles import CandleStore


class ScalpWaitTests(unittest.TestCase):
    @staticmethod
    def make_store(direction):
        store = CandleStore()
        candles_by_timeframe = {}
        for timeframe, interval, count, step in (
            ('1m', 60, 80, 0.1),
            ('5m', 300, 80, 0.5),
        ):
            candles = []
            for index in range(count):
                movement = index * step * direction
                close = 100 + movement
                candles.append({
                    'epoch': index * interval,
                    'open': close - 0.02 * direction,
                    'high': close + 0.08,
                    'low': close - 0.08,
                    'close': close,
                })
            candles_by_timeframe[timeframe] = candles
        for timeframe, candles in candles_by_timeframe.items():
            store.load_candles(timeframe, candles)
        return store

    def test_bullish_context_names_waiting_buy_confirmation(self):
        signal = SignalEngine('1HZ100V').evaluate_scalp(self.make_store(1), connected=True)

        self.assertEqual(signal['status'], 'SCALP WAIT — TIMEFRAMES NOT ALIGNED')
        self.assertNotIn('watch_direction', signal)
        self.assertIsNone(signal['direction'])
        self.assertTrue(any('4H' in reason for reason in signal['reasons']))

    def test_bearish_context_names_waiting_sell_confirmation(self):
        signal = SignalEngine('1HZ100V').evaluate_scalp(self.make_store(-1), connected=True)

        self.assertEqual(signal['status'], 'SCALP WAIT — TIMEFRAMES NOT ALIGNED')
        self.assertNotIn('watch_direction', signal)
        self.assertIsNone(signal['direction'])
        self.assertTrue(any('4H' in reason for reason in signal['reasons']))


if __name__ == '__main__':
    unittest.main()
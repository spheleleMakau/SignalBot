import unittest

from analysis.signal_engine import SignalEngine
from market.candles import CandleStore


class ScalpWaitTests(unittest.TestCase):
    def test_scalping_always_returns_disabled_without_direction_or_trade_plan(self):
        signal_engine = SignalEngine('1HZ100V')
        for connected in (True, False):
            with self.subTest(connected=connected):
                signal = signal_engine.evaluate_scalp(CandleStore(), connected=connected)

                self.assertEqual(signal['status'], 'SCALPING DISABLED — USE MAIN SIGNAL')
                self.assertIsNone(signal['direction'])
                self.assertIsNone(signal['id'])
                self.assertNotIn('entry', signal)
                self.assertNotIn('watch_direction', signal)


if __name__ == '__main__':
    unittest.main()
import tempfile
import unittest
from pathlib import Path

from data.database import Database
from data.shadow import resolve_pending_shadow_candidates, resolve_shadow_outcome


def candidate():
    return {
        'signal_id': 'candidate-1',
        'evaluated_at': 125,
        'entry': 100.0,
        'stop_loss': 99.0,
        'take_profit_1': 102.0,
        'direction': 'BUY',
    }


def candle(timestamp, high=101.0, low=99.5, close=100.0):
    return {
        'timestamp': timestamp,
        'open': 100.0,
        'high': high,
        'low': low,
        'close': close,
    }


class ShadowOutcomeTests(unittest.TestCase):
    def test_ignores_observation_minute_and_resolves_first_future_target(self):
        result = resolve_shadow_outcome(candidate(), [
            candle(120, high=105.0, low=98.0),
            candle(180, high=102.5),
            candle(240, high=104.0),
        ])

        self.assertEqual(result['outcome'], 'TARGET_1')
        self.assertEqual(result['exit_price'], 102.0)
        self.assertEqual(result['gross_r'], 2.0)
        self.assertEqual(result['bars_held'], 1)
        self.assertFalse(result['ambiguous'])

    def test_same_bar_stop_and_target_uses_conservative_stop_first(self):
        result = resolve_shadow_outcome(candidate(), [candle(180, high=103.0, low=98.0)])

        self.assertEqual(result['outcome'], 'STOP')
        self.assertEqual(result['gross_r'], -1.0)
        self.assertTrue(result['ambiguous'])

    def test_price_action_timeout_is_marked_to_close_in_r_units(self):
        future = [candle(180 + index * 60, close=100.25) for index in range(120)]

        result = resolve_shadow_outcome(candidate(), future)

        self.assertEqual(result['outcome'], 'TIMEOUT')
        self.assertEqual(result['bars_held'], 120)
        self.assertAlmostEqual(result['gross_r'], 0.25)

    def test_missing_future_bar_marks_data_gap_without_fabricating_result(self):
        result = resolve_shadow_outcome(candidate(), [candle(240)])

        self.assertEqual(result['outcome'], 'DATA_GAP')
        self.assertIsNone(result['gross_r'])

    def test_waits_until_a_future_closed_candle_is_available(self):
        result = resolve_shadow_outcome(candidate(), [candle(120)])

        self.assertIsNone(result)


class ShadowDatabaseTests(unittest.TestCase):
    def test_persists_candidate_once_and_reports_gate_cohort_results(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Database(str(Path(directory) / 'shadow.db'))
            signal = {
                'id': 'candidate-1',
                'timestamp': 185,
                'setup_timestamp': 120,
                'symbol': 'stpRNG',
                'direction': 'BUY',
                'entry': 100.0,
                'stop_loss': 99.0,
                'tp1': 102.0,
                'tp2': 103.0,
                'score': 85,
                'reasons': ['closed-bar confirmation'],
            }

            database.record_shadow_candidate(
                signal, 185, backtest_passed=True, tradingview_confirmed=False,
                gate_status='BLOCKED_TRADINGVIEW',
            )
            database.record_shadow_candidate(
                signal, 190, backtest_passed=True, tradingview_confirmed=False,
                gate_status='BLOCKED_TRADINGVIEW',
            )
            resolve_pending_shadow_candidates(
                database, 'stpRNG', [candle(240, high=102.5)]
            )

            report = database.shadow_performance(symbol='stpRNG')

        self.assertEqual(report['candidates'], 1)
        self.assertEqual(report['resolved'], 1)
        self.assertEqual(report['wins'], 1)
        self.assertEqual(report['average_gross_r'], 2.0)
        self.assertEqual(report['by_gate']['BLOCKED_TRADINGVIEW']['resolved'], 1)
        self.assertIn('spread, slippage', report['cost_model'])
        self.assertEqual(report['recent'][0]['entry_latency_seconds'], 5)
        self.assertEqual(report['average_entry_latency_seconds'], 5.0)


if __name__ == '__main__':
    unittest.main()

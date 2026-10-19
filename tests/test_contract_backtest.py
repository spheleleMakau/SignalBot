import unittest
from unittest.mock import patch

import pandas as pd

from backtest.contracts import evaluate_rise_fall_signals, resolve_rise_fall_contract
from backtest.engine import run_backtest


class RiseFallContractTests(unittest.TestCase):
    def test_entry_uses_first_quote_after_signal_and_expiry_uses_entry_time(self):
        result = resolve_rise_fall_contract(
            {'signal_timestamp': 1_000, 'direction': 'BUY'},
            [
                {'epoch': 1_000, 'quote': 100.0},
                {'epoch': 1_001, 'quote': 100.5},
                {'epoch': 1_061, 'quote': 101.0},
                {'epoch': 1_062, 'quote': 99.0},
            ],
        )

        self.assertEqual(result['entry_timestamp'], 1_001)
        self.assertEqual(result['entry_quote'], 100.5)
        self.assertEqual(result['expiry_timestamp'], 1_061)
        self.assertEqual(result['expiry_quote'], 101.0)
        self.assertEqual(result['outcome'], 'WIN')

    def test_missing_exact_expiry_quote_is_incomplete(self):
        result = resolve_rise_fall_contract(
            {'timestamp': 1_000, 'direction': 'SELL'},
            [
                {'timestamp': 1_001, 'price': 100.0},
                {'timestamp': 1_060, 'price': 99.0},
                {'timestamp': 1_062, 'price': 98.0},
            ],
        )

        self.assertEqual(result['outcome'], 'INCOMPLETE')
        self.assertEqual(result['reason'], 'EXACT_EXPIRY_QUOTE_UNAVAILABLE')
        self.assertIsNone(result['expiry_quote'])

    def test_quote_at_signal_timestamp_is_not_used_as_entry(self):
        result = resolve_rise_fall_contract(
            {'timestamp': 1_000, 'direction': 'RISE'},
            [{'timestamp': 1_000, 'price': 100.0}],
        )

        self.assertEqual(result['outcome'], 'INCOMPLETE')
        self.assertEqual(result['reason'], 'ENTRY_QUOTE_UNAVAILABLE')
        self.assertIsNone(result['entry_quote'])

    def test_entry_delay_exceeded_is_incomplete(self):
        result = resolve_rise_fall_contract(
            {'timestamp': 1_000, 'direction': 'FALL'},
            [{'timestamp': 1_006, 'price': 100.0}],
            max_entry_delay_seconds=5,
        )

        self.assertEqual(result['reason'], 'ENTRY_QUOTE_UNAVAILABLE')

    def test_equal_entry_and_expiry_quotes_are_reported_as_tie(self):
        result = resolve_rise_fall_contract(
            {'timestamp': 1_000, 'direction': 'SELL'},
            [
                {'timestamp': 1_001, 'price': 100.0},
                {'timestamp': 1_061, 'price': 100.0},
            ],
        )

        self.assertEqual(result['outcome'], 'TIE')

    def test_conflicting_duplicate_quote_timestamps_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Conflicting quotes'):
            resolve_rise_fall_contract(
                {'timestamp': 1_000, 'direction': 'BUY'},
                [
                    {'timestamp': 1_001, 'price': 100.0},
                    {'timestamp': 1_001, 'price': 101.0},
                ],
            )

    def test_overlapping_and_duplicate_signals_do_not_inflate_results(self):
        result = evaluate_rise_fall_signals(
            [
                {'id': 'first', 'timestamp': 1_000, 'direction': 'BUY', 'split': 'DEVELOPMENT'},
                {'id': 'overlap', 'timestamp': 1_030, 'direction': 'SELL'},
                {'id': 'duplicate', 'timestamp': 1_000, 'direction': 'BUY'},
                {'id': 'second', 'timestamp': 1_061, 'direction': 'SELL', 'split': 'VALIDATION'},
            ],
            [
                {'timestamp': 1_001, 'price': 100.0},
                {'timestamp': 1_061, 'price': 101.0},
                {'timestamp': 1_062, 'price': 100.0},
                {'timestamp': 1_122, 'price': 99.0},
            ],
        )

        self.assertEqual(result['completed'], 2)
        self.assertEqual(result['excluded_overlap'], 1)
        self.assertEqual(result['excluded_duplicates'], 1)
        self.assertEqual(result['wins'], 2)
        self.assertEqual(result['payout_data'], 'UNAVAILABLE')
        self.assertIsNone(result['net_expected_return'])
        self.assertEqual(result['development']['completed'], 1)
        self.assertEqual(result['validation']['completed'], 1)


class RunBacktestContractModeTests(unittest.TestCase):
    @staticmethod
    def candles(count, seconds):
        return pd.DataFrame([
            {
                'timestamp': index * seconds,
                'open': 100.0,
                'high': 100.2,
                'low': 99.8,
                'close': 100.0,
                'volume': 0,
            }
            for index in range(count)
        ])

    def test_contract_mode_requires_raw_tick_quotes(self):
        result = run_backtest(
            self.candles(300, 60),
            self.candles(60, 300),
            self.candles(40, 900),
            self.candles(40, 3_600),
            four_hour=self.candles(30, 14_400),
            evaluation_mode='rise_fall_contract',
            contract_symbol='stpRNG',
        )

        self.assertEqual(result['status'], 'INSUFFICIENT TICK DATA')
        self.assertEqual(result['evaluation_mode'], 'RISE_FALL_CONTRACT')

    def test_contract_mode_rejects_ticks_for_a_different_instrument(self):
        with self.assertRaisesRegex(ValueError, 'must all match'):
            run_backtest(
                self.candles(300, 60),
                self.candles(60, 300),
                self.candles(40, 900),
                self.candles(40, 3_600),
                four_hour=self.candles(30, 14_400),
                evaluation_mode='rise_fall_contract',
                contract_symbol='stpRNG',
                contract_ticks=pd.DataFrame([
                    {'timestamp': 1, 'quote': 100.0, 'symbol': 'R_75'},
                ]),
            )

    def test_contract_mode_uses_quote_after_candle_signal_not_stop_target_backtest(self):
        def enrich(frame):
            result = frame.copy()
            slope = pd.Series(result.index, index=result.index) * 0.000001
            result['ema_20'] = result['close'] - 0.01 + slope
            result['ema_50'] = result['close'] - 0.02 + slope
            result['ema_200'] = result['close'] - 0.03 + slope
            result['atr_14'] = 0.1
            result['rsi_14'] = 60.0
            return result

        ticks = pd.DataFrame([
            {'timestamp': 43_201, 'quote': 100.0},
            {'timestamp': 43_261, 'quote': 100.1},
        ])
        with patch('backtest.engine.indicators', side_effect=enrich), \
                patch('backtest.engine.market_structure', return_value={'bias': 'BULLISH'}), \
                patch('backtest.engine.candle_confirmation', return_value={'direction': 'BUY'}), \
                patch('backtest.engine.breakout_confirmation', return_value=True), \
                patch('backtest.engine.levels', return_value=[]):
            result = run_backtest(
                self.candles(1_200, 60),
                self.candles(240, 300),
                self.candles(100, 900),
                self.candles(40, 3_600),
                four_hour=self.candles(30, 14_400),
                evaluation_mode='rise_fall_contract',
                contract_ticks=ticks,
                contract_symbol='stpRNG',
            )

        self.assertEqual(result['evaluation_mode'], 'RISE_FALL_CONTRACT')
        self.assertGreaterEqual(result['completed'], 1)
        first_completed = next(record for record in result['records'] if record['outcome'] == 'WIN')
        self.assertEqual(first_completed['signal_timestamp'], 43_200)
        self.assertEqual(first_completed['entry_timestamp'], 43_201)
        self.assertEqual(first_completed['expiry_timestamp'], 43_261)
        self.assertEqual(first_completed['strategy_version'], 'main-v1')
        self.assertEqual(first_completed['symbol'], 'stpRNG')


if __name__ == '__main__':
    unittest.main()

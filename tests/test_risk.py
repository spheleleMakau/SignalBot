import unittest

from trading.risk import FIXED_LOT_SIZE, estimate_trade_values


class TradeValueTests(unittest.TestCase):
    def test_buy_trade_values_use_fixed_point_multiplier(self):
        values = estimate_trade_values({
            'status': 'ENTRY CONFIRMED',
            'direction': 'BUY',
            'entry': 100,
            'stop_loss': 90,
            'tp1': 120,
            'tp2': 130,
        }, usd_per_price_unit_per_lot=2)

        self.assertEqual(FIXED_LOT_SIZE, 0.1)
        self.assertTrue(values['available'])
        self.assertAlmostEqual(values['estimated_loss_usd'], 2)
        self.assertAlmostEqual(values['estimated_target_1_usd'], 4)
        self.assertAlmostEqual(values['estimated_target_2_usd'], 6)

    def test_sell_trade_values_reverse_price_direction(self):
        values = estimate_trade_values({
            'status': 'SCALP ENTRY CONFIRMED',
            'direction': 'SELL',
            'entry': 100,
            'stop_loss': 110,
            'tp1': 85,
            'tp2': 80,
        }, usd_per_price_unit_per_lot=2)

        self.assertAlmostEqual(values['estimated_loss_usd'], 2)
        self.assertAlmostEqual(values['estimated_target_1_usd'], 3)
        self.assertAlmostEqual(values['estimated_target_2_usd'], 4)

    def test_dollars_are_not_guessed_without_contract_value(self):
        values = estimate_trade_values({
            'status': 'ENTRY CONFIRMED',
            'direction': 'BUY',
            'entry': 100,
            'stop_loss': 90,
            'tp1': 120,
            'tp2': 130,
        }, usd_per_price_unit_per_lot=None)

        self.assertFalse(values['available'])
        self.assertEqual(values['risk_price_units'], 10)
        self.assertNotIn('estimated_loss_usd', values)


if __name__ == '__main__':
    unittest.main()
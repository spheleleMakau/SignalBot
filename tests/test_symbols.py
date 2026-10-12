import unittest

from market.symbols import DEFAULT_MARKET, discover_markets


class MarketDiscoveryTests(unittest.TestCase):
    def test_gold_is_the_default_live_market(self):
        self.assertEqual(DEFAULT_MARKET, 'gold')

    def test_discovers_requested_deriv_markets(self):
        catalog = [
            {'underlying_symbol': '1HZ100V', 'underlying_symbol_name': 'Volatility 100 (1s) Index'},
            {'underlying_symbol': 'BOOM1000', 'underlying_symbol_name': 'Boom 1000 Index'},
            {'underlying_symbol': 'BOOM500', 'underlying_symbol_name': 'Boom 500 Index'},
            {'underlying_symbol': 'CRASH1000', 'underlying_symbol_name': 'Crash 1000 Index'},
            {'underlying_symbol': 'CRASH500', 'underlying_symbol_name': 'Crash 500 Index'},
            {'underlying_symbol': 'R_75', 'underlying_symbol_name': 'Volatility 75 Index'},
            {'underlying_symbol': 'stpRNG', 'underlying_symbol_name': 'Step Index'},
            {'underlying_symbol': 'frxXAUUSD', 'underlying_symbol_name': 'Gold/USD'},
            {'underlying_symbol': 'GOLD_BASKET', 'underlying_symbol_name': 'Gold Basket'},
        ]

        result = discover_markets(catalog)

        self.assertEqual(set(result), {
            'step_index', 'boom_1000', 'boom_500', 'crash_1000', 'crash_500', 'volatility_75', 'gold',
        })
        self.assertEqual(result['volatility_75']['symbol'], 'R_75')
        self.assertEqual(result['gold']['symbol'], 'frxXAUUSD')

    def test_prefers_standard_index_over_one_second_variant(self):
        result = discover_markets([
            {'underlying_symbol': '1HZ1000V', 'underlying_symbol_name': 'Boom 1000 (1s) Index'},
            {'underlying_symbol': 'BOOM1000', 'underlying_symbol_name': 'Boom 1000 Index'},
        ])

        self.assertEqual(result['boom_1000']['symbol'], 'BOOM1000')


if __name__ == '__main__':
    unittest.main()
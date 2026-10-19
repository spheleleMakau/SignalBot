import unittest

import pandas as pd

from analysis.indicators import indicators


class IndicatorConfluenceTests(unittest.TestCase):
    @staticmethod
    def candles(closes):
        return pd.DataFrame([
            {
                'timestamp': index * 60,
                'open': close,
                'high': close + 0.2,
                'low': close - 0.2,
                'close': close,
                'volume': 1,
            }
            for index, close in enumerate(closes)
        ])

    def test_trending_prices_produce_bullish_supertrend_and_efficient_t3_flow(self):
        enriched = indicators(self.candles([100 + index for index in range(100)]))
        latest = enriched.iloc[-1]

        self.assertEqual(latest.supertrend_confluence, 1)
        self.assertGreaterEqual(latest.efficiency_ratio_10, 0.2)
        self.assertEqual(latest.flow_direction, 1)
        self.assertEqual(latest.trend_confluence, 1)

    def test_flat_market_is_not_confirmed_by_flow_filter(self):
        enriched = indicators(self.candles([100] * 100))
        latest = enriched.iloc[-1]

        self.assertEqual(latest.efficiency_ratio_10, 0)
        self.assertEqual(latest.flow_direction, 0)
        self.assertEqual(latest.trend_confluence, 0)

    def test_falling_prices_produce_bearish_supertrend_and_t3_flow(self):
        enriched = indicators(self.candles([200 - index for index in range(100)]))
        latest = enriched.iloc[-1]

        self.assertEqual(latest.supertrend_confluence, -1)
        self.assertGreaterEqual(latest.efficiency_ratio_10, 0.2)
        self.assertEqual(latest.flow_direction, -1)
        self.assertEqual(latest.trend_confluence, -1)

    def test_indicators_preserve_input_and_expose_all_three_supertrend_directions(self):
        candles = self.candles([100 + index * 0.1 for index in range(80)])
        enriched = indicators(candles)

        self.assertNotIn('trend_confluence', candles)
        self.assertTrue(all(
            f'supertrend_{period}_{factor:g}_direction' in enriched
            for period, factor in ((10, 1.0), (11, 2.0), (12, 3.0))
        ))
        self.assertIn('t3_8', enriched)
        self.assertIn('efficiency_ratio_10', enriched)


if __name__ == '__main__':
    unittest.main()

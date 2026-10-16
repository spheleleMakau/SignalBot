import asyncio
import unittest
from dataclasses import replace
from unittest.mock import patch

from fastapi import HTTPException

import app


class TradingViewWebhookTests(unittest.TestCase):
    def test_tradingview_symbols_are_configured_per_supported_market(self):
        test_settings = replace(
            app.settings,
            tradingview_symbol='STEP:EXACT',
            tradingview_gold_symbol='GOLD:EXACT',
        )
        with patch.object(app, 'settings', test_settings):
            self.assertEqual(app.tradingview_symbol_for_market('step_index'), 'STEP:EXACT')
            self.assertEqual(app.tradingview_symbol_for_market('gold'), 'GOLD:EXACT')
            self.assertEqual(app.tradingview_symbol_for_market('boom_500'), '')

    def test_accepts_fresh_matching_utc_alert(self):
        now = 1_700_000_000
        alert = app.TradingViewWebhookAlert(
            ticker='EXACT:STEPINDEX',
            direction='BUY',
            timeframe='1',
            bar_time='2023-11-14T22:13:20Z',
        )

        test_settings = replace(
            app.settings,
            tradingview_webhook_token='secret',
            tradingview_symbol='EXACT:STEPINDEX',
        )
        with patch.object(app, 'settings', test_settings), \
                patch.object(app.time, 'time', return_value=now), \
                patch.object(app, 'latest_tradingview_alert', None):
            result = asyncio.run(app.tradingview_webhook('secret', alert))

        self.assertEqual(result['status'], 'CONFIRMATION RECEIVED')
        self.assertEqual(result['bar_timestamp'], now)

    def test_gold_alert_uses_gold_ticker_configuration(self):
        now = 1_700_000_000
        alert = app.TradingViewWebhookAlert(
            ticker='EXACT:GOLD',
            direction='SELL',
            timeframe='1',
            bar_time='2023-11-14T22:13:20Z',
        )
        test_settings = replace(
            app.settings,
            tradingview_webhook_token='secret',
            tradingview_symbol='EXACT:STEPINDEX',
            tradingview_gold_symbol='EXACT:GOLD',
        )
        with patch.object(app, 'settings', test_settings), \
                patch.dict(app.state, {'market_id': 'gold'}), \
                patch.object(app.time, 'time', return_value=now), \
                patch.object(app, 'latest_tradingview_alert', None):
            result = asyncio.run(app.tradingview_webhook('secret', alert))

        self.assertEqual(result['ticker'], 'EXACT:GOLD')

    def test_rejects_invalid_token(self):
        alert = app.TradingViewWebhookAlert(
            ticker='EXACT:STEPINDEX',
            direction='BUY',
            timeframe='1',
            bar_time='2023-11-14T22:13:20Z',
        )
        test_settings = replace(
            app.settings,
            tradingview_webhook_token='secret',
            tradingview_symbol='EXACT:STEPINDEX',
        )
        with patch.object(app, 'settings', test_settings):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(app.tradingview_webhook('wrong', alert))

        self.assertEqual(error.exception.status_code, 401)

    def test_rejects_mismatched_ticker_and_non_utc_timestamp(self):
        alert = app.TradingViewWebhookAlert(
            ticker='OTHER:SYMBOL',
            direction='SELL',
            timeframe='1',
            bar_time='2023-11-14T22:13:20Z',
        )
        test_settings = replace(
            app.settings,
            tradingview_webhook_token='secret',
            tradingview_symbol='EXACT:STEPINDEX',
        )
        with patch.object(app, 'settings', test_settings):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(app.tradingview_webhook('secret', alert))

        self.assertEqual(error.exception.status_code, 422)

        offset_alert = alert.model_copy(update={
            'ticker': 'EXACT:STEPINDEX',
            'bar_time': '2023-11-15T00:13:20+02:00',
        })
        with patch.object(app, 'settings', test_settings), \
                patch.object(app.time, 'time', return_value=1_700_000_000):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(app.tradingview_webhook('secret', offset_alert))

        self.assertEqual(error.exception.status_code, 422)

    def test_rejects_non_one_minute_alert(self):
        alert = app.TradingViewWebhookAlert(
            ticker='EXACT:STEPINDEX',
            direction='BUY',
            timeframe='5',
            bar_time='2023-11-14T22:13:20Z',
        )
        test_settings = replace(
            app.settings,
            tradingview_webhook_token='secret',
            tradingview_symbol='EXACT:STEPINDEX',
        )
        with patch.object(app, 'settings', test_settings):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(app.tradingview_webhook('secret', alert))

        self.assertEqual(error.exception.status_code, 422)


if __name__ == '__main__':
    unittest.main()

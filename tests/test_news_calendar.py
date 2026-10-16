import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import httpx

from news.calendar import TradingEconomicsCalendar


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc_value, _traceback):
        return False

    async def get(self, url, params):
        self.calls.append((url, params))
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


class TradingEconomicsCalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_api_key_is_explicit_and_does_not_call_provider(self):
        calendar = TradingEconomicsCalendar('')

        result = await calendar.refresh(datetime(2026, 10, 16, tzinfo=timezone.utc))

        self.assertEqual(result['status'], 'NOT CONFIGURED')
        self.assertEqual(result['events'], [])

    async def test_fetches_multiple_macro_countries_and_filters_upcoming_impactful_events(self):
        now = datetime(2026, 10, 16, 8, tzinfo=timezone.utc)
        payload = [
            {
                'CalendarId': 1,
                'Date': '2026-10-16T09:30:00',
                'Country': 'United States',
                'Event': 'CPI',
                'Importance': 3,
                'Forecast': '0.2%',
                'Previous': '0.3%',
                'Source': 'BLS',
                'SourceURL': 'https://www.bls.gov/',
            },
            {
                'CalendarId': 2,
                'Date': '2026-10-16T10:00:00Z',
                'Country': 'Japan',
                'Event': 'Low importance item',
                'Importance': 1,
            },
            {
                'CalendarId': 3,
                'Date': '2026-10-15T09:00:00Z',
                'Country': 'China',
                'Event': 'Already released',
                'Importance': 3,
            },
        ]
        client = FakeClient(payload=payload)
        calendar = TradingEconomicsCalendar('private-api-key')

        with patch('news.calendar.httpx.AsyncClient', return_value=client):
            result = await calendar.refresh(now)

        self.assertEqual(result['status'], 'LIVE')
        self.assertEqual(len(result['events']), 1)
        event = result['events'][0]
        self.assertEqual(event['event'], 'CPI')
        self.assertEqual(event['importance'], 3)
        self.assertEqual(event['time'], '2026-10-16T09:30:00+00:00')
        self.assertEqual(event['forecast'], '0.2%')
        self.assertEqual(event['source'], 'BLS')
        request_url, request_params = client.calls[0]
        self.assertIn('united%20states,china,euro%20area,united%20kingdom,japan', request_url)
        self.assertEqual(request_params, {'c': 'private-api-key', 'f': 'json'})

    async def test_successful_calendar_response_is_cached(self):
        now = datetime(2026, 10, 16, 8, tzinfo=timezone.utc)
        client = FakeClient(payload=[])
        calendar = TradingEconomicsCalendar('private-api-key')

        with patch('news.calendar.httpx.AsyncClient', return_value=client):
            first = await calendar.refresh(now)
            second = await calendar.refresh(now.replace(minute=5))

        self.assertEqual(first['status'], 'LIVE')
        self.assertEqual(second['status'], 'LIVE')
        self.assertEqual(len(client.calls), 1)

    async def test_source_failure_is_explicit_then_preserves_cached_events_as_stale(self):
        now = datetime(2026, 10, 16, 8, tzinfo=timezone.utc)
        live_client = FakeClient(payload=[{
            'CalendarId': 1,
            'Date': '2026-10-16T09:30:00Z',
            'Country': 'United States',
            'Event': 'CPI',
            'Importance': 3,
        }])
        failed_client = FakeClient(error=httpx.RequestError('unavailable'))
        calendar = TradingEconomicsCalendar('private-api-key')

        with patch('news.calendar.httpx.AsyncClient', side_effect=[live_client, failed_client]):
            live = await calendar.refresh(now)
            stale = await calendar.refresh(now.replace(minute=16))

        self.assertEqual(live['status'], 'LIVE')
        self.assertEqual(stale['status'], 'STALE')
        self.assertTrue(stale['stale'])
        self.assertEqual(stale['events'][0]['event'], 'CPI')
        self.assertIn('Could not reach', stale['message'])


if __name__ == '__main__':
    unittest.main()

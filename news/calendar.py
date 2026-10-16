import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx

TRADING_ECONOMICS_CALENDAR_URL = 'https://api.tradingeconomics.com/calendar/country'
CALENDAR_COUNTRIES = ('united states', 'china', 'euro area', 'united kingdom', 'japan')
CALENDAR_LOOKAHEAD_DAYS = 7
CALENDAR_REFRESH_SECONDS = 15 * 60
CALENDAR_RETRY_SECONDS = 60


class TradingEconomicsCalendar:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self._cached: dict[str, Any] | None = None
        self._next_refresh = 0.0
        self._lock = asyncio.Lock()

    async def refresh(self, now: datetime | None = None) -> dict[str, Any]:
        if not self.api_key:
            return self._empty(
                'NOT CONFIGURED',
                'Set TRADING_ECONOMICS_API_KEY to enable the Gold economic calendar.',
            )

        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            raise ValueError('Calendar refresh time must include a timezone')
        moment = moment.astimezone(timezone.utc)
        now_epoch = moment.timestamp()
        if self._cached and now_epoch < self._next_refresh:
            return dict(self._cached)

        async with self._lock:
            if self._cached and now_epoch < self._next_refresh:
                return dict(self._cached)
            start_date = moment.date()
            end_date = start_date + timedelta(days=CALENDAR_LOOKAHEAD_DAYS)
            countries = ','.join(quote(country, safe='') for country in CALENDAR_COUNTRIES)
            url = (
                f'{TRADING_ECONOMICS_CALENDAR_URL}/{countries}/'
                f'{start_date.isoformat()}/{end_date.isoformat()}'
            )
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, params={'c': self.api_key, 'f': 'json'})
                    response.raise_for_status()
                    payload = response.json()
                events = self._normalize_events(payload, moment)
            except httpx.TimeoutException:
                return self._failure('Trading Economics request timed out.', now_epoch)
            except httpx.HTTPStatusError as error:
                return self._failure(
                    f'Trading Economics returned HTTP {error.response.status_code}.',
                    now_epoch,
                )
            except httpx.RequestError:
                return self._failure('Could not reach Trading Economics.', now_epoch)
            except (ValueError, TypeError, KeyError):
                return self._failure('Trading Economics returned an invalid calendar response.', now_epoch)

            self._cached = {
                'status': 'LIVE',
                'provider': 'Trading Economics',
                'updated_at': int(now_epoch),
                'stale': False,
                'message': 'Upcoming medium- and high-importance macro events; calendar context only.',
                'timezone': 'UTC',
                'events': events,
            }
            self._next_refresh = now_epoch + CALENDAR_REFRESH_SECONDS
            return dict(self._cached)

    def _failure(self, message: str, now_epoch: float) -> dict[str, Any]:
        self._next_refresh = now_epoch + CALENDAR_RETRY_SECONDS
        if self._cached:
            now = datetime.fromtimestamp(now_epoch, timezone.utc)
            upcoming_events = [
                event for event in self._cached['events']
                if datetime.fromisoformat(event['time']) >= now
            ]
            return {
                **self._cached,
                'status': 'STALE',
                'stale': True,
                'message': message,
                'events': upcoming_events,
            }
        return self._empty('SOURCE ERROR', message)

    @staticmethod
    def _empty(status: str, message: str) -> dict[str, Any]:
        return {
            'status': status,
            'provider': 'Trading Economics',
            'updated_at': None,
            'stale': False,
            'message': message,
            'timezone': 'UTC',
            'events': [],
        }

    @staticmethod
    def _normalize_events(payload: Any, now: datetime) -> list[dict[str, Any]]:
        if not isinstance(payload, list):
            raise ValueError('Calendar response must be a list')

        events = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError('Calendar entry must be an object')
            try:
                importance = int(item.get('Importance') or 0)
            except (TypeError, ValueError):
                importance = 0
            if importance < 2:
                continue

            raw_date = item.get('Date')
            if not isinstance(raw_date, str) or not raw_date:
                continue
            try:
                event_time = datetime.fromisoformat(raw_date.replace('Z', '+00:00'))
            except ValueError:
                continue
            if event_time.tzinfo is None:
                event_time = event_time.replace(tzinfo=timezone.utc)
            event_time = event_time.astimezone(timezone.utc)
            if event_time < now:
                continue

            name = item.get('Event') or item.get('Category')
            if not isinstance(name, str) or not name.strip():
                continue
            events.append({
                'id': str(item.get('CalendarId') or f'{event_time.timestamp()}:{name}'),
                'time': event_time.isoformat(),
                'country': str(item.get('Country') or ''),
                'event': name.strip(),
                'importance': importance,
                'forecast': item.get('Forecast') or item.get('TEForecast'),
                'previous': item.get('Previous'),
                'actual': item.get('Actual'),
                'source': item.get('Source'),
                'source_url': item.get('SourceURL'),
            })

        events.sort(key=lambda event: event['time'])
        return events

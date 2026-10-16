import asyncio
import json
import unittest
from unittest.mock import patch

from market.candles import CandleStore
from market.websocket import DerivFeed


class FakeSocket:
    def __init__(self, tick=None):
        self.responses = []
        self.tick = tick
        self.requests = []

    async def send(self, payload):
        request = json.loads(payload)
        self.requests.append(request)
        if 'active_symbols' in request:
            self.responses.append(json.dumps({'active_symbols': [
                {'underlying_symbol': 'stpRNG', 'underlying_symbol_name': 'Step Index'},
                {'underlying_symbol': 'frxXAUUSD', 'underlying_symbol_name': 'Gold/USD'},
            ]}))
        elif 'ticks_history' in request:
            candles = [{'epoch': 0, 'open': 100, 'high': 101, 'low': 99, 'close': 100}]
            if request['granularity'] == 300:
                candles.append({'epoch': 1, 'open': 100, 'high': 101, 'low': 99, 'close': 100})
            self.responses.append(json.dumps({'candles': candles}))
        elif 'ticks' in request:
            self.responses.append(json.dumps({'subscription': {'id': 'test'}}))
            if self.tick:
                self.responses.append(json.dumps({'tick': self.tick}))

    async def recv(self):
        if self.responses:
            return self.responses.pop(0)
        await asyncio.Future()


class FakeConnection:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class DerivFeedTests(unittest.IsolatedAsyncioTestCase):
    async def run_feed_once(self, tick=None, market=None):
        store = CandleStore()
        socket = FakeSocket(tick)
        feed = DerivFeed(store, self.on_tick, self.on_status)
        if market:
            feed.request_market(market)
        self.ticks = []
        self.statuses = []

        async def stop_retry(_delay):
            feed.running = False

        with patch('market.websocket.TICK_TIMEOUT_SECONDS', 0.01):
            with patch('market.websocket.websockets.connect', return_value=FakeConnection(socket)):
                with patch('market.websocket.asyncio.sleep', new=stop_retry):
                    await feed.run()

        return feed, socket

    async def on_tick(self, epoch, price):
        self.ticks.append((epoch, price))

    async def on_status(self, status):
        self.statuses.append(status)

    async def test_tick_timeout_marks_feed_unavailable(self):
        feed, _ = await self.run_feed_once()

        self.assertFalse(feed.connected)
        self.assertTrue(any(status.startswith('ERROR:') for status in self.statuses))
        self.assertEqual(self.ticks, [])

    async def test_candle_gap_triggers_feed_resync(self):
        feed, _ = await self.run_feed_once({'epoch': 180, 'quote': 100})

        self.assertFalse(feed.connected)
        self.assertTrue(any('gap detected' in status.lower() for status in self.statuses))
        self.assertEqual(self.ticks, [])

    async def test_default_feed_loads_and_subscribes_to_step_index_symbol(self):
        feed, socket = await self.run_feed_once({'epoch': 1, 'quote': 100})

        history_requests = [request for request in socket.requests if 'ticks_history' in request]
        tick_requests = [request for request in socket.requests if 'ticks' in request]
        self.assertEqual(feed.requested_market, 'step_index')
        self.assertEqual(len(history_requests), 5)
        self.assertTrue(all(request['ticks_history'] == 'stpRNG' for request in history_requests))
        self.assertEqual(tick_requests, [{'ticks': 'stpRNG', 'subscribe': 1}])
        self.assertEqual(self.ticks, [(1, 100)])
        self.assertEqual(len(feed.store.dataframe('5m')), 1)

    async def test_step_index_selection_uses_step_index_symbol(self):
        _, socket = await self.run_feed_once({'epoch': 1, 'quote': 100}, market='step_index')

        history_requests = [request for request in socket.requests if 'ticks_history' in request]
        tick_requests = [request for request in socket.requests if 'ticks' in request]
        self.assertTrue(all(request['ticks_history'] == 'stpRNG' for request in history_requests))
        self.assertEqual(tick_requests, [{'ticks': 'stpRNG', 'subscribe': 1}])


if __name__ == '__main__':
    unittest.main()
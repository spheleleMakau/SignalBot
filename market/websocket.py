import asyncio, json, logging, time
import websockets
from config import settings
from .symbols import DEFAULT_MARKET, MARKET_LABELS, discover_markets

TICK_TIMEOUT_SECONDS = 10
logger = logging.getLogger(__name__)

class DerivFeed:
    def __init__(self, store, on_tick, on_status, on_symbol=None):
        self.store, self.on_tick, self.on_status, self.on_symbol = store, on_tick, on_status, on_symbol
        self.running = True; self.connected = False; self.last_tick_at = None
        self.requested_market = DEFAULT_MARKET
        self.markets = {}
        self.selection_changed = asyncio.Event()

    def request_market(self, market_id):
        if market_id not in MARKET_LABELS:
            raise ValueError('Unsupported market')
        if market_id != self.requested_market:
            self.requested_market = market_id
            self.selection_changed.set()

    async def run(self):
        url = 'wss://api.derivws.com/trading/v1/options/ws/public'
        while self.running:
            self.selection_changed.clear()
            try:
                await self.on_status('RECONNECTING')
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as socket:
                    await socket.send(json.dumps({'active_symbols': 'brief'}))
                    catalog = json.loads(await socket.recv())
                    if catalog.get('error'):
                        raise RuntimeError(catalog['error'].get('message', 'Deriv symbol catalog failed'))
                    self.markets = discover_markets(catalog.get('active_symbols', []))
                    market_id = self.requested_market
                    if market_id not in self.markets:
                        raise RuntimeError(f'{MARKET_LABELS[market_id]} was not present in active_symbols')
                    selected_market = self.markets[market_id]
                    symbol = selected_market['symbol']
                    if self.on_symbol: await self.on_symbol(market_id, symbol, selected_market['name'])
                    for timeframe, granularity in (('1m', 60), ('5m', 300), ('15m', 900), ('1h', 3600), ('4h', 14400)):
                        await socket.send(json.dumps({
                            'ticks_history': symbol,
                            'count': 500,
                            'end': 'latest',
                            'style': 'candles',
                            'granularity': granularity,
                        }))
                        candle_response = json.loads(await socket.recv())
                        if candle_response.get('error'):
                            raise RuntimeError(candle_response['error'].get('message', f'Deriv {timeframe} candles failed'))
                        candles = candle_response.get('candles', [])
                        aligned_candles = [
                            candle for candle in candles
                            if int(candle['epoch']) % granularity == 0
                        ]
                        skipped = len(candles) - len(aligned_candles)
                        if skipped:
                            logger.warning(
                                'Skipped %d misaligned %s history candles for %s',
                                skipped, timeframe, symbol,
                            )
                        if candles and not aligned_candles:
                            raise RuntimeError(f'Deriv returned no time-aligned {timeframe} candles for {symbol}')
                        self.store.load_candles(timeframe, aligned_candles)
                    if self.requested_market != market_id:
                        continue
                    await socket.send(json.dumps({'ticks': symbol, 'subscribe': 1}))
                    response = json.loads(await socket.recv())
                    if response.get('error'):
                        raise RuntimeError(response['error'].get('message', 'Deriv tick subscription failed'))
                    await self.on_status('LIVE'); self.connected = True
                    switch_market = False
                    while self.running:
                        receive_task = asyncio.create_task(asyncio.wait_for(socket.recv(), timeout=TICK_TIMEOUT_SECONDS))
                        selection_task = asyncio.create_task(self.selection_changed.wait())
                        done, pending = await asyncio.wait(
                            (receive_task, selection_task),
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)
                        if selection_task in done and self.requested_market != market_id:
                            switch_market = True
                            break
                        raw = receive_task.result()
                        message = json.loads(raw)
                        if message.get('error'):
                            raise RuntimeError(message['error'].get('message', 'Deriv tick stream failed'))
                        tick = message.get('tick')
                        if tick and 'quote' in tick:
                            epoch = int(tick.get('epoch', time.time())); price = float(tick['quote']); self.store.add_tick(epoch, price); self.last_tick_at = epoch; await self.on_tick(epoch, price)
                    self.connected = False
                    if switch_market:
                        continue
            except asyncio.CancelledError: break
            except Exception as error:
                self.connected = False
                await self.on_status(f'ERROR: {error}')
                await asyncio.sleep(3)
        self.connected = False; await self.on_status('OFFLINE')

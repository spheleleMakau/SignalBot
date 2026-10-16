import asyncio, base64, hmac, json, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
import plotly.graph_objects as go
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from config import TIMEFRAMES, settings
from data.database import Database
from market.candles import CandleStore
from market.websocket import DerivFeed
from market.symbols import DEFAULT_MARKET, MARKET_LABELS
from analysis.signal_engine import SignalEngine
from analysis.signal_journal import SignalJournal
from backtest.engine import run_backtest
from trading.risk import estimate_trade_values
from trading.trade_manager import TradeManager

if settings.dashboard_auth_required and not (settings.dashboard_username and settings.dashboard_password):
    raise RuntimeError('DASHBOARD_USERNAME and DASHBOARD_PASSWORD are required when dashboard authentication is enabled.')

BASE_DIR = Path(__file__).resolve().parent
database_path = Path(settings.database_path)
if not database_path.is_absolute():
    database_path = BASE_DIR / database_path

store = CandleStore(); database = Database(str(database_path)); engine = SignalEngine(settings.symbol, settings.min_signal_score); manager = TradeManager(); journal = SignalJournal()
SCALPING_DISABLED = {
    'status': 'SCALPING DISABLED — USE MAIN SIGNAL',
    'direction': None,
    'reasons': ['Rapid scalp entries are disabled. Wait for the validated multi-timeframe main signal.'],
}
TRADINGVIEW_ALERT_MAX_AGE_SECONDS = 125
latest_tradingview_alert = None
state = {'connection': 'OFFLINE', 'last_tick': None, 'price': None, 'symbol': None, 'market_id': DEFAULT_MARKET, 'market_name': MARKET_LABELS[DEFAULT_MARKET], 'signal': {'status': 'NO LIVE DATA — NO SIGNAL', 'reasons': ['Waiting for a fresh live tick before evaluating an entry.']}, 'scalp_signal': dict(SCALPING_DISABLED), 'trade_status': 'WAITING', 'exit_alert': None, 'backtest': {'status': 'WAITING FOR DATA'}, 'scalp_backtest': {'status': 'DISABLED'}, 'app_mode': settings.app_mode}; feed_task = None; feed = None; last_saved_signal = None; last_backtest_candle = None; last_saved_candles = {}
HISTORY_LIMIT = 20
HISTORY_DETAIL_LIMIT = 50
HISTORY_MAX_AGE_SECONDS = 24 * 60 * 60


def detect_mode(request: Request | None = None):
    if request is not None:
        request_mode = (request.query_params.get('mode') or '').strip().lower()
        if request_mode in {'aviator', 'power'}:
            return 'aviator'
    return settings.app_mode if settings.app_mode in {'step_index', 'aviator'} else 'step_index'


async def fetch_aviator_signal():
    empty = {'status': 'NO AVIATOR SIGNAL', 'direction': None, 'score': 0, 'reasons': ['No live Aviator signal source configured'], 'timestamp': int(time.time()), 'entry': None, 'stop_loss': None, 'tp1': None, 'tp2': None, 'risk_reward': None, 'symbol': 'AVIATOR'}
    if not settings.aviator_signal_url:
        return empty
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(settings.aviator_signal_url)
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, dict):
            return {
                'status': payload.get('status', 'AVIATOR SIGNAL'),
                'direction': payload.get('direction') or None,
                'score': payload.get('score', 0),
                'reasons': payload.get('reasons', ['Live Aviator feed connected']),
                'timestamp': int(payload.get('timestamp') or time.time()),
                'entry': payload.get('entry'),
                'stop_loss': payload.get('stop_loss'),
                'tp1': payload.get('tp1'),
                'tp2': payload.get('tp2'),
                'risk_reward': payload.get('risk_reward'),
                'symbol': payload.get('symbol', 'AVIATOR')
            }
    except Exception:
        return {'status': 'AVIATOR FEED ERROR', 'direction': None, 'score': 0, 'reasons': ['Signal source unreachable'], 'timestamp': int(time.time()), 'entry': None, 'stop_loss': None, 'tp1': None, 'tp2': None, 'risk_reward': None, 'symbol': 'AVIATOR'}
    return empty


def build_history(limit: int = HISTORY_LIMIT, symbol: str | None = None):
    now = int(time.time())
    stored = database.recent_signals(limit=limit, since=now - HISTORY_MAX_AGE_SECONDS)
    merged, seen = [], set()
    for entry in journal.recent(limit) + stored:
        if symbol and entry.get('symbol') != symbol:
            continue
        timestamp = int(entry.get('timestamp') or 0)
        if entry.get('outcome') != 'ENTRY CONFIRMED' or not now - HISTORY_MAX_AGE_SECONDS <= timestamp <= now:
            continue
        if not entry.get('direction') or entry.get('direction') == 'NONE':
            continue
        if entry.get('entry') is None:
            continue
        entry['confirmed'] = True
        identifier = entry.get('id')
        if identifier in seen:
            continue
        seen.add(identifier)
        merged.append(entry)
    merged.sort(key=lambda item: item.get('timestamp') or 0, reverse=True)
    return merged[:limit]


def backtest_passes(backtest: dict) -> bool:
    return (
        backtest.get('status') == 'COMPLETE'
        and backtest.get('trades', 0) >= 10
        and (backtest.get('profit_factor') or 0) > 1
        and backtest.get('net_result', 0) > 0
        and backtest.get('validation_trades', 0) >= 5
        and (backtest.get('validation_profit_factor') or 0) > 1
        and backtest.get('validation_net_result', 0) > 0
    )


def backtest_gate_status(backtest: dict) -> str:
    if backtest_passes(backtest):
        return 'PASS'
    if backtest.get('status') != 'COMPLETE':
        return backtest.get('status', 'WAITING FOR DATA')
    if backtest.get('trades', 0) < 10:
        return f"BLOCKED · {backtest.get('trades', 0)}/10 TRADES"
    if backtest.get('validation_trades', 0) < 5:
        return f"BLOCKED · {backtest.get('validation_trades', 0)}/5 HOLDOUT TRADES"
    return 'BLOCKED · EXPECTANCY NOT POSITIVE'


def tradingview_confirms(signal: dict, now: int | None = None) -> bool:
    if not settings.tradingview_symbol or not settings.tradingview_webhook_token or not latest_tradingview_alert:
        return False
    moment = int(time.time()) if now is None else now
    alert = latest_tradingview_alert
    age = moment - int(alert['bar_timestamp'])
    received_age = moment - int(alert['received_at'])
    return (
        alert['ticker'] == settings.tradingview_symbol
        and alert['direction'] == signal.get('direction')
        and alert['timeframe'] == '1'
        and alert['bar_timestamp'] == signal.get('setup_timestamp')
        and 0 <= received_age <= TRADINGVIEW_ALERT_MAX_AGE_SECONDS
        and -5 <= age <= TRADINGVIEW_ALERT_MAX_AGE_SECONDS
    )


def withhold_unconfirmed_entry(signal: dict) -> None:
    signal.update({
        'status': 'WAIT — TRADINGVIEW CONFIRMATION REQUIRED',
        'direction': None,
        'score': 0,
        'reasons': ['Entry withheld: no matching TradingView alert for this exact 1-minute candle, ticker, and direction.'],
    })
    for key in ('id', 'entry', 'stop_loss', 'tp1', 'tp2', 'risk_reward', 'setup_timestamp'):
        signal.pop(key, None)


async def on_status(status):
    global last_backtest_candle, latest_tradingview_alert
    state['connection'] = status
    if status != 'LIVE':
        last_backtest_candle = None
        latest_tradingview_alert = None
        last_saved_candles.clear()
        state['signal'] = {'status': 'NO LIVE DATA — NO SIGNAL', 'reasons': ['Waiting for a fresh live tick before evaluating an entry.']}
        state['scalp_signal'] = dict(SCALPING_DISABLED)
        state['trade_status'] = 'WAITING'
        state['backtest'] = {'status': 'WAITING FOR DATA'}
        state['scalp_backtest'] = {'status': 'DISABLED'}

async def on_tick(epoch, price):
    global last_saved_signal, last_backtest_candle
    state.update({'last_tick': epoch, 'price': price})
    signal = engine.evaluate(store, state['connection'] == 'LIVE')
    scalp_signal = {**SCALPING_DISABLED, 'symbol': state['symbol'], 'timestamp': int(epoch)}
    five_minute = store.dataframe('5m')
    closed_five_minute = five_minute.iloc[:-1].reset_index(drop=True) if len(five_minute) > 1 else five_minute.iloc[:0].copy()
    one_minute = store.dataframe('1m')
    closed_one_minute = one_minute.iloc[:-1].reset_index(drop=True) if len(one_minute) > 1 else one_minute.iloc[:0].copy()
    fifteen_minute = store.dataframe('15m')
    closed_fifteen_minute = fifteen_minute.iloc[:-1].reset_index(drop=True) if len(fifteen_minute) > 1 else fifteen_minute.iloc[:0].copy()
    one_hour = store.dataframe('1h')
    closed_one_hour = one_hour.iloc[:-1].reset_index(drop=True) if len(one_hour) > 1 else one_hour.iloc[:0].copy()
    four_hour = store.dataframe('4h')
    closed_four_hour = four_hour.iloc[:-1].reset_index(drop=True) if len(four_hour) > 1 else four_hour.iloc[:0].copy()
    backtest_candle = int(closed_five_minute.timestamp.iloc[-1]) if not closed_five_minute.empty else None
    if backtest_candle is not None and backtest_candle != last_backtest_candle:
        state['backtest'] = run_backtest(
            closed_one_minute,
            closed_five_minute,
            closed_fifteen_minute,
            closed_one_hour,
            minimum_score=engine.minimum_score,
            four_hour=closed_four_hour,
        )
        last_backtest_candle = backtest_candle
    state['scalp_backtest'] = {'status': 'DISABLED'}
    backtest = state['backtest']
    if signal.get('status') == 'ENTRY CONFIRMED' and not backtest_passes(backtest):
        signal['status'] = 'NO TRADE — BACKTEST FILTER'
        signal['reasons'] = signal.get('reasons', []) + ['Historical validation has not confirmed positive expectancy']
        signal.pop('id', None); signal.pop('entry', None); signal.pop('stop_loss', None); signal.pop('tp1', None); signal.pop('tp2', None); signal.pop('risk_reward', None)
    if signal.get('status') == 'ENTRY CONFIRMED' and not tradingview_confirms(signal):
        withhold_unconfirmed_entry(signal)
    journal.record(signal)
    active_trade = manager.active.copy() if manager.active else None
    trade_status = manager.update(signal, price)
    if active_trade and trade_status in {'STOP LOSS HIT', 'TARGET 1 HIT', 'TARGET 2 HIT'}:
        state['exit_alert'] = {
            'id': f"{active_trade.get('id', 'trade')}:{trade_status}:{int(epoch)}",
            'status': trade_status,
            'direction': active_trade.get('direction'),
            'entry': active_trade.get('entry'),
            'price': price,
            'timestamp': int(epoch),
        }
    state['signal'] = signal; state['scalp_signal'] = scalp_signal; state['trade_status'] = trade_status
    for timeframe, candles in store.snapshot().items():
        if candles and candles[-1]['timestamp'] != last_saved_candles.get(timeframe):
            database.save_candles(state['symbol'], timeframe, candles[-2:])
            last_saved_candles[timeframe] = candles[-1]['timestamp']
    if signal.get('id') and signal.get('id') != last_saved_signal:
        database.save_signal(signal); last_saved_signal = signal['id']

async def on_symbol(market_id, symbol, market_name):
    reset_market_state(market_id, symbol, market_name)

def reset_market_state(market_id, symbol, market_name):
    global last_saved_signal, last_backtest_candle, latest_tradingview_alert
    store.clear()
    manager.active = None
    engine.symbol = symbol
    engine.last_setup_key = None
    journal.entries.clear()
    last_saved_signal = None
    last_backtest_candle = None
    latest_tradingview_alert = None
    last_saved_candles.clear()
    state.update({
        'market_id': market_id,
        'market_name': market_name,
        'symbol': symbol,
        'connection': 'RECONNECTING',
        'last_tick': None,
        'price': None,
        'signal': {'status': 'NO LIVE DATA — NO SIGNAL', 'reasons': ['Waiting for the selected market feed.']},
        'scalp_signal': dict(SCALPING_DISABLED),
        'trade_status': 'WAITING',
        'exit_alert': None,
        'backtest': {'status': 'WAITING FOR DATA'},
        'scalp_backtest': {'status': 'DISABLED'},
    })

@asynccontextmanager
async def lifespan(app):
    global feed, feed_task
    feed = DerivFeed(store, on_tick, on_status, on_symbol); feed_task = asyncio.create_task(feed.run())
    yield
    feed.running = False; feed_task.cancel(); await asyncio.gather(feed_task, return_exceptions=True)

app = FastAPI(title='Step Index Trader', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=BASE_DIR / 'dashboard' / 'static'), name='static'); templates = Jinja2Templates(directory=BASE_DIR / 'dashboard' / 'templates')

@app.middleware('http')
async def disable_static_cache(request, call_next):
    response = await call_next(request)
    if request.url.path == '/static/app.js':
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.middleware('http')
async def protect_dashboard(request, call_next):
    is_tradingview_webhook = request.url.path.startswith('/api/tradingview/webhook/')
    if settings.dashboard_auth_required and request.url.path != '/healthz' and not is_tradingview_webhook:
        credentials = f'{settings.dashboard_username}:{settings.dashboard_password}'.encode()
        expected = 'Basic ' + base64.b64encode(credentials).decode('ascii')
        supplied = request.headers.get('authorization', '')
        if not hmac.compare_digest(supplied, expected):
            return Response(
                status_code=401,
                headers={'WWW-Authenticate': 'Basic realm="Step Index Dashboard"'},
            )
    return await call_next(request)

@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    mode = detect_mode(request)
    title = 'Aviator / Live Signal' if mode == 'aviator' else f"{state.get('market_name', MARKET_LABELS[DEFAULT_MARKET])} / Live Analysis"
    symbol_label = 'AVIATOR' if mode == 'aviator' else (state.get('symbol') or 'WAITING FOR LIVE SYMBOL')
    template_name = 'aviator.html' if mode == 'aviator' else 'index.html'
    return templates.TemplateResponse(template_name, {'request': request, 'symbol': symbol_label, 'app_mode': mode, 'page_title': title})


class TradingViewWebhookAlert(BaseModel):
    ticker: str
    direction: Literal['BUY', 'SELL']
    timeframe: str
    bar_time: str


@app.post('/api/tradingview/webhook/{webhook_token}')
async def tradingview_webhook(webhook_token: str, alert: TradingViewWebhookAlert):
    global latest_tradingview_alert
    if not settings.tradingview_webhook_token or not settings.tradingview_symbol:
        raise HTTPException(status_code=503, detail='TradingView confirmation is not configured')
    if not hmac.compare_digest(webhook_token, settings.tradingview_webhook_token):
        raise HTTPException(status_code=401, detail='Invalid TradingView webhook token')
    if not hmac.compare_digest(alert.ticker, settings.tradingview_symbol):
        raise HTTPException(status_code=422, detail='TradingView ticker does not match the configured market')
    if alert.timeframe != '1':
        raise HTTPException(status_code=422, detail='Only confirmed 1-minute TradingView alerts are accepted')
    try:
        bar_time = datetime.fromisoformat(alert.bar_time.replace('Z', '+00:00'))
    except ValueError as error:
        raise HTTPException(status_code=422, detail='bar_time must be a UTC ISO-8601 timestamp') from error
    if bar_time.tzinfo is None:
        raise HTTPException(status_code=422, detail='bar_time must include a timezone')
    if bar_time.utcoffset() != timezone.utc.utcoffset(bar_time):
        raise HTTPException(status_code=422, detail='bar_time must be expressed in UTC')
    bar_timestamp = int(bar_time.timestamp())
    now = int(time.time())
    age = now - bar_timestamp
    if age < -5 or age > TRADINGVIEW_ALERT_MAX_AGE_SECONDS:
        raise HTTPException(status_code=422, detail='TradingView alert is outside the accepted time window')
    latest_tradingview_alert = {
        'ticker': alert.ticker,
        'direction': alert.direction,
        'timeframe': alert.timeframe,
        'bar_timestamp': bar_timestamp,
        'received_at': now,
    }
    return {'status': 'CONFIRMATION RECEIVED', 'ticker': alert.ticker, 'direction': alert.direction, 'bar_timestamp': bar_timestamp}

@app.get('/healthz')
async def health_check():
    return {'status': 'ok', 'service': 'step-index-trader'}

@app.get('/api/markets')
async def api_markets():
    available = feed.markets if feed else {}
    return {
        'selected': state.get('market_id', DEFAULT_MARKET),
        'options': [
            {
                'id': market_id,
                'label': label,
                'symbol': available.get(market_id, {}).get('symbol'),
                'available': market_id in available,
            }
            for market_id, label in MARKET_LABELS.items()
        ],
    }

class MarketSelection(BaseModel):
    market_id: str

@app.post('/api/select-market')
async def select_market(selection: MarketSelection):
    if selection.market_id not in MARKET_LABELS:
        raise HTTPException(status_code=422, detail='Unsupported market')
    if not feed or selection.market_id not in feed.markets:
        raise HTTPException(status_code=503, detail='Market is not available in the live feed')
    if selection.market_id == state.get('market_id'):
        return {'selected': selection.market_id, 'status': 'ALREADY SELECTED'}
    if manager.active:
        raise HTTPException(status_code=409, detail='Close the active tracked trade before switching markets')
    feed.request_market(selection.market_id)
    market = feed.markets[selection.market_id]
    reset_market_state(selection.market_id, market['symbol'], market.get('name') or MARKET_LABELS[selection.market_id])
    state['connection'] = 'SWITCHING MARKET'
    return {'selected': selection.market_id, 'status': 'SWITCHING'}

@app.get('/api/state')
async def api_state(request: Request):
    mode = detect_mode(request)
    state['app_mode'] = mode
    if mode == 'aviator':
        payload = {
            'app_mode': mode,
            'connection': 'LIVE' if bool(settings.aviator_signal_url) else 'OFFLINE',
            'last_tick': int(time.time()),
            'price': None,
            'symbol': 'AVIATOR',
            'signal': await fetch_aviator_signal(),
            'scalp_signal': dict(SCALPING_DISABLED),
            'trade_status': 'WAITING',
            'backtest': {'status': 'POWER MODE'},
            'candles': {},
            'history': [],
            'timeframe_analysis': {},
            'bot': {'mode': 'AVIATOR POWER MODE', 'orders_enabled': False, 'feed_age_seconds': 0, 'feed_quality': 'LIVE' if bool(settings.aviator_signal_url) else 'OFFLINE', 'risk_guard': 'ACTIVE', 'tradingview_confirmation': 'NOT USED IN AVIATOR MODE', 'execution_note': 'Separate mode for Aviator signal feed; Step Index behavior remains unchanged.'},
            'today_trend': {'direction': 'WAITING'}
        }
        return payload
    payload = dict(state); payload['candles'] = {tf: list(values)[-120:] for tf, values in store.frames.items()}; payload['history'] = build_history(limit=HISTORY_DETAIL_LIMIT, symbol=state.get('symbol')); payload['app_mode'] = mode
    payload['trade_values'] = estimate_trade_values(payload.get('signal', {}), settings.usd_per_price_unit_per_lot)
    feed_age = None if not state['last_tick'] else max(0, int(time.time()) - int(state['last_tick']))
    feed_is_fresh = state['connection'] == 'LIVE' and feed_age is not None and feed_age <= 10
    payload['timeframe_analysis'] = build_timeframe_analysis(store, state['last_tick'], feed_is_fresh)
    backtest = state.get('backtest') or {}
    tv_configured = bool(settings.tradingview_symbol and settings.tradingview_webhook_token)
    payload['bot'] = {'mode': 'ALERT_ONLY', 'orders_enabled': False, 'feed_age_seconds': feed_age, 'feed_quality': 'LIVE' if state['connection'] == 'LIVE' and feed_age is not None and feed_age <= 10 else 'STALE', 'risk_guard': 'ACTIVE', 'backtest_status': backtest_gate_status(backtest), 'backtest_trades': backtest.get('trades', 0), 'backtest_profit_factor': backtest.get('profit_factor'), 'backtest_validation_trades': backtest.get('validation_trades', 0), 'backtest_validation_profit_factor': backtest.get('validation_profit_factor'), 'scalp_backtest_status': 'DISABLED', 'tradingview_confirmation': 'CONFIGURED · WAITING FOR MATCH' if tv_configured else 'NOT CONFIGURED · ENTRIES BLOCKED', 'execution_note': 'No orders are placed by this application. Scalping is disabled.'}
    today = datetime.now(timezone.utc).date()
    candles = [candle for candle in store.snapshot()['5m'] if datetime.fromtimestamp(candle['timestamp'], timezone.utc).date() == today]
    if candles:
        opening = float(candles[0]['open']); latest = float(candles[-1]['close']); change = latest - opening
        payload['today_trend'] = {'direction': 'BULLISH' if change > 0 else 'BEARISH' if change < 0 else 'FLAT', 'open': opening, 'current': latest, 'high': max(candle['high'] for candle in candles), 'low': min(candle['low'] for candle in candles), 'change': change, 'change_percent': (change / opening * 100) if opening else 0, 'candles': len(candles)}
    else:
        payload['today_trend'] = {'direction': 'WAITING'}
    return payload


def build_timeframe_analysis(market_store, last_tick, feed_is_fresh):
    from analysis.candle_patterns import candle_confirmation
    from analysis.candle_patterns import breakout_confirmation
    from analysis.indicators import indicators
    from analysis.structure import market_structure

    analysis = {}
    for timeframe in TIMEFRAMES:
        frame = market_store.dataframe(timeframe)
        if last_tick is not None and not frame.empty:
            active_bucket = int(last_tick) - int(last_tick) % TIMEFRAMES[timeframe]
            if int(frame.timestamp.iloc[-1]) == active_bucket:
                frame = frame.iloc[:-1].reset_index(drop=True)
        if len(frame) < 30:
            analysis[timeframe] = {
                'status': 'WAITING FOR DATA',
                'candles': len(frame),
                'bias': 'UNCLEAR',
                'action': 'WAIT',
            }
            continue
        enriched = indicators(frame)
        latest = enriched.iloc[-1]
        structure = market_structure(enriched)
        ema_ready = all(latest[key] == latest[key] for key in ('ema_20', 'ema_50', 'ema_200'))
        recent_price_change = latest.close - enriched.close.iloc[-4]
        recent_ema_change = latest.ema_20 - enriched.ema_20.iloc[-4]
        bullish_breakout = breakout_confirmation(enriched, 'BUY')
        bearish_breakout = breakout_confirmation(enriched, 'SELL')
        short_bullish = ema_ready and latest.close > latest.ema_20 > latest.ema_50 > latest.ema_200 and recent_price_change > 0 and recent_ema_change > 0 and bullish_breakout
        short_bearish = ema_ready and latest.close < latest.ema_20 < latest.ema_50 < latest.ema_200 and recent_price_change < 0 and recent_ema_change < 0 and bearish_breakout
        pattern = candle_confirmation(enriched)
        layers = {
            'trend': 'BULLISH' if short_bullish else 'BEARISH' if short_bearish else 'NEUTRAL',
            'structure': 'BULLISH' if structure['bias'] == 'BULLISH' else 'BEARISH' if structure['bias'] == 'BEARISH' else 'NEUTRAL',
            'momentum': 'BULLISH' if recent_price_change > 0 and recent_ema_change > 0 else 'BEARISH' if recent_price_change < 0 and recent_ema_change < 0 else 'NEUTRAL',
            'rsi': 'BULLISH' if 52 <= latest.rsi_14 <= 68 else 'BEARISH' if 32 <= latest.rsi_14 <= 48 else 'NEUTRAL',
            'pattern': pattern['direction'] if pattern['direction'] in {'BUY', 'SELL'} and breakout_confirmation(enriched, pattern['direction']) else 'NEUTRAL',
        }
        layers['pattern'] = 'BULLISH' if layers['pattern'] == 'BUY' else 'BEARISH' if layers['pattern'] == 'SELL' else 'NEUTRAL'
        bullish_votes = sum(value == 'BULLISH' for value in layers.values())
        bearish_votes = sum(value == 'BEARISH' for value in layers.values())
        ema_alignment = 'BULLISH' if ema_ready and latest.close > latest.ema_20 > latest.ema_50 > latest.ema_200 else 'BEARISH' if ema_ready and latest.close < latest.ema_20 < latest.ema_50 < latest.ema_200 else 'MIXED'
        action = 'BUY' if bullish_votes >= 3 and bullish_votes - bearish_votes >= 2 and short_bullish else 'SELL' if bearish_votes >= 3 and bearish_votes - bullish_votes >= 2 and short_bearish else 'WAIT'
        if not feed_is_fresh:
            action = 'WAIT'
        confluence = {
            'bullish_votes': bullish_votes,
            'bearish_votes': bearish_votes,
            'total_layers': len(layers),
            'layers': layers,
            'action': action,
        }
        analysis[timeframe] = {
            'status': 'LIVE ANALYSIS' if feed_is_fresh else 'STALE · WAITING',
            'candles': len(frame),
            'timestamp': int(latest.timestamp),
            'open': float(latest.open),
            'high': float(latest.high),
            'low': float(latest.low),
            'close': float(latest.close),
            'bias': 'BULLISH' if action == 'BUY' else 'BEARISH' if action == 'SELL' else 'RANGING' if structure['bias'] == 'RANGING' else 'MIXED' if feed_is_fresh else 'UNCLEAR',
            'action': action,
            'confluence': confluence,
            'structure': (structure.get('bos') or structure['bias']) if feed_is_fresh else 'WAIT',
            'ema_alignment': ema_alignment if feed_is_fresh else 'MIXED',
            'rsi': float(latest.rsi_14) if latest.rsi_14 == latest.rsi_14 else None,
            'atr': float(latest.atr_14) if latest.atr_14 == latest.atr_14 else None,
        }
    return analysis

@app.get('/api/chart')
async def api_chart(timeframe: str = '5m'):
    if timeframe not in store.frames:
        timeframe = '5m'
    timeframe_label = {'1m': '1 MINUTE', '5m': '5 MINUTES', '15m': '15 MINUTES', '1h': '1 HOUR', '4h': '4 HOURS'}[timeframe]
    chart_context = {
        'market_id': state.get('market_id'),
        'market_name': state.get('market_name', 'Market'),
        'symbol': state.get('symbol'),
        'timeframe': timeframe,
    }
    frame = store.dataframe(timeframe)
    if state.get('connection') != 'LIVE' or frame.empty:
        return {
            **chart_context,
            'data': [],
            'layout': {
                'template': 'plotly_dark',
                'title': f"{chart_context['market_name']} · {timeframe_label} · WAITING FOR LIVE CANDLES",
                'uirevision': f"{chart_context['market_id']}:{chart_context['symbol']}:{timeframe}",
            },
        }
    from analysis.candle_patterns import candle_confirmation
    from analysis.indicators import indicators
    from analysis.structure import market_structure
    from analysis.support_resistance import levels
    enriched = indicators(frame)
    chart = go.Figure(data=[go.Candlestick(x=enriched.timestamp, open=enriched.open, high=enriched.high, low=enriched.low, close=enriched.close, name='Live price candles')])
    for period, label, color in ((20,'Short trend line (20 candles)','#f6c85f'),(50,'Middle trend line (50 candles)','#66c7f2'),(200,'Long trend line (200 candles)','#ff7f66')):
        chart.add_trace(go.Scatter(x=enriched.timestamp, y=enriched[f'ema_{period}'], name=label, line={'color':color,'width':1.2}))

    closed = enriched
    last_tick = state.get('last_tick')
    if last_tick is not None and not closed.empty:
        active_bucket = int(last_tick) - int(last_tick) % TIMEFRAMES[timeframe]
        if int(closed.timestamp.iloc[-1]) == active_bucket:
            closed = closed.iloc[:-1].reset_index(drop=True)
    structure = market_structure(closed)
    swing_line_specs = (
        (structure.get('swing_lows', []), 'low', 'swing support', '#75e6a2'),
        (structure.get('swing_highs', []), 'high', 'swing resistance', '#ff8a8a'),
    )
    for points, price_key, label, color in swing_line_specs:
        if len(points) < 2:
            continue
        first, second = points[-2:]
        if second['timestamp'] <= first['timestamp']:
            continue
        slope = (second[price_key] - first[price_key]) / (second['timestamp'] - first['timestamp'])
        if slope == 0:
            continue
        direction = 'Rising' if slope > 0 else 'Falling'
        name = f'{direction} {label}'
        end_time = int(closed.timestamp.iloc[-1])
        end_price = second[price_key] + slope * (end_time - second['timestamp'])
        chart.add_trace(go.Scatter(
            x=[first['timestamp'], second['timestamp'], end_time],
            y=[first[price_key], second[price_key], end_price],
            mode='lines', name=name,
            line={'color': color, 'width': 1.5, 'dash': 'dash'},
            hovertemplate=f'{name}<br>%{{y:.2f}}<extra></extra>',
        ))

    pattern_x = {'BUY': [], 'SELL': []}
    pattern_y = {'BUY': [], 'SELL': []}
    pattern_text = {'BUY': [], 'SELL': []}
    pattern_start = max(2, len(closed) - 120)
    for index in range(pattern_start, len(closed)):
        sample = closed.iloc[:index + 1]
        confirmation = candle_confirmation(sample)
        direction = confirmation['direction']
        if direction is None:
            continue
        candle = closed.iloc[index]
        offset = float(candle.atr_14) * .2 if candle.atr_14 == candle.atr_14 else 0
        pattern_x[direction].append(int(candle.timestamp))
        pattern_y[direction].append(float(candle.high + offset if direction == 'SELL' else candle.low - offset))
        pattern_text[direction].append(', '.join(confirmation['patterns']))
    for direction, symbol, color in (('BUY', 'triangle-up', '#75e6a2'), ('SELL', 'triangle-down', '#ff6b6b')):
        if pattern_x[direction]:
            chart.add_trace(go.Scatter(
                x=pattern_x[direction], y=pattern_y[direction], mode='markers',
                name=f'{direction} candle patterns',
                marker={'symbol': symbol, 'size': 10, 'color': color},
                text=pattern_text[direction], hovertemplate='%{text}<extra></extra>',
            ))

    marker_data = (state.get('backtest') or {}).get('trade_markers', [])
    if marker_data and not enriched.empty:
        visible_markers = [marker for marker in marker_data if int(enriched.timestamp.iloc[0]) <= marker['timestamp'] <= int(enriched.timestamp.iloc[-1])]
        if visible_markers:
            marker_colors = {'WIN': '#75e6a2', 'LOSS': '#ff6b6b', 'FLAT': '#f6c85f'}
            chart.add_trace(go.Scatter(
                x=[marker['timestamp'] for marker in visible_markers],
                y=[marker['entry'] for marker in visible_markers],
                mode='markers', name='Resolved backtest entries',
                marker={
                    'symbol': ['triangle-up' if marker['direction'] == 'BUY' else 'triangle-down' for marker in visible_markers],
                    'size': 13,
                    'color': [marker_colors.get(marker['result'], '#d9e2e5') for marker in visible_markers],
                    'line': {'width': 1, 'color': '#0b1117'},
                },
                text=[f"Backtest {marker['direction']} · {marker['result']} · {marker['entry']:.2f}" for marker in visible_markers],
                hovertemplate='%{text}<extra></extra>',
            ))

    plan = state.get('signal', {})
    if plan.get('status') == 'ENTRY CONFIRMED':
        entry = plan.get('entry')
        stop = plan.get('stop_loss')
        target_1 = plan.get('tp1')
        target_2 = plan.get('tp2')
        if entry is not None and stop is not None:
            chart.add_hrect(
                y0=min(entry, stop), y1=max(entry, stop), x0=0, x1=1,
                fillcolor='#ff6b6b', opacity=.12, line_width=0,
                layer='below',
            )
        if entry is not None and target_2 is not None:
            chart.add_hrect(
                y0=min(entry, target_2), y1=max(entry, target_2), x0=0, x1=1,
                fillcolor='#75e6a2', opacity=.08, line_width=0,
                layer='below',
            )
        for key, color, label in (
            ('entry', '#75e6a2', 'ENTRY'),
            ('stop_loss', '#ff6b6b', 'STOP · CLOSE IF WRONG'),
            ('tp1', '#75e6a2', 'TARGET 1'),
            ('tp2', '#75e6a2', 'TARGET 2'),
        ):
            if plan.get(key) is not None:
                chart.add_hline(
                    y=plan[key], line_color=color, line_dash='dash' if key == 'stop_loss' else 'solid',
                    line_width=2, annotation_text=f"{label} · {float(plan[key]):.2f}",
                    annotation_position='right', annotation_font_color=color,
                    annotation_bgcolor='rgba(11,17,23,.85)',
                )
    current_price = float(enriched.close.iloc[-1])
    nearest_levels = sorted(levels(closed, structure), key=lambda level: abs(level['price'] - current_price))[:8]
    for level in nearest_levels:
        color = '#75e6a2' if level['type'] == 'support' else '#ff6b6b'
        label = 'PRICE FLOOR' if level['type'] == 'support' else 'PRICE CEILING'
        chart.add_hline(y=level['price'], line_color=color, line_dash='dot', opacity=.65, annotation_text=f"{label} · {level['tests']} tests")
    action = state.get('timeframe_analysis', {}).get(timeframe, {}).get('action', 'WAIT')
    bias_label = {'BUY': 'UP BIAS', 'SELL': 'DOWN BIAS', 'WAIT': 'WAIT'}[action]
    chart.update_layout(template='plotly_dark', height=520, margin={'l':20,'r':20,'t':54,'b':34}, title={'text': f"{chart_context['market_name']} · {timeframe_label} · {bias_label} · BIAS ONLY, NOT AN ENTRY", 'x': .02, 'xanchor': 'left', 'font': {'size': 16}}, legend={'orientation': 'h', 'y': 1.02, 'x': 0}, hovermode='x unified', xaxis={'fixedrange': False}, yaxis={'fixedrange': False}, xaxis_rangeslider_visible=False, uirevision=f"{chart_context['market_id']}:{chart_context['symbol']}:{timeframe}")
    return {**chart_context, **json.loads(chart.to_json())}

class ExitAlertAcknowledgement(BaseModel): id: str

@app.post('/api/exit-alert/acknowledge')
async def acknowledge_exit_alert(request: ExitAlertAcknowledgement):
    alert = state.get('exit_alert')
    if alert and alert.get('id') == request.id:
        state['exit_alert'] = None
        return {'acknowledged': True}
    return {'acknowledged': False}

@app.get('/api/performance')
async def api_performance(): return {'status': 'NO LIVE PERFORMANCE DATA' if not database.recent_signals(1) else 'LIVE SIGNAL HISTORY ONLY', 'trades': 0}

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)

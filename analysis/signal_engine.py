import time
import uuid
from math import floor
from .candle_patterns import breakout_confirmation, candle_confirmation
from .support_resistance import levels
from .timeframe import multi_timeframe
from .indicators import indicators

REQUIRED_SIGNAL_TIMEFRAMES = ('4h', '1h', '15m', '5m', '1m')
TIMEFRAME_LABELS = {'4h': '4H', '1h': '1H', '15m': '15M', '5m': '5M', '1m': '1M'}
MAX_ENTRY_SIGNAL_AGE_SECONDS = 60
MAX_ENTRY_DRIFT_ATR = 0.25
VOLUME_PROFILE_LOOKBACK = 60
MIN_PROFILE_CANDLES = 10


def _swing_volume_confirmation(one_minute, structure, current_price):
    result = {
        'direction': structure.get('bias', 'UNCLEAR'),
        'swing_high': None,
        'swing_low': None,
        'poc': None,
        'price': current_price,
        'price_vs_poc': 'UNAVAILABLE',
        'direction_poc_aligned': None,
        'volume_candles': 0,
        'status': 'WAITING FOR CLOSED LIVE TICK-VOLUME CANDLES',
        'entry_context': 'POC is advisory and does not change signal eligibility.',
        'source': 'Tick-volume estimate; Deriv historical candles do not provide traded volume.',
    }
    swing_highs = structure.get('swing_highs', [])
    swing_lows = structure.get('swing_lows', [])
    if swing_highs:
        result['swing_high'] = float(swing_highs[-1]['high'])
    if swing_lows:
        result['swing_low'] = float(swing_lows[-1]['low'])

    if one_minute is None or one_minute.empty or 'volume' not in one_minute:
        return result

    recent = one_minute.tail(VOLUME_PROFILE_LOOKBACK)
    recent = recent.loc[recent['volume'] > 0]
    result['volume_candles'] = int(len(recent))
    if len(recent) < MIN_PROFILE_CANDLES:
        return result

    typical_prices = (recent['high'] + recent['low'] + recent['close']) / 3
    atr = float(one_minute['high'].sub(one_minute['low']).tail(VOLUME_PROFILE_LOOKBACK).mean())
    if atr <= 0 or atr != atr:
        result['status'] = 'WAITING FOR VALID PRICE RANGE'
        return result

    bin_size = atr * 0.1
    price_origin = float(typical_prices.min())
    volume_by_bin = {}
    price_by_bin = {}
    for price, volume in zip(typical_prices, recent['volume']):
        bin_index = floor((float(price) - price_origin) / bin_size)
        volume_by_bin[bin_index] = volume_by_bin.get(bin_index, 0.0) + float(volume)
        price_by_bin.setdefault(bin_index, []).append((float(price), float(volume)))

    poc_bin = max(volume_by_bin, key=volume_by_bin.get)
    bin_prices = price_by_bin[poc_bin]
    total_volume = sum(volume for _, volume in bin_prices)
    poc = sum(price * volume for price, volume in bin_prices) / total_volume
    result.update({'poc': poc, 'status': 'AVAILABLE · TICK-VOLUME ESTIMATE'})

    if current_price is None:
        return result
    distance = float(current_price) - poc
    tolerance = bin_size
    if abs(distance) <= tolerance:
        result['price_vs_poc'] = 'AT POC'
    elif distance > 0:
        result['price_vs_poc'] = 'ABOVE POC'
    else:
        result['price_vs_poc'] = 'BELOW POC'

    direction = result['direction']
    if direction in {'BULLISH', 'BEARISH'} and result['price_vs_poc'] != 'AT POC':
        result['direction_poc_aligned'] = (
            result['price_vs_poc'] == ('ABOVE POC' if direction == 'BULLISH' else 'BELOW POC')
        )
    if result['price_vs_poc'] == 'AT POC':
        result['entry_context'] = 'Price is near the estimated POC; watch for a directional reaction. Advisory only.'
    elif result['direction_poc_aligned'] is True:
        result['entry_context'] = 'Price location is consistent with swing direction relative to POC. Advisory only.'
    elif result['direction_poc_aligned'] is False:
        result['entry_context'] = 'Price location conflicts with swing direction relative to POC. Advisory only.'
    else:
        result['entry_context'] = 'Swing direction is unclear; use POC as context only.'
    return result


def _timeframe_alignment(frames):
    biases = []
    for timeframe in REQUIRED_SIGNAL_TIMEFRAMES:
        item = frames.get(timeframe, {})
        if not item.get('available') or item.get('bias') not in {'BULLISH', 'BEARISH'}:
            return None
        biases.append(item['bias'])
    if all(bias == 'BULLISH' for bias in biases):
        return 'BUY'
    if all(bias == 'BEARISH' for bias in biases):
        return 'SELL'
    return None


def _live_entry_price(store, signal_candle, atr):
    tick = store.last_tick
    if not tick:
        return None, 'WAIT — LIVE PRICE UNAVAILABLE'
    signal_close_time = int(signal_candle.timestamp) + 60
    signal_age = int(tick['timestamp']) - signal_close_time
    if signal_age < 0 or signal_age >= MAX_ENTRY_SIGNAL_AGE_SECONDS:
        return None, 'WAIT — ENTRY WINDOW EXPIRED'
    live_price = float(tick['price'])
    if abs(live_price - float(signal_candle.close)) > atr * MAX_ENTRY_DRIFT_ATR:
        return None, 'WAIT — PRICE MOVED'
    return live_price, None


class SignalEngine:
    def __init__(self, symbol, minimum_score=75):
        self.symbol = symbol; self.minimum_score = minimum_score; self.last_setup_key = None

    def evaluate(self, store, connected: bool):
        base = {'id': None, 'symbol': self.symbol, 'status': 'NO TRADE', 'direction': None, 'score': 0, 'reasons': [], 'timestamp': int(time.time()), 'timeframes': {}, 'levels': [], 'indicators': {}, 'swing_volume_confirmation': _swing_volume_confirmation(None, {}, None)}
        if not connected: base['status'] = 'NO LIVE DATA — NO SIGNAL'; return base
        frames = multi_timeframe(store, closed_only=True); base['timeframes'] = {key: {k:v for k,v in value.items() if k != 'frame'} for key,value in frames.items()}
        fifteen_minute = frames.get('15m', {})
        one_minute = frames.get('1m', {}).get('frame')
        latest_tick = getattr(store, 'last_tick', None)
        base['swing_volume_confirmation'] = _swing_volume_confirmation(
            one_minute,
            fifteen_minute.get('structure', {}),
            latest_tick.get('price') if latest_tick else None,
        )
        aligned_direction = _timeframe_alignment(frames)
        if aligned_direction is None:
            summary = ' · '.join(
                f"{TIMEFRAME_LABELS[timeframe]} {frames.get(timeframe, {}).get('bias', 'NO DATA')}"
                if frames.get(timeframe, {}).get('available') else f"{TIMEFRAME_LABELS[timeframe]} NO DATA"
                for timeframe in REQUIRED_SIGNAL_TIMEFRAMES
            )
            base.update({
                'status': 'WAIT — TIMEFRAMES NOT ALIGNED',
                'reasons': [
                    'Wait until every closed timeframe from 4H to 1M points the same way.',
                    f'Current readings: {summary}.',
                ],
            })
            return base
        one_minute = frames['1m']['frame']; structure = frames['15m']['structure']; higher = frames['1h']['bias']; setup = frames['5m']['bias']; confirmation = candle_confirmation(one_minute); atr = float(one_minute.atr_14.iloc[-1])
        if atr != atr or atr <= 0: base['status'] = 'NO TRADE — VOLATILITY UNAVAILABLE'; return base
        current, timing_status = _live_entry_price(store, one_minute.iloc[-1], atr)
        if timing_status:
            base.update({
                'status': timing_status,
                'reasons': ['Wait for a fresh 1-minute close and a live price near its signal level.'],
            })
            return base
        sr = levels(one_minute, structure); base['levels'] = sr; latest = one_minute.iloc[-1]; base['indicators'] = {key: float(latest[key]) for key in ('ema_20','ema_50','ema_200','rsi_14','atr_14','supertrend_confluence','flow_direction','efficiency_ratio_10','t3_8','trend_confluence') if key in latest and latest[key] == latest[key]}
        setup_frame = frames['5m']['frame']
        if len(setup_frame) < 2:
            base['status'] = 'NO TRADE — WAITING FOR 5M SETUP'
            return base
        setup_candle = setup_frame.iloc[-1]
        setup_previous = setup_frame.iloc[-2]
        buy_trend_confluence = latest.get('trend_confluence', 0) == 1 and setup_candle.get('trend_confluence', 0) == 1
        sell_trend_confluence = latest.get('trend_confluence', 0) == -1 and setup_candle.get('trend_confluence', 0) == -1
        buy_ema_alignment = all((latest[key] == latest[key]) for key in ('ema_20', 'ema_50', 'ema_200')) and latest.close > latest.ema_20 > latest.ema_50 > latest.ema_200 and setup_candle.close > setup_candle.ema_20 > setup_candle.ema_50 > setup_candle.ema_200 and setup_candle.ema_20 > setup_previous.ema_20
        sell_ema_alignment = all((latest[key] == latest[key]) for key in ('ema_20', 'ema_50', 'ema_200')) and latest.close < latest.ema_20 < latest.ema_50 < latest.ema_200 and setup_candle.close < setup_candle.ema_20 < setup_candle.ema_50 < setup_candle.ema_200 and setup_candle.ema_20 < setup_previous.ema_20
        rsi_momentum = (45 < latest.rsi_14 < 70) if higher == 'BULLISH' else (30 < latest.rsi_14 < 55) if higher == 'BEARISH' else False
        not_chasing = abs(current - latest.ema_20) <= atr * 1.5 if latest.ema_20 == latest.ema_20 else False
        follow_through = breakout_confirmation(one_minute, aligned_direction)
        direction = 'BUY' if aligned_direction == 'BUY' and higher == 'BULLISH' and setup == 'BULLISH' and structure['bias'] == 'BULLISH' and confirmation['direction'] == 'BUY' and follow_through and buy_ema_alignment and buy_trend_confluence and rsi_momentum and not_chasing else 'SELL' if aligned_direction == 'SELL' and higher == 'BEARISH' and setup == 'BEARISH' and structure['bias'] == 'BEARISH' and confirmation['direction'] == 'SELL' and follow_through and sell_ema_alignment and sell_trend_confluence and rsi_momentum and not_chasing else None
        score = 0; reasons = []
        if direction:
            score += 20; reasons.append('Higher-timeframe direction and 15M structure align'); score += 20; reasons.append('Market structure confirms direction')
            nearby = [x for x in sr if (x['type'] == 'support' if direction == 'BUY' else x['type'] == 'resistance')]
            if nearby: score += 15; reasons.append('Price is interacting with a relevant structure level')
            momentum_ok = (latest.rsi_14 > 50 and latest.rsi_14 < 70) if direction == 'BUY' else (latest.rsi_14 < 50 and latest.rsi_14 > 30)
            if momentum_ok: score += 15; reasons.append('RSI momentum confirms without chasing an extreme')
            score += 10; reasons.append(', '.join(confirmation['patterns']))
            score += 10; reasons.append('1M confirmation agrees with all higher timeframes')
            score += 10; reasons.append('Triple SuperTrend and efficient T3 flow align on 1M and 5M')
            risk = atr * 1.25; swing = min((x['price'] for x in sr if x['type'] == 'support' and x['price'] < current), default=current-risk) if direction == 'BUY' else max((x['price'] for x in sr if x['type'] == 'resistance' and x['price'] > current), default=current+risk)
            stop = min(swing - atr * .25, current-risk) if direction == 'BUY' else max(swing + atr * .25, current+risk)
            unit_risk = abs(current-stop); targets = sorted([x['price'] for x in sr if (x['price'] > current if direction == 'BUY' else x['price'] < current)], reverse=direction == 'SELL')
            tp1 = targets[0] if targets else current + unit_risk * 2 * (1 if direction == 'BUY' else -1); tp2 = targets[1] if len(targets) > 1 else current + unit_risk * 3 * (1 if direction == 'BUY' else -1)
            rr = abs(tp1-current) / unit_risk if unit_risk else 0
            if rr >= 2 and score >= self.minimum_score:
                key = f'{self.symbol}:{direction}:{one_minute.timestamp.iloc[-1]}'; base.update({'id': str(uuid.uuid5(uuid.NAMESPACE_URL, key)), 'status': 'ENTRY CONFIRMED', 'direction': direction, 'setup_timestamp': int(one_minute.timestamp.iloc[-1]), 'score': score, 'entry': current, 'stop_loss': stop, 'tp1': tp1, 'tp2': tp2, 'risk_reward': rr, 'reasons': reasons, 'setup': 'PULLBACK'})
                self.last_setup_key = key; return base
            base['status'] = 'NO TRADE — POOR RISK/REWARD' if rr < 2 else 'NO TRADE — SCORE BELOW THRESHOLD'
        else:
            base['status'] = 'WAIT — ENTRY CONDITIONS NOT MET'
            base['reasons'] = (
                [f'Wait for a closed 1-minute candle to break the previous candle {"high" if aligned_direction == "BUY" else "low"} in the {aligned_direction.lower()} direction.']
                if confirmation['direction'] == aligned_direction and not follow_through
                else ['All timeframe directions agree, but the 1-minute trigger and risk checks have not all passed.']
            )
        return base

    def evaluate_scalp(self, store, connected: bool):
        return {
            'id': None,
            'symbol': self.symbol,
            'status': 'SCALPING DISABLED — USE MAIN SIGNAL',
            'direction': None,
            'score': 0,
            'reasons': ['Rapid scalp entries are disabled. Wait for the validated multi-timeframe main signal.'],
            'timestamp': int(time.time()),
        }

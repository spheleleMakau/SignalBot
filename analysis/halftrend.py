"""Attributed HalfTrend adaptation; see the license notice below.

Adapted from "HalfTrend Long/Short Signal Engine [BigBeluga]":
https://www.tradingview.com/script/ZHGPnlAz-HalfTrend-Long-Short-Signal-Engine-BigBeluga/
Copyright BigBeluga; original HalfTrend logic credited by the author to everget.
Licensed under CC BY-NC-SA 4.0: https://creativecommons.org/licenses/by-nc-sa/4.0/
This derivative module is for non-commercial use and must be shared under the same license.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from typing import Any


class HalfTrendDataError(ValueError):
    """Raised when candle history is not safe for indicator evaluation."""


@dataclass(frozen=True)
class HalfTrendConfig:
    amplitude: int = 20
    channel_deviation: float = 2.0
    base_risk: float = 3.0
    atr_period: int = 100

    def __post_init__(self):
        if (
            isinstance(self.amplitude, bool)
            or not isinstance(self.amplitude, int)
            or not 1 <= self.amplitude <= 1000
        ):
            raise ValueError('Amplitude must be an integer from 1 to 1000')
        if not isfinite(self.channel_deviation) or self.channel_deviation < 0.1:
            raise ValueError('Channel deviation must be finite and at least 0.1')
        if not isfinite(self.base_risk) or self.base_risk <= 0:
            raise ValueError('Base risk must be finite and positive')
        if (
            isinstance(self.atr_period, bool)
            or not isinstance(self.atr_period, int)
            or self.atr_period < 1
        ):
            raise ValueError('ATR period must be a positive integer')


def _normalize_candles(
    candles: Sequence[Mapping[str, Any]],
    timeframe_seconds: int | None,
) -> list[dict[str, float | int]]:
    if timeframe_seconds is not None and timeframe_seconds < 1:
        raise ValueError('Timeframe duration must be positive')
    normalized = []
    for index, candle in enumerate(candles):
        try:
            timestamp = int(candle['timestamp'])
            opening = float(candle['open'])
            high = float(candle['high'])
            low = float(candle['low'])
            close = float(candle['close'])
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            raise HalfTrendDataError(f'Candle {index} is missing valid timestamp/OHLC data') from error
        if timestamp < 0 or not all(isfinite(value) and value > 0 for value in (opening, high, low, close)):
            raise HalfTrendDataError(f'Candle {index} contains an invalid timestamp or price')
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise HalfTrendDataError(f'Candle {index} has inconsistent OHLC values')
        if timeframe_seconds is not None and timestamp % timeframe_seconds:
            raise HalfTrendDataError(f'Candle {index} is not aligned to the selected timeframe')
        if normalized:
            previous = normalized[-1]['timestamp']
            if timestamp <= previous:
                raise HalfTrendDataError('Candle timestamps must be strictly increasing')
            if timeframe_seconds is not None and timestamp != previous + timeframe_seconds:
                raise HalfTrendDataError('Candle history has a missing timeframe boundary')
        normalized.append({
            'timestamp': timestamp,
            'open': opening,
            'high': high,
            'low': low,
            'close': close,
        })
    return normalized


def _wilder_atr(candles: list[dict[str, float | int]], period: int) -> list[float | None]:
    true_ranges = []
    atr_values: list[float | None] = [None] * len(candles)
    for index, candle in enumerate(candles):
        high = float(candle['high'])
        low = float(candle['low'])
        if index == 0:
            true_ranges.append(high - low)
        else:
            previous_close = float(candles[index - 1]['close'])
            true_ranges.append(max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            ))
        if index == period - 1:
            atr_values[index] = sum(true_ranges[-period:]) / period
        elif index >= period:
            previous_atr = atr_values[index - 1]
            if previous_atr is None:
                raise HalfTrendDataError('ATR warm-up state is inconsistent')
            atr_values[index] = (previous_atr * (period - 1) + true_ranges[index]) / period
    return atr_values


def calculate_halftrend(
    candles: Sequence[Mapping[str, Any]],
    config: HalfTrendConfig = HalfTrendConfig(),
    timeframe_seconds: int | None = None,
) -> list[dict[str, Any]]:
    """Calculate HalfTrend lines and close-confirmed trend flips chronologically."""
    rows = _normalize_candles(candles, timeframe_seconds)
    if not rows:
        return []

    highs = [float(row['high']) for row in rows]
    lows = [float(row['low']) for row in rows]
    closes = [float(row['close']) for row in rows]
    atrs = _wilder_atr(rows, config.atr_period)

    trend = 0
    next_trend = 0
    max_low_price = lows[0]
    min_high_price = highs[0]
    up = 0.0
    down = 0.0
    previous_trend: int | None = None
    output = []

    for index, candle in enumerate(rows):
        start = max(0, index - config.amplitude + 1)
        high_window = highs[start:index + 1]
        low_window = lows[start:index + 1]
        high_price = max(high_window)
        low_price = min(low_window)
        high_ma = sum(high_window) / config.amplitude if len(high_window) == config.amplitude else None
        low_ma = sum(low_window) / config.amplitude if len(low_window) == config.amplitude else None
        previous_high = highs[index - 1] if index else highs[index]
        previous_low = lows[index - 1] if index else lows[index]

        if next_trend == 1:
            max_low_price = max(low_price, max_low_price)
            if high_ma is not None and high_ma < max_low_price and closes[index] < previous_low:
                trend = 1
                next_trend = 0
                min_high_price = high_price
            else:
                min_high_price = min(high_price, min_high_price)
        else:
            min_high_price = min(high_price, min_high_price)
            if low_ma is not None and low_ma > min_high_price and closes[index] > previous_high:
                trend = 0
                next_trend = 1
                max_low_price = low_price

        atr = atrs[index]
        atr_half = atr / 2 if atr is not None else None
        deviation = config.channel_deviation * atr_half if atr_half is not None else None
        signal = None
        if trend == 0:
            if previous_trend is not None and previous_trend != 0:
                up = down
            else:
                up = max_low_price if index == 0 else max(max_low_price, up)
            line = up
            band_high = line + deviation if deviation is not None else None
            band_low = line - deviation if deviation is not None else None
        else:
            if previous_trend is not None and previous_trend != 1:
                down = up
            else:
                down = min_high_price if index == 0 else min(min_high_price, down)
            line = down
            band_high = line + deviation if deviation is not None else None
            band_low = line - deviation if deviation is not None else None

        if previous_trend is not None and trend != previous_trend:
            signal = 'LONG' if trend == 0 else 'SHORT'

        risk_distance = atr_half * config.base_risk if atr_half is not None else None
        entry = float(candle['close']) if signal else None
        if signal == 'LONG' and risk_distance is not None:
            stop_loss = entry - risk_distance
            targets = [entry + risk_distance * multiple for multiple in (1, 2, 3)]
        elif signal == 'SHORT' and risk_distance is not None:
            stop_loss = entry + risk_distance
            targets = [entry - risk_distance * multiple for multiple in (1, 2, 3)]
        else:
            stop_loss = None
            targets = [None, None, None]

        output.append({
            'timestamp': int(candle['timestamp']),
            'close_timestamp': int(candle['timestamp']) + timeframe_seconds if timeframe_seconds else None,
            'trend': 'BULLISH' if trend == 0 else 'BEARISH',
            'trend_code': trend,
            'line': line,
            'atr_100': atr,
            'atr_half': atr_half,
            'band_high': band_high,
            'band_low': band_low,
            'signal': signal,
            'entry': entry,
            'stop_loss': stop_loss,
            'tp1': targets[0],
            'tp2': targets[1],
            'tp3': targets[2],
        })
        previous_trend = trend
    return output


def backtest_halftrend(
    candles: Sequence[Mapping[str, Any]],
    bars: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate confirmed close signals with conservative OHLC exit handling."""
    if len(candles) != len(bars):
        raise ValueError('Candle data and HalfTrend results must have matching lengths')
    outcomes = []
    active = None

    def record(exit_status: str, exit_price: float | None):
        nonlocal active
        if active is None:
            return
        direction = 1 if active['direction'] == 'LONG' else -1
        result_r = (
            (exit_price - active['entry']) * direction / active['risk_distance']
            if exit_price is not None and active['risk_distance'] > 0
            else None
        )
        outcomes.append({
            **active,
            'status': exit_status,
            'exit_price': exit_price,
            'result_r': result_r,
        })
        active = None

    for index, (candle, bar) in enumerate(zip(candles, bars)):
        high = float(candle['high'])
        low = float(candle['low'])
        close = float(candle['close'])
        if active is not None and index > active['entry_index']:
            stop_hit = low <= active['stop_loss'] if active['direction'] == 'LONG' else high >= active['stop_loss']
            target_hit = high >= active['tp1'] if active['direction'] == 'LONG' else low <= active['tp1']
            if stop_hit and target_hit:
                record('UNRESOLVED · STOP AND TARGET IN SAME CANDLE', None)
            elif stop_hit:
                record('LOSS · STOP', active['stop_loss'])
            elif target_hit:
                record('WIN · TP1', active['tp1'])

        signal = bar.get('signal')
        if active is not None and signal and signal != active['direction']:
            record('REVERSED', close)
        if active is None and signal:
            risk_distance = (
                float(bar['entry']) - float(bar['stop_loss'])
                if signal == 'LONG'
                else float(bar['stop_loss']) - float(bar['entry'])
            ) if bar.get('entry') is not None and bar.get('stop_loss') is not None else 0
            if risk_distance > 0:
                active = {
                    'direction': signal,
                    'timestamp': int(bar['timestamp']),
                    'entry_index': index,
                    'entry': float(bar['entry']),
                    'stop_loss': float(bar['stop_loss']),
                    'tp1': float(bar['tp1']),
                    'tp2': float(bar['tp2']),
                    'tp3': float(bar['tp3']),
                    'risk_distance': risk_distance,
                }

    open_trade = dict(active) if active is not None else None
    if active is not None:
        record('UNRESOLVED · OPEN AT END OF DATA', None)

    wins = sum(
        item['status'].startswith('WIN') or (
            item['status'] == 'REVERSED' and (item['result_r'] or 0) > 0
        )
        for item in outcomes
    )
    losses = sum(
        item['status'].startswith('LOSS') or (
            item['status'] == 'REVERSED' and (item['result_r'] or 0) < 0
        )
        for item in outcomes
    )
    unresolved = sum(item['status'].startswith('UNRESOLVED') for item in outcomes)
    flats = sum(item['status'] == 'REVERSED' and item['result_r'] == 0 for item in outcomes)
    realized = [float(item['result_r']) for item in outcomes if item['result_r'] is not None]
    equity = peak = max_drawdown = 0.0
    for result in realized:
        equity += result
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return {
        'trades': len(outcomes),
        'wins': wins,
        'losses': losses,
        'unresolved': unresolved,
        'flats': flats,
        'net_result_r': sum(realized),
        'max_drawdown_r': max_drawdown,
        'active_trade': open_trade,
        'outcomes': outcomes[-100:],
        'cost_assumptions': (
            'Gross price movement only. Spread, slippage, commission, financing, and '
            'contract payout are unavailable and excluded; this is not a Rise/Fall payout result.'
        ),
    }

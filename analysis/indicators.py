import numpy as np
import pandas as pd


SUPERTREND_SETTINGS = ((10, 1.0), (11, 2.0), (12, 3.0))
T3_PERIOD = 8
T3_VOLUME_FACTOR = 0.7
FLOW_EFFICIENCY_PERIOD = 10
MIN_FLOW_EFFICIENCY = 0.2


def _supertrend_direction(high, low, close, atr, factor):
    midpoint = (high + low) / 2
    basic_upper = midpoint + factor * atr
    basic_lower = midpoint - factor * atr
    directions = np.full(len(close), np.nan)
    valid = np.flatnonzero(np.isfinite(atr))
    if not len(valid):
        return directions

    start = int(valid[0])
    upper = basic_upper[start]
    lower = basic_lower[start]
    direction = 1.0
    directions[start] = direction

    for index in range(start + 1, len(close)):
        upper = (
            basic_upper[index]
            if basic_upper[index] < upper or close[index - 1] > upper
            else upper
        )
        lower = (
            basic_lower[index]
            if basic_lower[index] > lower or close[index - 1] < lower
            else lower
        )
        if direction < 0 and close[index] > upper:
            direction = 1.0
        elif direction > 0 and close[index] < lower:
            direction = -1.0
        directions[index] = direction
    return directions


def indicators(candles: pd.DataFrame) -> pd.DataFrame:
    frame = candles.copy()
    for period in (20, 50, 200): frame[f'ema_{period}'] = frame['close'].ewm(span=period, adjust=False, min_periods=period).mean()
    delta = frame['close'].diff(); gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    frame['rsi_14'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    previous_close = frame['close'].shift(1)
    true_range = pd.concat([frame['high'] - frame['low'], (frame['high'] - previous_close).abs(), (frame['low'] - previous_close).abs()], axis=1).max(axis=1)
    frame['atr_14'] = true_range.ewm(alpha=1/14, adjust=False, min_periods=14).mean()

    high = frame['high'].to_numpy(dtype=float)
    low = frame['low'].to_numpy(dtype=float)
    close = frame['close'].to_numpy(dtype=float)
    for period, factor in SUPERTREND_SETTINGS:
        direction_column = f'supertrend_{period}_{factor:g}_direction'
        supertrend_atr = true_range.ewm(
            alpha=1 / period, adjust=False, min_periods=period
        ).mean().to_numpy(dtype=float)
        frame[direction_column] = _supertrend_direction(
            high, low, close, supertrend_atr, factor
        )
    supertrend_directions = frame[
        [f'supertrend_{period}_{factor:g}_direction' for period, factor in SUPERTREND_SETTINGS]
    ]
    frame['supertrend_confluence'] = np.where(
        supertrend_directions.eq(1).all(axis=1),
        1.0,
        np.where(supertrend_directions.eq(-1).all(axis=1), -1.0, 0.0),
    )

    ema_values = [
        frame['close'].ewm(
            span=T3_PERIOD, adjust=False, min_periods=T3_PERIOD
        ).mean()
    ]
    for _ in range(5):
        ema_values.append(
            ema_values[-1].ewm(
                span=T3_PERIOD, adjust=False, min_periods=T3_PERIOD
            ).mean()
        )
    e3, e4, e5, e6 = ema_values[2], ema_values[3], ema_values[4], ema_values[5]
    factor = T3_VOLUME_FACTOR
    c1 = -(factor ** 3)
    c2 = 3 * factor ** 2 + 3 * factor ** 3
    c3 = -6 * factor ** 2 - 3 * factor - 3 * factor ** 3
    c4 = 1 + 3 * factor + factor ** 3 + 3 * factor ** 2
    frame[f't3_{T3_PERIOD}'] = c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3

    net_change = frame['close'].diff(FLOW_EFFICIENCY_PERIOD).abs()
    total_change = frame['close'].diff().abs().rolling(
        FLOW_EFFICIENCY_PERIOD, min_periods=FLOW_EFFICIENCY_PERIOD
    ).sum()
    efficiency_ratio = net_change / total_change
    frame[f'efficiency_ratio_{FLOW_EFFICIENCY_PERIOD}'] = efficiency_ratio.mask(
        total_change.eq(0), 0.0
    )
    t3_change = frame[f't3_{T3_PERIOD}'].diff()
    efficient = frame[f'efficiency_ratio_{FLOW_EFFICIENCY_PERIOD}'] >= MIN_FLOW_EFFICIENCY
    frame['flow_direction'] = np.select(
        [
            efficient & (t3_change > 0) & (frame['close'] > frame[f't3_{T3_PERIOD}']),
            efficient & (t3_change < 0) & (frame['close'] < frame[f't3_{T3_PERIOD}']),
        ],
        [1.0, -1.0],
        default=0.0,
    )
    frame['trend_confluence'] = np.where(
        (frame['supertrend_confluence'] == frame['flow_direction'])
        & (frame['supertrend_confluence'] != 0),
        frame['supertrend_confluence'],
        0.0,
    )
    return frame

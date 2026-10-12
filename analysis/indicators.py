import numpy as np
import pandas as pd

def indicators(candles: pd.DataFrame) -> pd.DataFrame:
    frame = candles.copy()
    for period in (20, 50, 200): frame[f'ema_{period}'] = frame['close'].ewm(span=period, adjust=False, min_periods=period).mean()
    delta = frame['close'].diff(); gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean(); loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    frame['rsi_14'] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    previous_close = frame['close'].shift(1)
    true_range = pd.concat([frame['high'] - frame['low'], (frame['high'] - previous_close).abs(), (frame['low'] - previous_close).abs()], axis=1).max(axis=1)
    frame['atr_14'] = true_range.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
    return frame

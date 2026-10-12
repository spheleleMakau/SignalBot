from collections import deque
from math import isfinite
import pandas as pd
from config import TIMEFRAMES


class CandleGapError(ValueError):
    """Raised when live ticks cannot safely extend the candle history."""


class CandleStore:
    def __init__(self, limit=500):
        self.frames = {tf: deque(maxlen=limit) for tf in TIMEFRAMES}
        self.last_tick = None

    def add_tick(self, epoch: int, price: float):
        timestamp = int(epoch)
        quote = float(price)
        if timestamp < 0 or not isfinite(quote) or quote <= 0:
            raise ValueError('Tick timestamp and price must be valid positive market data')
        if self.last_tick and timestamp < self.last_tick['timestamp']:
            raise CandleGapError('Out-of-order tick received; candle history must be resynced')

        buckets = {timeframe: timestamp - timestamp % seconds for timeframe, seconds in TIMEFRAMES.items()}
        for timeframe, bucket in buckets.items():
            series = self.frames[timeframe]
            if not series:
                continue
            previous_bucket = series[-1]['timestamp']
            seconds = TIMEFRAMES[timeframe]
            if bucket < previous_bucket or bucket > previous_bucket + seconds:
                raise CandleGapError(f'{timeframe} candle gap detected; market history must be resynced')

        self.last_tick = {'timestamp': timestamp, 'price': quote}
        for timeframe, seconds in TIMEFRAMES.items():
            bucket = buckets[timeframe]
            series = self.frames[timeframe]
            if series and series[-1]['timestamp'] == bucket:
                candle = series[-1]
                candle['high'] = max(candle['high'], quote)
                candle['low'] = min(candle['low'], quote)
                candle['close'] = quote
            else:
                series.append({'timestamp': bucket, 'open': quote, 'high': quote, 'low': quote, 'close': quote, 'volume': 1})

    def load_candles(self, timeframe: str, candles: list[dict]):
        if timeframe not in self.frames:
            raise ValueError(f'Unsupported timeframe: {timeframe}')
        series = self.frames[timeframe]
        seconds = TIMEFRAMES[timeframe]
        normalized = []
        for candle in candles:
            item = {
                'timestamp': int(candle['epoch']),
                'open': float(candle['open']),
                'high': float(candle['high']),
                'low': float(candle['low']),
                'close': float(candle['close']),
                'volume': 0,
            }
            prices = (item['open'], item['high'], item['low'], item['close'])
            if item['timestamp'] < 0 or item['timestamp'] % seconds or not all(isfinite(value) and value > 0 for value in prices):
                raise ValueError(f'Invalid {timeframe} candle received')
            if not item['low'] <= min(item['open'], item['close']) <= max(item['open'], item['close']) <= item['high']:
                raise ValueError(f'Invalid OHLC values in {timeframe} candle')
            normalized.append(item)

        normalized.sort(key=lambda item: item['timestamp'])
        if any(left['timestamp'] == right['timestamp'] for left, right in zip(normalized, normalized[1:])):
            raise ValueError(f'Duplicate {timeframe} candle timestamps received')
        series.clear()
        series.extend(normalized)
        self.last_tick = None

    def dataframe(self, timeframe):
        return pd.DataFrame(list(self.frames[timeframe]))

    def snapshot(self):
        return {tf: list(values) for tf, values in self.frames.items()}

    def clear(self):
        for series in self.frames.values():
            series.clear()
        self.last_tick = None

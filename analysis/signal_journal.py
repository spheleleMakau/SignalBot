import json
import time
from collections import deque

CONFIRMED_STATUSES = ('ENTRY CONFIRMED', 'SCALP ENTRY CONFIRMED')
NON_SIGNAL_STATUSES = {
    'NO TRADE',
    'NO TRADE — WAITING FOR MULTI-TIMEFRAME DATA',
    'NO TRADE — VOLATILITY UNAVAILABLE',
    'NO LIVE DATA — NO SIGNAL',
    'NO LIVE DATA — NO SCALP SIGNAL',
    'NO TRADE — POOR RISK/REWARD',
    'NO TRADE — SCORE BELOW THRESHOLD',
    'NO TRADE — BACKTEST FILTER',
    'SETUP FORMING',
    'SCALP SETUP — WAITING FOR PULLBACK',
    'SCALP NO TRADE — WAITING FOR 1M TRIGGER',
    'SCALP WAITING FOR 1M/5M DATA',
    'SCALP WAITING FOR VOLATILITY',
}


class SignalJournal:
    """Rolling in-memory log of actual trade entries only.

    Setup-forming and inactive states are intentionally excluded so the UI only
    shows real signal plans instead of provisional market structure reads.
    """

    def __init__(self, capacity: int = 50, sample_interval: int = 60):
        self.capacity = capacity
        self.sample_interval = sample_interval
        self.entries = deque(maxlen=capacity)
        self.last_key = None
        self.last_recorded_at = 0

    @staticmethod
    def is_signal(signal: dict) -> bool:
        status = signal.get('status')
        if status not in CONFIRMED_STATUSES or status in NON_SIGNAL_STATUSES:
            return False
        if signal.get('direction') in (None, 'NONE'):
            return False
        if signal.get('entry') is None:
            return False
        return True

    def record(self, signal: dict) -> None:
        """Store a snapshot when the signal changes or the sample window elapses."""
        if not self.is_signal(signal):
            return
        moment = int(signal.get('timestamp') or time.time())
        key = (signal.get('id'), signal.get('status'), signal.get('direction'))
        transition = key != self.last_key
        if not transition and moment - self.last_recorded_at < self.sample_interval:
            return
        self.last_key = key
        self.last_recorded_at = moment
        self.entries.appendleft(self.normalise(signal))

    def recent(self, limit: int = 20) -> list:
        return list(self.entries)[:limit]

    @staticmethod
    def normalise(signal: dict) -> dict:
        identifier = signal.get('id') or f"{signal.get('status', 'UNKNOWN')}:{signal.get('timestamp')}"
        return {
            'id': identifier,
            'timestamp': signal.get('timestamp'),
            'symbol': signal.get('symbol'),
            'direction': signal.get('direction') or 'NONE',
            'confidence': signal.get('score', 0),
            'outcome': signal.get('status'),
            'entry': signal.get('entry'),
            'stop_loss': signal.get('stop_loss'),
            'take_profit_1': signal.get('tp1'),
            'take_profit_2': signal.get('tp2'),
            'reason': json.dumps(signal.get('reasons', [])),
            'confirmed': signal.get('status') in CONFIRMED_STATUSES,
        }

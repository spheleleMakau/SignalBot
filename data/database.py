import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

class Database:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.init_schema()

    def connect(self):
        connection = sqlite3.connect(self.path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def init_schema(self):
        with closing(self.connect()) as db, db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS candles (id INTEGER PRIMARY KEY, timestamp INTEGER NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL, UNIQUE(timestamp, symbol, timeframe));
            CREATE TABLE IF NOT EXISTS signals (id TEXT PRIMARY KEY, timestamp INTEGER NOT NULL, symbol TEXT NOT NULL, timeframe TEXT NOT NULL, direction TEXT, entry REAL, stop_loss REAL, take_profit_1 REAL, take_profit_2 REAL, confidence INTEGER, reason TEXT, outcome TEXT);
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, signal_id TEXT, opened_at INTEGER, closed_at INTEGER, direction TEXT, entry REAL, stop_loss REAL, take_profit REAL, outcome TEXT, pnl REAL);
            CREATE TABLE IF NOT EXISTS performance (id INTEGER PRIMARY KEY, timestamp INTEGER, metric TEXT, value REAL);
            ''')

    def save_candles(self, symbol: str, timeframe: str, candles: list[dict[str, Any]]):
        with closing(self.connect()) as db, db:
            db.executemany('INSERT OR REPLACE INTO candles(timestamp,symbol,timeframe,open,high,low,close,volume) VALUES(?,?,?,?,?,?,?,?)', [(c['timestamp'], symbol, timeframe, c['open'], c['high'], c['low'], c['close'], c.get('volume')) for c in candles])

    def save_signal(self, signal: dict[str, Any]):
        with closing(self.connect()) as db, db:
            db.execute('INSERT OR REPLACE INTO signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (signal['id'], signal['timestamp'], signal['symbol'], signal.get('timeframe','1m'), signal.get('direction'), signal.get('entry'), signal.get('stop_loss'), signal.get('tp1'), signal.get('tp2'), signal.get('score', 0), json.dumps(signal.get('reasons', [])), signal.get('status')))
            db.execute('DELETE FROM signals WHERE id NOT IN (SELECT id FROM signals WHERE entry IS NOT NULL AND direction IS NOT NULL ORDER BY timestamp DESC LIMIT 50)')

    def recent_signals(self, limit=20, since=None):
        with closing(self.connect()) as db, db:
            if since is None:
                query = 'SELECT * FROM signals WHERE entry IS NOT NULL AND direction IS NOT NULL ORDER BY timestamp DESC LIMIT ?'
                params = (limit,)
            else:
                query = 'SELECT * FROM signals WHERE entry IS NOT NULL AND direction IS NOT NULL AND timestamp >= ? ORDER BY timestamp DESC LIMIT ?'
                params = (since, limit)
            return [dict(row) for row in db.execute(query, params).fetchall()]

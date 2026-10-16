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
            CREATE TABLE IF NOT EXISTS shadow_candidates (
                signal_id TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                evaluated_at INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                setup_timestamp INTEGER NOT NULL,
                direction TEXT NOT NULL,
                entry REAL NOT NULL,
                stop_loss REAL NOT NULL,
                take_profit_1 REAL NOT NULL,
                take_profit_2 REAL NOT NULL,
                score INTEGER NOT NULL,
                entry_latency_seconds INTEGER NOT NULL,
                reasons TEXT NOT NULL,
                backtest_passed INTEGER NOT NULL,
                tradingview_confirmed INTEGER NOT NULL,
                eligible INTEGER NOT NULL,
                gate_status TEXT NOT NULL,
                outcome TEXT NOT NULL DEFAULT 'PENDING',
                outcome_at INTEGER,
                exit_price REAL,
                gross_r REAL,
                ambiguous INTEGER NOT NULL DEFAULT 0,
                bars_held INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_shadow_symbol_outcome
                ON shadow_candidates(symbol, outcome, evaluated_at);
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

    def record_shadow_candidate(
        self,
        signal: dict[str, Any],
        evaluated_at: int,
        backtest_passed: bool,
        tradingview_confirmed: bool,
        gate_status: str,
    ):
        setup_timestamp = int(signal['setup_timestamp'])
        evaluated_at = int(evaluated_at)
        latency = max(0, evaluated_at - (setup_timestamp + 60))
        with closing(self.connect()) as db, db:
            db.execute(
                '''
                INSERT INTO shadow_candidates (
                    signal_id, created_at, last_seen_at, evaluated_at, symbol,
                    setup_timestamp, direction, entry, stop_loss, take_profit_1,
                    take_profit_2, score, entry_latency_seconds, reasons,
                    backtest_passed, tradingview_confirmed, eligible, gate_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(signal_id) DO UPDATE SET
                    last_seen_at = excluded.last_seen_at,
                    backtest_passed = excluded.backtest_passed,
                    tradingview_confirmed = excluded.tradingview_confirmed,
                    eligible = excluded.eligible,
                    gate_status = excluded.gate_status
                WHERE shadow_candidates.outcome = 'PENDING'
                    AND (
                        shadow_candidates.backtest_passed != excluded.backtest_passed
                        OR shadow_candidates.tradingview_confirmed != excluded.tradingview_confirmed
                        OR shadow_candidates.gate_status != excluded.gate_status
                    )
                ''',
                (
                    signal['id'], evaluated_at, evaluated_at, evaluated_at,
                    signal['symbol'], setup_timestamp, signal['direction'],
                    signal['entry'], signal['stop_loss'], signal['tp1'],
                    signal['tp2'], int(signal.get('score', 0)), latency,
                    json.dumps(signal.get('reasons', [])),
                    int(backtest_passed), int(tradingview_confirmed),
                    int(backtest_passed and tradingview_confirmed), gate_status,
                ),
            )

    def pending_shadow_candidates(self, symbol: str | None = None):
        with closing(self.connect()) as db, db:
            if symbol is None:
                rows = db.execute(
                    "SELECT * FROM shadow_candidates WHERE outcome = 'PENDING' ORDER BY evaluated_at"
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT * FROM shadow_candidates WHERE outcome = 'PENDING' AND symbol = ? ORDER BY evaluated_at",
                    (symbol,),
                ).fetchall()
            return [dict(row) for row in rows]

    def complete_shadow_candidate(self, signal_id: str, result: dict[str, Any]):
        with closing(self.connect()) as db, db:
            db.execute(
                '''
                UPDATE shadow_candidates SET
                    outcome = ?, outcome_at = ?, exit_price = ?, gross_r = ?,
                    ambiguous = ?, bars_held = ?
                WHERE signal_id = ? AND outcome = 'PENDING'
                ''',
                (
                    result['outcome'], result.get('outcome_at'),
                    result.get('exit_price'), result.get('gross_r'),
                    int(result.get('ambiguous', False)), result.get('bars_held'),
                    signal_id,
                ),
            )

    def mark_shadow_candidates_incomplete(self, symbol: str, timestamp: int):
        with closing(self.connect()) as db, db:
            db.execute(
                '''
                UPDATE shadow_candidates
                SET outcome = 'INCOMPLETE', outcome_at = ?
                WHERE symbol = ? AND outcome = 'PENDING'
                ''',
                (int(timestamp), symbol),
            )

    def shadow_performance(self, symbol: str | None = None):
        with closing(self.connect()) as db, db:
            where = '' if symbol is None else 'WHERE symbol = ?'
            params = () if symbol is None else (symbol,)
            aggregate = '''
                COUNT(*) AS candidates,
                    COALESCE(SUM(outcome = 'PENDING'), 0) AS pending,
                    COUNT(gross_r) AS resolved,
                    COALESCE(SUM(gross_r > 0), 0) AS wins,
                    COALESCE(SUM(gross_r < 0), 0) AS losses,
                    AVG(gross_r) AS average_gross_r,
                    AVG(entry_latency_seconds) AS average_entry_latency_seconds,
                    COALESCE(SUM(CASE WHEN gross_r > 0 THEN gross_r ELSE 0 END), 0) AS gross_profit,
                    COALESCE(SUM(CASE WHEN gross_r < 0 THEN -gross_r ELSE 0 END), 0) AS gross_loss,
                    COALESCE(SUM(CASE WHEN gross_r IS NOT NULL THEN ambiguous ELSE 0 END), 0) AS ambiguous,
                    COALESCE(SUM(outcome IN ('DATA_GAP', 'INCOMPLETE')), 0) AS data_gaps
            '''
            total = db.execute(f'SELECT {aggregate} FROM shadow_candidates {where}', params).fetchone()
            cohort_rows = db.execute(
                f'SELECT gate_status, {aggregate} FROM shadow_candidates {where} GROUP BY gate_status',
                params,
            ).fetchall()
            recent_rows = db.execute(
                f'''
                SELECT signal_id, evaluated_at, symbol, direction, entry,
                    gate_status, outcome, gross_r, entry_latency_seconds,
                    ambiguous, bars_held
                FROM shadow_candidates
                {where}
                ORDER BY evaluated_at DESC
                LIMIT 20
                ''',
                params,
            ).fetchall()

        def metrics(row):
            resolved = row['resolved']
            gross_loss = row['gross_loss']
            return {
                'candidates': row['candidates'],
                'pending': row['pending'],
                'resolved': resolved,
                'wins': row['wins'],
                'losses': row['losses'],
                'win_rate_percent': row['wins'] / resolved * 100 if resolved else None,
                'average_gross_r': row['average_gross_r'],
                'average_entry_latency_seconds': row['average_entry_latency_seconds'],
                'gross_profit_factor': row['gross_profit'] / gross_loss if gross_loss else None,
                'ambiguous': row['ambiguous'],
                'data_gaps': row['data_gaps'],
            }

        by_gate = {row['gate_status']: metrics(row) for row in cohort_rows}
        recent = [{
            'signal_id': row['signal_id'],
            'timestamp': row['evaluated_at'],
            'symbol': row['symbol'],
            'direction': row['direction'],
            'entry': row['entry'],
            'gate_status': row['gate_status'],
            'outcome': row['outcome'],
            'gross_r': row['gross_r'],
            'entry_latency_seconds': row['entry_latency_seconds'],
            'ambiguous': bool(row['ambiguous']),
            'bars_held': row['bars_held'],
        } for row in recent_rows]

        return {
            'mode': 'SHADOW ONLY · NO ORDERS',
            'methodology': 'Closed 1-minute bars after the observation minute; stop or TP1 first, stop-first if both touch, 120-bar maximum.',
            'cost_model': 'UNAVAILABLE · gross price movement only; spread, slippage, and fill latency are not modeled.',
            **metrics(total),
            'by_gate': by_gate,
            'recent': recent,
        }

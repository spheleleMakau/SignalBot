from collections.abc import Iterable
from typing import Any

SHADOW_HOLDING_BARS = 120
ONE_MINUTE_SECONDS = 60


def resolve_shadow_outcome(
    candidate: dict[str, Any],
    closed_candles: Iterable[dict[str, Any]],
    holding_bars: int = SHADOW_HOLDING_BARS,
) -> dict[str, Any] | None:
    """Resolve a candidate on complete 1-minute bars after its observation minute."""
    evaluated_at = int(candidate['evaluated_at'])
    first_bar = evaluated_at - evaluated_at % ONE_MINUTE_SECONDS + ONE_MINUTE_SECONDS
    future = sorted(
        (
            candle for candle in closed_candles
            if int(candle['timestamp']) >= first_bar
        ),
        key=lambda candle: int(candle['timestamp']),
    )
    if not future:
        return None

    entry = float(candidate['entry'])
    stop = float(candidate['stop_loss'])
    target = float(candidate['take_profit_1'])
    risk = abs(entry - stop)
    direction = 1 if candidate['direction'] == 'BUY' else -1
    if risk <= 0 or candidate['direction'] not in {'BUY', 'SELL'}:
        return {
            'outcome': 'INVALID_PLAN',
            'outcome_at': None,
            'exit_price': None,
            'gross_r': None,
            'ambiguous': False,
            'bars_held': 0,
        }

    expected_bar = first_bar
    for index, candle in enumerate(future[:holding_bars], start=1):
        timestamp = int(candle['timestamp'])
        if timestamp != expected_bar:
            return {
                'outcome': 'DATA_GAP',
                'outcome_at': timestamp,
                'exit_price': None,
                'gross_r': None,
                'ambiguous': False,
                'bars_held': index - 1,
            }

        hit_stop = float(candle['low']) <= stop if direction == 1 else float(candle['high']) >= stop
        hit_target = float(candle['high']) >= target if direction == 1 else float(candle['low']) <= target
        if hit_stop or hit_target:
            ambiguous = hit_stop and hit_target
            outcome = 'STOP' if hit_stop else 'TARGET_1'
            exit_price = stop if hit_stop else target
            return {
                'outcome': outcome,
                'outcome_at': timestamp + ONE_MINUTE_SECONDS,
                'exit_price': exit_price,
                'gross_r': direction * (exit_price - entry) / risk,
                'ambiguous': ambiguous,
                'bars_held': index,
            }

        expected_bar += ONE_MINUTE_SECONDS
        if index == holding_bars:
            exit_price = float(candle['close'])
            return {
                'outcome': 'TIMEOUT',
                'outcome_at': timestamp + ONE_MINUTE_SECONDS,
                'exit_price': exit_price,
                'gross_r': direction * (exit_price - entry) / risk,
                'ambiguous': False,
                'bars_held': index,
            }

    return None


def resolve_pending_shadow_candidates(database, symbol: str, closed_candles: list[dict[str, Any]]) -> None:
    for candidate in database.pending_shadow_candidates(symbol):
        outcome = resolve_shadow_outcome(candidate, closed_candles)
        if outcome is not None:
            database.complete_shadow_candidate(candidate['signal_id'], outcome)

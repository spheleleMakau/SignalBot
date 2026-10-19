from bisect import bisect_left, bisect_right
from collections.abc import Iterable, Mapping
from math import isfinite
from typing import Any


def _validate_contract_parameters(duration_seconds: int, max_entry_delay_seconds: int) -> None:
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds <= 0:
        raise ValueError('Contract duration must be a positive whole number of seconds')
    if isinstance(max_entry_delay_seconds, bool) or not isinstance(max_entry_delay_seconds, int) or max_entry_delay_seconds < 0:
        raise ValueError('Maximum entry delay must be a non-negative whole number of seconds')


def _integer_timestamp(value: Any, field: str) -> int:
    try:
        timestamp = int(value)
        if float(value) != timestamp or timestamp < 0:
            raise ValueError
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f'{field} must be a non-negative whole-second timestamp') from error
    return timestamp


def _normalise_ticks(ticks: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if hasattr(ticks, 'to_dict'):
        ticks = ticks.to_dict('records')

    normalized = []
    for tick in ticks:
        if not isinstance(tick, Mapping):
            raise ValueError('Each contract quote must be a mapping')
        timestamp_value = tick.get('timestamp', tick.get('epoch'))
        quote_value = tick.get('quote', tick.get('price'))
        timestamp = _integer_timestamp(timestamp_value, 'Quote timestamp')
        try:
            quote = float(quote_value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError('Quote price must be a finite positive number') from error
        if not isfinite(quote) or quote <= 0:
            raise ValueError('Quote price must be a finite positive number')
        normalized.append({'timestamp': timestamp, 'quote': quote})

    normalized.sort(key=lambda item: item['timestamp'])
    unique = []
    for tick in normalized:
        if unique and unique[-1]['timestamp'] == tick['timestamp']:
            if unique[-1]['quote'] != tick['quote']:
                raise ValueError('Conflicting quotes share the same timestamp')
            continue
        unique.append(tick)
    return unique


def resolve_rise_fall_contract(
    signal: Mapping[str, Any],
    ticks: Iterable[Mapping[str, Any]],
    duration_seconds: int = 60,
    max_entry_delay_seconds: int = 5,
) -> dict[str, Any]:
    """Resolve a directional contract only from observed entry and expiry ticks."""
    _validate_contract_parameters(duration_seconds, max_entry_delay_seconds)
    quotes = _normalise_ticks(ticks)
    return _resolve_with_normalised_quotes(
        signal,
        quotes,
        duration_seconds,
        max_entry_delay_seconds,
    )


def _resolve_with_normalised_quotes(
    signal: Mapping[str, Any],
    quotes: list[dict[str, Any]],
    duration_seconds: int,
    max_entry_delay_seconds: int,
    quote_timestamps: list[int] | None = None,
) -> dict[str, Any]:
    signal_timestamp = _integer_timestamp(
        signal.get('signal_timestamp', signal.get('timestamp')),
        'Signal timestamp',
    )
    supplied_direction = signal.get('direction')
    directions = {
        'BUY': 'RISE',
        'LONG': 'RISE',
        'RISE': 'RISE',
        'SELL': 'FALL',
        'SHORT': 'FALL',
        'FALL': 'FALL',
    }
    direction = directions.get(supplied_direction)
    if direction is None:
        raise ValueError('Signal direction must be BUY/LONG/RISE or SELL/SHORT/FALL')

    base = {
        'signal_id': signal.get('signal_id', signal.get('id')),
        'strategy_version': signal.get('strategy_version'),
        'symbol': signal.get('symbol'),
        'signal_timestamp': signal_timestamp,
        'direction': direction,
        'contract_type': 'RISE_FALL',
        'duration_seconds': duration_seconds,
        'entry_timestamp': None,
        'entry_quote': None,
        'expiry_timestamp': None,
        'expiry_quote': None,
        'outcome': 'INCOMPLETE',
        'reason': None,
    }

    if quote_timestamps is None:
        quote_timestamps = [tick['timestamp'] for tick in quotes]
    entry_index = bisect_right(quote_timestamps, signal_timestamp)
    if entry_index == len(quotes):
        base['reason'] = 'ENTRY_QUOTE_UNAVAILABLE'
        return base
    entry = quotes[entry_index]
    if entry['timestamp'] - signal_timestamp > max_entry_delay_seconds:
        base['reason'] = 'ENTRY_QUOTE_UNAVAILABLE'
        return base

    expiry_timestamp = entry['timestamp'] + duration_seconds
    base.update({
        'entry_timestamp': entry['timestamp'],
        'entry_quote': entry['quote'],
        'expiry_timestamp': expiry_timestamp,
    })
    expiry_index = bisect_left(quote_timestamps, expiry_timestamp)
    if expiry_index == len(quotes) or quote_timestamps[expiry_index] != expiry_timestamp:
        base['reason'] = 'EXACT_EXPIRY_QUOTE_UNAVAILABLE'
        return base
    expiry = quotes[expiry_index]

    base['expiry_quote'] = expiry['quote']
    if expiry['quote'] == entry['quote']:
        outcome = 'TIE'
    elif (expiry['quote'] > entry['quote']) == (direction == 'RISE'):
        outcome = 'WIN'
    else:
        outcome = 'LOSS'
    base.update({'outcome': outcome, 'reason': None})
    return base


def evaluate_rise_fall_signals(
    signals: Iterable[Mapping[str, Any]],
    ticks: Iterable[Mapping[str, Any]],
    duration_seconds: int = 60,
    max_entry_delay_seconds: int = 5,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Evaluate non-overlapping signal contracts; payout and net return stay unknown."""
    _validate_contract_parameters(duration_seconds, max_entry_delay_seconds)
    if hasattr(signals, 'to_dict'):
        signals = signals.to_dict('records')
    signal_list = list(signals)
    if hasattr(ticks, 'to_dict'):
        ticks = ticks.to_dict('records')
    quotes = _normalise_ticks(ticks)

    ordered_signals = sorted(
        signal_list,
        key=lambda item: _integer_timestamp(
            item.get('signal_timestamp', item.get('timestamp')),
            'Signal timestamp',
        ),
    )
    records = []
    seen = set()
    active_until = None
    quote_timestamps = [tick['timestamp'] for tick in quotes]
    for signal in ordered_signals:
        signal_timestamp = _integer_timestamp(
            signal.get('signal_timestamp', signal.get('timestamp')),
            'Signal timestamp',
        )
        direction = signal.get('direction')
        signature = (signal_timestamp, direction)
        if signature in seen:
            records.append({
                'signal_id': signal.get('signal_id', signal.get('id')),
                'symbol': signal.get('symbol', symbol),
                'signal_timestamp': signal_timestamp,
                'direction': direction,
                'outcome': 'EXCLUDED_DUPLICATE',
                'reason': 'DUPLICATE_SIGNAL',
            })
            continue
        seen.add(signature)
        if active_until is not None and signal_timestamp < active_until:
            records.append({
                'signal_id': signal.get('signal_id', signal.get('id')),
                'symbol': signal.get('symbol', symbol),
                'signal_timestamp': signal_timestamp,
                'direction': direction,
                'outcome': 'EXCLUDED_OVERLAP',
                'reason': 'PREVIOUS_CONTRACT_NOT_EXPIRED',
            })
            continue

        result = _resolve_with_normalised_quotes(
            signal,
            quotes,
            duration_seconds,
            max_entry_delay_seconds,
            quote_timestamps,
        )
        result['symbol'] = result.get('symbol') or symbol
        result['split'] = signal.get('split')
        records.append(result)
        if result['expiry_timestamp'] is not None:
            active_until = result['expiry_timestamp']

    completed = [record for record in records if record['outcome'] in {'WIN', 'LOSS', 'TIE'}]
    wins = sum(record['outcome'] == 'WIN' for record in completed)
    losses = sum(record['outcome'] == 'LOSS' for record in completed)
    ties = sum(record['outcome'] == 'TIE' for record in completed)
    by_direction = {}
    for direction in ('RISE', 'FALL'):
        directional = [record for record in completed if record['direction'] == direction]
        directional_wins = sum(record['outcome'] == 'WIN' for record in directional)
        by_direction[direction] = {
            'completed': len(directional),
            'wins': directional_wins,
            'losses': sum(record['outcome'] == 'LOSS' for record in directional),
            'ties': sum(record['outcome'] == 'TIE' for record in directional),
            'win_rate_percent': directional_wins / len(directional) * 100 if directional else None,
        }

    def split_metrics(split_name: str) -> dict[str, Any]:
        split_records = [
            record for record in completed
            if record.get('split') == split_name
        ]
        split_wins = sum(record['outcome'] == 'WIN' for record in split_records)
        return {
            'completed': len(split_records),
            'wins': split_wins,
            'losses': sum(record['outcome'] == 'LOSS' for record in split_records),
            'ties': sum(record['outcome'] == 'TIE' for record in split_records),
            'win_rate_percent': split_wins / len(split_records) * 100 if split_records else None,
        }

    return {
        'status': 'COMPLETE',
        'evaluation_mode': 'RISE_FALL_CONTRACT',
        'contract_type': 'RISE_FALL',
        'symbol': symbol,
        'duration_seconds': duration_seconds,
        'signals': len(signal_list),
        'completed': len(completed),
        'incomplete': sum(record['outcome'] == 'INCOMPLETE' for record in records),
        'excluded_overlap': sum(record['outcome'] == 'EXCLUDED_OVERLAP' for record in records),
        'excluded_duplicates': sum(record['outcome'] == 'EXCLUDED_DUPLICATE' for record in records),
        'wins': wins,
        'losses': losses,
        'ties': ties,
        'win_rate_percent': wins / len(completed) * 100 if completed else None,
        'by_direction': by_direction,
        'development': split_metrics('DEVELOPMENT'),
        'validation': split_metrics('VALIDATION'),
        'payout_data': 'UNAVAILABLE',
        'net_expected_return': None,
        'records': records,
        'methodology': (
            'Entry uses the first observed quote strictly after signal availability, '
            'within the configured entry delay. Settlement requires a quote exactly '
            'at entry time plus contract duration. Missing quotes remain incomplete; '
            'overlapping contracts are excluded. Payouts, fees, and net returns are '
            'not inferred.'
        ),
    }

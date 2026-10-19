from __future__ import annotations

from typing import Any

import pandas as pd

from analysis.candle_patterns import breakout_confirmation, candle_confirmation
from analysis.indicators import indicators
from analysis.structure import market_structure
from analysis.support_resistance import levels

LESSONS = (
    {
        'id': 'read-structure',
        'title': 'Read the swing structure',
        'duration': '3 min',
        'objective': 'Use recent swing highs and lows to describe who has controlled price.',
        'lesson': 'A sequence of higher swing highs and higher swing lows supports an upward structure; lower highs and lower lows support a downward structure. One green candle alone does not establish a trend.',
        'question': 'At this completed candle, which choice best fits the visible evidence?',
        'rule': 'analysis.structure.market_structure',
    },
    {
        'id': 'trend-or-range',
        'title': 'Trend or consolidation?',
        'duration': '3 min',
        'objective': 'Separate directional structure from unclear or sideways movement.',
        'lesson': 'SignalBot may report UNCLEAR or RANGING when swing structure does not make a clear directional sequence. Waiting through a range avoids treating every small push as a breakout.',
        'question': 'Would you act on direction here, or wait for clearer structure?',
        'rule': 'analysis.structure.market_structure',
    },
    {
        'id': 'levels-breakouts',
        'title': 'Levels, breaks, and failed breaks',
        'duration': '4 min',
        'objective': 'Read a level as a zone to observe, not an automatic trade instruction.',
        'lesson': 'Support and resistance are calculated from prior candles. A test is not a confirmed break: SignalBot checks for a completed close beyond the previous candle extreme. A move back through a level can invalidate a breakout idea.',
        'question': 'Given only the candles shown, is there confirmation to act or is WAIT safer?',
        'rule': 'analysis.support_resistance.levels · analysis.candle_patterns.breakout_confirmation',
    },
    {
        'id': 'one-minute-trigger',
        'title': 'Wait for the 1-minute trigger',
        'duration': '4 min',
        'objective': 'Check what the last completed 1-minute candle did before considering a setup.',
        'lesson': 'The 1-minute chart times a candidate entry; the 5-minute chart supplies context. The latest completed candle must provide the strategy’s candle and breakout confirmation. An unfinished candle is not confirmation.',
        'question': 'Does the completed 1-minute candle confirm a directional trigger?',
        'rule': 'analysis.candle_patterns.candle_confirmation · analysis.candle_patterns.breakout_confirmation',
    },
    {
        'id': 'indicators-context',
        'title': 'Indicators in chart context',
        'duration': '4 min',
        'objective': 'Interpret EMA, RSI, and ATR together with actual price structure.',
        'lesson': 'EMA alignment and slope describe trend context; RSI is used as a bounded momentum filter, not an automatic overbought/oversold command; ATR estimates recent movement and helps identify extended entries. These related measures can agree and still be wrong.',
        'question': 'Do the readings support a setup, contradict each other, or leave too much uncertainty?',
        'rule': 'analysis.indicators.indicators · analysis.signal_engine.SignalEngine.evaluate',
    },
    {
        'id': 'wait-and-invalidation',
        'title': 'WAIT is a valid decision',
        'duration': '3 min',
        'objective': 'Name the evidence still required and what would invalidate the idea.',
        'lesson': 'SignalBot can withhold a directional entry when timeframes disagree, a candle trigger is missing, data is stale, risk/reward is insufficient, or required confirmation is absent. A price level by itself is not an entry.',
        'question': 'Which action best respects the evidence currently visible?',
        'rule': 'analysis.signal_engine._timeframe_alignment · analysis.signal_engine.SignalEngine.evaluate',
    },
    {
        'id': 'contract-expiry',
        'title': 'Rise/Fall entry and expiry',
        'duration': '4 min',
        'objective': 'Distinguish fixed-duration settlement from stop-loss/take-profit exits.',
        'lesson': 'A one-minute contract lasts 60 seconds from its actual entry, not necessarily one chart candle. Its result depends on the contract’s entry and expiry quotes and tie rules. This candle-only exercise cannot calculate a contract settlement: exact raw ticks and contract-specific payout terms are required.',
        'question': 'Can these candle snapshots prove the exact entry quote, expiry quote, and payout?',
        'rule': 'backtest.contracts.resolve_rise_fall_contract',
    },
    {
        'id': 'review-decisions',
        'title': 'Review the decision, not just the result',
        'duration': '3 min',
        'objective': 'Judge whether your choice followed the evidence available at the decision point.',
        'lesson': 'A good process can lose and a poor process can win. Review the visible evidence, confirmation rules, and invalidation conditions before looking at the subsequent candles.',
        'question': 'Was your choice consistent with the evidence and the rules you identified?',
        'rule': 'analysis.signal_engine.SignalEngine.evaluate · backtest.contracts',
    },
)

GLOSSARY = (
    {'term': 'ATR', 'definition': 'Average True Range: a measure of recent candle movement size, not a forecast of direction.'},
    {'term': 'Breakout', 'definition': 'A completed price move beyond an observed level; a touch or unfinished candle is not proof.'},
    {'term': 'EMA', 'definition': 'Exponential Moving Average: a smoothed price line that weights recent closes more heavily.'},
    {'term': 'Expiry', 'definition': 'The settlement time of a fixed-duration contract, counted from its actual contract entry.'},
    {'term': 'Higher high / higher low', 'definition': 'Successive swing points rising; evidence consistent with an upward structure, not a guarantee.'},
    {'term': 'RSI', 'definition': 'Relative Strength Index: a bounded momentum measure used by SignalBot as a filter, not an automatic trade command.'},
    {'term': 'Retest', 'definition': 'Price returning to a previously crossed level; it can hold, fail, or remain unresolved.'},
    {'term': 'Support / resistance', 'definition': 'Historical price areas where prior candles show potential buying or selling response.'},
    {'term': 'Stop-loss / take-profit', 'definition': 'Exit levels for a price-movement trade plan; they are different from fixed-time contract settlement.'},
    {'term': 'WAIT', 'definition': 'No directional entry is justified by the required evidence at this time.'},
)

LESSONS_BY_ID = {lesson['id']: lesson for lesson in LESSONS}


def public_curriculum(progress: dict[str, dict[str, Any]]) -> dict[str, Any]:
    lessons = []
    for lesson in LESSONS:
        completion = progress.get(lesson['id'], {})
        lessons.append({
            **lesson,
            'completed': bool(completion.get('completion_count')),
            'completion_count': int(completion.get('completion_count', 0)),
        })
    return {
        'title': 'Practical Step Index Trading Course',
        'data_policy': 'Exercises use saved historical candles only. No candle after a decision is shown until you answer. This is education, not a trade instruction.',
        'lessons': lessons,
        'glossary': list(GLOSSARY),
        'completed_lessons': sum(lesson['completed'] for lesson in lessons),
        'total_lessons': len(lessons),
    }


def explain_signal(signal: dict[str, Any]) -> dict[str, Any]:
    status = str(signal.get('status') or 'UNKNOWN')
    reasons = signal.get('reasons') or []
    if isinstance(reasons, str):
        reasons = [reasons]

    evidence = [str(reason) for reason in reasons if reason]
    indicators_at_signal = signal.get('indicators') or {}
    timeframes = signal.get('timeframes') or {}
    timeframe_readings = []
    contradictions = []
    directions = {'BULLISH': 'BUY', 'BEARISH': 'SELL'}
    signal_direction = signal.get('direction')
    for timeframe in ('4h', '1h', '15m', '5m', '1m'):
        item = timeframes.get(timeframe)
        if not item:
            continue
        bias = item.get('bias', 'UNCLEAR') if item.get('available') else 'NO DATA'
        timeframe_readings.append({'timeframe': timeframe, 'bias': bias})
        expected = signal_direction or (signal.get('candidate_direction') if signal.get('candidate_direction') else None)
        if expected and bias in directions and directions[bias] != expected:
            contradictions.append(f'{timeframe} closed-candle bias is {bias}, opposite the {expected} setup.')

    if not evidence:
        evidence.append(f'The recorded status is {status}; no detailed reason text was stored with this snapshot.')
    if not indicators_at_signal:
        evidence.append('Indicator values were not present in this signal snapshot; no current or historical readings are inferred.')
    if not timeframe_readings:
        evidence.append('Timeframe readings were not present in this signal snapshot.')

    waiting = []
    normalized = status.upper()
    if 'LIVE DATA' in normalized or 'DATA' in normalized:
        waiting.append('Restore and verify fresh live market data before using the analysis.')
    if 'TIMEFRAMES' in normalized or 'ALIGN' in normalized:
        waiting.append('Wait until SignalBot’s required completed-timeframe direction checks agree.')
    if 'TRADINGVIEW' in normalized:
        waiting.append('The matching ticker, direction, and closed 1-minute candle alert is not confirmed.')
    if 'PRICE MOVED' in normalized or 'WINDOW EXPIRED' in normalized:
        waiting.append('Wait for a new completed 1-minute setup and a timely, nearby live quote.')
    if 'VOLATILITY' in normalized:
        waiting.append('Wait for a valid ATR reading from closed candles.')
    if 'BACKTEST' in normalized:
        waiting.append('The historical sample or holdout gate has not passed.')
    if 'RISK/REWARD' in normalized:
        waiting.append('Wait for a candidate plan that meets the configured risk/reward requirement.')
    if 'ENTRY CONFIRMED' in normalized:
        waiting.append('The strategy rules passed at this snapshot; this does not predict the outcome or guarantee a winning trade.')
    elif not waiting:
        waiting.append('No specific missing condition was recorded for this snapshot. Review the actual evidence; do not infer a trigger.')

    return {
        'status': status,
        'direction': signal_direction,
        'summary': 'Rule status only; it is not a probability or a prediction.',
        'evidence': evidence,
        'contradictions': contradictions,
        'waiting_for': waiting,
        'timeframes': timeframe_readings,
        'indicators': indicators_at_signal,
        'entry': signal.get('entry'),
        'signal_timestamp': signal.get('timestamp'),
        'strategy_version': signal.get('strategy_version') or 'Current strategy (version not stored on this snapshot)',
        'risk_note': 'A confirmed rule setup can still lose. Do not treat this explanation as a recommendation to trade.',
    }


def build_exercise(
    lesson_id: str,
    candles: list[dict[str, Any]],
    attempt_number: int,
    symbol: str,
    context_candles: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    lesson = LESSONS_BY_ID.get(lesson_id)
    if lesson is None:
        raise ValueError('Unknown lesson')
    if len(candles) < 222:
        return None

    frame = pd.DataFrame(candles).sort_values('timestamp').reset_index(drop=True)
    candidate_index = len(frame) - 2 - max(0, attempt_number - 1)
    if candidate_index < 220:
        candidate_index = 220 + (max(0, attempt_number - 1) % max(1, len(frame) - 221))
    candidate_index = min(candidate_index, len(frame) - 2)
    history = frame.iloc[:candidate_index + 1].copy().reset_index(drop=True)
    if len(history) < 220:
        return None

    enriched = indicators(history)
    latest = enriched.iloc[-1]
    structure = market_structure(enriched)
    pattern = candle_confirmation(enriched)
    breakout_buy = breakout_confirmation(enriched, 'BUY')
    breakout_sell = breakout_confirmation(enriched, 'SELL')
    resistance = levels(enriched, structure)
    timestamp = int(latest.timestamp) + 60
    observed = []
    for _, candle in history.tail(90).iterrows():
        observed.append({
            'timestamp': int(candle.timestamp),
            'open': float(candle.open),
            'high': float(candle.high),
            'low': float(candle.low),
            'close': float(candle.close),
        })
    indicator_values = {}
    for key in ('ema_20', 'ema_50', 'ema_200', 'rsi_14', 'atr_14'):
        value = latest[key]
        indicator_values[key] = float(value) if pd.notna(value) else None
    recent_levels = [
        {'type': level['type'], 'price': float(level['price'])}
        for level in resistance
    ]
    swing_highs = [
        {'timestamp': int(point['timestamp']), 'price': float(point['high'])}
        for point in structure.get('swing_highs', [])[-3:]
    ]
    swing_lows = [
        {'timestamp': int(point['timestamp']), 'price': float(point['low'])}
        for point in structure.get('swing_lows', [])[-3:]
    ]
    features = {
        'structure_bias': structure.get('bias', 'UNCLEAR'),
        'swing_highs': swing_highs,
        'swing_lows': swing_lows,
        'candle_pattern_direction': pattern.get('direction'),
        'candle_patterns': pattern.get('patterns', []),
        'breakout_buy': bool(breakout_buy),
        'breakout_sell': bool(breakout_sell),
        'indicators': indicator_values,
        'levels': recent_levels,
        'timeframes': {},
    }
    for timeframe, timeframe_candles in (context_candles or {}).items():
        duration = {'5m': 300, '15m': 900, '1h': 3600, '4h': 14400}.get(timeframe)
        if duration is None:
            continue
        closed_candles = [
            candle for candle in timeframe_candles
            if int(candle['timestamp']) + duration <= timestamp
        ]
        context = {'available': len(closed_candles) >= 30, 'bias': 'NO DATA', 'candles': len(closed_candles)}
        if context['available']:
            context_frame = pd.DataFrame(closed_candles).sort_values('timestamp').reset_index(drop=True)
            context['bias'] = market_structure(context_frame).get('bias', 'UNCLEAR')
            context['last_close_timestamp'] = int(context_frame.timestamp.iloc[-1]) + duration
        features['timeframes'][timeframe] = context
    return {
        'lesson': lesson,
        'symbol': symbol,
        'source': 'HISTORICAL DERIV CANDLES · educational replay, not a live quote',
        'decision_timestamp': timestamp,
        'observed_candles': observed,
        'features': features,
        'contract_note': 'Raw ticks are not stored with these candles. Exact contract entry, expiry settlement, and payout cannot be calculated from this exercise.',
    }


def build_review(
    exercise: dict[str, Any],
    decision: str,
    future_candles: list[dict[str, Any]],
) -> dict[str, Any]:
    if decision not in {'LONG', 'SHORT', 'WAIT'}:
        raise ValueError('Decision must be LONG, SHORT, or WAIT')
    features = exercise['features']
    bias = features['structure_bias']
    agreement = (
        decision == 'LONG' and bias == 'BULLISH'
        or decision == 'SHORT' and bias == 'BEARISH'
        or decision == 'WAIT' and bias not in {'BULLISH', 'BEARISH'}
    )
    return {
        'decision': decision,
        'rule_process_aligned': agreement,
        'rule_process_note': (
            'Your directional choice agrees with the observed 1-minute structure bias.'
            if agreement and decision != 'WAIT'
            else 'WAIT avoids forcing a direction while the observed 1-minute structure is unclear.'
            if agreement
            else 'This choice does not match the observed 1-minute structure alone. Higher-timeframe, confirmation, freshness, and entry filters still matter.'
        ),
        'subsequent_candles': future_candles,
        'directional_candle_context': (
            'UP' if future_candles[-1]['close'] > exercise['observed_candles'][-1]['close']
            else 'DOWN' if future_candles[-1]['close'] < exercise['observed_candles'][-1]['close']
            else 'UNCHANGED'
        ) if future_candles else 'UNAVAILABLE',
        'subsequent_movement': (
            'Subsequent closed candle prices are shown for review only; they were withheld at the decision point.'
            if future_candles else 'No subsequent closed candle is available in the saved history.'
        ),
        'contract_result': {
            'outcome': 'INCOMPLETE',
            'reason': 'RAW_TICK_HISTORY_UNAVAILABLE',
            'entry_quote': None,
            'expiry_quote': None,
            'payout': None,
            'note': exercise['contract_note'],
        },
        'learning_note': 'Review whether your process followed the evidence at the time. A later price move does not make an unsupported decision correct.',
    }

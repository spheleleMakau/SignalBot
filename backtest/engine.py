import numpy as np
import pandas as pd
from analysis.indicators import indicators
from analysis.candle_patterns import breakout_confirmation, candle_confirmation
from analysis.structure import market_structure
from analysis.support_resistance import levels
from .contracts import evaluate_rise_fall_signals

def run_backtest(one_minute: pd.DataFrame, five_minute: pd.DataFrame | None = None,
                 fifteen_minute: pd.DataFrame | None = None, one_hour: pd.DataFrame | None = None,
                 minimum_score: int = 75, validation_fraction: float = 0.3,
                 holding_bars: int = 120, four_hour: pd.DataFrame | None = None,
                 evaluation_mode: str = 'stop_target', contract_ticks: pd.DataFrame | None = None,
                 contract_duration_seconds: int = 60, max_contract_entry_delay_seconds: int = 5,
                 contract_symbol: str | None = None):
    if evaluation_mode not in {'stop_target', 'rise_fall_contract'}:
        raise ValueError(f'Unsupported backtest evaluation mode: {evaluation_mode}')
    if evaluation_mode == 'rise_fall_contract' and (
        not isinstance(contract_symbol, str) or not contract_symbol.strip()
    ):
        raise ValueError('Contract evaluation requires the exact instrument symbol')
    frames = (one_minute, five_minute, fifteen_minute, one_hour, four_hour)
    minimums = (220, 30, 30, 30, 30)
    if any(frame is None or len(frame) < minimum for frame, minimum in zip(frames, minimums)):
        return {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0}
    if evaluation_mode == 'rise_fall_contract' and contract_ticks is None:
        return {
            'status': 'INSUFFICIENT TICK DATA',
            'evaluation_mode': 'RISE_FALL_CONTRACT',
            'trades': 0,
            'incomplete': 0,
        }
    if (
        evaluation_mode == 'rise_fall_contract'
        and not contract_ticks.empty
        and 'symbol' in contract_ticks
        and (
            contract_ticks['symbol'].isna().any()
            or set(contract_ticks['symbol']) != {contract_symbol}
        )
    ):
        raise ValueError('Contract tick symbols must all match the requested instrument')

    minute, five, fifteen, hour, four = (
        indicators(frame).reset_index(drop=True) for frame in frames
    )
    close_times = [
        minute.timestamp.to_numpy() + 60,
        five.timestamp.to_numpy() + 300,
        fifteen.timestamp.to_numpy() + 900,
        hour.timestamp.to_numpy() + 3600,
        four.timestamp.to_numpy() + 14400,
    ]
    validation_start = int(len(minute) * (1 - validation_fraction))
    outcomes = []
    validation_outcomes = []
    trade_markers = []
    contract_signals = []
    ambiguous = 0
    last_exit_index = -1

    for index in range(200, len(minute) - 1):
        if index <= last_exit_index:
            continue
        decision_time = close_times[0][index]
        aligned = [int(np.searchsorted(times, decision_time, side='right') - 1) for times in close_times[1:]]
        five_index, fifteen_index, hour_index, four_index = aligned
        if min(aligned) < 2:
            continue

        current = minute.iloc[index]
        previous = minute.iloc[index - 1]
        setup = five.iloc[five_index]
        setup_previous = five.iloc[five_index - 1]
        atr = float(current.atr_14)
        rsi = float(current.rsi_14)
        if not np.isfinite(atr) or atr <= 0 or not np.isfinite(rsi):
            continue

        minute_history = minute.iloc[:index + 1]
        five_history = five.iloc[:five_index + 1]
        fifteen_history = fifteen.iloc[:fifteen_index + 1]
        hour_history = hour.iloc[:hour_index + 1]
        five_structure = market_structure(five_history)
        fifteen_structure = market_structure(fifteen_history)
        hour_structure = market_structure(hour_history)
        four_history = four.iloc[:four_index + 1]
        minute_structure = market_structure(minute_history)
        four_structure = market_structure(four_history)
        higher = four_structure['bias']
        setup_bias = five_structure['bias']
        pattern = candle_confirmation(minute.iloc[index - 2:index + 1])

        buy_aligned = (
            higher == 'BULLISH'
            and hour_structure['bias'] == 'BULLISH'
            and setup_bias == 'BULLISH'
            and fifteen_structure['bias'] == 'BULLISH'
            and minute_structure['bias'] == 'BULLISH'
            and pattern['direction'] == 'BUY'
            and breakout_confirmation(minute.iloc[index - 2:index + 1], 'BUY')
            and current.close > current.ema_20 > current.ema_50 > current.ema_200
            and setup.close > setup.ema_20 > setup.ema_50 > setup.ema_200
            and setup.ema_20 > setup_previous.ema_20
            and current.trend_confluence == 1
            and setup.trend_confluence == 1
            and 45 < rsi < 70
            and abs(float(current.close) - float(current.ema_20)) <= atr * 1.5
        )
        sell_aligned = (
            higher == 'BEARISH'
            and hour_structure['bias'] == 'BEARISH'
            and setup_bias == 'BEARISH'
            and fifteen_structure['bias'] == 'BEARISH'
            and minute_structure['bias'] == 'BEARISH'
            and pattern['direction'] == 'SELL'
            and breakout_confirmation(minute.iloc[index - 2:index + 1], 'SELL')
            and current.close < current.ema_20 < current.ema_50 < current.ema_200
            and setup.close < setup.ema_20 < setup.ema_50 < setup.ema_200
            and setup.ema_20 < setup_previous.ema_20
            and current.trend_confluence == -1
            and setup.trend_confluence == -1
            and 30 < rsi < 55
            and abs(float(current.close) - float(current.ema_20)) <= atr * 1.5
        )
        if not buy_aligned and not sell_aligned:
            continue

        trade_direction = 'BUY' if buy_aligned else 'SELL'
        direction = 1 if buy_aligned else -1
        entry = float(current.close)
        minute_levels = levels(minute_history, minute_structure)
        relevant = [level for level in minute_levels if level['type'] == ('support' if buy_aligned else 'resistance')]
        momentum_ok = (50 < rsi < 70) if buy_aligned else (30 < rsi < 50)
        score = 60 + (15 if relevant else 0) + (15 if momentum_ok else 0) + 10
        if score < minimum_score:
            continue

        risk = atr * 1.25
        swing = min((level['price'] for level in minute_levels if level['type'] == 'support' and level['price'] < entry), default=entry - risk) if buy_aligned else max((level['price'] for level in minute_levels if level['type'] == 'resistance' and level['price'] > entry), default=entry + risk)
        stop = min(swing - atr * .25, entry - risk) if buy_aligned else max(swing + atr * .25, entry + risk)
        unit_risk = abs(entry - stop)
        targets = sorted(
            [level['price'] for level in minute_levels if (level['price'] > entry if buy_aligned else level['price'] < entry)],
            reverse=not buy_aligned,
        )
        target_1 = targets[0] if targets else entry + unit_risk * 2 * direction
        target_2 = targets[1] if len(targets) > 1 else entry + unit_risk * 3 * direction
        reward_risk = abs(target_1 - entry) / unit_risk if unit_risk else 0
        if evaluation_mode == 'stop_target' and reward_risk < 2:
            continue
        if evaluation_mode == 'rise_fall_contract':
            contract_signals.append({
                'signal_id': f'main-v2:{contract_symbol}:{int(decision_time)}:{trade_direction}',
                'signal_timestamp': int(decision_time),
                'direction': trade_direction,
                'strategy_version': 'main-v2',
                'symbol': contract_symbol,
                'split': 'VALIDATION' if index >= validation_start else 'DEVELOPMENT',
            })
            continue

        future = minute.iloc[index + 1: min(index + holding_bars + 1, len(minute))]
        outcome, last_exit_index, was_ambiguous = _resolve_exit(
            minute, index, direction, entry, stop, target_1, unit_risk,
            target_r=reward_risk, holding_bars=len(future),
        )
        if outcome is None:
            continue
        if index < validation_start <= last_exit_index:
            continue
        outcomes.append(outcome)
        trade_markers.append({
            'timestamp': int(current.timestamp),
            'direction': trade_direction,
            'entry': entry,
            'result': 'WIN' if outcome > 0 else 'LOSS' if outcome < 0 else 'FLAT',
        })
        if index >= validation_start:
            validation_outcomes.append(outcome)
        ambiguous += int(was_ambiguous)

    if evaluation_mode == 'rise_fall_contract':
        return evaluate_rise_fall_signals(
            contract_signals,
            contract_ticks,
            duration_seconds=contract_duration_seconds,
            max_entry_delay_seconds=max_contract_entry_delay_seconds,
            symbol=contract_symbol,
        )

    wins = [result for result in outcomes if result > 0]
    losses = [result for result in outcomes if result < 0]
    net_result = sum(outcomes)
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for result in outcomes:
        equity += result
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        'status': 'COMPLETE',
        'trades': len(outcomes),
        'ambiguous_trades': ambiguous,
        'winning_trades': len(wins),
        'losing_trades': len(losses),
        'win_rate': len(wins) / len(outcomes) * 100 if outcomes else 0,
        'average_rr': net_result / len(outcomes) if outcomes else 0,
        'profit_factor': _profit_factor(outcomes),
        'validation_trades': len(validation_outcomes),
        'validation_net_result': sum(validation_outcomes),
        'validation_profit_factor': _profit_factor(validation_outcomes),
        'max_drawdown': drawdown,
        'net_result': net_result,
        'trade_markers': trade_markers[-100:],
        'timeframes': ['4h', '1h', '15m', '5m', '1m'],
    }


def _resolve_exit(frame, entry_index, direction, entry, stop, target, risk, target_r, holding_bars):
    future = frame.iloc[entry_index + 1:entry_index + holding_bars + 1]
    for candle_index, candle in future.iterrows():
        hit_stop = candle.low <= stop if direction == 1 else candle.high >= stop
        hit_target = candle.high >= target if direction == 1 else candle.low <= target
        if hit_stop and hit_target:
            return -1.0, int(candle_index), True
        if hit_stop:
            return -1.0, int(candle_index), False
        if hit_target:
            return float(target_r), int(candle_index), False
    if future.empty:
        return None, None, False
    final_index = int(future.index[-1])
    final_price = float(future.close.iloc[-1])
    return direction * (final_price - entry) / risk, final_index, False


def run_scalp_backtest(one_minute: pd.DataFrame, five_minute: pd.DataFrame, holding_bars: int = 10, validation_fraction: float = 0.3):
    """Walk forward through closed 1M/5M candles using the live scalp rules."""
    if len(one_minute) < 220 or len(five_minute) < 60:
        return {'status': 'INSUFFICIENT HISTORICAL DATA', 'trades': 0}

    one = indicators(one_minute).reset_index(drop=True)
    five = indicators(five_minute).reset_index(drop=True)
    one['ema_9'] = one.close.ewm(span=9, adjust=False, min_periods=9).mean()
    one['ema_21'] = one.close.ewm(span=21, adjust=False, min_periods=21).mean()
    five_close_times = five.timestamp + 300
    outcomes = []
    validation_outcomes = []
    validation_start = max(60, int(len(one) * (1 - validation_fraction)))
    ambiguous = 0
    latest_five_index = -1
    last_exit_index = -1

    for index in range(60, len(one) - holding_bars):
        minute_close_time = one.timestamp.iloc[index] + 60
        while latest_five_index + 1 < len(five) and five_close_times.iloc[latest_five_index + 1] <= minute_close_time:
            latest_five_index += 1
        if latest_five_index < 0 or index <= last_exit_index:
            continue

        current = one.iloc[index]
        previous = one.iloc[index - 1]
        trend = five.iloc[latest_five_index]
        confirmation = candle_confirmation(one.iloc[index - 2:index + 1])
        atr = float(current.atr_14)
        if pd.isna(atr) or atr <= 0:
            continue

        bullish = (
            trend.close > trend.ema_20 > trend.ema_50
            and current.ema_9 > current.ema_21
            and current.close > current.ema_9
            and current.ema_9 >= previous.ema_9
            and confirmation['direction'] == 'BUY'
            and breakout_confirmation(one.iloc[index - 2:index + 1], 'BUY')
            and 48 < current.rsi_14 < 68
            and abs(float(current.close) - float(current.ema_21)) <= atr * 1.25
        )
        bearish = (
            trend.close < trend.ema_20 < trend.ema_50
            and current.ema_9 < current.ema_21
            and current.close < current.ema_9
            and current.ema_9 <= previous.ema_9
            and confirmation['direction'] == 'SELL'
            and breakout_confirmation(one.iloc[index - 2:index + 1], 'SELL')
            and 32 < current.rsi_14 < 52
            and abs(float(current.close) - float(current.ema_21)) <= atr * 1.25
        )
        if not bullish and not bearish:
            continue

        direction = 1 if bullish else -1
        entry = float(current.close)
        risk = atr * 1.1
        stop = entry - direction * risk
        target = entry + direction * risk * 1.5
        result, last_exit_index, was_ambiguous = _resolve_exit(
            one, index, direction, entry, stop, target, risk, target_r=1.5, holding_bars=holding_bars
        )
        if result is None:
            continue
        if index < validation_start <= last_exit_index:
            continue
        outcomes.append(result)
        if index >= validation_start:
            validation_outcomes.append(result)
        ambiguous += int(was_ambiguous)

    wins = [result for result in outcomes if result > 0]
    losses = [result for result in outcomes if result < 0]
    net_result = sum(outcomes)
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for result in outcomes:
        equity += result
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    return {
        'status': 'COMPLETE',
        'trades': len(outcomes),
        'ambiguous_trades': ambiguous,
        'winning_trades': len(wins),
        'losing_trades': len(losses),
        'win_rate': len(wins) / len(outcomes) * 100 if outcomes else 0,
        'profit_factor': gross_wins / gross_losses if gross_losses else None,
        'validation_trades': len(validation_outcomes),
        'validation_net_result': sum(validation_outcomes),
        'validation_profit_factor': _profit_factor(validation_outcomes),
        'max_drawdown': max_drawdown,
        'net_result': net_result,
    }


def _profit_factor(outcomes):
    wins = sum(result for result in outcomes if result > 0)
    losses = abs(sum(result for result in outcomes if result < 0))
    return wins / losses if losses else None

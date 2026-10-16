def candle_confirmation(frame):
    if len(frame) < 3: return {'direction': None, 'patterns': []}
    previous, current = frame.iloc[-2], frame.iloc[-1]
    body = abs(current.close - current.open); span = max(current.high - current.low, 1e-12)
    bullish_engulfing = previous.close < previous.open and current.close > current.open and current.close >= previous.open and current.open <= previous.close
    bearish_engulfing = previous.close > previous.open and current.close < current.open and current.open >= previous.close and current.close <= previous.open
    lower_wick = min(current.open, current.close) - current.low; upper_wick = current.high - max(current.open, current.close)
    bullish_pin = lower_wick >= body * 2 and lower_wick / span > .5 and current.close > current.open
    bearish_pin = upper_wick >= body * 2 and upper_wick / span > .5 and current.close < current.open
    patterns = (["bullish engulfing"] if bullish_engulfing else []) + (["bearish engulfing"] if bearish_engulfing else []) + (["bullish rejection pin"] if bullish_pin else []) + (["bearish rejection pin"] if bearish_pin else [])
    return {'direction': 'BUY' if bullish_engulfing or bullish_pin else 'SELL' if bearish_engulfing or bearish_pin else None, 'patterns': patterns}


def breakout_confirmation(frame, direction):
    if len(frame) < 2 or direction not in {'BUY', 'SELL'}:
        return False
    previous, current = frame.iloc[-2], frame.iloc[-1]
    return current.close > previous.high if direction == 'BUY' else current.close < previous.low

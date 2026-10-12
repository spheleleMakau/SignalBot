import pandas as pd

def market_structure(candles: pd.DataFrame, window=3):
    if len(candles) < window * 2 + 5: return {'bias': 'UNCLEAR', 'swings': [], 'bos': None, 'choch': None}
    highs = candles['high'].rolling(window * 2 + 1, center=True).max(); lows = candles['low'].rolling(window * 2 + 1, center=True).min()
    swing_highs = candles.loc[candles['high'].eq(highs), ['timestamp','high']].dropna().tail(8).to_dict('records')
    swing_lows = candles.loc[candles['low'].eq(lows), ['timestamp','low']].dropna().tail(8).to_dict('records')
    hh = len(swing_highs) >= 2 and swing_highs[-1]['high'] > swing_highs[-2]['high']; hl = len(swing_lows) >= 2 and swing_lows[-1]['low'] > swing_lows[-2]['low']
    lh = len(swing_highs) >= 2 and swing_highs[-1]['high'] < swing_highs[-2]['high']; ll = len(swing_lows) >= 2 and swing_lows[-1]['low'] < swing_lows[-2]['low']
    bias = 'BULLISH' if hh and hl else 'BEARISH' if lh and ll else 'RANGING' if swing_highs and swing_lows else 'UNCLEAR'
    bos = 'BULLISH' if hh else 'BEARISH' if ll else None
    return {'bias': bias, 'swing_highs': swing_highs, 'swing_lows': swing_lows, 'higher_high': hh, 'higher_low': hl, 'lower_high': lh, 'lower_low': ll, 'bos': bos, 'choch': None}

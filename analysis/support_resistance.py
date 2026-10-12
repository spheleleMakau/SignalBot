import numpy as np

def levels(candles, structure):
    values = []
    for item in structure.get('swing_highs', []): values.append({'price': item['high'], 'type': 'resistance', 'tests': 1})
    for item in structure.get('swing_lows', []): values.append({'price': item['low'], 'type': 'support', 'tests': 1})
    grouped = []
    tolerance = max(float(candles['close'].iloc[-1]) * 0.0008, float(candles['close'].iloc[-1] - candles['low'].iloc[-1])) if len(candles) else 0
    for level in sorted(values, key=lambda x: x['price']):
        match = next((x for x in grouped if abs(x['price'] - level['price']) <= tolerance), None)
        if match: match['tests'] += 1; match['price'] = (match['price'] + level['price']) / 2
        else: grouped.append(level.copy())
    return sorted(grouped, key=lambda x: x['tests'], reverse=True)[:12]

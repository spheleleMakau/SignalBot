from .indicators import indicators
from .structure import market_structure

def multi_timeframe(store, closed_only=False):
    result = {}
    for timeframe in ('4h','1h','15m','5m','1m'):
        frame = store.dataframe(timeframe)
        if closed_only and len(frame) > 1:
            frame = frame.iloc[:-1].reset_index(drop=True)
        if len(frame) < 30: result[timeframe] = {'available': False, 'bias': 'UNCLEAR'}
        else:
            enriched = indicators(frame); structure = market_structure(enriched)
            result[timeframe] = {'available': True, 'bias': structure['bias'], 'structure': structure, 'frame': enriched}
    return result

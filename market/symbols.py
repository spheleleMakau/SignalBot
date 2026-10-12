"""Helpers for selecting symbols from Deriv's live catalog."""

MARKET_LABELS = {
    'step_index': 'Step Index',
    'boom_1000': 'Boom 1000',
    'boom_500': 'Boom 500',
    'crash_1000': 'Crash 1000',
    'crash_500': 'Crash 500',
    'volatility_75': 'Volatility 75',
    'gold': 'Gold',
}

DEFAULT_MARKET = 'gold'


def discover_markets(symbols: list[dict]) -> dict[str, dict[str, str]]:
    markets = {}
    for item in symbols:
        symbol = item.get('underlying_symbol')
        if not symbol:
            continue
        name = ' '.join(str(item.get(field, '')) for field in (
            'underlying_symbol_name', 'display_name', 'symbol_name'
        )).strip()
        normalized_name = name.lower()
        normalized_symbol = str(symbol).replace('_', '').lower()
        for market_id, label in MARKET_LABELS.items():
            normalized_label = label.lower()
            if market_id == 'step_index':
                matches = 'step index' in normalized_name
            elif market_id == 'volatility_75':
                matches = 'volatility 75' in normalized_name or normalized_symbol == 'r75'
            elif market_id == 'gold':
                matches = normalized_symbol.endswith('xauusd') or ('gold' in normalized_name and 'basket' not in normalized_name)
            else:
                matches = normalized_label in normalized_name or normalized_symbol == market_id.replace('_', '')
            if matches:
                current = markets.get(market_id)
                candidate = {'symbol': str(symbol), 'name': name or label}
                if current is None or ('1s' not in normalized_name and '1s' in current['name'].lower()):
                    markets[market_id] = candidate
                break
    return markets


def select_step_index(symbols: list[dict]) -> str | None:
    candidates = []
    for item in symbols:
        symbol = item.get("underlying_symbol")
        name = " ".join(str(item.get(field, "")) for field in (
            "underlying_symbol_name", "display_name", "symbol_name"
        )).lower()
        if symbol and "step index" in name:
            candidates.append((name, symbol))
    candidates.sort(key=lambda candidate: candidate[0])
    return candidates[0][1] if candidates else None

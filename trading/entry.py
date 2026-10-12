def entry_is_current(signal, current_price, max_distance):
    return bool(signal and signal.get('entry') is not None and abs(current_price - signal['entry']) <= max_distance)

from math import isfinite

FIXED_LOT_SIZE = 0.1


def estimate_trade_values(signal, usd_per_price_unit_per_lot):
    if signal.get('status') not in {'ENTRY CONFIRMED', 'SCALP ENTRY CONFIRMED'}:
        return {'lot_size': FIXED_LOT_SIZE, 'available': False}
    try:
        entry = float(signal['entry'])
        stop = float(signal['stop_loss'])
        target_1 = float(signal['tp1'])
        target_2 = float(signal['tp2'])
        direction = 1 if signal['direction'] == 'BUY' else -1
    except (KeyError, TypeError, ValueError):
        return {'lot_size': FIXED_LOT_SIZE, 'available': False}

    risk_distance = abs(entry - stop)
    target_1_distance = (target_1 - entry) * direction
    target_2_distance = (target_2 - entry) * direction
    values = {
        'lot_size': FIXED_LOT_SIZE,
        'available': False,
        'risk_price_units': risk_distance,
        'target_1_price_units': target_1_distance,
        'target_2_price_units': target_2_distance,
    }
    if risk_distance <= 0 or target_1_distance <= 0 or target_2_distance <= 0:
        return values
    if usd_per_price_unit_per_lot is None:
        return values
    try:
        usd_value = float(usd_per_price_unit_per_lot)
    except (TypeError, ValueError):
        return values
    if not isfinite(usd_value) or usd_value <= 0:
        return values

    scale = FIXED_LOT_SIZE * usd_value
    values.update({
        'available': True,
        'estimated_loss_usd': risk_distance * scale,
        'estimated_target_1_usd': target_1_distance * scale,
        'estimated_target_2_usd': target_2_distance * scale,
    })
    return values

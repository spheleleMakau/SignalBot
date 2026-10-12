class TradeManager:
    def __init__(self): self.active = None
    def update(self, signal, price):
        if not self.active and signal.get('status') == 'ENTRY CONFIRMED': self.active = signal.copy()
        if not self.active: return 'WAITING'
        direction = self.active['direction']
        if direction == 'BUY':
            if price <= self.active['stop_loss']: result = 'STOP LOSS HIT'
            elif price >= self.active['tp2']: result = 'TARGET 2 HIT'
            elif price >= self.active['tp1']: result = 'TARGET 1 HIT'
            else: result = 'TRADE ACTIVE'
        else:
            if price >= self.active['stop_loss']: result = 'STOP LOSS HIT'
            elif price <= self.active['tp2']: result = 'TARGET 2 HIT'
            elif price <= self.active['tp1']: result = 'TARGET 1 HIT'
            else: result = 'TRADE ACTIVE'
        if result != 'TRADE ACTIVE': self.active = None
        return result

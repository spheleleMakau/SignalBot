from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    app_id: str = os.getenv("DERIV_APP_ID", "")
    app_name: str = os.getenv("DERIV_APP_NAME", "stepindex")
    redirect_url: str = os.getenv("DERIV_REDIRECT_URL", "")
    api_token: str = os.getenv("DERIV_API_TOKEN", "")
    symbol: str = os.getenv("DERIV_SYMBOL", "")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    database_path: str = os.getenv("DATABASE_PATH", "data/step_index.db")
    dashboard_username: str = os.getenv("DASHBOARD_USERNAME", "")
    dashboard_password: str = os.getenv("DASHBOARD_PASSWORD", "")
    dashboard_auth_required: bool = os.getenv("DASHBOARD_AUTH_REQUIRED", "false").lower() == "true"
    min_signal_score: int = int(os.getenv("MIN_SIGNAL_SCORE", "75"))
    usd_per_price_unit_per_lot: float | None = float(os.getenv("USD_PER_PRICE_UNIT_PER_LOT")) if os.getenv("USD_PER_PRICE_UNIT_PER_LOT") else None
    tradingview_webhook_token: str = os.getenv("TRADINGVIEW_WEBHOOK_TOKEN", "")
    tradingview_symbol: str = os.getenv("TRADINGVIEW_SYMBOL", "")
    app_mode: str = os.getenv("APP_MODE", "step_index").lower()
    aviator_signal_url: str = os.getenv("AVIATOR_SIGNAL_URL", "")

settings = Settings()
TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400}

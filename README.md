# Deriv Market Trader

A Python 3 FastAPI dashboard for live Deriv market analysis. Gold/XAUUSD is selected by default; Step Index and other supported Deriv markets can be selected from the dashboard. It builds 1m, 5m, 15m, 1h, and 4h candles from Deriv market data, calculates indicators and structure, and stores candles/signals in SQLite.

## Important data policy

This application never creates simulated prices or placeholder signals. Main entries require a fresh live Deriv feed, closed-candle history and aligned conditions across 1m/5m/15m/1h/4h, a score of at least 75, at least 1:2 risk/reward, and positive results across at least 10 resolved historical trades plus 5 separate recent holdout trades. The main backtest now applies the same five-timeframe trend alignment required by live entries. Scalp entries have a separate walk-forward backtest using closed 1m/5m bars and are blocked until there are at least 220 1m candles, 60 5m candles, 10 resolved trades, and positive results in at least 5 separate holdout trades. Backtests are historical, gross price-movement estimates; they do not include execution costs and do not predict future performance.

The technical checks combine multi-timeframe trend/structure, EMA alignment, RSI momentum, candle patterns, support/resistance, and ATR-based risk; they are not independent guarantees. The dashboard also shows the latest 15-minute swing high/low and an advisory point-of-control (POC) estimate from up to 60 closed 1-minute candles. Deriv historical candles do not provide traded volume, so this estimate uses live tick counts weighted at each candle's typical price, requires at least 10 candles with observed live ticks, and does not block or confirm signals. The public Deriv candle/tick feed does not supply institutional positions, order-book depth, company filings, or verified company/news catalysts, and those are not inferred by this application. Signal points are rule scores, not a probability of winning. No strategy can guarantee accurate outcomes or zero errors. Signal history shows only explicitly confirmed entries from the last 24 hours. Candle gaps, out-of-order ticks, invalid prices, and feed silence invalidate live analysis until Deriv history has been reloaded. Sound alerts start automatically when browser audio is permitted; some browsers only permit playback after the first ordinary interaction with the page.

Trade plans use a fixed 0.10 lot size and show the estimated stop and target outcomes. The public Deriv `active_symbols` response provides `pip_size`, not the account-specific USD value per price unit per lot. Set `USD_PER_PRICE_UNIT_PER_LOT` only from the contract specification for the exact broker and instrument; leave it blank to avoid guessed dollar figures. Stop/target alerts remain on screen until acknowledged and speak “Close order now” when browser speech is available.

## Local Setup

```powershell
cd c:\Users\Siphe\Desktop\umuzi
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

The dashboard uses Deriv's unauthenticated public market-data WebSocket. It discovers each selected instrument's `underlying_symbol` through `active_symbols`, requests that symbol's real `ticks_history`, and subscribes to live `ticks` for the same symbol. Switching markets clears the previous instrument's in-memory candles and live price before loading the new history. Gold/XAUUSD is the startup selection; if Deriv does not list it in `active_symbols`, the dashboard reports the feed error instead of substituting Step Index data. `DERIV_APP_ID`, `DERIV_API_TOKEN`, and `DERIV_SYMBOL` are not required for the chart or signal feed; they are reserved for future authenticated features.

Start the application from the project folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Check service health at <http://127.0.0.1:8000/healthz>. The first complete 1h timeframe requires live collection time. The dashboard will remain explicit about missing data while candles form.

Run the regression tests with `.\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v`.

## Deploy To Render

The repository includes `render.yaml`. Render uses Python 3.13.4, installs `requirements.txt`, starts Uvicorn on its assigned port, checks `/healthz`, and stores SQLite data on a persistent 1 GB disk mounted at `/var/data`. The blueprint uses Render's paid `starter` web-service plan because persistent disks are not available on free web services. Without persistent storage, deploys/restarts can erase the signal history.

1. Push this project to the GitHub repository. From PowerShell in the project folder, run:

	```powershell
	git init
	git add .
	git commit -m "Prepare SignalBot for Render deployment"
	git branch -M main
	git remote add origin https://github.com/spheleleMakau/SignalBot.git
	git push -u origin main
	```

	`.env`, local databases, virtual environments, and local logs are excluded by `.gitignore`; do not commit credentials.

2. In Render, choose **New +** → **Blueprint**, connect that GitHub repository, and deploy the detected `render.yaml`.

3. When prompted for `DASHBOARD_USERNAME` and `DASHBOARD_PASSWORD`, set unique credentials. Render requires these because the deployed dashboard is protected with HTTP Basic authentication. `/healthz` remains available to Render's health checker.

4. After deployment, open the assigned `onrender.com` URL and enter those credentials. Confirm `<your-service-url>/healthz` returns `{"status":"ok","service":"step-index-trader"}`. The public Deriv market-data WebSocket needs outbound connectivity for live quotes.

Leave `USD_PER_PRICE_UNIT_PER_LOT` unset unless you have verified the value in the exact broker/instrument contract specification. Render cannot infer this USD multiplier from public quote data.

The deployment commands configured in `render.yaml` are:

```text
Build:  pip install -r requirements.txt
Start:  uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Render Limitations

The current dashboard and trade manager keep live candles, active positions, and pending close alerts in process memory. SQLite history persists on the Render disk, but an instance restart resets that live state; use a single web-service instance and do not treat an app alert as a substitute for your broker terminal's stop-loss or take-profit orders. This app does not place or manage broker orders.

## Project map

- `app.py`: FastAPI entry point, background feed lifecycle, API routes, Plotly chart serialization.
- `config.py`: environment-backed configuration and supported timeframes.
- `data/database.py`: SQLite schema and persistence for candles and signals.
- `market/websocket.py`: Deriv WebSocket connection, reconnect behavior, and live/offline state.
- `market/candles.py`: deterministic tick aggregation into 1m/5m/15m/1h candles.
- `analysis/`: EMA, RSI, ATR, market structure, advisory tick-volume POC context, support/resistance, candle confirmation, multi-timeframe scoring.
- `trading/`: entry validity, ATR-based sizing, and signal lifecycle statuses.
- `backtest/engine.py`: closed-candle walk-forward filters for main and scalp entries, kept separate from live trading.
- `dashboard/`: dark HTML/CSS/JavaScript dashboard with interactive Plotly candlesticks.

Signals are analytical setups, not guaranteed profitable trades. This project does not place orders.

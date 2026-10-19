# SignalBot

SignalBot is a self-hosted market-analysis and signal-review dashboard for Deriv markets. It combines live quotes, multi-timeframe technical analysis, historical backtest gates, and optional TradingView confirmation to help an operator evaluate setups. Step Index is selected by default; Gold/XAUUSD and other supported Deriv markets can be selected from the dashboard.

## Product overview

- Streams public Deriv market data and builds closed 1m, 5m, 15m, 1h, and 4h candles.
- Presents technical context, candidate risk levels, signal history, and interactive charts in one dashboard.
- Requires aligned rule conditions, closed-candle confirmation, historical gates, and (when configured) a matching TradingView alert before showing a confirmed main entry.
- Adds upcoming scheduled macroeconomic events as Gold-only context; events do not create trade directions.
- Tracks shadow outcomes without placing orders, allowing users to evaluate rule-qualified candidates against observed market data.
- Supports a single selected market and a single-process deployment, with optional HTTP Basic authentication for the dashboard.
- Includes an interactive learning area with historical candle exercises, SignalBot rule explanations, a searchable glossary, and persisted lesson progress.

SignalBot is decision-support software, not an execution platform, broker, investment adviser, or guarantee of trading performance. It does not submit orders. Signals and historical results are not promises of future results; users remain responsible for independent validation, position sizing, and broker-side protections.

## Enterprise readiness status

The current repository is suitable for local evaluation and a controlled, single-instance pilot. **It is not yet an enterprise production offering.** The current deployment uses process-local live state and SQLite; authentication is a shared Basic Auth username/password rather than organization identity. There is no tenant isolation, role-based access control, centralized audit trail, high-availability design, or documented recovery objective.

The selected enterprise packaging direction is a dedicated deployment per customer, not a shared multi-tenant service. Each customer deployment must have separately managed credentials, provider keys, persistent data, backups, and operational access. Repeatable provisioning and lifecycle management for those isolated deployments are not implemented yet.

Before representing or deploying this as an enterprise-ready service, the product needs a scoped design and verification for at least:

- Organization identity integration (such as OIDC/SAML), user lifecycle, and role-based access for customer teams.
- Repeatable customer-specific provisioning, upgrades, rollback, and decommissioning, including separation of credentials, data, backups, and operational access.
- Shared production-grade persistence and coordinated live state before running multiple app instances for a customer.
- Auditable administrative and signal events, with defined retention and export controls.
- Operational monitoring, alerting, backup/restore drills, availability objectives, and incident procedures.
- Independent security testing, dependency and vulnerability management, and a secrets-management process.
- Review of data-provider licensing, commercial use terms, financial-services obligations, and customer contracts.
- Validated performance reporting that includes spread, slippage, fees, execution delay, representative samples, and clear methodology.

These are product requirements, not claims that SignalBot currently meets them. Enterprise controls should be designed around the target customer, deployment environment, and applicable obligations rather than implied by marketing language.

## Verification

GitHub Actions runs the regression suite on pushes and pull requests. Run it locally with:

```powershell
.\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v
```

## Important data policy

This application never creates simulated prices or placeholder signals. Rapid scalp entries and scalp alerts are disabled. Main entries require a fresh live Deriv feed, closed-candle history and aligned conditions across 1m/5m/15m/1h/4h, a score of at least 75, at least 1:2 risk/reward, positive results across at least 10 resolved historical trades plus 5 separate recent holdout trades, and a matching TradingView alert for the exact same configured ticker, direction, and closed 1-minute candle. If TradingView is not configured or its alert does not match exactly, the entry is withheld. The main backtest applies the same five-timeframe trend alignment required by live entries. Backtests are historical, gross price-movement estimates; they do not include execution costs and do not predict future performance.

The technical checks combine multi-timeframe trend/structure, EMA alignment, RSI momentum, candle patterns, support/resistance, ATR-based risk, and a closed-candle break of the previous candle's high/low before directional entries. TradingView is an additional same-ticker, same-direction, same-candle confirmation—not a guarantee—and mismatched/late alerts are rejected. A TradingView symbol may not exist for every Deriv synthetic index. Do not substitute a different symbol: without an exact matching feed and alert, the app deliberately waits rather than issuing a main entry. These filters can reduce signal frequency or make entries later; they cannot guarantee accuracy or profitability. The dashboard also shows the latest 15-minute swing high/low and an advisory point-of-control (POC) estimate from up to 60 closed 1-minute candles. Deriv historical candles do not provide traded volume, so this estimate uses live tick counts weighted at each candle's typical price, requires at least 10 candles with observed live ticks, and does not block or confirm signals. The public Deriv candle/tick feed does not supply institutional positions, order-book depth, company filings, or verified company/news catalysts, and those are not inferred by this application. Signal points are rule scores, not a probability of winning. Signal history shows only explicitly confirmed main entries from the last 24 hours. Candle gaps, out-of-order ticks, invalid prices, and feed silence invalidate live analysis until Deriv history has been reloaded. Sound alerts start automatically when browser audio is permitted; some browsers only permit playback after the first ordinary interaction with the page.

Trade plans use a fixed 0.10 lot size and show the estimated stop and target outcomes. These are alerts, not automatic trades or guarantees; independently assess the risk and verify the stop before taking any position. The public Deriv `active_symbols` response provides `pip_size`, not the account-specific USD value per price unit per lot. Set `USD_PER_PRICE_UNIT_PER_LOT` only from the contract specification for the exact broker and instrument; leave it blank to avoid guessed dollar figures. Stop/target alerts remain on screen until acknowledged and speak “Close order now” when browser speech is available.

### Practical learning area

Open **LEARN PRACTICALLY** from the Step Index dashboard or visit `/learn`. Lessons show saved historical Deriv 1-minute candles, actual indicator readings computed only through the marked decision candle, a LONG/SHORT/WAIT exercise, and a review that reveals later candles only after the answer is submitted. Completion counts and each review are stored in SQLite. **WHY THIS SIGNAL?** explains the evidence captured on the current or stored signal; historical explanations explicitly note when indicator and timeframe snapshots were not persisted.

Exercises are educational and do not submit orders. Saved candle OHLC is not a raw quote archive: the review will not invent the entry quote, one-minute Rise/Fall expiry settlement, or payout. A winning or losing later candle move does not by itself establish whether the original decision followed the rules.

### BigBeluga HalfTrend chart overlay

The existing interactive Plotly chart now has the HalfTrend Long/Short Engine overlay, using the currently selected instrument's verified Deriv candles and the existing 1m/5m/15m/1h/4h selector. The public TradingView script page's example chart is Binance BTCUSDT, not Deriv Step Index; SignalBot does not substitute that feed. The overlay calculates the published trend flips, HalfTrend line, ATR bands, close-confirmed LONG/SHORT markers, and the source's ATR(100)/2-based stop and three target levels. Amplitude, channel deviation, and base risk multiplier are configurable in the dashboard. An open-candle flip is labelled provisional and is not plotted as a confirmed signal.

The calculation is adapted from [HalfTrend Long/Short Signal Engine [BigBeluga]](https://www.tradingview.com/script/ZHGPnlAz-HalfTrend-Long-Short-Signal-Engine-BigBeluga/), copyright BigBeluga, with the original HalfTrend logic credited by the author to everget. The published source declares **CC BY-NC-SA 4.0**. The derived module `analysis/halftrend.py` carries attribution and that same license: it is restricted to non-commercial use, and adaptations must be shared under the same terms. Obtain separate permission before any commercial use. The license applies to the derived HalfTrend module, not to unrelated SignalBot files.

The indicator's backtest runs chronologically on closed candles, enters at the signal candle close, and checks only later candles for the first target or stop. It evaluates at most the 500 candles currently retained for the selected timeframe. If an OHLC candle touches both the stop and target, its outcome remains unresolved because candle data cannot establish intrabar ordering. Open trades at the end of the sample are unresolved. Results are gross price-movement R values; spread, slippage, commission, financing, and contract payout are not available and are excluded. This is an indicator evaluation, not a broker payout simulation, prediction, or guarantee. No orders are placed.

### One-minute Rise/Fall contract evaluation

`backtest.engine.run_backtest` retains its existing stop/target evaluation by default. Its separate `evaluation_mode='rise_fall_contract'` mode uses the same closed-candle signal rules but requires an explicit `contract_symbol` and a separate `contract_ticks` series of observed `{timestamp, quote}` (or `{epoch, quote}`) records. If a symbol column is supplied, every tick must match that instrument. It records the signal availability time at the completed 1-minute candle close, enters only on the first quote with a later timestamp (within the default 5-second entry-delay limit), and calculates expiry from that observed entry timestamp plus `contract_duration_seconds` (default 60). It resolves a result only when a quote exists at that exact expiry timestamp. Missing entry or expiry quotes remain incomplete; no OHLC candle close is substituted. Duplicate identical ticks are collapsed, conflicting same-time quotes are rejected, and overlapping or duplicate signals are excluded.

This evaluator reports directional outcomes only. Tie results are kept distinct, and payout, refund, spread, fees, and net expected return remain unavailable unless verified contract-specific data is supplied. The live app currently stores candles rather than a persistent historical raw-tick archive, so its existing dashboard backtest cannot produce this contract evaluation automatically. Do not pass resampled candle closes as tick quotes or use the resulting directional hit rate as profitability evidence.

## Local Setup

```powershell
cd c:\Users\Siphe\Desktop\umuzi
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

The dashboard uses Deriv's unauthenticated public market-data WebSocket. It discovers each selected instrument's `underlying_symbol` through `active_symbols`, requests that symbol's real `ticks_history`, and subscribes to live `ticks` for the same symbol. Switching markets clears the previous instrument's in-memory candles and live price before loading the new history. Step Index is the startup selection; if Deriv does not list it in `active_symbols`, the dashboard reports the feed error instead of silently substituting another market. `DERIV_APP_ID`, `DERIV_API_TOKEN`, and `DERIV_SYMBOL` are not required for the chart or signal feed; they are reserved for future authenticated features.

### TradingView confirmation

To enable Step Index main entries, set `TRADINGVIEW_SYMBOL` to the exact ticker shown in the TradingView chart header. For Gold, set `TRADINGVIEW_GOLD_SYMBOL` to Gold's exact chart ticker. Set `TRADINGVIEW_WEBHOOK_TOKEN` to a long random secret. Verify each TradingView feed represents the same instrument as the selected Deriv market; this app cannot infer or verify broker-to-TradingView symbol equivalence. If no exact matching feed is available, leave that market's symbol unset and its entries remain blocked.

Create TradingView alerts from an indicator/strategy that provides the intended matching BUY or SELL confirmation. Use a one-minute chart and trigger only once the bar is closed. Configure the webhook URL as `https://<your-host>/api/tradingview/webhook/<your-token>` and send JSON matching this shape (create a corresponding alert for each direction):

```json
{
  "ticker": "{{ticker}}",
  "direction": "BUY",
  "timeframe": "1",
  "bar_time": "{{time}}"
}
```

Use `"SELL"` in the separate sell alert. The webhook rejects wrong tokens, ticker/timeframe mismatches, timestamps outside the freshness window, and timestamps without a UTC timezone. An alert confirms an entry only when its ticker, direction, and candle-open timestamp exactly match the app's candidate signal. TradingView is an additional filter, not a guarantee of accuracy; no strategy can eliminate false signals or guarantee profits. Keep the token private and do not put it in public scripts or source control.

### Gold economic calendar

The Gold panel can show upcoming medium- and high-importance scheduled economic events aggregated by Trading Economics for the United States, China, Euro Area, United Kingdom, and Japan. Configure `TRADING_ECONOMICS_API_KEY` in `.env` locally or as a private Render environment variable. The dashboard refreshes the calendar every 15 minutes, retries source errors after one minute, and labels cached data stale when refresh fails. The calendar endpoint and key requirements are documented by [Trading Economics](https://docs.tradingeconomics.com/economic_calendar/country/).

This is a scheduled macroeconomic calendar, not a complete breaking-news feed. Event times are interpreted as UTC when the provider omits a timezone and displayed in the browser's local timezone. The panel is shown only while Gold is selected; it is not applied to synthetic Step Index. Economic releases can cause volatility in either direction and are not used to invent a BUY/SELL forecast or bypass technical signal, backtest, or TradingView checks. The market selector continues to analyze one selected market at a time.

### Shadow outcome tracking

The dashboard's **Shadow Signal Results** panel and `/api/performance` endpoint record each rule-qualified main-entry candidate before the backtest and TradingView gates modify or suppress it. Candidate plans are observed only; the tracker never submits orders. It resolves outcomes using closed 1-minute candles after the candidate's observation minute, tests stop loss versus TP1 (assuming the stop is hit first if both fall within one candle), and marks a candidate at the close after 120 bars if neither level is reached. Feed gaps and market switches are reported as incomplete rather than counted as wins or losses.

Results are gross price-movement R only. The feed does not provide verified bid/ask spread or actual fills, so spread, slippage, execution latency, and commissions are not modeled and the displayed results are not net profitability estimates. Setup-to-observation delay is recorded as a diagnostic. Compare candidates by their recorded backtest/TradingView gate status, and collect a meaningful sample across market conditions before changing rules; small samples are not evidence of reliable accuracy.

Start the application from the project folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open <http://127.0.0.1:8000>. Check service health at <http://127.0.0.1:8000/healthz>. The first complete 1h timeframe requires live collection time. The dashboard will remain explicit about missing data while candles form.

Run the regression tests with `.\.venv\Scripts\python.exe -W error::ResourceWarning -m unittest discover -s tests -v`.

## Deploy To Render

The repository includes `render.yaml`. Render uses Python 3.13.4, installs `requirements.txt`, starts Uvicorn on its assigned port, checks `/healthz`, and stores SQLite data on a persistent 1 GB disk mounted at `/var/data`. The blueprint uses Render's paid `starter` web-service plan because persistent disks are not available on free web services. Without persistent storage, deploys/restarts can erase the signal history.

The application refuses to start on a non-loopback `HOST` unless `DASHBOARD_AUTH_REQUIRED=true`; when enabled, both dashboard credentials must be set. This is a basic deployment safety guard, not enterprise identity management.

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
Start:  uvicorn app:app --host 0.0.0.0 --port $PORT --no-access-log
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

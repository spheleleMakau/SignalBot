const FRONTEND_BUILD = 'signal-plan-1';
const $ = id => document.getElementById(id);
const fmt = value => value == null || Number.isNaN(Number(value)) ? '--' : Number(value).toFixed(2);
const usdValue = (values, key, priceKey) => values?.available
  ? `$${Number(values[key]).toFixed(2)}`
  : values?.[priceKey] != null ? `USD NEEDED · ${Number(values[priceKey]).toFixed(2)} PRICE UNITS` : '--';

function plainReason(reason) {
  return String(reason)
    .replace('Higher-timeframe direction and 15M structure align', 'The big-picture trend and 15-minute chart agree')
    .replace('Market structure confirms direction', 'Recent price highs and lows point the same way')
    .replace('RSI momentum confirms without an extreme', 'The recent buying/selling push is not at an extreme')
    .replace('1M confirmation agrees with all higher timeframes', 'The finished 1-minute candle agrees with the bigger charts')
    .replace(/bullish engulfing or rejection-pin confirmation/gi, 'a strong green candle covering the previous red candle or turning up from a low')
    .replace(/bearish engulfing or rejection-pin confirmation/gi, 'a strong red candle covering the previous green candle or turning down from a high')
    .replace(/Wait for price to return within 1\.25 ATR of 1M EMA21 at ([\d.]+)\./i, 'Wait for price to come back near the middle short-term line at $1.')
    .replace(/Wait for 1M RSI in ([\d.-]+); current RSI is ([\d.]+)\./i, 'Wait for the buy/sell push meter to be between $1; it now reads $2 out of 100.')
    .replace(/Wait for 1M RSI between ([\d.]+) and ([\d.]+); current RSI is ([\d.]+)\./i, 'Wait for the buy/sell push meter to be between $1 and $2; it now reads $3 out of 100.')
    .replace(/EMA\s*9/g, 'fast trend line')
    .replace(/EMA\s*21/g, 'slower short-term trend line')
    .replace(/EMA\s*20(?!0)/g, 'short trend line')
    .replace(/EMA\s*50/g, 'middle trend line')
    .replace(/EMA\s*200/g, 'long trend line')
    .replace(/\bRSI\b/g, 'buy/sell push meter')
    .replace(/\bATR\b/g, 'usual price move')
    .replace(/\b1M\b/g, '1-minute')
    .replace(/\b5M\b/g, '5-minute')
    .replace(/bullish engulfing/gi, 'green candle covering the previous red candle')
    .replace(/bearish engulfing/gi, 'red candle covering the previous green candle')
    .replace(/rejection[- ]pin/gi, 'candle with a long wick that turns away from a price level');
}

function plainDirection(value) {
  return ({BULLISH: 'MOVING UP', BEARISH: 'MOVING DOWN', RANGING: 'SIDEWAYS', UNCLEAR: 'NOT CLEAR', MIXED: 'LINES DISAGREE'})[value] || value || 'WAITING';
}

function mainSignalLabel(signal) {
  if (signal.status === 'ENTRY CONFIRMED') return `${signal.direction} · ENTRY RULES PASSED`;
  if (signal.status === 'WAIT — TIMEFRAMES NOT ALIGNED') return 'WAIT · TIMEFRAMES NOT ALIGNED';
  if (signal.status === 'WAIT — ENTRY CONDITIONS NOT MET') return 'WAIT · ENTRY CONDITIONS NOT MET';
  if (signal.status === 'WAIT — PRICE MOVED') return 'WAIT · PRICE MOVED';
  if (signal.status === 'WAIT — ENTRY WINDOW EXPIRED') return 'WAIT · ENTRY WINDOW EXPIRED';
  if (signal.status === 'WAIT — LIVE PRICE UNAVAILABLE') return 'WAIT · LIVE PRICE NEEDED';
  if (String(signal.status || '').includes('BACKTEST')) return 'WAIT · PAST TEST NOT PASSED';
  if (String(signal.status || '').includes('RISK/REWARD')) return 'WAIT · RISK/REWARD CHECK FAILED';
  if (String(signal.status || '').includes('DATA')) return 'WAIT · NEED MORE DATA';
  return 'WAIT · ENTRY RULES NOT MET';
}

function plainBacktest(value) {
  const status = String(value || 'WAITING FOR DATA');
  if (status === 'PASS') return 'PAST CHECK PASSED';
  if (status === 'INSUFFICIENT HISTORICAL DATA') return 'NEED MORE PAST DATA';
  if (status.startsWith('BLOCKED')) return status.replace('BLOCKED', 'NOT READY').replace('TRADES', 'PAST TRADES').replace('EXPECTANCY NOT POSITIVE', 'PAST RESULTS NOT POSITIVE');
  return status;
}

function directionalHint(direction, scope = 'signal') {
  const label = scope === 'scalp' ? '1-minute trigger' : 'live setup';
  const normalized = String(direction || '').toUpperCase();
  if (normalized === 'BUY') {
    return `The ${label} can keep moving up while price stays above the fast trend line and the 5-minute trend stays supportive. It can turn down if price slips back under the fast line or the 5-minute setup weakens.`;
  }
  if (normalized === 'SELL') {
    return `The ${label} can keep moving down while price stays below the fast trend line and the 5-minute trend stays supportive. It can turn up if price pushes back above the fast line or the 5-minute setup flips.`;
  }
  if (normalized === 'BUY' || normalized === 'SELL') {
    return `The ${label} is still neutral until the fast line and the 5-minute trend agree again.`;
  }
  return `The ${label} can go either way until the 1-minute candle clears the active trend line and the 5-minute bias agrees.`;
}

function ensureSwingVolumePanel() {
  if ($('swing-volume-panel')) return;
  const panel = document.createElement('article');
  panel.id = 'swing-volume-panel';
  panel.className = 'swing-volume-panel';
  panel.style.gridColumn = '1 / -1';
  panel.innerHTML = '<div class="panel-heading"><span class="label">SWING + VOLUME PROFILE · ADVISORY</span><span id="swing-volume-status" class="muted">WAITING FOR DATA</span></div><div class="metrics profile-metrics"><div><span>15M SWING DIRECTION</span><b id="swing-direction">WAITING</b></div><div><span>LAST SWING HIGH</span><b id="swing-high">--</b></div><div><span>LAST SWING LOW</span><b id="swing-low">--</b></div><div><span>ESTIMATED POC</span><b id="swing-poc">--</b></div><div><span>PRICE VS POC</span><b id="swing-price-location">--</b></div></div><p id="swing-entry-context" class="reason">Waiting for closed candles with live tick-volume data.</p><small id="swing-volume-source">POC is an advisory tick-volume estimate, not traded volume; it does not block or confirm an entry.</small>';
  document.querySelector('.lower-grid')?.append(panel);
}

let selectedTimeframe = '5m';
let latestRefreshId = 0;
let pendingMarketId = '';
let audioContext = null;
let soundReady = false;
let pendingAudioAlerts = [];
let previousMainSignal = '';
let previousScalpSignal = '';
let activeExitAlertId = '';
let dismissedExitAlertId = '';
try { dismissedExitAlertId = sessionStorage.getItem('dismissedExitAlertId') || ''; } catch (error) {}
const confirmedStatuses = new Set(['ENTRY CONFIRMED', 'SCALP ENTRY CONFIRMED']);

function tone(frequency, duration, delay = 0) {
  if (!soundReady) return;
  audioContext ||= new (window.AudioContext || window.webkitAudioContext)();
  const oscillator = audioContext.createOscillator();
  const gain = audioContext.createGain();
  oscillator.frequency.value = frequency;
  gain.gain.setValueAtTime(.0001, audioContext.currentTime + delay);
  gain.gain.exponentialRampToValueAtTime(.16, audioContext.currentTime + delay + .02);
  gain.gain.exponentialRampToValueAtTime(.0001, audioContext.currentTime + delay + duration);
  oscillator.connect(gain).connect(audioContext.destination);
  oscillator.start(audioContext.currentTime + delay);
  oscillator.stop(audioContext.currentTime + delay + duration + .03);
}

function playAudioAlert(type) {
  if (!soundReady) {
    pendingAudioAlerts.push(type);
    return;
  }
  if (type === 'entry') { tone(880, .16); tone(1175, .2, .2); }
  else { tone(520, .2); tone(330, .3, .24); }
}

function enableAutomaticAudio() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;
  audioContext ||= new AudioContextClass();
  audioContext.resume().then(() => {
    soundReady = audioContext.state === 'running';
    if ($('sound-state')) $('sound-state').textContent = soundReady
      ? 'Automatic entry and exit alerts are active.'
      : 'Waiting for browser audio permission.';
    if (soundReady) {
      const alerts = pendingAudioAlerts;
      pendingAudioAlerts = [];
      alerts.forEach(playAudioAlert);
    }
  }).catch(() => {
    if ($('sound-state')) $('sound-state').textContent = 'Audio will start automatically after your first interaction with this page.';
  });
}

function entryAlert() { playAudioAlert('entry'); }
function closeAlert() { playAudioAlert('close'); }

function acknowledgeExitAlert(alertId) {
  activeExitAlertId = '';
  dismissedExitAlertId = alertId;
  try { sessionStorage.setItem('dismissedExitAlertId', alertId); } catch (error) {}
  $('exit-alert-modal')?.remove();
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  fetch('/api/exit-alert/acknowledge', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id: alertId})
  }).catch(() => {});
}

function showExitAlert(alert) {
  if (!alert?.id || alert.id === dismissedExitAlertId || alert.id === activeExitAlertId) return;
  activeExitAlertId = alert.id;
  closeAlert();
  const cause = alert.status === 'STOP LOSS HIT'
    ? 'Stop loss reached.'
    : `${alert.status.replace(' HIT', '').replace('TARGET', 'Target')} reached.`;
  if ('speechSynthesis' in window && 'SpeechSynthesisUtterance' in window) {
    try {
      window.speechSynthesis.cancel();
      const message = new SpeechSynthesisUtterance(`Close order now. ${cause}`);
      message.rate = 1;
      window.speechSynthesis.speak(message);
    } catch (error) {}
  }

  const overlay = document.createElement('div');
  overlay.id = 'exit-alert-modal';
  overlay.setAttribute('role', 'alertdialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-labelledby', 'exit-alert-title');
  Object.assign(overlay.style, {
    position: 'fixed', inset: '0', zIndex: '1000', display: 'grid',
    placeItems: 'center', padding: '20px', background: 'rgba(4, 9, 12, .82)'
  });

  const panel = document.createElement('section');
  Object.assign(panel.style, {
    width: 'min(100%, 460px)', padding: '28px', color: '#e9f0f3',
    background: '#111b23', border: `2px solid ${alert.status === 'STOP LOSS HIT' ? '#ff6b6b' : '#f6c85f'}`,
    boxShadow: '0 18px 60px rgba(0,0,0,.55)', fontFamily: 'Space Grotesk, sans-serif'
  });

  const title = document.createElement('h2');
  title.id = 'exit-alert-title';
  title.textContent = 'CLOSE ORDER NOW';
  title.style.cssText = 'margin:0 0 12px;font-size:24px;color:#ff6b6b';
  const description = document.createElement('p');
  description.textContent = `${cause} ${alert.direction || 'Open'} order. Exit price: ${fmt(alert.price)}.`;
  description.style.cssText = 'line-height:1.6;margin:0 0 20px';
  const acknowledge = document.createElement('button');
  acknowledge.type = 'button';
  acknowledge.textContent = 'ACKNOWLEDGE';
  acknowledge.style.cssText = 'border:1px solid #8496a1;background:#0b1117;color:#e9f0f3;padding:10px 14px;font:500 11px DM Mono,monospace;cursor:pointer';
  acknowledge.addEventListener('click', () => acknowledgeExitAlert(alert.id));
  panel.append(title, description, acknowledge);
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  acknowledge.focus();
}

enableAutomaticAudio();
document.addEventListener('pointerdown', enableAutomaticAudio, {once: true});
document.addEventListener('keydown', enableAutomaticAudio, {once: true});

function paint(data) {
  ensureSwingVolumePanel();
  const connection = data.connection.toLowerCase();
  $('connection').className = `connection ${connection}`;
  $('connection').textContent = `* ${data.connection}`;
  $('price').textContent = fmt(data.price);
  if ($('symbol') && data.symbol) $('symbol').textContent = data.symbol;
  if (data.market_name) {
    const heading = document.querySelector('header h1');
    if (heading?.firstChild) heading.firstChild.textContent = `${data.market_name} `;
  }
  $('tick-time').textContent = data.last_tick ? new Date(data.last_tick * 1000).toLocaleString() : 'Waiting for a verified tick';
  const signal = data.signal || {};
  const swingVolume = signal.swing_volume_confirmation || {};
  const scalp = data.scalp_signal || {};
  const bot = data.bot || {};
  if (signal.status === 'ENTRY CONFIRMED' && previousMainSignal !== signal.id) entryAlert();
  if (scalp.status === 'SCALP ENTRY CONFIRMED' && previousScalpSignal !== scalp.id) entryAlert();
  showExitAlert(data.exit_alert);
  previousMainSignal = signal.id || '';
  previousScalpSignal = scalp.id || '';
  $('signal').textContent = mainSignalLabel(signal);
  $('score').textContent = signal.score ? `${signal.score}/100 rule points · not win odds` : 'No entry has passed every check';
  const signalReasons = (signal.reasons || []).map(plainReason);
  $('reason').textContent = signalReasons.join(' | ') || (signal.status === 'ENTRY CONFIRMED'
    ? `${directionalHint(signal.direction, 'signal')} This is not a guaranteed outcome.`
    : 'WAIT: no entry has passed every required check.');
  $('trade-status').textContent = data.trade_status || 'WAITING';
  $('swing-volume-status').textContent = swingVolume.status || 'WAITING FOR DATA';
  $('swing-direction').textContent = plainDirection(swingVolume.direction);
  $('swing-high').textContent = fmt(swingVolume.swing_high);
  $('swing-low').textContent = fmt(swingVolume.swing_low);
  $('swing-poc').textContent = fmt(swingVolume.poc);
  $('swing-price-location').textContent = swingVolume.price_vs_poc || 'UNAVAILABLE';
  $('swing-entry-context').textContent = swingVolume.entry_context || 'POC is advisory and does not change signal eligibility.';
  $('swing-volume-source').textContent = swingVolume.source || 'POC is an advisory tick-volume estimate, not traded volume.';
  Object.entries(signal.timeframes || {}).forEach(([timeframe, value]) => {
    const element = $(`bias-${timeframe}`);
    if (element) element.textContent = value.available === false ? 'WAITING FOR DATA' : plainDirection(value.bias);
  });
  const indicators = signal.indicators || {};
  const indicatorGuide = {
    ema_20: ['Short trend line', 'Follows recent price closely.'],
    ema_50: ['Middle trend line', 'Shows the middle-sized trend.'],
    ema_200: ['Long trend line', 'Shows the bigger, slower trend.'],
    rsi_14: ['Buying/selling push · 0-100', 'Shows which side pushed more recently; it cannot predict the next move.'],
    atr_14: ['Usual 1-minute move', 'Recent move size; it helps set stop distance, not direction.'],
  };
  $('indicators').innerHTML = Object.entries(indicators).map(([key, value]) => {
    const [label, explanation] = indicatorGuide[key] || [plainReason(key), ''];
    return `<div class="indicator-row"><span><b>${label}</b><small>${explanation}</small></span><strong>${fmt(value)}</strong></div>`;
  }).join('') || 'Waiting for enough closed candles.';
  renderHistory(data.history);
  $('scalp-status').textContent = scalp.status || 'NO SCALP SIGNAL';
  $('scalp-score').textContent = scalp.score ? `${scalp.score}/100 rule points · not win odds` : '--';
  $('scalp-direction').textContent = scalp.direction || (scalp.watch_direction ? `WAITING TO ${scalp.watch_direction}` : '--');
  $('scalp-entry').textContent = fmt(scalp.entry);
  $('scalp-sl').textContent = fmt(scalp.stop_loss);
  $('scalp-tp1').textContent = fmt(scalp.tp1);
  $('scalp-tp2').textContent = fmt(scalp.tp2);
  const timeframeConflict = scalp.status === 'SCALP WAIT — TIMEFRAMES NOT ALIGNED';
  const scalpHint = timeframeConflict ? '' : directionalHint(scalp.direction || scalp.watch_direction, 'scalp');
  const scalpExplanation = scalp.watch_direction === 'BUY'
    ? 'Simple version: wait for price to dip, then turn upward on a finished 1-minute candle.'
    : scalp.watch_direction === 'SELL'
      ? 'Simple version: wait for price to rise, then turn downward on a finished 1-minute candle.'
      : '';
  $('scalp-reason').textContent = [scalpHint, scalpExplanation, ...(scalp.reasons || []).map(plainReason)].filter(Boolean).join(' ')
    || 'Waiting for fresh live 1M and 5M candles before describing a BUY or SELL trigger.';
  const scenarioGrid = $('scalp-scenarios');
  if (scenarioGrid) scenarioGrid.hidden = timeframeConflict;
  const scenarios = scalp.scenarios || {};
  for (const direction of ['BUY', 'SELL']) {
    const scenario = scenarios[direction] || {};
    const status = $(`scalp-${direction.toLowerCase()}-status`);
    const reasons = $(`scalp-${direction.toLowerCase()}-reasons`);
    if (status) status.textContent = scenario.status || 'WAITING FOR LIVE CANDLES';
    if (reasons) reasons.textContent = (scenario.reasons || ['Waiting for live candle data.']).map(plainReason).join(' ');
  }
  const scalpValues = data.scalp_trade_values || {};
  $('scalp-lot-size').textContent = `${Number(scalpValues.lot_size ?? .1).toFixed(2)} LOT`;
  $('scalp-loss-usd').textContent = usdValue(scalpValues, 'estimated_loss_usd', 'risk_price_units');
  $('scalp-tp1-usd').textContent = usdValue(scalpValues, 'estimated_target_1_usd', 'target_1_price_units');
  $('scalp-tp2-usd').textContent = usdValue(scalpValues, 'estimated_target_2_usd', 'target_2_price_units');
  const scalpProfitFactor = bot.scalp_backtest_profit_factor == null ? '--' : Number(bot.scalp_backtest_profit_factor).toFixed(2);
  const scalpHoldoutFactor = bot.scalp_backtest_validation_profit_factor == null ? '--' : Number(bot.scalp_backtest_validation_profit_factor).toFixed(2);
  $('scalp-validation').textContent = `Past test: ${plainBacktest(bot.scalp_backtest_status)} · ${bot.scalp_backtest_trades ?? 0} total trades · recent check ${bot.scalp_backtest_validation_trades ?? 0} trades / ratio ${scalpHoldoutFactor}`;
  const today = data.today_trend || {};
  $('today-direction').textContent = today.direction || 'WAITING';
  $('today-change').textContent = today.change_percent == null ? '--' : `${Number(today.change_percent).toFixed(2)}%`;
  $('today-open').textContent = fmt(today.open);
  $('today-current').textContent = fmt(today.current);
  $('today-range').textContent = today.high == null ? '--' : `${fmt(today.low)} - ${fmt(today.high)}`;
  $('today-candles').textContent = today.candles == null ? '--' : today.candles;
  $('bot-mode').textContent = bot.mode === 'ALERT_ONLY' ? 'SIGNALS ONLY' : (bot.mode || 'SIGNALS ONLY');
  $('bot-feed').textContent = bot.feed_quality || 'STALE';
  $('bot-age').textContent = bot.feed_age_seconds == null ? '--' : `${bot.feed_age_seconds}s`;
  $('bot-backtest').textContent = plainBacktest(bot.backtest_status);
  const profitFactor = bot.backtest_profit_factor == null ? '--' : Number(bot.backtest_profit_factor).toFixed(2);
  $('bot-backtest-sample').textContent = `${bot.backtest_trades ?? 0} past trades · gain/loss ratio ${profitFactor}`;
  $('bot-backtest-holdout').textContent = `${bot.backtest_validation_trades ?? 0} recent trades · ratio ${bot.backtest_validation_profit_factor == null ? '--' : Number(bot.backtest_validation_profit_factor).toFixed(2)}`;
  const analysis = data.timeframe_analysis || {};
  Object.entries(analysis).forEach(([timeframe, item]) => {
    const card = $(`analysis-${timeframe}`);
    if (!card) return;
    card.querySelector('.analysis-status').textContent = item.status === 'LIVE ANALYSIS' ? 'CURRENT' : 'WAITING';
    card.querySelector('.analysis-close').textContent = fmt(item.close);
    card.querySelector('.analysis-bias').textContent = plainDirection(item.bias);
    const action = card.querySelector('.analysis-action');
    const confluence = item.confluence || {};
    action.textContent = item.action === 'BUY' ? `BUY · ${confluence.bullish_votes ?? 0}/5 AGREE` : item.action === 'SELL' ? `SELL · ${confluence.bearish_votes ?? 0}/5 AGREE` : `WAIT · ${Math.max(confluence.bullish_votes ?? 0, confluence.bearish_votes ?? 0)}/5`; 
    action.style.color = item.action === 'BUY' ? '#75e6a2' : item.action === 'SELL' ? '#ff6b6b' : '#f6c85f';
    card.querySelector('.analysis-ema').textContent = confluence.layers?.trend || (item.ema_alignment === 'BULLISH' ? 'BULLISH' : item.ema_alignment === 'BEARISH' ? 'BEARISH' : 'NEUTRAL');
    card.querySelector('.analysis-rsi').textContent = item.rsi == null ? '--' : `${Math.round(item.rsi)} / 100`;
    card.querySelector('.analysis-atr').textContent = item.atr == null ? '--' : `${fmt(item.atr)} price units`;
    const layersElement = card.querySelector('.analysis-layers');
    if (layersElement) {
      layersElement.innerHTML = Object.entries(confluence.layers || {}).map(([name, direction]) => {
        const label = direction === 'BULLISH' ? 'UP' : direction === 'BEARISH' ? 'DOWN' : 'NEUTRAL';
        return `<span class="confluence-chip ${direction.toLowerCase()}">${name.toUpperCase()} · ${label}</span>`;
      }).join('') || 'Waiting for layer data';
    }
  });
}

async function refresh() {
  const refreshId = ++latestRefreshId;
  const timeframe = selectedTimeframe;
  try {
    const state = await (await fetch('/api/state')).json();
    if (refreshId !== latestRefreshId || (pendingMarketId && state.market_id !== pendingMarketId)) return;
    paint(state);
    const chart = await (await fetch(`/api/chart?timeframe=${timeframe}`)).json();
    if (refreshId !== latestRefreshId || selectedTimeframe !== timeframe) return;
    if (chart.timeframe !== timeframe) return;
    if (state.market_id && (chart.market_id !== state.market_id || chart.symbol !== state.symbol)) return;
    Plotly.react('chart', chart.data, chart.layout, {responsive: true, displayModeBar: true, displaylogo: false, modeBarButtonsToRemove: ['lasso2d', 'select2d']});
    Plotly.Plots.resize('chart');
  } catch (error) {
    if (refreshId === latestRefreshId) $('connection').textContent = '* OFFLINE';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.mode-btn').forEach(button => {
    button.addEventListener('click', () => {
      const mode = button.dataset.mode;
      const url = new URL(window.location.href);
      url.searchParams.set('mode', mode);
      window.location.href = url.toString();
    });
  });
});

function addTimeframeControls() {
  const chart = $('chart');
  const tabs = document.createElement('div');
  tabs.className = 'timeframe-tabs';
  tabs.style.cssText = 'display:flex;gap:8px;margin:0 0 12px;';
  tabs.setAttribute('role', 'group');
  tabs.setAttribute('aria-label', 'Chart timeframe');
  for (const timeframe of ['1m', '5m', '15m', '1h', '4h']) {
    const button = document.createElement('button');
    button.className = `timeframe ${timeframe === selectedTimeframe ? 'active' : ''}`;
    button.style.cssText = 'border:1px solid #24333e;background:#111b23;color:#8496a1;padding:8px 12px;font:500 11px DM Mono,monospace;cursor:pointer;';
    if (timeframe === selectedTimeframe) {
      button.style.color = '#75e6a2';
      button.style.borderColor = '#75e6a2';
    }
    button.textContent = ({'1m': '1 MIN', '5m': '5 MIN', '15m': '15 MIN', '1h': '1 HOUR', '4h': '4 HOUR'})[timeframe];
    button.type = 'button';
    button.addEventListener('click', () => {
      selectedTimeframe = timeframe;
      tabs.querySelectorAll('button').forEach(item => {
        item.classList.toggle('active', item === button);
        item.style.color = item === button ? '#75e6a2' : '#8496a1';
        item.style.borderColor = item === button ? '#75e6a2' : '#24333e';
      });
      refresh();
    });
    tabs.appendChild(button);
  }
  chart.parentElement.insertBefore(tabs, chart);
}

async function refreshMarketOptions() {
  const selector = $('market-selector');
  if (!selector) return;
  try {
    const response = await fetch('/api/markets');
    if (!response.ok) return;
    const markets = await response.json();
    const currentChoice = selector.value;
    selector.replaceChildren(...markets.options.map(market => {
      const option = document.createElement('option');
      option.value = market.id;
      option.textContent = market.available ? market.label : `${market.label} · OFFLINE`;
      option.disabled = !market.available;
      return option;
    }));
    if (selector.dataset.pending === 'true' && markets.selected === currentChoice) {
      selector.dataset.pending = 'false';
    }
    if (selector.dataset.pending !== 'true') selector.dataset.selected = markets.selected;
    selector.value = selector.dataset.pending === 'true' ? currentChoice : markets.selected;
  } catch (error) {}
}

function addMarketSelector() {
  const selector = document.createElement('select');
  selector.id = 'market-selector';
  selector.setAttribute('aria-label', 'Select market');
  selector.style.cssText = 'border:1px solid #24333e;background:#111b23;color:#e9f0f3;padding:9px 10px;font:500 11px DM Mono,monospace;max-width:190px;';
  selector.addEventListener('change', async () => {
    const previous = selector.dataset.selected || 'gold';
    const marketId = selector.value;
    pendingMarketId = marketId;
    latestRefreshId += 1;
    const marketName = selector.selectedOptions[0]?.textContent.replace(' · OFFLINE', '') || 'Market';
    Plotly.react('chart', [], {
      template: 'plotly_dark',
      title: {text: `${marketName} · WAITING FOR LIVE CANDLES`},
    }, {responsive: true, displayModeBar: true, displaylogo: false});
    selector.disabled = true;
    selector.dataset.pending = 'true';
    try {
      const response = await fetch('/api/select-market', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({market_id: marketId}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Market switch failed');
      selector.dataset.selected = marketId;
      pendingMarketId = '';
      refresh();
    } catch (error) {
      pendingMarketId = '';
      selector.dataset.pending = 'false';
      selector.value = previous;
      window.alert(error.message);
      refresh();
    } finally {
      selector.disabled = false;
    }
  });
  document.querySelector('.mode-switch')?.after(selector);
  refreshMarketOptions();
  setInterval(refreshMarketOptions, 5000);
}

function addFourHourContext() {
  const metrics = document.querySelector('.metrics');
  if (!metrics) return;
  const item = document.createElement('div');
  item.innerHTML = '<span>4H CONTEXT · UTC</span><b id="bias-4h">WAITING FOR DATA</b>';
  metrics.appendChild(item);
  metrics.style.gridTemplateColumns = 'repeat(auto-fit, minmax(120px, 1fr))';
}

function renderHistory(history) {
  const now = Math.floor(Date.now() / 1000);
  const items = (history || []).filter(item => confirmedStatuses.has(item.outcome)
    && item.confirmed === true
    && item.timestamp >= now - 24 * 60 * 60
    && item.timestamp <= now
    && item.direction
    && item.entry != null);
  if ($('history-count')) $('history-count').textContent = `${items.length} confirmed signals in the last 24 hours`;
  if (!items.length) {
    $('history-list').innerHTML = '<span class="history-empty">No confirmed signals in the last 24 hours.</span>';
    return;
  }
  const list = $('history-list');
  list.replaceChildren();
  items.forEach(item => {
    const card = document.createElement('article');
    card.className = `confirmed-signal-card ${item.direction === 'SELL' ? 'sell' : 'buy'}`;

    const heading = document.createElement('div');
    heading.className = 'confirmed-signal-heading';
    const identity = document.createElement('strong');
    identity.textContent = `${item.direction} · ${item.symbol || 'UNKNOWN SYMBOL'}`;
    const time = document.createElement('span');
    time.textContent = item.timestamp ? new Date(item.timestamp * 1000).toLocaleString() : 'Time unavailable';
    heading.append(identity, time);
    const type = document.createElement('span');
    type.className = 'confirmed-signal-type';
    type.textContent = item.outcome === 'SCALP ENTRY CONFIRMED' ? 'SCALP SIGNAL CONFIRMED' : 'MAIN SIGNAL CONFIRMED';
    card.append(heading, type);

    const levels = document.createElement('div');
    levels.className = 'confirmed-signal-levels';
    const stop = item.stop_loss;
    const target1 = item.take_profit_1 ?? item.tp1;
    const target2 = item.take_profit_2 ?? item.tp2;
    const risk = stop == null ? null : Math.abs(Number(item.entry) - Number(stop));
    const reward = target1 == null ? null : Math.abs(Number(target1) - Number(item.entry));
    const values = [
      ['ENTRY', item.entry],
      ['STOP LOSS', stop],
      ['TARGET 1', target1],
      ['TARGET 2', target2],
      ['RISK / REWARD', risk > 0 && reward != null ? `1:${(reward / risk).toFixed(2)}` : null],
      ['RULE SCORE', `${item.confidence ?? 0}/100`],
    ];
    values.forEach(([label, value]) => {
      const cell = document.createElement('div');
      const caption = document.createElement('span');
      caption.textContent = label;
      const reading = document.createElement('strong');
      reading.textContent = label === 'RISK / REWARD' || label === 'RULE SCORE'
        ? (value ?? '--')
        : fmt(value);
      cell.append(caption, reading);
      levels.appendChild(cell);
    });
    card.appendChild(levels);

    let reasons = [];
    try {
      const parsed = typeof item.reason === 'string' ? JSON.parse(item.reason) : item.reason;
      reasons = Array.isArray(parsed) ? parsed : [];
    } catch (error) {
      reasons = item.reason ? [String(item.reason)] : [];
    }
    if (reasons.length) {
      const reasonList = document.createElement('p');
      reasonList.className = 'confirmed-signal-reasons';
      reasonList.textContent = reasons.map(plainReason).join(' · ');
      card.appendChild(reasonList);
    }
    list.appendChild(card);
  });
}

function addTodayTrend() {
  const card = document.createElement('article');
  card.className = 'today-card';
  card.innerHTML = '<div class="panel-heading"><span class="label">TODAY\'S TREND · UTC</span><span id="today-direction" class="trend-direction">WAITING</span></div><div class="today-grid"><div><span>CHANGE</span><b id="today-change">--</b></div><div><span>OPEN</span><b id="today-open">--</b></div><div><span>CURRENT</span><b id="today-current">--</b></div><div><span>RANGE</span><b id="today-range">--</b></div><div><span>5M CANDLES</span><b id="today-candles">--</b></div></div>';
  $('chart').parentElement.parentElement.insertBefore(card, $('chart').parentElement);
}

function addScalpPanel() {
  const panel = document.createElement('article');
  panel.className = 'scalp-card';
  panel.innerHTML = '<div class="panel-heading"><span class="label">QUICK TRADE · 1-MINUTE TRIGGER / 5-MINUTE SETUP</span><span id="scalp-status" class="trend-direction">WAITING</span></div><div id="scalp-validation" class="validation-line">Past test: WAITING FOR DATA</div><div class="scalp-head"><strong id="scalp-direction">--</strong><span id="scalp-score" class="muted">--</span></div><div class="scalp-levels"><span>ENTRY <b id="scalp-entry">--</b></span><span>STOP · EXIT IF WRONG <b id="scalp-sl">--</b></span><span>TARGET 1 <b id="scalp-tp1">--</b></span><span>TARGET 2 <b id="scalp-tp2">--</b></span></div><div class="scalp-money-grid"><span>SIZE <b id="scalp-lot-size">0.10 LOT</b></span><span>EST. LOSS AT STOP <b id="scalp-loss-usd">--</b></span><span>POSSIBLE AT TARGET 1 <b id="scalp-tp1-usd">--</b></span><span>POSSIBLE AT TARGET 2 <b id="scalp-tp2-usd">--</b></span></div><p id="scalp-reason" class="reason">Waiting for fresh 1-minute and 5-minute candles.</p><div id="scalp-scenarios" class="scenario-grid" aria-label="Conditional BUY and SELL scalp setups"><article class="scenario-card buy"><div><strong>BUY SCENARIO</strong><b id="scalp-buy-status">WAITING FOR LIVE CANDLES</b></div><p id="scalp-buy-reasons">Waiting for live candle data.</p></article><article class="scenario-card sell"><div><strong>SELL SCENARIO</strong><b id="scalp-sell-status">WAITING FOR LIVE CANDLES</b></div><p id="scalp-sell-reasons">Waiting for live candle data.</p></article></div><small class="scenario-note">These are conditional setups, not simultaneous entry instructions. Only the main signal marked ENTRY CONFIRMED has passed validation.</small>';
  const signalPanel = document.querySelector('.signal-panel');
  signalPanel.parentElement.appendChild(panel);
}

function addBotPanel() {
  const panel = document.createElement('article');
  panel.className = 'bot-card';
  panel.innerHTML = '<div class="panel-heading"><span class="label">DATA CHECK</span><span class="trend-direction">NO AUTO-ORDERS</span></div><div class="bot-grid"><div><span>MODE</span><b id="bot-mode">ALERT_ONLY</b></div><div><span>PRICE FEED</span><b id="bot-feed">STALE</b></div><div><span>TICK AGE</span><b id="bot-age">--</b></div><div><span>MAIN PAST TEST</span><b id="bot-backtest">WAITING FOR DATA</b></div><div><span>ALL PAST TRADES</span><b id="bot-backtest-sample">0 trades</b></div><div><span>RECENT HOLDOUT CHECK</span><b id="bot-backtest-holdout">0 trades</b></div></div><div class="sound-row"><span id="sound-state">Audio alerts start automatically when the browser permits playback.</span></div><small>The app never opens orders. A signal can still lose; check the stop amount first.</small>';
  document.querySelector('main').appendChild(panel);
}

function addTimeframeAnalysis() {
  const section = document.createElement('section');
  section.className = 'analysis-section';
  const timeframes = {'1m': '1-MINUTE TRIGGER', '5m': '5-MINUTE SETUP', '15m': '15-MINUTE CHECK', '1h': 'BIG PICTURE · 1 HOUR'};
  section.innerHTML = '<div class="panel-heading"><span class="label">MULTI-LAYER CONFLUENCE</span><span class="muted">5 layers: trend, structure, momentum, RSI, candle pattern. A score is not a confirmed entry.</span></div><div class="analysis-grid">' + Object.entries(timeframes).map(([timeframe, label]) => `<article id="analysis-${timeframe}" class="analysis-card"><div class="analysis-card-head"><strong>${label}</strong><span class="analysis-status">WAITING</span></div><div class="analysis-values"><span>CONFLUENCE <b class="analysis-action">WAIT</b></span><span>DIRECTION <b class="analysis-bias">--</b></span><span>TREND <b class="analysis-ema">--</b></span><span>BUY/SELL PUSH <b class="analysis-rsi">--</b></span><span>USUAL CANDLE MOVE <b class="analysis-atr">--</b></span><span>LAST PRICE <b class="analysis-close">--</b></span></div><div class="analysis-layers">Waiting for layer data</div></article>`).join('') + '</div>';
  document.querySelector('main').appendChild(section);
}

function addChartGuide() {
  const chart = $('chart');
  const heading = chart.parentElement.querySelector('.panel-heading .muted');
  if (heading) heading.textContent = 'Compare the colored guide lines with your phone chart.';
  const guide = document.createElement('div');
  guide.className = 'chart-guide';
  guide.innerHTML = '<span><i style="background:#f6c85f"></i>Gold: recent direction</span><span><i style="background:#66c7f2"></i>Blue: middle direction</span><span><i style="background:#ff7f66"></i>Coral: big direction</span><span><i style="background:#75e6a2"></i>Green: entry/targets or price floor</span><span><i style="background:#ff6b6b"></i>Red: stop/price ceiling</span>';
  chart.parentElement.appendChild(guide);
}

function removeTradePlan() {
  document.querySelector('.trade-card')?.remove();
  document.querySelector('.content-grid')?.classList.add('chart-only');
  const headings = document.querySelectorAll('.lower-grid .panel-heading .label');
  if (headings[0]) headings[0].textContent = 'DIRECTION AT EACH SPEED';
  if (headings[1]) headings[1].textContent = 'WHAT THESE NUMBERS MEAN';
  document.querySelectorAll('.metrics span').forEach((label, index) => {
    label.textContent = ['BIG PICTURE · 1 HOUR', 'CHECK · 15 MINUTES', 'SETUP · 5 MINUTES', 'TRIGGER · 1 MINUTE'][index];
  });
}

function addResponsiveStyles() {
  const style = document.createElement('style');
    style.textContent = '.today-card{grid-column:1/-1;background:linear-gradient(145deg,rgba(25,39,49,.96),rgba(13,22,29,.96));border:1px solid #24333e;padding:18px 22px}.today-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.bot-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(125px,1fr));gap:12px}.today-grid div,.bot-grid div{background:#0c151c;padding:12px}.today-grid span,.bot-grid span{display:block;color:#8496a1;font:500 9px DM Mono,monospace;letter-spacing:1px;margin-bottom:7px}.today-grid b,.bot-grid b{font:500 14px DM Mono,monospace}.scalp-card,.bot-card,.analysis-section{grid-column:1/-1;background:linear-gradient(145deg,rgba(25,39,49,.96),rgba(13,22,29,.96));border:1px solid #24333e;padding:18px 22px}.scalp-head{display:flex;justify-content:space-between;align-items:center;margin:12px 0}.scalp-head strong{font:600 22px DM Mono,monospace;color:#75e6a2}.scalp-levels{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.scalp-levels span{color:#8496a1;font:500 10px DM Mono,monospace}.scalp-levels b{display:block;color:#e9f0f3;font-size:14px;margin-top:6px}.analysis-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.analysis-card{background:#0c151c;border:1px solid #24333e;padding:14px}.analysis-card-head{display:flex;justify-content:space-between;margin-bottom:13px}.analysis-card-head strong{font:600 18px DM Mono,monospace}.analysis-status,.analysis-action{color:#75e6a2;font:500 10px DM Mono,monospace}.analysis-values{display:grid;gap:9px}.analysis-values span{color:#8496a1;font:500 9px DM Mono,monospace}.analysis-values b{float:right;color:#e9f0f3;font-size:11px}.trend-direction{font:500 12px DM Mono,monospace;color:#75e6a2}.confirmed-signal-card{margin-top:12px;padding:16px;background:#0c151c;border:1px solid #24333e;border-left:3px solid #75e6a2}.confirmed-signal-card.sell{border-left-color:#ff6b6b}.confirmed-signal-heading{display:flex;justify-content:space-between;gap:12px;align-items:center}.confirmed-signal-heading strong{font:600 15px DM Mono,monospace;color:#75e6a2}.confirmed-signal-card.sell .confirmed-signal-heading strong{color:#ff6b6b}.confirmed-signal-heading span,.confirmed-signal-type{font:11px DM Mono,monospace;color:#8496a1}.confirmed-signal-type{display:block;margin-top:8px}.confirmed-signal-levels{display:grid;grid-template-columns:repeat(auto-fit,minmax(115px,1fr));gap:8px;margin-top:12px}.confirmed-signal-levels div{padding:10px;background:#111b23}.confirmed-signal-levels span{display:block;color:#8496a1;font:500 9px DM Mono,monospace;margin-bottom:7px}.confirmed-signal-levels strong{font:500 13px DM Mono,monospace;color:#e9f0f3}.confirmed-signal-reasons{margin:12px 0 0;color:#b7c5ca;font-size:12px;line-height:1.5}@media(max-width:800px){header{align-items:flex-start;gap:14px;flex-wrap:wrap}h1{font-size:27px}.panel-heading{gap:12px;align-items:flex-start}.today-grid,.analysis-grid{grid-template-columns:repeat(2,1fr)}.today-grid div:last-child{grid-column:1/-1}.scalp-levels{grid-template-columns:repeat(2,1fr);row-gap:14px}.timeframe-tabs{overflow-x:auto;padding-bottom:3px} .timeframe-tabs button{flex:0 0 auto}#chart{min-height:330px}.confirmed-signal-heading{align-items:flex-start;flex-direction:column}}';
  style.textContent += '.trade-money-grid,.scalp-money-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin:14px 0}.trade-money-grid div,.scalp-money-grid span{background:#0c151c;padding:12px;color:#8496a1;font:500 9px DM Mono,monospace}.trade-money-grid span,.scalp-money-grid b{display:block;margin-bottom:7px}.trade-money-grid b,.scalp-money-grid b{color:#e9f0f3;font:500 13px DM Mono,monospace;overflow-wrap:anywhere}.trade-card .reason{font-size:12px}.chart-guide{display:flex;flex-wrap:wrap;gap:8px 14px;margin-top:12px}.chart-guide span{display:flex;align-items:center;gap:7px;color:#b7c5ca;font-size:11px}.chart-guide i{width:10px;height:10px;flex:none;border-radius:50%}.indicator-row{align-items:center;gap:8px;min-width:0}.indicator-row span{display:grid;gap:5px;min-width:0}.indicator-row span b{font:500 11px DM Mono,monospace;color:#e9f0f3}.indicator-row small{font:11px Space Grotesk,sans-serif;line-height:1.35;letter-spacing:0}.indicator-row strong{font:500 12px DM Mono,monospace;color:#e9f0f3;white-space:nowrap}.phone-check{margin-top:10px}';
  document.head.appendChild(style);
  const polish = document.createElement('style');
  polish.textContent = 'body{background:radial-gradient(circle at 10% 0,rgba(71,130,119,.16),transparent 30%),radial-gradient(circle at 90% 8%,rgba(246,200,95,.08),transparent 24%),#0b1117;overflow-x:hidden}header{max-width:1480px;padding-top:26px}main{max-width:1480px}.price-panel,.signal-panel,.chart-card,.trade-card,.lower-grid article,.history,.today-card,.scalp-card,.bot-card,.analysis-section{border-radius:12px;box-shadow:0 14px 34px rgba(0,0,0,.18)}.signal{letter-spacing:0}.analysis-card{border-radius:9px;transition:border-color .2s,transform .2s}.analysis-card:hover{border-color:#75e6a2;transform:translateY(-2px)}.analysis-action{padding:5px 8px;border:1px solid currentColor;border-radius:999px}.trade-card{border-color:rgba(117,230,162,.28)}.price-panel{border-color:rgba(246,200,95,.24)}.history-row{border-radius:7px;padding:13px 10px}.signal-modal-panel{border-radius:14px}.plan-levels strong{color:#75e6a2}@media(max-width:800px){main{padding-left:12px;padding-right:12px}.panel-heading{flex-wrap:wrap}.chart-card{padding:14px}.js-plotly-plot .plotly .modebar{transform:scale(.82);transform-origin:top right}.analysis-section,.bot-card,.scalp-card,.today-card{padding:14px}.analysis-grid,.indicator-list{grid-template-columns:1fr}.analysis-values span{font-size:10px}.chart-guide span{font-size:10px}}';
  document.head.appendChild(polish);
  const scenarioStyle = document.createElement('style');
  scenarioStyle.textContent = '.scenario-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0 8px}.scenario-card{min-width:0;background:#0c151c;border:1px solid #24333e;border-left:3px solid #75e6a2;padding:12px}.scenario-card.sell{border-left-color:#ff6b6b}.scenario-card>div{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}.scenario-card strong{font:600 12px DM Mono,monospace;color:#e9f0f3}.scenario-card b{font:500 10px DM Mono,monospace;color:#75e6a2}.scenario-card.sell b{color:#ff8a8a}.scenario-card p{margin:9px 0 0;color:#b7c5ca;font-size:12px;line-height:1.5;overflow-wrap:anywhere}.scenario-note{display:block;color:#8496a1;font-size:11px;line-height:1.5}@media(max-width:600px){.scenario-grid{grid-template-columns:1fr}}';
  document.head.appendChild(scenarioStyle);
  const confluenceStyle = document.createElement('style');
  confluenceStyle.textContent = '.analysis-layers{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.confluence-chip{border:1px solid #34434d;padding:5px 7px;color:#aab7be;font:500 9px DM Mono,monospace}.confluence-chip.bullish{border-color:#75e6a2;color:#75e6a2}.confluence-chip.bearish{border-color:#ff6b6b;color:#ff8a8a}.confluence-chip.neutral{color:#aab7be}.analysis-action{white-space:normal;text-align:right}';
  document.head.appendChild(confluenceStyle);
  const chartLayout = document.createElement('style');
  chartLayout.textContent = '.content-grid.chart-only{grid-template-columns:minmax(0,1fr)}.content-grid.chart-only .chart-card{grid-column:1/-1}';
  document.head.appendChild(chartLayout);
}

addTodayTrend();
addResponsiveStyles();
addChartGuide();
removeTradePlan();
addFourHourContext();
addMarketSelector();
addScalpPanel();
addBotPanel();
addTimeframeAnalysis();
addTimeframeControls();
refresh();
setInterval(refresh, 3000);

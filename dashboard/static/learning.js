const byId = id => document.getElementById(id);
let course = null;
let selectedLesson = null;
let activeAttempt = null;
let chosenDecision = null;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text != null) element.textContent = text;
  return element;
}

function showMessage(message, isError = false) {
  const output = byId('learning-message');
  output.textContent = message;
  output.style.color = isError ? '#ff6b6b' : '#f6c85f';
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || 'Learning request failed');
  return body;
}

function renderGlossary(query = '') {
  const search = query.trim().toLowerCase();
  const results = byId('glossary-results');
  results.replaceChildren();
  const matches = (course?.glossary || []).filter(entry =>
    `${entry.term} ${entry.definition}`.toLowerCase().includes(search)
  );
  matches.forEach(entry => {
    const card = node('article', 'glossary-entry');
    card.append(node('strong', '', entry.term), node('p', '', entry.definition));
    results.append(card);
  });
  if (!matches.length) results.textContent = 'No glossary terms match that search.';
}

function renderLessons() {
  const list = byId('lesson-list');
  list.replaceChildren();
  const nav = node('div', 'lesson-nav-list');
  course.lessons.forEach((lesson, index) => {
    const button = node('button', 'lesson-nav-item');
    button.type = 'button';
    button.setAttribute('aria-current', lesson.id === selectedLesson ? 'step' : 'false');
    button.append(document.createTextNode(`${index + 1}. ${lesson.title}`));
    const progress = node('small', '', lesson.completed ? `DONE · ${lesson.completion_count}` : lesson.duration);
    button.append(progress);
    button.addEventListener('click', () => selectLesson(lesson.id));
    nav.append(button);
  });
  list.append(nav);
  byId('course-progress').textContent = `${course.completed_lessons} / ${course.total_lessons} LESSONS`;
}

function renderFeatureValues(features) {
  const container = byId('exercise-features');
  container.replaceChildren();
  const indicators = features.indicators || {};
  const readings = [
    ['1M STRUCTURE', features.structure_bias || 'UNCLEAR'],
    ['EMA 20', indicators.ema_20],
    ['EMA 50', indicators.ema_50],
    ['EMA 200', indicators.ema_200],
    ['RSI 14', indicators.rsi_14],
    ['ATR 14', indicators.atr_14],
    ['CANDLE PATTERN', (features.candle_patterns || []).join(', ') || 'None detected'],
    ['CLOSED BREAKOUT', `LONG ${features.breakout_buy ? 'YES' : 'NO'} · SHORT ${features.breakout_sell ? 'YES' : 'NO'}`],
  ];
  readings.forEach(([label, value]) => {
    const item = node('div');
    item.append(node('span', '', label));
    item.append(node('b', '', typeof value === 'number' ? value.toFixed(4) : String(value ?? 'Unavailable')));
    container.append(item);
  });
}

function renderCandles(candles, markerTimestamp, revealFromTimestamp = null) {
  if (!window.Plotly || !candles.length) return;
  const x = candles.map(candle => new Date(candle.timestamp * 1000).toISOString());
  const traces = [{
    type: 'candlestick',
    name: 'Historical 1-minute candles',
    x,
    open: candles.map(candle => candle.open),
    high: candles.map(candle => candle.high),
    low: candles.map(candle => candle.low),
    close: candles.map(candle => candle.close),
    increasing: {line: {color: '#75e6a2'}},
    decreasing: {line: {color: '#ff6b6b'}},
  }];
  const shapes = [{
    type: 'line',
    x0: new Date(markerTimestamp * 1000).toISOString(),
    x1: new Date(markerTimestamp * 1000).toISOString(),
    y0: 0,
    y1: 1,
    yref: 'paper',
    line: {color: '#f6c85f', dash: 'dot'},
  }];
  if (revealFromTimestamp != null) {
    shapes.push({
      type: 'line',
      x0: new Date(revealFromTimestamp * 1000).toISOString(),
      x1: new Date(revealFromTimestamp * 1000).toISOString(),
      y0: 0,
      y1: 1,
      yref: 'paper',
      line: {color: '#66c7f2', dash: 'dash'},
    });
  }
  Plotly.react('learning-chart', traces, {
    template: 'plotly_dark',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    margin: {l: 48, r: 18, t: 20, b: 42},
    xaxis: {rangeslider: {visible: false}, title: 'UTC · historical candle time'},
    yaxis: {title: 'Observed candle price'},
    shapes,
    showlegend: false,
  }, {responsive: true, displaylogo: false});
}

function renderExercise(exercise) {
  activeAttempt = exercise;
  chosenDecision = null;
  const content = byId('lesson-content');
  content.replaceChildren();
  content.append(node('div', 'label', exercise.source));
  content.append(node('h2', '', exercise.lesson.title));
  content.append(node('p', 'reason', exercise.lesson.objective));
  const lesson = node('div', 'learning-callout');
  lesson.append(node('strong', '', 'SHORT LESSON'));
  lesson.append(node('p', 'reason', exercise.lesson.lesson));
  content.append(lesson);
  content.append(node('p', 'muted', `Instrument: ${exercise.symbol} · Decision point: ${new Date(exercise.decision_timestamp * 1000).toLocaleString()} · Gold marker = decision candle`));
  const chart = node('div');
  chart.id = 'learning-chart';
  content.append(chart);
  content.append(node('p', 'reason', 'Only candles up to the marked decision point are visible. Inspect the chart and values before selecting your answer.'));
  const featureTitle = node('div', 'label', 'ACTUAL INDICATOR READINGS AT THE DECISION POINT');
  content.append(featureTitle);
  const features = node('div', 'learning-features');
  features.id = 'exercise-features';
  content.append(features);
  renderFeatureValues(exercise.features);
  content.append(node('p', 'muted', `SignalBot code reference: ${exercise.lesson.rule}`));

  const question = node('section', 'learning-evidence');
  question.append(node('h3', '', 'YOUR DECISION'));
  question.append(node('p', 'reason', exercise.lesson.question));
  const choices = node('div', 'learning-choices');
  ['LONG', 'SHORT', 'WAIT'].forEach(decision => {
    const button = node('button', 'learning-choice', decision);
    button.type = 'button';
    button.setAttribute('aria-pressed', 'false');
    button.addEventListener('click', () => {
      chosenDecision = decision;
      choices.querySelectorAll('button').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      submit.disabled = false;
    });
    choices.append(button);
  });
  question.append(choices);
  const submit = node('button', 'lesson-start', 'LOCK ANSWER & REVEAL NEXT CANDLES');
  submit.type = 'button';
  submit.disabled = true;
  submit.addEventListener('click', submitAnswer);
  question.append(submit);
  content.append(question);
  renderCandles(exercise.observed_candles, exercise.decision_timestamp);
  showMessage('Historical candle exercise. No orders are placed.');
}

function renderReview(review) {
  const content = byId('lesson-content');
  const panel = node('section', 'learning-review');
  panel.append(node('h3', '', 'DECISION REVIEW'));
  panel.append(node('p', 'reason', `Your choice: ${review.decision}. ${review.rule_process_note}`));
  panel.append(node('p', 'reason', review.subsequent_movement));
  const future = review.subsequent_candles || [];
  if (future.length) {
    const lastObservedTimestamp = activeAttempt.observed_candles.at(-1).timestamp;
    renderCandles(
      [...activeAttempt.observed_candles, ...future],
      activeAttempt.decision_timestamp,
      lastObservedTimestamp + 60,
    );
  }
  panel.append(node('p', 'reason', review.directional_candle_context === 'UNAVAILABLE'
    ? 'Following candle movement is unavailable in the saved data.'
    : `Following candle-close context: ${review.directional_candle_context}. This movement is review context, not a contract result.`));
  panel.append(node('h4', '', 'CONTRACT SETTLEMENT'));
  panel.append(node('p', 'reason', `${review.contract_result.outcome}: ${review.contract_result.note}`));
  panel.append(node('p', 'reason', review.learning_note));
  const nav = node('div', 'lesson-nav');
  const next = node('button', 'lesson-start', 'NEXT LESSON');
  next.type = 'button';
  next.addEventListener('click', () => {
    const index = course.lessons.findIndex(lesson => lesson.id === selectedLesson);
    selectLesson(course.lessons[(index + 1) % course.lessons.length].id);
  });
  const retry = node('button', 'lesson-start', 'TRY ANOTHER SNAPSHOT');
  retry.type = 'button';
  retry.addEventListener('click', startExercise);
  nav.append(next, retry);
  panel.append(nav);
  content.append(panel);
}

async function submitAnswer() {
  if (!activeAttempt || !chosenDecision) return;
  try {
    const result = await requestJson('/api/learning/answer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({attempt_id: activeAttempt.attempt_id, decision: chosenDecision}),
    });
    renderReview(result.review);
    course = await requestJson('/api/learning');
    renderLessons();
    showMessage('Review complete. The answer was judged against the visible rule context, not whether later candles happened to move your way.');
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function startExercise() {
  if (!selectedLesson) return;
  showMessage('Loading a historical exercise…');
  try {
    const exercise = await requestJson('/api/learning/attempt', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({lesson_id: selectedLesson}),
    });
    renderExercise(exercise);
  } catch (error) {
    showMessage(error.message, true);
  }
}

function selectLesson(lessonId) {
  selectedLesson = lessonId;
  renderLessons();
  const lesson = course.lessons.find(item => item.id === lessonId);
  const content = byId('lesson-content');
  content.replaceChildren();
  content.append(node('div', 'panel-heading', `LESSON · ${lesson.duration}`));
  content.append(node('h2', '', lesson.title));
  content.append(node('p', 'reason', lesson.objective));
  const callout = node('div', 'learning-callout');
  callout.append(node('p', 'reason', lesson.lesson));
  callout.append(node('p', 'muted', `SignalBot rule: ${lesson.rule}`));
  content.append(callout);
  const start = node('button', 'lesson-start', 'START HISTORICAL CHART EXERCISE');
  start.type = 'button';
  start.addEventListener('click', startExercise);
  content.append(start);
  activeAttempt = null;
  showMessage('Choose LONG, SHORT, or WAIT only after reviewing the chart and indicator snapshot.');
}

async function initializeCourse() {
  try {
    course = await requestJson('/api/learning');
    byId('course-policy').textContent = `${course.data_policy} Source: ${course.historical_candle_source}. Exact contract ticks available: ${course.raw_tick_history_available ? 'yes' : 'no'}.`;
    renderLessons();
    renderGlossary();
    if (course.lessons.length) selectLesson(course.lessons[0].id);
    byId('glossary-search').addEventListener('input', event => renderGlossary(event.target.value));
  } catch (error) {
    showMessage(error.message, true);
  }
}

document.addEventListener('DOMContentLoaded', initializeCourse);

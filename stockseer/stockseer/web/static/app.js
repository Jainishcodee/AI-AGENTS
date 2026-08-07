/* StockSeer dashboard front-end.
   Every panel posts to /api/jobs and polls until done, streaming the same console
   output the CLI prints -- so the UI can never quietly disagree with the terminal. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = { symbol: 'RELIANCE.NS', watchlist: [], chart: null, series: {} };

const fmtPct = (v, d = 2) => v == null || Number.isNaN(v) ? '—' : `${(v * 100).toFixed(d)}%`;
const fmtNum = (v, d = 2) => v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(d);
const fmtInr = v => v == null || Number.isNaN(v) ? '—' :
  '₹' + Math.round(v).toLocaleString('en-IN');
const cls = v => v == null ? '' : v > 0 ? 'pos' : v < 0 ? 'neg' : '';

/* ------------------------------------------------------------------ theme */
$('#themeToggle').onclick = () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('ss-theme', next);
  if (state.chart) applyChartTheme();
};
document.documentElement.dataset.theme = localStorage.getItem('ss-theme') || 'dark';

const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

/* -------------------------------------------------------------- navigation */
$$('.nav-btn').forEach(b => b.onclick = () => {
  $$('.nav-btn').forEach(x => x.classList.remove('active'));
  $$('.panel').forEach(x => x.classList.remove('active'));
  b.classList.add('active');
  $(`#panel-${b.dataset.panel}`).classList.add('active');
  if (b.dataset.panel === 'journal') loadJournal();
  if (b.dataset.panel === 'advisor') loadAdvisor();
  if (b.dataset.panel === 'chart' && state.chart) state.chart.timeScale().fitContent();
});

/* ------------------------------------------------------------------- chart */
function buildChart() {
  const el = $('#chart');
  el.innerHTML = '';
  state.chart = LightweightCharts.createChart(el, {
    layout: { background: { color: css('--surface') }, textColor: css('--muted'), fontSize: 11 },
    grid: { vertLines: { color: css('--grid') }, horzLines: { color: css('--grid') } },
    rightPriceScale: { borderColor: css('--line'), scaleMargins: { top: 0.08, bottom: 0.26 } },
    timeScale: { borderColor: css('--line'), timeVisible: true, secondsVisible: false },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: css('--muted'), labelBackgroundColor: css('--series-1') },
      horzLine: { color: css('--muted'), labelBackgroundColor: css('--series-1') },
    },
    autoSize: true,
  });

  state.series.candles = state.chart.addCandlestickSeries({
    upColor: css('--up'), downColor: css('--down'),
    borderUpColor: css('--up'), borderDownColor: css('--down'),
    wickUpColor: css('--up'), wickDownColor: css('--down'),
  });
  state.series.volume = state.chart.addHistogramSeries({
    priceFormat: { type: 'volume' }, priceScaleId: 'vol',
  });
  state.chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

  state.series.vwap = state.chart.addLineSeries(
    { color: css('--series-2'), lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
  state.series.ema9 = state.chart.addLineSeries(
    { color: css('--series-1'), lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
  state.series.ema21 = state.chart.addLineSeries(
    { color: css('--muted'), lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
}

function applyChartTheme() {
  state.chart.applyOptions({
    layout: { background: { color: css('--surface') }, textColor: css('--muted') },
    grid: { vertLines: { color: css('--grid') }, horzLines: { color: css('--grid') } },
  });
  state.series.candles.applyOptions({
    upColor: css('--up'), downColor: css('--down'),
    borderUpColor: css('--up'), borderDownColor: css('--down'),
    wickUpColor: css('--up'), wickDownColor: css('--down'),
  });
  state.series.vwap.applyOptions({ color: css('--series-2') });
  state.series.ema9.applyOptions({ color: css('--series-1') });
}

async function loadChart() {
  const interval = $('#chartInterval').value, days = $('#chartDays').value;
  $('#chartSymbol').textContent = state.symbol;
  $('#chartPrice').textContent = 'loading…';
  $('#chartChange').textContent = '';
  try {
    const d = await (await fetch(
      `/api/candles?symbol=${encodeURIComponent(state.symbol)}&interval=${interval}&days=${days}`
    )).json();
    if (d.error) throw new Error(d.error);
    if (!state.chart) buildChart();

    state.series.candles.setData(d.candles);
    state.series.volume.setData(d.volume);
    state.series.vwap.setData(d.vwap);
    state.series.ema9.setData(d.ema9);
    state.series.ema21.setData(d.ema21);
    state.series.candles.setMarkers(d.markers || []);
    state.chart.timeScale().fitContent();

    $('#chartPrice').textContent = fmtNum(d.last);
    const ch = $('#chartChange');
    ch.textContent = `${d.change_pct >= 0 ? '+' : ''}${fmtPct(d.change_pct)}`;
    ch.className = cls(d.change_pct);
    $('#chartLegend').innerHTML = (interval === '1d'
      ? [['--series-2', 'SMA 20'], ['--series-1', 'EMA 9'], ['--muted', 'EMA 50']]
      : [['--series-2', 'VWAP'], ['--series-1', 'EMA 9'], ['--muted', 'EMA 21']]
    ).map(([c, l]) =>
      `<span class="key"><span class="swatch" style="background:${css(c)}"></span>${l}</span>`
    ).join('') + (d.markers?.length
      ? `<span class="key" style="color:var(--muted)">${d.markers.length} signal(s) on chart</span>`
      : '');
  } catch (e) {
    $('#chartPrice').textContent = '—';
    $('#chartLegend').innerHTML = `<span class="err">${e.message}</span>`;
  }
}

$('#chartRefresh').onclick = loadChart;
$('#chartInterval').onchange = loadChart;
$('#chartDays').onchange = loadChart;

/* --------------------------------------------------------------- watchlist */
async function loadState() {
  const s = await (await fetch('/api/state')).json();
  state.watchlist = s.watchlist || [];
  $('#feedBadge').textContent = s.feed;
  if (/delayed/i.test(s.feed)) $('#feedBadge').classList.add('warn');
  renderWatchlist();
  loadTickerStrip();
}

function renderWatchlist() {
  $('#watchlist').innerHTML = state.watchlist.map(s => `
    <div class="wl-item" data-sym="${s}">
      <span>${s}</span><span class="rm" data-rm="${s}">×</span>
    </div>`).join('');
  $$('#watchlist .wl-item').forEach(el => el.onclick = ev => {
    if (ev.target.dataset.rm) {
      state.watchlist = state.watchlist.filter(x => x !== ev.target.dataset.rm);
      saveWatchlist(); return;
    }
    state.symbol = el.dataset.sym;
    $$('.nav-btn').forEach(x => x.classList.remove('active'));
    $$('.panel').forEach(x => x.classList.remove('active'));
    $('.nav-btn[data-panel="chart"]').classList.add('active');
    $('#panel-chart').classList.add('active');
    loadChart();
  });
}

async function saveWatchlist() {
  await fetch('/api/state', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ watchlist: state.watchlist }),
  });
  renderWatchlist(); loadTickerStrip();
}

$('#addSymbolForm').onsubmit = e => {
  e.preventDefault();
  const v = $('#addSymbolInput').value.trim().toUpperCase();
  if (v && !state.watchlist.includes(v)) { state.watchlist.push(v); saveWatchlist(); }
  $('#addSymbolInput').value = '';
};

async function loadTickerStrip() {
  const strip = $('#tickerStrip');
  strip.innerHTML = state.watchlist.map(s =>
    `<span class="tk" data-sym="${s}"><span class="sym">${s.replace('.NS', '')}</span>
     <span class="px" id="px-${CSS.escape(s)}">…</span></span>`).join('');
  $$('.tk', strip).forEach(el => el.onclick = () => {
    state.symbol = el.dataset.sym; loadChart();
  });
  for (const s of state.watchlist) {
    try {
      const d = await (await fetch(
        `/api/candles?symbol=${encodeURIComponent(s)}&interval=5m&days=2`)).json();
      const el = $(`#px-${CSS.escape(s)}`);
      if (el && !d.error) {
        el.textContent = `${fmtNum(d.last)} ${d.change_pct >= 0 ? '+' : ''}${fmtPct(d.change_pct, 1)}`;
        el.className = 'px ' + cls(d.change_pct);
      }
    } catch { /* a dead symbol should not break the strip */ }
  }
}

/* -------------------------------------------------------------- job runner */
function showConsole(title) {
  $('#console').hidden = false;
  $('#consoleTitle').textContent = title;
  $('#consoleBody').textContent = '';
}
$('#consoleClose').onclick = () => $('#console').hidden = true;

async function runJob(command, params, outEl, render) {
  const btn = outEl.closest('.panel').querySelector('button[type=submit], .btn.primary');
  if (btn) { btn.disabled = true; }
  outEl.innerHTML = `<div class="card"><span class="spinner"></span>running ${command}…</div>`;
  showConsole(command);

  try {
    const { job_id, error } = await (await fetch('/api/jobs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, params }),
    })).json();
    if (error) throw new Error(error);

    while (true) {
      await new Promise(r => setTimeout(r, 700));
      const j = await (await fetch(`/api/jobs/${job_id}`)).json();
      if (j.output) {
        const body = $('#consoleBody');
        body.textContent = j.output;
        body.parentElement.scrollTop = body.parentElement.scrollHeight;
      }
      if (j.status === 'error') throw new Error(j.error);
      if (j.status === 'done') { render(j.result, outEl); return j.result; }
    }
  } catch (e) {
    outEl.innerHTML = `<div class="err"><b>${command} failed:</b> ${e.message}</div>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

const formData = form => {
  const o = {};
  new FormData(form).forEach((v, k) => o[k] = v);
  $$('input[type=checkbox]', form).forEach(c => o[c.name] = c.checked);
  return o;
};

function bindForm(id, command, render) {
  const form = $(`#form-${id}`);
  if (!form) return;
  form.onsubmit = e => {
    e.preventDefault();
    runJob(command, formData(form), $(`#out-${id}`), render);
  };
}

/* ------------------------------------------------------------- renderers */
const tile = (k, v, n = '', c = '') =>
  `<div class="tile"><div class="k">${k}</div><div class="v ${c}">${v}</div>
   ${n ? `<div class="n">${n}</div>` : ''}</div>`;

function renderBacktest(r, el) {
  const m = r.metrics, s = r.strategy, st = s.strategy, bh = s.buy_and_hold;
  const isClf = m.accuracy != null;
  const edgeT = m.edge_t_stat;

  let html = `<div class="card"><h2>Predictive skill (out-of-sample)</h2><div class="tiles">`;
  if (isClf) {
    html += tile('Accuracy', fmtPct(m.accuracy), `baseline ${fmtPct(m.baseline_accuracy)}`);
    html += tile('Edge over baseline', fmtPct(m.edge_vs_baseline),
      `t = ${fmtNum(edgeT)}`, cls(m.edge_vs_baseline));
    html += tile('ROC AUC', fmtNum(m.auc, 4), '0.50 = coin flip');
    html += tile('Verdict', edgeT > 2 ? 'Real edge' : 'No edge',
      edgeT > 2 ? 'statistically distinguishable' : 't < 2, indistinguishable from luck',
      edgeT > 2 ? 'pos' : 'neg');
  } else {
    html += tile('Spearman IC', fmtNum(m.ic_spearman, 4));
    html += tile('OOS R²', fmtNum(m.r2_oos, 4), '< 0 = worse than the mean');
    html += tile('Direction accuracy', fmtPct(m.direction_accuracy));
  }
  html += `</div></div>`;

  if (r.control) {
    const leak = Math.abs((r.control.auc ?? 0.5) - 0.5) > 0.03;
    html += `<div class="card"><h2>Leakage control (labels shuffled)</h2><div class="tiles">
      ${tile('Control AUC', fmtNum(r.control.auc, 4), 'must be ~0.50')}
      ${tile('Verdict', leak ? 'LEAK' : 'Clean',
        leak ? 'numbers above are untrustworthy' : 'no detectable leakage',
        leak ? 'neg' : 'pos')}</div></div>`;
  }

  html += `<div class="card"><h2>Strategy vs buy &amp; hold (net of costs)</h2><div class="tiles">
    ${tile('Strategy return', fmtPct(st.total_return), `CAGR ${fmtPct(st.cagr)}`, cls(st.total_return))}
    ${tile('Buy &amp; hold', fmtPct(bh.total_return), `CAGR ${fmtPct(bh.cagr)}`, cls(bh.total_return))}
    ${tile('Sharpe', fmtNum(st.sharpe), `B&amp;H ${fmtNum(bh.sharpe)}`)}
    ${tile('Max drawdown', fmtPct(st.max_drawdown), `B&amp;H ${fmtPct(bh.max_drawdown)}`, 'neg')}
    ${tile('Excess CAGR', fmtPct(s.excess_cagr), 'vs buy &amp; hold', cls(s.excess_cagr))}
    ${tile('Ann. turnover', fmtNum(s.ann_turnover, 1) + '×',
      `cost drag ${fmtPct(s.total_cost_drag)}`)}
  </div></div>`;

  html += `<div class="card"><h2>Equity curve</h2>
    <div id="btEquity" style="height:300px"></div>
    <div class="legend" style="margin-top:8px">
      <span class="key"><span class="swatch" style="background:${css('--series-1')}"></span>Strategy</span>
      <span class="key"><span class="swatch" style="background:${css('--series-2')}"></span>Buy &amp; hold</span>
    </div></div>`;

  const imp = Object.entries(r.importance || {});
  if (imp.length) {
    const max = Math.max(...imp.map(([, v]) => v));
    html += `<div class="card"><h2>Feature importance</h2>` + imp.map(([k, v]) =>
      `<div class="bar-row"><span class="lbl">${k}</span>
       <span class="track"><span class="fill" style="width:${(v / max) * 100}%"></span></span>
       <span class="val">${fmtPct(v, 1)}</span></div>`).join('') + `</div>`;
  }
  el.innerHTML = html;

  if (r.equity?.length) {
    const c = LightweightCharts.createChart($('#btEquity'), {
      layout: { background: { color: css('--surface') }, textColor: css('--muted'), fontSize: 11 },
      grid: { vertLines: { color: css('--grid') }, horzLines: { color: css('--grid') } },
      rightPriceScale: { borderColor: css('--line') },
      timeScale: { borderColor: css('--line') },
      autoSize: true,
    });
    c.addLineSeries({ color: css('--series-1'), lineWidth: 2, title: 'Strategy' })
      .setData(r.equity.map(p => ({ time: p.time, value: p.strategy })));
    c.addLineSeries({ color: css('--series-2'), lineWidth: 2, title: 'Buy & hold' })
      .setData(r.equity.map(p => ({ time: p.time, value: p.market })));
    c.timeScale().fitContent();
  }
}

function renderSweep(r, el) {
  el.innerHTML = `<div class="card"><h2>Results</h2><div class="table-wrap"><table>
    <thead><tr><th>Symbol</th><th>Accuracy</th><th>Edge t</th><th>AUC</th>
    <th>Sharpe</th><th>B&amp;H</th><th>Excess CAGR</th></tr></thead><tbody>
    ${r.rows.map(x => `<tr><td>${x.ticker}</td><td>${fmtPct(x.accuracy)}</td>
      <td class="${(x.edge_t ?? 0) > 2 ? 'pos' : ''}">${fmtNum(x.edge_t)}</td>
      <td>${fmtNum(x.auc, 3)}</td><td>${fmtNum(x.sharpe)}</td><td>${fmtNum(x.bh_sharpe)}</td>
      <td class="${cls(x.excess_cagr)}">${fmtPct(x.excess_cagr)}</td></tr>`).join('')}
    </tbody></table></div>
    <p class="note"><b>${r.hits} of ${r.rows.length}</b> show t &gt; 2.
    Chance alone would give about <b>${fmtNum(r.expected_by_chance, 1)}</b>.
    If those numbers are close, you have found noise, not signal.</p></div>`;
}

function renderPredict(r, el) {
  const long = r.signal === 'LONG';
  el.innerHTML = `<div class="card"><div class="tiles">
    ${tile('Signal', r.signal, `${r.ticker} · next ${r.horizon_days}d`,
      r.signal === 'FLAT' ? '' : long ? 'pos' : 'neg')}
    ${tile('Score', fmtNum(r.score, 4), 'model probability')}
    ${tile('Last close', fmtNum(r.last_close), `as of ${r.as_of}`)}
    ${tile('Trained through', r.trained_through, `${r.stale_bars || 0} days stale`)}
  </div><p class="note">A signal is not a recommendation. Check the same symbol in
  <b>Backtest</b> — if its edge t-stat is below 2, this score carries no evidence.</p></div>`;
}

function renderInspect(r, el) {
  const max = Math.max(...r.ic.map(x => Math.abs(x.rho)));
  el.innerHTML = `<div class="card"><div class="tiles">
      ${tile('Rows', r.rows)} ${tile('Features', r.features)}
      ${tile('Up days', fmtPct(r.up_pct))}
      ${tile('Forward return', fmtPct(r.fwd_mean, 3), `sd ${fmtPct(r.fwd_sd, 2)}`)}
    </div></div>
    <div class="card"><h2>Correlation with the forward return</h2>
    ${r.ic.map(x => `<div class="bar-row"><span class="lbl">${x.feature}</span>
      <span class="track"><span class="fill" style="width:${(Math.abs(x.rho) / max) * 100}%;
      background:${x.rho > 0 ? css('--up') : css('--down')}"></span></span>
      <span class="val">${fmtNum(x.rho, 3)}</span></div>`).join('')}
    <p class="note">For daily equity data almost everything lands under |0.05|.
    That is normal — and it is why a single feature is never a strategy.</p></div>`;
}

function renderPlan(r, el) {
  const risky = r.p_ruin > r.p_hit_target;
  el.innerHTML = `<div class="card"><h2>Outcome over ${fmtNum(r.capital ? 500 : 500, 0)} trades,
    20,000 simulated paths</h2><div class="tiles">
    ${tile('Reach target', fmtPct(r.p_hit_target, 1),
      `${fmtInr(r.capital)} → +${fmtInr(r.target)}`, r.p_hit_target > 0.5 ? 'pos' : 'warn')}
    ${tile('Lose half the account', fmtPct(r.p_ruin, 1), 'ruin threshold', 'neg')}
    ${tile('Chance you have no edge', fmtPct(r.p_edge_negative, 1),
      `true win rate below ${fmtPct(r.breakeven_win_rate, 1)}`, 'warn')}
    ${tile('Median final capital', fmtInr(r.median_final),
      `5th pct ${fmtInr(r.p5_final)}`)}
    ${tile('Median max drawdown', fmtPct(r.median_max_drawdown, 1))}
    ${tile('Expectancy', fmtNum(r.expectancy_r, 3) + 'R',
      'per trade, net of costs', cls(r.expectancy_r))}
  </div></div>
  <div class="card"><h2>Costs and sizing</h2><div class="tiles">
    ${tile('Cost per trade', fmtInr(r.cost_per_trade_rs), `${fmtNum(r.cost_per_r, 3)}R of risk`)}
    ${tile('Break-even win rate', fmtPct(r.breakeven_win_rate, 1), 'below this you lose by arithmetic')}
    ${tile('Full Kelly', fmtPct(r.kelly, 1), `use ¼–½ → ${fmtPct(r.kelly / 4, 1)}–${fmtPct(r.kelly / 2, 1)}`)}
    ${tile('Real risk / trade', fmtPct(r.effective_risk_pct, 1),
      r.effective_risk_pct < r.requested_risk_pct
        ? `capped from ${fmtPct(r.requested_risk_pct, 1)} by buying power` : 'as requested',
      r.effective_risk_pct < r.requested_risk_pct ? 'warn' : '')}
    ${tile('Median costs paid', fmtInr(r.total_costs_median))}
    ${tile('Win rate range', `${fmtPct(r.win_rate_p5, 0)}–${fmtPct(r.win_rate_p95, 0)}`,
      'what your estimate actually supports')}
  </div>
  ${risky ? `<p class="note"><span class="pill bad">Warning</span>
    You are more likely to lose half the account than to reach the target.
    The goal is driving the risk, not the edge.</p>` : ''}
  </div>`;
}

function renderRules(r, el) {
  if (!r.rows?.length) { el.innerHTML = `<div class="empty">No rules scored.</div>`; return; }
  el.innerHTML = `<div class="card"><h2>Measured on real bars</h2><div class="table-wrap"><table>
    <thead><tr><th>Symbol</th><th>Rule</th><th>Signals</th><th>Hit %</th><th>Stop %</th>
    <th>Expectancy</th><th>Break-even</th><th>Verdict</th></tr></thead><tbody>
    ${r.rows.map(x => {
      const v = x.n_signals === 0 ? ['mid', 'never fired']
        : x.worth_trading ? ['good', 'TRADE']
        : x.n_signals < 30 ? ['mid', 'too few'] : ['bad', 'MUTE'];
      return `<tr><td>${x.symbol}</td><td>${x.rule}</td><td>${fmtNum(x.n_signals, 0)}</td>
        <td>${fmtPct(x.hit_rate, 1)}</td><td>${fmtPct(x.stop_rate, 1)}</td>
        <td class="${cls(x.expectancy_r)}">${fmtNum(x.expectancy_r, 3)}R</td>
        <td>${fmtPct(x.breakeven_win_rate, 1)}</td>
        <td><span class="pill ${v[0]}">${v[1]}</span></td></tr>`;
    }).join('')}</tbody></table></div>
    <p class="note">Only rules marked <b>TRADE</b> are allowed to fire alerts in Live Scan.
    Expectancy is profit per signal in units of risk, net of costs.</p></div>`;
}

function renderWatch(r, el) {
  if (!r.alerts?.length) {
    el.innerHTML = `<div class="card"><div class="empty">
      No signals on the latest completed bar.<br>
      <span style="font-size:12px">Rules that failed calibration are muted and cannot fire —
      see the Rule Scorecard.</span></div></div>`;
    return;
  }
  el.innerHTML = `<div class="card"><h2>${r.alerts.length} alert(s)</h2>
    <div class="results">${r.alerts.map(a =>
      `<div class="alert ${a.urgency === 'act' ? 'act' : ''}">${a.message}</div>`).join('')}
    </div></div>`;
}

function renderAdvisorScore(r, el) {
  const rows = Object.values(r.stats || {});
  if (!rows.length) {
    el.innerHTML = `<div class="card"><div class="empty">
      No calls logged yet. Add a few above, then score them.</div></div>`;
    loadAdvisor(); return;
  }
  el.innerHTML = `<div class="card"><h2>Scorecard vs random entry</h2><div class="table-wrap"><table>
    <thead><tr><th>Source</th><th>Calls</th><th>Hit %</th><th>Avg return</th>
    <th>Random baseline</th><th>Edge</th><th>Edge t</th><th>Verdict</th></tr></thead><tbody>
    ${rows.map(s => `<tr><td>${s.source}</td><td>${s.n_scored}</td>
      <td>${fmtPct(s.hit_rate, 1)}</td><td class="${cls(s.avg_pct)}">${fmtPct(s.avg_pct)}</td>
      <td>${fmtPct(s.baseline_avg_pct)}</td>
      <td class="${cls(s.edge_vs_baseline)}">${fmtPct(s.edge_vs_baseline)}</td>
      <td class="${(s.edge_t_stat ?? 0) > 2 ? 'pos' : ''}">${fmtNum(s.edge_t_stat)}</td>
      <td><span class="pill ${(s.edge_t_stat ?? 0) > 2 ? 'good' : 'mid'}">${s.verdict}</span></td>
      </tr>`).join('')}</tbody></table></div>
    <p class="note"><b>Random baseline</b> is what entering the same symbols on random dates
    over the same holding period returned. Beating it is the whole job — in a rising market,
    long calls make money with no skill at all.</p></div>`;
  loadAdvisor();
}

/* ------------------------------------------------------------ form binding */
bindForm('backtest', 'backtest', renderBacktest);
bindForm('sweep', 'sweep', renderSweep);
bindForm('predict', 'predict', renderPredict);
bindForm('inspect', 'inspect', renderInspect);
bindForm('plan', 'plan', renderPlan);
bindForm('rules', 'rules', renderRules);
bindForm('watch', 'watch', renderWatch);
$('#advisorScore').onclick = () =>
  runJob('advisor', {}, $('#out-advisor'), renderAdvisorScore);

/* ----------------------------------------------------------------- journal */
async function loadJournal() {
  const d = await (await fetch('/api/journal')).json();
  const s = d.stats, el = $('#out-journal');
  const be = 0.42;
  let html = '';

  if (s.n_closed > 0) {
    const verdict = s.win_rate_lo > be ? ['good', 'Evidence of a real edge']
      : s.win_rate_hi < be ? ['bad', 'Evidence of NO edge — change something']
      : ['mid', `Not yet an answer (${s.n_closed} trades)`];
    html += `<div class="card"><h2>Your measured performance</h2><div class="tiles">
      ${tile('Win rate', fmtPct(s.win_rate, 1), `${s.wins}W / ${s.losses}L`)}
      ${tile('95% interval', `${fmtPct(s.win_rate_lo, 0)}–${fmtPct(s.win_rate_hi, 0)}`,
        `break-even is ${fmtPct(be, 0)}`)}
      ${tile('Expectancy', fmtNum(s.expectancy_r, 3) + 'R', 'per trade', cls(s.expectancy_r))}
      ${tile('Total P&amp;L', fmtInr(s.total_pnl), `costs ${fmtInr(s.total_costs)}`, cls(s.total_pnl))}
      ${tile('Avg win / loss', `${fmtNum(s.avg_win_r)}R / ${fmtNum(s.avg_loss_r)}R`)}
      ${tile('Worst streak', `${s.max_consecutive_losses} losses`, 'consecutive')}
    </div><p class="note"><span class="pill ${verdict[0]}">${verdict[1]}</span></p></div>`;
  }

  html += `<div class="card"><h2>Trades (${d.trades.length})</h2>`;
  html += d.trades.length ? `<div class="table-wrap"><table>
    <thead><tr><th>ID</th><th>Symbol</th><th>Source</th><th>Entry</th><th>Stop</th>
    <th>Target</th><th>Qty</th><th>Exit</th><th>P&amp;L</th><th>R</th><th></th></tr></thead><tbody>
    ${d.trades.map(t => `<tr><td>${t.id}</td><td>${t.symbol}</td><td>${t.rule}</td>
      <td>${fmtNum(t.entry)}</td><td>${fmtNum(t.stop)}</td><td>${fmtNum(t.target)}</td>
      <td>${t.qty}</td><td>${t.exit == null ? '—' : fmtNum(t.exit)}</td>
      <td class="${cls(t.pnl)}">${t.is_open ? '—' : fmtInr(t.pnl)}</td>
      <td class="${cls(t.r_multiple)}">${t.is_open ? '—' : fmtNum(t.r_multiple) + 'R'}</td>
      <td>${t.is_open
        ? `<button class="btn" data-close="${t.id}">Close</button>`
        : `<span class="pill ${t.pnl > 0 ? 'good' : 'bad'}">${t.exit_reason || ''}</span>`}</td>
      </tr>`).join('')}</tbody></table></div>`
    : `<div class="empty">No trades yet. Log one above — costs are charged even on paper.</div>`;
  html += `</div>`;
  el.innerHTML = html;

  $$('[data-close]').forEach(b => b.onclick = async () => {
    const px = prompt('Exit price?');
    if (!px) return;
    await fetch('/api/journal/close', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: b.dataset.close, exit: parseFloat(px), reason: 'manual' }),
    });
    loadJournal();
  });
}

$('#form-journal-open').onsubmit = async e => {
  e.preventDefault();
  const b = formData(e.target);
  const res = await fetch('/api/journal/open', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b),
  });
  if (res.ok) { e.target.reset(); loadJournal(); }
};
$('#journalRefresh').onclick = loadJournal;

/* ----------------------------------------------------------------- advisor */
async function loadAdvisor() {
  const d = await (await fetch('/api/advisor/calls')).json();
  const host = $('#out-advisor');
  const existing = host.querySelector('.card')?.outerHTML.includes('Scorecard')
    ? host.querySelector('.card').outerHTML : '';
  host.innerHTML = existing + `<div class="card">
    <h2>Logged calls (${d.n} from ${d.sources.length} source(s))</h2>
    ${d.calls.length ? `<div class="table-wrap"><table>
      <thead><tr><th>ID</th><th>Source</th><th>Symbol</th><th>Side</th>
      <th>Published</th><th>Target</th><th>Stop</th><th>Hold</th></tr></thead><tbody>
      ${d.calls.slice(0, 60).map(c => `<tr><td>${c.id}</td><td>${c.source}</td>
        <td>${c.symbol}</td><td>${c.side}</td><td>${(c.published_at || '').slice(0, 10)}</td>
        <td>${c.target == null ? '—' : fmtNum(c.target)}</td>
        <td>${c.stop == null ? '—' : fmtNum(c.stop)}</td><td>${c.horizon_days}d</td></tr>`).join('')}
      </tbody></table></div>`
      : `<div class="empty">No calls logged. Add one above, or bulk-import a CSV
         with <code>stockseer advisor import --csv their_calls.csv</code>.</div>`}
    </div>`;
}

$('#form-advisor-add').onsubmit = async e => {
  e.preventDefault();
  const b = formData(e.target);
  ['entry', 'stop', 'target'].forEach(k => b[k] = b[k] ? parseFloat(b[k]) : null);
  const res = await fetch('/api/advisor/add', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b),
  });
  if (res.ok) { e.target.reset(); loadAdvisor(); }
};

/* -------------------------------------------------------------------- boot */
loadState().then(loadChart);

const SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"];
const TFS = ["1m", "5m", "15m", "1H"];
let chartSym = "BTCUSDT", chartTf = "15m", capital = 50;
let btData = null, sortKey = "return_pct", sortDir = -1, selScenario = null;
const dec = (s) => s >= 100 ? 2 : 4;
const fmt = (n, d = 2) => Number(n).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

/* ---------------- clock + status ---------------- */
setInterval(() => {
  document.getElementById("clock").textContent = new Date().toUTCString().slice(17, 25) + " UTC";
}, 1000);
function setConn(ok) {
  document.getElementById("dot").className = "dot " + (ok ? "on" : "off");
  document.getElementById("conn").textContent = ok ? "en vivo" : "sin conexión";
}

/* ---------------- live tickers ---------------- */
const lastPx = {};
function renderTickers(data) {
  const el = document.getElementById("tickers");
  el.innerHTML = SYMBOLS.map(s => {
    const t = data[s];
    if (!t) return `<div class="tk"><div class="sym">${s}</div><div class="price">…</div></div>`;
    const d = dec(t.last), up = t.chg24h >= 0;
    const prev = lastPx[s]; let fl = "";
    if (prev != null) fl = t.last > prev ? "flash-up" : (t.last < prev ? "flash-down" : "");
    lastPx[s] = t.last;
    return `<div class="tk">
      <div class="sym">${s} · perp</div>
      <div class="price ${fl}">${fmt(t.last, d)}</div>
      <div class="row"><span class="chg ${up ? "up" : "down"}">${up ? "▲" : "▼"} ${fmt(t.chg24h, 2)}% 24h</span>
        <span>funding ${fmt(t.funding, 4)}%</span></div>
      <div class="row"><span>bid ${fmt(t.bid, d)}</span><span>ask ${fmt(t.ask, d)}</span></div>
    </div>`;
  }).join("");
}
async function pollTicker() {
  try {
    const r = await fetch("/api/ticker"); const j = await r.json();
    const any = SYMBOLS.some(s => j[s]); setConn(any); renderTickers(j);
  } catch (e) { setConn(false); }
}
setInterval(pollTicker, 1500); pollTicker();

/* ---------------- realtime chart ---------------- */
let chart, candle, e9, e21, e200;
function initChart() {
  const el = document.getElementById("chart");
  chart = LightweightCharts.createChart(el, {
    layout: { background: { color: "transparent" }, textColor: "#8a93a8" },
    grid: { vertLines: { color: "#1b2233" }, horzLines: { color: "#1b2233" } },
    timeScale: { timeVisible: true, borderColor: "#263049" },
    rightPriceScale: { borderColor: "#263049" },
    crosshair: { mode: 0 },
    width: el.clientWidth, height: 380,
  });
  candle = chart.addCandlestickSeries({ upColor: "#16c784", downColor: "#ea3943", borderVisible: false, wickUpColor: "#16c784", wickDownColor: "#ea3943" });
  e9 = chart.addLineSeries({ color: "#f5a623", lineWidth: 1 });
  e21 = chart.addLineSeries({ color: "#4f8cff", lineWidth: 1 });
  e200 = chart.addLineSeries({ color: "#a06bff", lineWidth: 1 });
  new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth })).observe(el);
}
function ema(vals, n) {
  const k = 2 / (n + 1); let prev = vals[0]; const out = [];
  vals.forEach((v, i) => { prev = i ? v * k + prev * (1 - k) : v; out.push(prev); });
  return out;
}
let _chartKey = "";
async function loadChart() {
  try {
    const r = await fetch(`/api/candles?symbol=${chartSym}&tf=${chartTf}&limit=300`);
    const d = await r.json();
    if (!Array.isArray(d) || !d.length) return;
    candle.setData(d);
    const closes = d.map(x => x.close), t = d.map(x => x.time);
    const mk = (n) => ema(closes, n).map((v, i) => ({ time: t[i], value: v }));
    e9.setData(mk(9)); e21.setData(mk(21)); e200.setData(mk(200));
    // al cambiar de símbolo/temporalidad: recentrar escala de precio y tiempo
    const key = chartSym + "_" + chartTf;
    if (key !== _chartKey) {
      _chartKey = key;
      chart.priceScale("right").applyOptions({ autoScale: true });
      chart.timeScale().fitContent();
    }
  } catch (e) {}
}
function buildChartControls() {
  const sel = document.getElementById("chartSymbol");
  sel.innerHTML = SYMBOLS.map(s => `<option>${s}</option>`).join("");
  sel.value = chartSym;
  sel.onchange = () => { chartSym = sel.value; loadChart(); };
  const g = document.getElementById("tfGroup");
  g.innerHTML = TFS.map(tf => `<button data-tf="${tf}" class="${tf === chartTf ? "active" : ""}">${tf}</button>`).join("");
  g.querySelectorAll("button").forEach(b => b.onclick = () => {
    chartTf = b.dataset.tf; g.querySelectorAll("button").forEach(x => x.classList.remove("active"));
    b.classList.add("active"); loadChart();
  });
}

/* ---------------- live analysis ---------------- */
async function pollAnalysis() {
  try {
    const r = await fetch("/api/analysis"); const j = await r.json();
    const el = document.getElementById("analysis");
    el.innerHTML = SYMBOLS.map(s => {
      const a = j[s]; if (!a) return `<div class="an">${s}: cargando…</div>`;
      const sigs = Object.entries(a.signals).map(([k, v]) =>
        `<span class="sig ${v}">${k}: ${v}</span>`).join("");
      return `<div class="an">
        <div class="top"><span class="name">${s}</span>
          <span class="badge ${a.trend}">tendencia ${a.trend}</span></div>
        <div class="metrics"><span>precio <b>${fmt(a.price, dec(a.price))}</b></span>
          <span>RSI <b>${a.rsi}</b></span><span>ATR <b>${a.atr_pct}%</b></span>
          <span>MACD <b>${a.macd_hist}</b></span></div>
        <div class="sigs">${sigs}</div></div>`;
    }).join("");
  } catch (e) {}
}
setInterval(pollAnalysis, 5000);

/* ---------------- AI reasoning ---------------- */
const DIRLABEL = { long: "▲ LONG", short: "▼ SHORT", none: "— FUERA" };
async function pollAI() {
  try {
    const r = await fetch("/api/ai"); const j = await r.json();
    const tag = document.getElementById("aiEngine");
    if (j.engine_mode === "claude") { tag.textContent = "panel gratis · Opus solo con el botón"; tag.className = "engine-tag claude"; }
    else { tag.textContent = "motor de confluencia (sin API key)"; tag.className = "engine-tag"; }
    renderAI(j.symbols);
  } catch (e) {}
}
function renderAI(symbols) {
  const el = document.getElementById("aiPanel");
  let latest = 0;
  el.innerHTML = SYMBOLS.map(s => {
    const o = symbols[s];
    if (!o || !o.decision) return `<div class="ai-card none"><div class="ai-sym">${s}</div><div class="hint">analizando…</div></div>`;
    const d = o.decision, dir = d.direction || "none";
    if (o.updated) latest = Math.max(latest, new Date(o.updated).getTime());
    const conf = Math.round((d.confidence || 0) * 100);
    const dd = dec(d.entry || 0);
    const lvl = (k, v, cls) => `<div class="lvl"><div class="lk">${k}</div><div class="lv ${cls}">${v != null ? fmt(v, dd) : "—"}</div></div>`;
    const factors = (d.key_factors || d.strategies_agreeing || []).slice(0, 6)
      .map(f => `<span class="f">${f}</span>`).join("");
    return `<div class="ai-card ${dir}">
      <div class="ai-top"><span class="ai-sym">${s}</span>
        <span class="ai-dir ${dir}">${DIRLABEL[dir] || dir}</span></div>
      <div class="ai-meta">confianza ${conf}%${d.leverage_suggested ? " · apal. " + d.leverage_suggested + "x" : ""}${d.timeframe ? " · " + d.timeframe : ""}</div>
      <div class="conf-bar"><div class="conf-fill" style="width:${conf}%"></div></div>
      <div class="ai-levels">${lvl("Entrada", d.entry, "entry")}${lvl("Stop", d.stop, "sl")}${lvl("Objetivo", d.take_profit, "tp")}</div>
      <div class="ai-factors">${factors}</div>
      <div class="ai-reason">${d.reasoning || ""}</div>
      <div class="ai-foot">
        <span class="ai-meta">score confluencia: ${o.snapshot ? o.snapshot.confluence_score : "?"}</span>
        <button class="ai-btn" data-sym="${s}">analizar ahora</button>
      </div></div>`;
  }).join("");
  el.querySelectorAll(".ai-btn").forEach(b => b.onclick = async () => {
    b.disabled = true; b.textContent = "analizando…";
    try { await fetch("/api/ai/" + b.dataset.sym); await pollAI(); } catch (e) {}
  });
  if (latest) document.getElementById("aiUpdated").textContent = "actualizado " + new Date(latest).toLocaleTimeString();
}
setInterval(pollAI, 10000);

/* ---------------- AI cost dashboard ---------------- */
let costChart, costSeries;
function initCost() {
  const el = document.getElementById("costChart");
  costChart = LightweightCharts.createChart(el, {
    layout: { background: { color: "transparent" }, textColor: "#8a93a8" },
    grid: { vertLines: { color: "#1b2233" }, horzLines: { color: "#1b2233" } },
    timeScale: { timeVisible: true, borderColor: "#263049" },
    rightPriceScale: { borderColor: "#263049" },
    width: el.clientWidth, height: 260,
  });
  costSeries = costChart.addAreaSeries({ lineColor: "#16c784", topColor: "rgba(22,199,132,.4)", bottomColor: "rgba(22,199,132,0)", lineWidth: 2 });
  new ResizeObserver(() => costChart.applyOptions({ width: el.clientWidth })).observe(el);
}
async function pollCost() {
  try {
    const c = await fetch("/api/cost").then(r => r.json());
    document.getElementById("costSummary").innerHTML =
      `<span class="ps">hoy <b>$${fmt(c.today, 4)}</b></span>
       <span class="ps">total <b>$${fmt(c.total, 4)}</b></span>
       <span class="ps">consultas <b>${c.n_calls}</b></span>`;
    const order = Object.entries(c.per_model || {});
    document.getElementById("costModels").innerHTML = order.length ? order.map(([k, v]) => {
      const cls = k.includes("Opus") ? "opus" : (k.includes("Haiku") ? "haiku" : "");
      return `<div class="cm ${cls}"><div><div class="cmn">${k}</div>
        <div class="cmd">${v.calls} consultas · ${(v.tokens / 1000).toFixed(1)}k tokens</div></div>
        <div class="cmc">$${fmt(v.cost, 4)}</div></div>`;
    }).join("") : `<div class="empty">Aún no se ha usado la IA de pago. El vigilante gratis está activo.</div>`;
    // tabla últimas llamadas
    document.querySelector("#costTable thead").innerHTML =
      "<tr><th>Hora</th><th>Modelo</th><th>Tokens</th><th>Costo$</th></tr>";
    document.querySelector("#costTable tbody").innerHTML = (c.recent || []).length
      ? c.recent.map(r => `<tr><td>${new Date(r.ts).toLocaleTimeString()}</td>
          <td>${r.model.includes("opus") ? "Opus" : (r.model.includes("haiku") ? "Haiku" : r.model)}</td>
          <td>${r.in + r.out}</td><td>$${fmt(r.cost, 5)}</td></tr>`).join("")
      : `<tr><td colspan="4" class="empty">Sin llamadas todavía.</td></tr>`;
    // gráfica acumulada
    if (costSeries && c.series) {
      let lastT = 0; const data = [];
      c.series.forEach(p => { let t = Math.floor(new Date(p.ts).getTime() / 1000); if (t <= lastT) t = lastT + 1; lastT = t; data.push({ time: t, value: p.cum }); });
      costSeries.setData(data); if (data.length) costChart.timeScale().fitContent();
    }
  } catch (e) {}
}
setInterval(pollCost, 8000);

/* ---------------- paper trading ---------------- */
async function pollPaper() {
  try {
    const p = await fetch("/api/paper").then(r => r.json());
    const rc = p.return_pct >= 0 ? "pos" : "neg";
    document.getElementById("paperSummary").innerHTML =
      `<span class="ps">capital <b class="${rc}">$${fmt(p.equity, 2)}</b></span>
       <span class="ps">resultado <b class="${rc}">${p.return_pct >= 0 ? "+" : ""}${p.return_pct}%</b></span>
       <span class="ps">abiertas <b>${p.n_open}</b></span>
       <span class="ps">cerradas <b>${p.n_closed}</b></span>
       <span class="ps">aciertos <b>${p.win_rate}%</b></span>`;
    // posiciones abiertas
    const open = Object.values(p.open || {});
    document.getElementById("paperOpen").innerHTML = open.length ? open.map(o => {
      const d = dec(o.entry);
      return `<div class="pos ${o.direction}">
        <div class="pt"><span>${o.direction === "long" ? "▲ LONG" : "▼ SHORT"} ${o.symbol}</span><span>${o.leverage}x</span></div>
        <div class="pl">entrada ${fmt(o.entry, d)} · stop ${fmt(o.stop, d)} · objetivo ${fmt(o.tp, d)}</div>
      </div>`;
    }).join("") : `<div class="empty">Sin posiciones abiertas. El vigilante está escaneando…</div>`;
    // historial
    const tb = document.querySelector("#paperHist tbody");
    document.querySelector("#paperHist thead").innerHTML =
      "<tr><th>Símbolo</th><th>Dir</th><th>Motivo</th><th>PnL$</th><th>Capital</th></tr>";
    const h = (p.history || []).slice().reverse();
    tb.innerHTML = h.length ? h.map(t => {
      const rc2 = t.pnl >= 0 ? "pos" : "neg";
      return `<tr><td>${t.symbol}</td><td>${t.direction}</td><td>${t.reason}</td>
        <td class="${rc2}">${t.pnl >= 0 ? "+" : ""}${fmt(t.pnl, 2)}</td><td>${fmt(t.equity_after, 2)}</td></tr>`;
    }).join("") : `<tr><td colspan="5" class="empty">Aún no hay operaciones cerradas.</td></tr>`;
    // alertas
    const a = (p.alerts || []).slice().reverse();
    document.getElementById("paperAlerts").innerHTML = a.length ? a.map(x =>
      `<div class="alert ${x.kind}"><div class="at">${new Date(x.ts).toLocaleString()}</div>${x.msg}</div>`).join("")
      : `<div class="empty">Sin alertas todavía. Aparecerán aquí (y en tu Telegram si lo configuras).</div>`;
  } catch (e) {}
}
setInterval(pollPaper, 5000);

/* ---------------- backtest ---------------- */
const COLS = [
  ["strategy", "Estrategia", 0], ["symbol", "Símbolo", 0], ["tf", "TF", 0], ["maker", "Orden", 0],
  ["trades", "Ops", 1], ["freq_week", "Ops/sem", 1], ["win_rate", "Win%", 1],
  ["profit_factor", "PF", 1], ["fees_pct", "Comis%", 1], ["max_dd_pct", "MaxDD%", 1],
  ["return_pct", "Retorno%", 1], ["net", "Neto$", 1],
];
async function loadBacktest() {
  try {
    const r = await fetch("/api/backtest");
    if (!r.ok) { document.getElementById("btMeta").textContent = "Aún no hay resultados: corre  python scenarios.py"; return; }
    btData = await r.json();
    renderMeta(); renderSummary(); renderTable(); renderNotes();
    const best = sortedScenarios()[0]; if (best) selectScenario(best.id);
  } catch (e) {}
}
function netOf(s) { return capital === 50 ? s.net_50 : s.net_100; }
function sortedScenarios() {
  const arr = [...btData.scenarios];
  arr.sort((a, b) => {
    const va = sortKey === "net" ? netOf(a) : a[sortKey];
    const vb = sortKey === "net" ? netOf(b) : b[sortKey];
    if (typeof va === "string") return sortDir * va.localeCompare(vb);
    return sortDir * (va - vb);
  });
  return arr;
}
function renderMeta() {
  const m = btData;
  document.getElementById("btMeta").innerHTML =
    `Periodo: <b>${m.period.from.slice(0, 16)}</b> → <b>${m.period.to.slice(0, 16)}</b> ·
     ${m.n_scenarios} escenarios · comisiones reales (maker ${(m.fees.maker * 100).toFixed(2)}% / taker ${(m.fees.taker * 100).toFixed(2)}%) ·
     riesgo ${(m.risk_per_trade_pct * 100)}%/op · apalancamiento máx ${m.max_leverage}x`;
}
function renderSummary() {
  const arr = sortedByReturn();
  const best = arr[0];
  const bestPF = [...arr].sort((a, b) => b.profit_factor - a.profit_factor)[0];
  const lowf = arr.filter(s => s.freq_week <= 15 && s.return_pct > 0)[0];
  const profitable = arr.filter(s => s.return_pct > 0).length;
  const card = (k, v, d, cls = "") => `<div class="sm"><div class="k">${k}</div><div class="v ${cls}">${v}</div><div class="d">${d}</div></div>`;
  document.getElementById("summary").innerHTML =
    card("Mejor retorno semanal", `<span class="${best.return_pct >= 0 ? "pos" : "neg"}">${best.return_pct >= 0 ? "+" : ""}${best.return_pct}%</span>`,
      `${best.strategy} · ${best.symbol} ${best.tf} · ${netcur(best)}`) +
    card("Más robusta (PF)", bestPF.profit_factor.toFixed(2),
      `${bestPF.strategy} · ${bestPF.symbol} ${bestPF.tf} · ${bestPF.return_pct >= 0 ? "+" : ""}${bestPF.return_pct}%`) +
    card("Mejor baja frecuencia", lowf ? `<span class="pos">+${lowf.return_pct}%</span>` : "—",
      lowf ? `${lowf.strategy} · ${lowf.symbol} ${lowf.tf} · ${lowf.freq_week} ops/sem` : "ninguna") +
    card("Escenarios rentables", `${profitable} / ${arr.length}`, "con todos los costos incluidos");
}
function netcur(s) { return (netOf(s) >= 0 ? "+$" : "-$") + Math.abs(netOf(s)).toFixed(2); }
function sortedByReturn() { return [...btData.scenarios].sort((a, b) => b.return_pct - a.return_pct); }

function renderTable() {
  const thead = document.querySelector("#scenTable thead");
  thead.innerHTML = "<tr>" + COLS.map(c =>
    `<th data-k="${c[0]}" class="${c[0] === sortKey ? "sorted" : ""}">${c[1]}</th>`).join("") + "</tr>";
  thead.querySelectorAll("th").forEach(th => th.onclick = () => {
    const k = th.dataset.k; if (k === sortKey) sortDir *= -1; else { sortKey = k; sortDir = -1; }
    renderTable();
  });
  const tb = document.querySelector("#scenTable tbody");
  tb.innerHTML = sortedScenarios().map(s => {
    const rc = s.return_pct >= 0 ? "pos" : "neg";
    return `<tr data-id="${s.id}" class="${s.id === selScenario ? "sel" : ""}">
      <td>${s.strategy}</td><td>${s.symbol}</td><td>${s.tf}</td>
      <td class="${s.maker ? "mk" : "tk2"}">${s.maker ? "límite" : "mercado"}</td>
      <td>${s.trades}</td><td>${s.freq_week}</td><td>${s.win_rate}</td>
      <td>${s.profit_factor}</td><td>${s.fees_pct}</td><td>${s.max_dd_pct}</td>
      <td class="${rc}">${s.return_pct >= 0 ? "+" : ""}${s.return_pct}</td>
      <td class="${rc}">${netcur(s)}</td></tr>`;
  }).join("");
  tb.querySelectorAll("tr").forEach(tr => tr.onclick = () => selectScenario(tr.dataset.id));
}

/* equity curve */
let eqChart, eqSeries;
function initEquity() {
  const el = document.getElementById("equity");
  eqChart = LightweightCharts.createChart(el, {
    layout: { background: { color: "transparent" }, textColor: "#8a93a8" },
    grid: { vertLines: { color: "#1b2233" }, horzLines: { color: "#1b2233" } },
    timeScale: { timeVisible: true, borderColor: "#263049" },
    rightPriceScale: { borderColor: "#263049" },
    width: el.clientWidth, height: 300,
  });
  eqSeries = eqChart.addAreaSeries({ lineColor: "#4f8cff", topColor: "rgba(79,140,255,.4)", bottomColor: "rgba(79,140,255,0)", lineWidth: 2 });
  new ResizeObserver(() => eqChart.applyOptions({ width: el.clientWidth })).observe(el);
}
function selectScenario(id) {
  selScenario = id;
  document.querySelectorAll("#scenTable tbody tr").forEach(tr =>
    tr.classList.toggle("sel", tr.dataset.id === id));
  const s = btData.scenarios.find(x => x.id === id);
  const curve = btData.equity_curves[id];
  document.getElementById("curveName").textContent =
    s ? `${s.strategy} · ${s.symbol} ${s.tf} · ${s.maker ? "límite" : "mercado"}` : id;
  if (!curve) { eqSeries.setData([]); return; }
  const scale = capital / 50;            // las curvas se guardaron a base $50
  let lastT = 0; const data = [];
  curve.forEach(([iso, eq]) => {
    let t = Math.floor(new Date(iso).getTime() / 1000);
    if (t <= lastT) t = lastT + 1; lastT = t;
    data.push({ time: t, value: +(eq * scale).toFixed(2) });
  });
  eqSeries.setData(data);
  eqChart.timeScale().fitContent();
}
function renderNotes() {
  document.getElementById("notes").innerHTML =
    `<b>Lecturas honestas del backtest:</b><br>
     • <b>El capital ($50 vs $100) NO cambia la rentabilidad %</b> — con sizing por % de riesgo todo escala lineal; $100 solo duplica el resultado en dólares, no crea ventaja.<br>
     • La <b>alta frecuencia pura</b> (1m/5m a mercado) pierde por comisiones; con <b>órdenes límite (maker)</b> mejora mucho y algunas medias frecuencias (15m) se vuelven rentables.<br>
     • Lo más <b>robusto</b> es baja/media frecuencia con tendencia (Donchian/MACD en 1H, PF&gt;2).<br>
     • Esto es <b>una sola semana</b> y un solo régimen de mercado: un resultado positivo aquí <b>no garantiza</b> el futuro. Hay que validar en más semanas y en modo papel antes de dinero real.`;
}

/* ---------------- capital toggle ---------------- */
document.getElementById("capGroup").querySelectorAll("button").forEach(b => b.onclick = () => {
  capital = +b.dataset.cap;
  document.getElementById("capGroup").querySelectorAll("button").forEach(x => x.classList.remove("active"));
  b.classList.add("active");
  if (btData) { renderSummary(); renderTable(); if (selScenario) selectScenario(selScenario); }
});

/* ---------------- boot ---------------- */
window.addEventListener("load", () => {
  initChart(); initEquity(); initCost(); buildChartControls(); loadChart();
  pollAnalysis(); pollAI(); pollPaper(); pollCost(); loadBacktest();
  setInterval(loadChart, 6000);
});

"""
Portal web del bot Bitget.
- Sirve el frontend (web/)
- /api/backtest  -> resultados del backtesting (results/backtest_results.json)
- /api/candles   -> velas en tiempo (casi) real (proxy a Bitget, datos publicos)
- /api/ticker    -> precios en vivo (WebSocket Bitget)
- /api/analysis  -> analisis en vivo: senal actual de cada estrategia + indicadores

Uso:
    python server.py            # http://127.0.0.1:5000
Nada de esto necesita API key (solo datos publicos).
"""
import os
import json
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import config
from indicators import add_indicators
from strategies import STRATEGIES, base_params
from live_monitor import BitgetLiveMonitor
import ai_analyst
from mtf import build_snapshot, ensemble_decision
from paper_trader import book
import notify
from data import fetch_recent

BASE = "https://api.bitget.com"
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
RESULTS = os.path.join(os.path.dirname(__file__), "results", "backtest_results.json")
WATCH = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

app = Flask(__name__, static_folder=None)
CORS(app)


# Serializador JSON tolerante a tipos de numpy (evita errores 500 en la VPS)
from flask.json.provider import DefaultJSONProvider
import numpy as _np


class _NpJSON(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, _np.integer):
            return int(o)
        if isinstance(o, _np.floating):
            return float(o)
        if isinstance(o, _np.ndarray):
            return o.tolist()
        try:
            return super().default(o)
        except TypeError:
            return str(o)


app.json = _NpJSON(app)

# -------- estado en vivo --------
monitor = BitgetLiveMonitor(WATCH)
analysis_state = {}          # symbol -> {tf -> {signals, indicators}}
analysis_lock = threading.Lock()
ai_state = {}                # symbol -> {snapshot, decision, engine, updated}
ai_lock = threading.Lock()


def _fetch_recent_candles(symbol, tf, limit=300):
    url = (f"{BASE}/api/v2/mix/market/candles?symbol={symbol}"
           f"&granularity={tf}&productType={config.PRODUCT_TYPE}&limit={limit}")
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json().get("data", [])


def _to_df(rows):
    import pandas as pd
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "quote_vol"])
    for c in ["ts", "open", "high", "low", "close", "vol", "quote_vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().sort_values("ts").reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df


def _analysis_worker():
    """Cada ~12s recalcula indicadores y la senal actual de cada estrategia."""
    tf = "15m"
    while True:
        for sym in WATCH:
            try:
                rows = _fetch_recent_candles(sym, tf, 300)
                df = _to_df(rows)
                p = base_params()
                df = add_indicators(df, p)
                last = df.iloc[-1]
                sigs = {}
                for sname, (func, ov) in STRATEGIES.items():
                    pp = base_params(); pp.update(ov)
                    sdf = func(df.copy(), pp)
                    sigs[sname] = sdf["signal"].iloc[-1] or "flat"
                trend = "alcista" if last["close"] > last["ema_trend"] else "bajista"
                info = {
                    "price": float(last["close"]),
                    "trend": trend,
                    "rsi": round(float(last["rsi"]), 1),
                    "atr_pct": round(float(last["atr_pct"]) * 100, 3),
                    "macd_hist": round(float(last["macd_hist"]), 2),
                    "ema_fast": float(last["ema_fast"]),
                    "ema_slow": float(last["ema_slow"]),
                    "signals": sigs,
                    "ts": int(last["ts"]),
                }
                with analysis_lock:
                    analysis_state[sym] = info
            except Exception as e:
                print(f"[analysis] {sym}: {e}")
        time.sleep(12)


def _panel_update(sym, snap=None, decision=None, engine="confluencia (gratis)"):
    """Actualiza el panel 'Razonamiento de la IA'. Por defecto usa el motor GRATIS."""
    if snap is None:
        snap = build_snapshot(sym)
    if decision is None:
        decision = ensemble_decision(snap)
    with ai_lock:
        ai_state[sym] = {"symbol": sym, "snapshot": snap, "decision": decision,
                         "engine": engine, "updated": datetime.now(timezone.utc).isoformat()}


def _ai_run_once():
    # llena el panel rapido y GRATIS con el motor de confluencia (sin gastar en IA)
    for sym in WATCH:
        try:
            _panel_update(sym)
        except Exception as e:
            print(f"[ai] {sym}: {e}")


def _ai_worker():
    """Analisis inicial una vez. Si AI_AUTO_RUN=True, repite cada AI_REFRESH_SECONDS.
    Si no, la IA solo corre bajo demanda (boton 'analizar ahora') -> controla el costo."""
    import time as _t
    _ai_run_once()
    if not getattr(config, "AI_AUTO_RUN", False):
        return  # modo bajo demanda: no mas llamadas automaticas
    while True:
        _t.sleep(max(config.AI_REFRESH_SECONDS, 60))
        _ai_run_once()


def _live_price(sym):
    s = monitor.state.get(sym)
    if s and s.get("last"):
        return float(s["last"])
    try:
        df = fetch_recent(sym, "1m", config.PRODUCT_TYPE, 2)
        return float(df["close"].iloc[-1])
    except Exception:
        return None


_ai_cooldown = {}   # symbol -> epoch hasta el que no se vuelve a consultar la IA


def _watcher_worker():
    """Vigila el mercado continuamente (Nivel 0 GRATIS). Cuando hay candidato, el modelo
    BARATO (Haiku) lo confirma (Nivel 1). Alerta + abre paper trade. Cierra por SL/TP."""
    import time as _t
    while True:
        try:
            for sym in WATCH:
                price = _live_price(sym)
                if price is None:
                    continue
                # 1) gestionar posicion abierta (cerrar por SL/TP) -> Nivel 0, gratis
                closed = book.update_price(sym, price)
                if closed:
                    notify.send_alert(book.alerts[-1]["msg"])
                # 2) snapshot + refrescar el panel SIEMPRE (gratis) -> nunca se queda en "analizando"
                snap = build_snapshot(sym)
                _panel_update(sym, snap)
                if book.has_open(sym):
                    continue
                # 3) ¿hay candidato?
                if abs(snap["confluence_score"]) < config.SETUP_SCORE_THRESHOLD:
                    continue
                if _t.time() < _ai_cooldown.get(sym, 0):
                    continue
                # 4) confirmar con el modelo BARATO (Haiku) o motor gratis
                if config.AI_CONFIRM_SETUPS:
                    res = ai_analyst.reason(sym, config.AI_WATCH_MODEL)
                    decision = res["decision"]
                    _panel_update(sym, res["snapshot"], decision, config.AI_WATCH_MODEL)
                else:
                    decision = ensemble_decision(snap)
                _ai_cooldown[sym] = _t.time() + config.AI_CONSULT_COOLDOWN_MIN * 60
                if (decision.get("direction") in ("long", "short")
                        and decision.get("confidence", 0) >= config.MIN_CONFIDENCE
                        and decision.get("entry") and decision.get("stop") and decision.get("take_profit")):
                    book.open_trade(sym, decision)
                    notify.send_alert(book.alerts[-1]["msg"])
        except Exception as e:
            print(f"[watcher] {e}")
        _t.sleep(max(config.SCAN_INTERVAL_SECONDS, 20))


# -------- rutas API --------
@app.route("/api/backtest")
def api_backtest():
    if not os.path.exists(RESULTS):
        return jsonify({"error": "Aun no hay resultados. Corre: python scenarios.py"}), 404
    with open(RESULTS, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/candles")
def api_candles():
    symbol = request.args.get("symbol", "BTCUSDT")
    tf = request.args.get("tf", "15m")
    limit = request.args.get("limit", "300")
    try:
        rows = _fetch_recent_candles(symbol, tf, int(limit))
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    out = [{"time": int(r[0]) // 1000, "open": float(r[1]), "high": float(r[2]),
            "low": float(r[3]), "close": float(r[4]), "volume": float(r[5])}
           for r in sorted(rows, key=lambda x: int(x[0]))]
    return jsonify(out)


@app.route("/api/ticker")
def api_ticker():
    return jsonify({s: monitor.state.get(s) for s in WATCH})


@app.route("/api/analysis")
def api_analysis():
    with analysis_lock:
        return jsonify(dict(analysis_state))


@app.route("/api/ai")
def api_ai():
    with ai_lock:
        data = dict(ai_state)
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    return jsonify({"engine_mode": "claude" if has_key else "ensemble",
                    "model": config.AI_MODEL, "symbols": data})


@app.route("/api/paper")
def api_paper():
    return jsonify(book.snapshot())


@app.route("/api/cost")
def api_cost():
    from cost_tracker import tracker
    return jsonify(tracker.summary())


@app.route("/api/ai/<symbol>")
def api_ai_one(symbol):
    """Fuerza un analisis A FONDO con el modelo POTENTE (Opus) bajo demanda."""
    try:
        out = ai_analyst.reason(symbol.upper(), config.AI_MODEL)
        out["updated"] = datetime.now(timezone.utc).isoformat()
        with ai_lock:
            ai_state[symbol.upper()] = out
        return jsonify(out)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# -------- frontend --------
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(WEB_DIR, path)


def start_background():
    threading.Thread(target=monitor.run, daemon=True).start()
    threading.Thread(target=_analysis_worker, daemon=True).start()
    threading.Thread(target=_ai_worker, daemon=True).start()
    if getattr(config, "PAPER_TRADING", False):
        threading.Thread(target=_watcher_worker, daemon=True).start()


if __name__ == "__main__":
    start_background()
    # En local: 127.0.0.1:5000. En hosting (Render/HF Space): lee PORT y escucha en 0.0.0.0.
    port = int(os.environ.get("PORT", "5000"))
    host = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"
    print(f"Portal en  http://{host}:{port}   (Ctrl+C para parar)")
    app.run(host=host, port=port, debug=False, threaded=True)

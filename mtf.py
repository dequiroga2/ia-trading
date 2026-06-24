"""
Motor MULTI-TIMEFRAME de confluencia.
Reune el estado del mercado en varias temporalidades (1m -> 4h), evalua TODAS las
estrategias en cada una, y calcula un "score de confluencia" combinando:
  - alineacion de tendencia entre timeframes (los TF altos pesan mas)
  - cuantas estrategias coinciden en direccion
  - momentum (MACD) y sobrecompra/sobreventa (RSI)
  - soportes/resistencias recientes

Sirve para dos cosas:
  1. Construir el contexto que se le pasa a la IA (Claude) para que razone.
  2. Funcionar como motor de decision de RESPALDO si no hay API key de Claude.
"""
import numpy as np
import config
from data import fetch_recent
from indicators import add_indicators
from strategies import STRATEGIES, base_params

# temporalidades de menor a mayor y su peso en la confluencia
TF_WEIGHTS = {"1m": 0.5, "5m": 1.0, "15m": 1.5, "1H": 2.5, "4H": 3.0}
TIMEFRAMES = list(TF_WEIGHTS.keys())


def _dir(sig):
    return {"long": 1, "short": -1}.get(sig, 0)


def timeframe_state(symbol, tf):
    df = fetch_recent(symbol, tf, config.PRODUCT_TYPE, 300)
    p = base_params()
    df = add_indicators(df, p)
    last = df.iloc[-1]
    # senal de cada estrategia en esta TF
    sigs = {}
    for sname, (func, ov) in STRATEGIES.items():
        pp = base_params(); pp.update(ov)
        sigs[sname] = func(df.copy(), pp)["signal"].iloc[-1]
    trend = 1 if last["close"] > last["ema_trend"] else -1
    # soporte/resistencia recientes (ult. 50 velas)
    window = df.tail(50)
    return {
        "tf": tf,
        "price": float(last["close"]),
        "trend": trend,                       # 1 alcista, -1 bajista
        "ema_fast": float(last["ema_fast"]),
        "ema_slow": float(last["ema_slow"]),
        "rsi": round(float(last["rsi"]), 1),
        "atr_pct": round(float(last["atr_pct"]) * 100, 3),
        "macd_hist": round(float(last["macd_hist"]), 3),
        "signals": {k: (v or "flat") for k, v in sigs.items()},
        "resistance": round(float(window["high"].max()), 2),
        "support": round(float(window["low"].min()), 2),
        "vol_ratio": round(float(last["atr"] / last["atr_ma"]) if last["atr_ma"] == last["atr_ma"] and last["atr_ma"] else 1.0, 2),
    }


def build_snapshot(symbol):
    """Estado multi-timeframe completo + score de confluencia."""
    tfs = {}
    for tf in TIMEFRAMES:
        try:
            tfs[tf] = timeframe_state(symbol, tf)
        except Exception as e:
            tfs[tf] = {"tf": tf, "error": str(e)}

    # ---- score de confluencia ----
    score = 0.0
    max_score = 0.0
    for tf, s in tfs.items():
        if "error" in s:
            continue
        w = TF_WEIGHTS[tf]
        max_score += w * 2
        score += w * s["trend"]                          # alineacion de tendencia
        strat_votes = sum(_dir(v) for v in s["signals"].values())
        score += w * np.clip(strat_votes / 2.0, -1, 1)   # acuerdo entre estrategias
    norm = score / max_score if max_score else 0          # -1..+1

    if norm > 0.30:
        bias, action = "alcista", "buscar LONG"
    elif norm < -0.30:
        bias, action = "bajista", "buscar SHORT"
    else:
        bias, action = "mixto", "esperar / fuera"

    # contar estrategias activas totales
    active = []
    for tf, s in tfs.items():
        if "error" in s:
            continue
        for st, v in s["signals"].items():
            if v in ("long", "short"):
                active.append(f"{st}@{tf}={v}")

    base = tfs.get("5m") or next((v for v in tfs.values() if "error" not in v), {})
    return {
        "symbol": symbol,
        "price": base.get("price"),
        "timeframes": tfs,
        "confluence_score": round(norm, 3),
        "bias": bias,
        "suggested_action": action,
        "active_signals": active,
    }


def ensemble_decision(snapshot):
    """Decision determinista de respaldo (sin IA), a partir del snapshot."""
    norm = snapshot["confluence_score"]
    bias = snapshot["bias"]
    tfs = snapshot["timeframes"]
    base = tfs.get("15m") or tfs.get("5m") or {}
    price = snapshot.get("price") or base.get("price")
    atr_pct = base.get("atr_pct", 0.3) / 100.0
    atr = price * atr_pct if price else 0

    direction = "long" if bias == "alcista" else ("short" if bias == "bajista" else "none")
    confidence = round(min(abs(norm) * 1.3, 0.95), 2)

    if direction == "none" or confidence < 0.45:
        return {
            "direction": "none", "confidence": confidence,
            "entry": price, "stop": None, "take_profit": None,
            "leverage_suggested": 0, "timeframe": "15m",
            "strategies_agreeing": snapshot["active_signals"],
            "reasoning": (f"Confluencia insuficiente (score {norm:+.2f}, sesgo {bias}). "
                          f"Las temporalidades no estan alineadas; el costo por comision "
                          f"(0.12% ida+vuelta) no justifica entrar. Mejor esperar."),
            "engine": "ensemble",
        }
    if direction == "long":
        stop = round(price - 1.2 * atr, 2)
        tp = round(price + 2.4 * atr, 2)
    else:
        stop = round(price + 1.2 * atr, 2)
        tp = round(price - 2.4 * atr, 2)
    lev = 3 if confidence < 0.6 else (5 if confidence < 0.8 else 8)
    return {
        "direction": direction, "confidence": confidence,
        "entry": price, "stop": stop, "take_profit": tp,
        "leverage_suggested": lev, "timeframe": "15m",
        "strategies_agreeing": snapshot["active_signals"],
        "reasoning": (f"Confluencia {bias} (score {norm:+.2f}). "
                      f"{len(snapshot['active_signals'])} senales activas alineadas con la tendencia "
                      f"de los TF altos. Objetivo 2:1 sobre el riesgo, SL a 1.2x ATR. "
                      f"Apalancamiento {lev}x acorde a la confianza."),
        "engine": "ensemble",
    }


if __name__ == "__main__":
    import json
    snap = build_snapshot(config.SYMBOL)
    print(json.dumps(snap, ensure_ascii=False, indent=2, default=str))
    print("\nDECISION (ensemble):")
    print(json.dumps(ensemble_decision(snap), ensure_ascii=False, indent=2, default=str))

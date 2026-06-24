"""
Catalogo de estrategias. Cada una recibe un df CON indicadores y devuelve el df
con una columna 'signal' in {'long','short',None} evaluada al cierre de cada vela.
El motor de backtest entra en la apertura de la vela SIGUIENTE (sin lookahead).

Estrategias:
  1. trend_pullback   - tendencia + retroceso a EMA rapida (scalp/intradia)
  2. mean_reversion   - rebote en bandas de Bollinger + RSI extremo (rango)
  3. donchian_breakout- ruptura de maximos/minimos de N velas (expansion)
  4. macd_trend       - cruce MACD a favor de tendencia (momentum)
  5. ema_swing        - cruce EMA rapida/lenta con filtro de tendencia (baja frecuencia)
"""
import numpy as np


def base_params():
    return {
        "ema_fast": 9, "ema_slow": 21, "ema_trend": 200,
        "rsi_n": 14, "atr_n": 14,
        "rsi_long_max": 68, "rsi_short_min": 32,
        "rsi_os": 30, "rsi_ob": 70,
        "min_atr_pct": 0.0010,
        "bb_n": 20, "bb_k": 2.0, "dc_n": 20,
        "tp_atr": 1.4, "sl_atr": 1.0, "max_hold": 24,
    }


def _vol_ok(df, p):
    return df["atr_pct"] >= p["min_atr_pct"]


# --------------------------------------------------------------------------
def trend_pullback(df, p):
    df = df.copy()
    up = df["close"] > df["ema_trend"]
    dn = df["close"] < df["ema_trend"]
    mom_up = df["ema_fast"] > df["ema_slow"]
    mom_dn = df["ema_fast"] < df["ema_slow"]
    vok = _vol_ok(df, p)
    longs = up & mom_up & vok & (df["low"] <= df["ema_fast"]) & \
        (df["close"] > df["ema_fast"]) & (df["rsi"] < p["rsi_long_max"])
    shorts = dn & mom_dn & vok & (df["high"] >= df["ema_fast"]) & \
        (df["close"] < df["ema_fast"]) & (df["rsi"] > p["rsi_short_min"])
    return _assign(df, longs, shorts)


def mean_reversion(df, p):
    df = df.copy()
    vok = _vol_ok(df, p)
    longs = vok & (df["close"] < df["bb_dn"]) & (df["rsi"] < p["rsi_os"])
    shorts = vok & (df["close"] > df["bb_up"]) & (df["rsi"] > p["rsi_ob"])
    return _assign(df, longs, shorts)


def donchian_breakout(df, p):
    df = df.copy()
    vok = _vol_ok(df, p)
    up = df["close"] > df["ema_trend"]
    dn = df["close"] < df["ema_trend"]
    longs = vok & up & (df["close"] > df["dc_up"])
    shorts = vok & dn & (df["close"] < df["dc_dn"])
    return _assign(df, longs, shorts)


def macd_trend(df, p):
    df = df.copy()
    vok = _vol_ok(df, p)
    cross_up = (df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1))
    cross_dn = (df["macd"] < df["macd_sig"]) & (df["macd"].shift(1) >= df["macd_sig"].shift(1))
    longs = vok & cross_up & (df["close"] > df["ema_trend"])
    shorts = vok & cross_dn & (df["close"] < df["ema_trend"])
    return _assign(df, longs, shorts)


def ema_swing(df, p):
    df = df.copy()
    cross_up = (df["ema_fast"] > df["ema_slow"]) & (df["ema_fast"].shift(1) <= df["ema_slow"].shift(1))
    cross_dn = (df["ema_fast"] < df["ema_slow"]) & (df["ema_fast"].shift(1) >= df["ema_slow"].shift(1))
    longs = cross_up & (df["close"] > df["ema_trend"])
    shorts = cross_dn & (df["close"] < df["ema_trend"])
    return _assign(df, longs, shorts)


def _assign(df, longs, shorts):
    sig = np.where(longs, "long", np.where(shorts, "short", None))
    sig = sig.astype(object)
    sig[0] = None  # nunca operar en la primera vela
    df["signal"] = sig
    return df


# nombre -> (funcion, overrides de parametros por defecto recomendados)
STRATEGIES = {
    "trend_pullback":    (trend_pullback,    {}),
    "mean_reversion":    (mean_reversion,    {"min_atr_pct": 0.0008, "tp_atr": 1.2, "sl_atr": 1.5}),
    "donchian_breakout": (donchian_breakout, {"dc_n": 20, "tp_atr": 2.0, "sl_atr": 1.0}),
    "macd_trend":        (macd_trend,        {"tp_atr": 2.0, "sl_atr": 1.2}),
    "ema_swing":         (ema_swing,         {"tp_atr": 3.0, "sl_atr": 1.5, "max_hold": 12}),
}

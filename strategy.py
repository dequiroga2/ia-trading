"""
ESTRATEGIA: "Trend-Pullback Scalper" (mi propuesta)

Idea central, dada la realidad de comisiones (0.12% ida+vuelta como taker):
no perseguir cientos de micro-operaciones (las comisiones te matan), sino
entradas de ALTA PROBABILIDAD a favor de la tendencia, con objetivo y stop
basados en volatilidad (ATR) y un ratio beneficio/riesgo > 1.

Reglas LONG (short = espejo):
  1. FILTRO DE TENDENCIA: close > ema_trend  (solo operamos a favor de la tendencia mayor)
  2. MOMENTUM: ema_fast > ema_slow
  3. PULLBACK: el precio retrocede y toca/baja de ema_fast (compramos barato en la tendencia)
  4. GATILLO: la vela cierra de nuevo por encima de ema_fast (rebote confirmado)
  5. RSI no sobrecomprado (rsi < rsi_long_max)
  6. FILTRO DE VOLATILIDAD: atr_pct >= min_atr_pct  (evita mercado plano donde la comision se come todo)

Salida: TP = entry + tp_atr*ATR, SL = entry - sl_atr*ATR, o time-stop a max_hold velas.
"""


def default_params() -> dict:
    return {
        # indicadores
        "ema_fast": 9, "ema_slow": 21, "ema_trend": 200,
        "rsi_n": 14, "atr_n": 14,
        # filtros de entrada
        "rsi_long_max": 68, "rsi_short_min": 32,
        "min_atr_pct": 0.0010,   # 0.10% de ATR minimo (filtra mercado plano)
        # gestion de salida (en multiplos de ATR)
        "tp_atr": 1.4,
        "sl_atr": 1.0,
        "max_hold": 24,          # cierre por tiempo (24 velas)
    }


def generate_signals(df, p: dict):
    """Anota df con columna 'signal' in {'long','short',None} evaluada en el cierre de cada vela."""
    df = df.copy()
    sig = [None] * len(df)

    up_trend = df["close"] > df["ema_trend"]
    dn_trend = df["close"] < df["ema_trend"]
    mom_up = df["ema_fast"] > df["ema_slow"]
    mom_dn = df["ema_fast"] < df["ema_slow"]
    vol_ok = df["atr_pct"] >= p["min_atr_pct"]

    low, high, close = df["low"], df["high"], df["close"]
    ema_f, rsi = df["ema_fast"], df["rsi"]

    for i in range(1, len(df)):
        if not vol_ok.iloc[i]:
            continue
        # LONG: pullback que toca ema_fast y rebote (cierre por encima)
        touched_long = low.iloc[i] <= ema_f.iloc[i]
        if (up_trend.iloc[i] and mom_up.iloc[i] and touched_long
                and close.iloc[i] > ema_f.iloc[i] and rsi.iloc[i] < p["rsi_long_max"]):
            sig[i] = "long"
            continue
        # SHORT: pullback que toca ema_fast por arriba y rechazo (cierre por debajo)
        touched_short = high.iloc[i] >= ema_f.iloc[i]
        if (dn_trend.iloc[i] and mom_dn.iloc[i] and touched_short
                and close.iloc[i] < ema_f.iloc[i] and rsi.iloc[i] > p["rsi_short_min"]):
            sig[i] = "short"

    df["signal"] = sig
    return df

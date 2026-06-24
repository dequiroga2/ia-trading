"""Indicadores tecnicos (sin librerias externas mas alla de pandas/numpy)."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    delta = s.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    roll_up = up.ewm(alpha=1 / n, adjust=False).mean()
    roll_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def macd(s: pd.Series, fast=12, slow=26, signal=9):
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    df = df.copy()
    c = df["close"]
    df["ema_fast"] = ema(c, p["ema_fast"])
    df["ema_slow"] = ema(c, p["ema_slow"])
    df["ema_trend"] = ema(c, p["ema_trend"])
    df["rsi"] = rsi(c, p["rsi_n"])
    df["atr"] = atr(df, p["atr_n"])
    df["atr_pct"] = df["atr"] / c
    df["atr_ma"] = df["atr"].rolling(p["atr_n"] * 3).mean()
    # Bollinger (para reversion a la media)
    bb_n = p.get("bb_n", 20)
    bb_k = p.get("bb_k", 2.0)
    mid = c.rolling(bb_n).mean()
    sd = c.rolling(bb_n).std()
    df["bb_mid"], df["bb_up"], df["bb_dn"] = mid, mid + bb_k * sd, mid - bb_k * sd
    # Donchian (para breakout) - usa velas previas (shift 1) para evitar lookahead
    dc_n = p.get("dc_n", 20)
    df["dc_up"] = df["high"].rolling(dc_n).max().shift(1)
    df["dc_dn"] = df["low"].rolling(dc_n).min().shift(1)
    # MACD (para momentum)
    df["macd"], df["macd_sig"], df["macd_hist"] = macd(c)
    return df

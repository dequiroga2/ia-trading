"""
Descarga de velas historicas de Bitget (API publica, sin API key).
Maneja paginacion hacia atras y cachea en CSV para no re-descargar.
"""
import os
import time
import requests
import pandas as pd

BASE = "https://api.bitget.com"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache")

# milisegundos por vela segun granularidad
_TF_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1H": 3_600_000, "4H": 14_400_000,
}


def _granularity(tf: str) -> str:
    # Bitget v2 usa 1m,5m,15m,1H,4H ... (mayuscula en horas)
    return tf


def fetch_klines(symbol: str, timeframe: str, product_type: str, days: int) -> pd.DataFrame:
    """Descarga `days` dias de velas terminando ahora. Devuelve DataFrame ordenado por tiempo."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    tf_ms = _TF_MS[timeframe]
    now = int(time.time() * 1000)
    start = now - days * 24 * 60 * 60 * 1000

    cache = os.path.join(CACHE_DIR, f"{symbol}_{timeframe}_{days}d.csv")
    if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < 600:
        df = pd.read_csv(cache)
        return _finalize(df)

    rows = []
    end = now
    # history-candles devuelve hasta 200 velas <= endTime; paginamos hacia atras
    while end > start:
        url = (f"{BASE}/api/v2/mix/market/history-candles"
               f"?symbol={symbol}&granularity={_granularity(timeframe)}"
               f"&productType={product_type}&limit=200&endTime={end}")
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            break
        # data viene como lista de [ts, o, h, l, c, baseVol, quoteVol], mas reciente primero o ultimo
        rows.extend(data)
        ts_min = min(int(x[0]) for x in data)
        new_end = ts_min - 1
        if new_end >= end:
            break
        end = new_end
        time.sleep(0.12)  # respetar rate limit

    if not rows:
        raise RuntimeError("No se descargaron velas. Revisa simbolo/conexion.")

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "quote_vol"])
    df = df.drop_duplicates(subset="ts")
    df.to_csv(cache, index=False)
    return _finalize(df)


def fetch_recent(symbol: str, timeframe: str, product_type: str, limit: int = 300) -> pd.DataFrame:
    """Velas recientes en vivo (endpoint candles, sin caché) para análisis en tiempo real."""
    url = (f"{BASE}/api/v2/mix/market/candles?symbol={symbol}"
           f"&granularity={timeframe}&productType={product_type}&limit={limit}")
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    rows = r.json().get("data", [])
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol", "quote_vol"])
    return _finalize(df)


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    for c in ["ts", "open", "high", "low", "close", "vol", "quote_vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna().sort_values("ts").reset_index(drop=True)
    df["dt"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df


if __name__ == "__main__":
    from config import SYMBOL, TIMEFRAME, PRODUCT_TYPE, BACKTEST_DAYS
    d = fetch_klines(SYMBOL, TIMEFRAME, PRODUCT_TYPE, BACKTEST_DAYS)
    print(f"{len(d)} velas  | {d['dt'].iloc[0]}  ->  {d['dt'].iloc[-1]}")
    print(d.tail(3).to_string())

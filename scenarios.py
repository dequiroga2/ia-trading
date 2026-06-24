"""
Corre TODOS los escenarios posibles y guarda resultados en results/backtest_results.json
para que el portal web los muestre.

Combinaciones: estrategia x simbolo x timeframe x (maker/taker).
Capital: se evalua a $50 y $100. NOTA IMPORTANTE: con dimensionamiento por % de
riesgo, el retorno PORCENTUAL es identico a $50 y a $100 (todo escala lineal);
el capital cambia el resultado en dolares, no el % ni la rentabilidad. Por eso
la palanca real no es el capital sino la estrategia/frecuencia.
"""
import os
import json
import time
from datetime import datetime, timezone

import config
from data import fetch_klines
from indicators import add_indicators
from strategies import STRATEGIES, base_params
from backtest import run_backtest
from run_backtest import metrics

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["1m", "5m", "15m", "1H"]
CAPITALS = [50, 100]
OUT = os.path.join(os.path.dirname(__file__), "results", "backtest_results.json")

# velas por semana segun tf (para anualizar/normalizar frecuencia)
_BARS_PER_WEEK = {"1m": 10080, "5m": 2016, "15m": 672, "1H": 168}


def run_all():
    days = config.BACKTEST_DAYS
    scenarios = []
    equity_curves = {}
    period = None

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            try:
                df_raw = fetch_klines(symbol, tf, config.PRODUCT_TYPE, days)
            except Exception as e:
                print(f"  [skip] {symbol} {tf}: {e}")
                continue
            if period is None:
                period = {"from": str(df_raw["dt"].iloc[0]), "to": str(df_raw["dt"].iloc[-1])}
            bp = base_params()
            df_ind = add_indicators(df_raw, bp)
            bh = (df_raw["close"].iloc[-1] / df_raw["close"].iloc[0] - 1) * 100

            for sname, (func, overrides) in STRATEGIES.items():
                p = base_params()
                p.update(overrides)
                df_sig = func(df_ind.copy(), p)
                for maker in [False, True]:
                    config.ENTRY_AS_MAKER = maker
                    config.TP_AS_MAKER = maker
                    trades, curve, final = run_backtest(df_sig, p, 50.0)
                    m = metrics(trades, curve, 50.0, final)
                    if m["trades"] == 0:
                        continue
                    weeks = len(df_raw) / _BARS_PER_WEEK[tf]
                    freq = m["trades"] / max(weeks, 1e-9)
                    ret = m["return_pct"]
                    sid = f"{sname}|{symbol}|{tf}|{'M' if maker else 'T'}"
                    scen = {
                        "id": sid, "strategy": sname, "symbol": symbol, "tf": tf,
                        "maker": maker, "trades": m["trades"],
                        "freq_week": round(freq, 1),
                        "win_rate": round(m["win_rate"] * 100, 1),
                        "profit_factor": round(min(m["profit_factor"], 99), 2),
                        "fees_pct": round(m["total_fees"] / 50.0 * 100, 1),
                        "return_pct": round(ret, 1),
                        "max_dd_pct": round(m["max_drawdown_pct"], 1),
                        "liquidations": m["liquidations"],
                        "net_50": round(50 * ret / 100, 2),
                        "net_100": round(100 * ret / 100, 2),
                        "buy_hold_pct": round(bh, 1),
                    }
                    scenarios.append(scen)
                    # guardar curva de capital (la usaremos para los mejores)
                    equity_curves[sid] = [[str(t), round(e, 4)] for t, e in curve]

    # ranking: priorizamos retorno positivo y consistencia (profit factor)
    scenarios.sort(key=lambda s: (s["return_pct"], s["profit_factor"]), reverse=True)

    # quedarnos con curvas solo de top 8 + mejor de baja frecuencia, para no inflar el JSON
    keep = set(s["id"] for s in scenarios[:8])
    lowfreq = [s for s in scenarios if s["freq_week"] <= 20 and s["return_pct"] > 0]
    for s in lowfreq[:3]:
        keep.add(s["id"])
    equity_curves = {k: v for k, v in equity_curves.items() if k in keep}

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "days": days,
        "capitals": CAPITALS,
        "fees": {"maker": config.FEE_MAKER, "taker": config.FEE_TAKER,
                 "slippage": config.SLIPPAGE_PCT},
        "risk_per_trade_pct": config.RISK_PER_TRADE_PCT,
        "max_leverage": config.MAX_LEVERAGE,
        "n_scenarios": len(scenarios),
        "scenarios": scenarios,
        "equity_curves": equity_curves,
        "note_capital": ("Con sizing por % de riesgo, el retorno % es identico a $50 y $100; "
                         "el capital solo escala el resultado en dolares."),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    t0 = time.time()
    print("Corriendo todos los escenarios (puede tardar ~1-2 min por descarga de 1m)...")
    out = run_all()
    print(f"\nListo en {time.time()-t0:.0f}s. {out['n_scenarios']} escenarios -> {OUT}")
    print(f"Periodo: {out['period']['from']} -> {out['period']['to']}\n")
    print("TOP 12 escenarios por retorno (capital $50, costos reales):")
    print(f"  {'estrategia':18} {'sym':8} {'tf':4} {'mk':3} {'trd':>4} {'fr/sem':>6} "
          f"{'win':>4} {'PF':>5} {'fees%':>6} {'ret%':>7} {'$50':>7} {'$100':>7}")
    for s in out["scenarios"][:12]:
        print(f"  {s['strategy']:18} {s['symbol']:8} {s['tf']:4} {('mk' if s['maker'] else 'tk'):3} "
              f"{s['trades']:>4} {s['freq_week']:>6} {s['win_rate']:>4.0f} {s['profit_factor']:>5.2f} "
              f"{s['fees_pct']:>6.1f} {s['return_pct']:>+7.1f} {s['net_50']:>+7.2f} {s['net_100']:>+7.2f}")

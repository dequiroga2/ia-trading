"""
Busca configuraciones de ALTA FRECUENCIA que sean rentables tras comisiones.
Prueba ordenes maker (limite), varios timeframes, objetivos (TP/SL) y filtros.

OJO: optimizar sobre una sola semana = riesgo de sobreajuste. Esto sirve para
ver SI EXISTE alguna config viable, no para garantizar futuro.
"""
import itertools
import config
from data import fetch_klines
from indicators import add_indicators
from strategy import default_params, generate_signals
from backtest import run_backtest
from run_backtest import metrics

MIN_TRADES = 35   # exigimos "alta frecuencia": al menos ~5 trades/dia


def evaluate(df_raw, p, maker):
    config.ENTRY_AS_MAKER = maker
    config.TP_AS_MAKER = maker
    df = add_indicators(df_raw, p)
    df = generate_signals(df, p)
    trades, curve, final = run_backtest(df, p, config.INITIAL_EQUITY)
    return metrics(trades, curve, config.INITIAL_EQUITY, final)


def search(symbol):
    results = []
    grids = {
        "tf":          ["1m", "3m", "5m"],
        "tp_atr":      [0.8, 1.2, 1.8, 2.5],
        "sl_atr":      [0.8, 1.2],
        "min_atr_pct": [0.0005, 0.0012, 0.0020],
        "rsi_long_max":[60, 72],
        "maker":       [True, False],
    }
    # cache de datos por timeframe
    data = {tf: fetch_klines(symbol, tf, config.PRODUCT_TYPE, config.BACKTEST_DAYS)
            for tf in grids["tf"]}

    combos = list(itertools.product(
        grids["tf"], grids["tp_atr"], grids["sl_atr"],
        grids["min_atr_pct"], grids["rsi_long_max"], grids["maker"]))

    for tf, tp, sl, vol, rmax, maker in combos:
        p = default_params()
        p.update({"tp_atr": tp, "sl_atr": sl, "min_atr_pct": vol,
                  "rsi_long_max": rmax, "rsi_short_min": 100 - rmax,
                  "max_hold": 12 if tf != "1m" else 30})
        m = evaluate(data[tf], p, maker)
        if m.get("trades", 0) < MIN_TRADES:
            continue
        results.append((m["net_pnl"], tf, tp, sl, vol, rmax, maker, m))

    results.sort(reverse=True, key=lambda x: x[0])
    return results


def main():
    for symbol in ["BTCUSDT", "ETHUSDT"]:
        print(f"\n{'#'*72}\n# {symbol}  (alta frecuencia, >= {MIN_TRADES} trades/semana, $50, costos reales)\n{'#'*72}")
        res = search(symbol)
        if not res:
            print("  Ninguna config de alta frecuencia alcanzo el minimo de trades.")
            continue
        print(f"  {'tf':4} {'tp':>4} {'sl':>4} {'volf':>7} {'rsi':>4} {'maker':>6} | "
              f"{'trades':>6} {'win':>4} {'PF':>5} {'fees$':>6} | {'NETO$':>8} {'ret%':>6}")
        for net, tf, tp, sl, vol, rmax, maker, m in res[:8]:
            print(f"  {tf:4} {tp:>4} {sl:>4} {vol:>7.4f} {rmax:>4} {str(maker):>6} | "
                  f"{m['trades']:>6} {m['win_rate']*100:>3.0f}% {m['profit_factor']:>5.2f} "
                  f"{m['total_fees']:>6.1f} | {net:>+8.2f} {m['return_pct']:>+5.0f}%")
        print("  (peores para contraste:)")
        for net, tf, tp, sl, vol, rmax, maker, m in res[-2:]:
            print(f"  {tf:4} {tp:>4} {sl:>4} {vol:>7.4f} {rmax:>4} {str(maker):>6} | "
                  f"{m['trades']:>6} {m['win_rate']*100:>3.0f}% {m['profit_factor']:>5.2f} "
                  f"{m['total_fees']:>6.1f} | {net:>+8.2f} {m['return_pct']:>+5.0f}%")


if __name__ == "__main__":
    main()

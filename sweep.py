"""Barrido de configuraciones para ver el impacto de timeframe, simbolo, comisiones y parametros."""
import copy
import config
from data import fetch_klines
from indicators import add_indicators
from strategy import default_params, generate_signals
from backtest import run_backtest
from run_backtest import metrics


def test(symbol, tf, days, param_overrides=None, label=""):
    df = fetch_klines(symbol, tf, config.PRODUCT_TYPE, days)
    p = default_params()
    if param_overrides:
        p.update(param_overrides)
    df = add_indicators(df, p)
    df = generate_signals(df, p)
    trades, curve, final = run_backtest(df, p, config.INITIAL_EQUITY)
    m = metrics(trades, curve, config.INITIAL_EQUITY, final)
    bh = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
    if m["trades"] == 0:
        print(f"{label:34} {symbol} {tf:4} | 0 trades")
        return
    print(f"{label:34} {symbol} {tf:4} | trades {m['trades']:3} | win {m['win_rate']*100:4.0f}% "
          f"| PF {m['profit_factor']:.2f} | fees ${m['total_fees']:5.1f} | "
          f"NETO ${m['net_pnl']:+6.2f} ({m['return_pct']:+5.0f}%) | B&H {bh:+5.1f}%")


if __name__ == "__main__":
    D = config.BACKTEST_DAYS
    print("Capital inicial $50 en todos los casos. Costos reales Bitget incluidos.\n")
    test("BTCUSDT", "5m", D, None, "Base (taker)")
    test("ETHUSDT", "5m", D, None, "Base (taker)")
    test("BTCUSDT", "15m", D, None, "Base (taker)")
    test("ETHUSDT", "15m", D, None, "Base (taker)")
    test("SOLUSDT", "5m", D, None, "Base (taker)")
    print()
    # menos riesgo por trade + objetivos mas amplios (menos trades relativos a fees)
    test("BTCUSDT", "15m", D, {"tp_atr": 2.5, "sl_atr": 1.2, "min_atr_pct": 0.0025}, "TP amplio + filtro vol")
    test("ETHUSDT", "15m", D, {"tp_atr": 2.5, "sl_atr": 1.2, "min_atr_pct": 0.0025}, "TP amplio + filtro vol")
    test("BTCUSDT", "1H", D, {"tp_atr": 3.0, "sl_atr": 1.5, "min_atr_pct": 0.003, "max_hold": 12}, "Swing 1H")
    test("ETHUSDT", "1H", D, {"tp_atr": 3.0, "sl_atr": 1.5, "min_atr_pct": 0.003, "max_hold": 12}, "Swing 1H")
    print()
    # mismo, pero simulando ENTRADA MAKER (limite, 0.02% en vez de 0.06%)
    config.ENTRY_AS_MAKER = True
    import backtest as bt
    bt.ENTRY_AS_MAKER = True
    test("BTCUSDT", "15m", D, {"tp_atr": 2.5, "sl_atr": 1.2, "min_atr_pct": 0.0025}, "TP amplio + ENTRADA MAKER")
    test("ETHUSDT", "15m", D, {"tp_atr": 2.5, "sl_atr": 1.2, "min_atr_pct": 0.0025}, "TP amplio + ENTRADA MAKER")

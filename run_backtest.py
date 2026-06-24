"""
Ejecuta el backtest sobre datos REALES de Bitget de los ultimos N dias
y muestra un reporte honesto con todos los costos incluidos.

Uso:
    python run_backtest.py
    python run_backtest.py --symbol ETHUSDT --tf 5m --days 7
"""
import argparse
import numpy as np
import pandas as pd

import config
from data import fetch_klines
from indicators import add_indicators
from strategy import default_params, generate_signals
from backtest import run_backtest


def metrics(trades, equity_curve, initial, final):
    n = len(trades)
    if n == 0:
        return {"trades": 0}
    pnls = np.array([t.pnl for t in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls <= 0]
    fees = sum(t.fees for t in trades)
    funding = sum(t.funding for t in trades)
    eq = pd.Series([e for _, e in equity_curve])
    peak = eq.cummax()
    dd = ((eq - peak) / peak).min()
    gross_win = wins.sum()
    gross_loss = -losses.sum()
    return {
        "trades": n,
        "win_rate": len(wins) / n,
        "avg_win": wins.mean() if len(wins) else 0,
        "avg_loss": losses.mean() if len(losses) else 0,
        "profit_factor": (gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        "total_fees": fees,
        "total_funding": funding,
        "net_pnl": final - initial,
        "return_pct": (final / initial - 1) * 100,
        "max_drawdown_pct": dd * 100,
        "final_equity": final,
        "reasons": pd.Series([t.reason for t in trades]).value_counts().to_dict(),
        "liquidations": sum(1 for t in trades if t.reason == "liquidation"),
    }


def print_report(name, m, initial):
    print(f"\n{'='*60}\n  {name}\n{'='*60}")
    if m["trades"] == 0:
        print("  Sin operaciones (filtros muy estrictos o mercado plano).")
        return
    print(f"  Operaciones .............. {m['trades']}")
    print(f"  Win rate ................. {m['win_rate']*100:5.1f}%")
    print(f"  Profit factor ............ {m['profit_factor']:.2f}")
    print(f"  Ganancia media (win) ..... ${m['avg_win']:+.3f}")
    print(f"  Perdida media (loss) ..... ${m['avg_loss']:+.3f}")
    print(f"  Comisiones totales ....... ${m['total_fees']:.3f}")
    print(f"  Funding total ............ ${m['total_funding']:.3f}")
    print(f"  Liquidaciones ............ {m['liquidations']}")
    print(f"  Salidas por motivo ....... {m['reasons']}")
    print(f"  Drawdown maximo .......... {m['max_drawdown_pct']:.1f}%")
    print(f"  {'-'*40}")
    print(f"  Capital inicial .......... ${initial:.2f}")
    print(f"  Capital final ............ ${m['final_equity']:.2f}")
    print(f"  Resultado NETO ........... ${m['net_pnl']:+.2f}  ({m['return_pct']:+.1f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default=config.SYMBOL)
    ap.add_argument("--tf", default=config.TIMEFRAME)
    ap.add_argument("--days", type=int, default=config.BACKTEST_DAYS)
    args = ap.parse_args()

    print(f"Descargando {args.days} dias de {args.symbol} {args.tf} desde Bitget (datos publicos)...")
    df = fetch_klines(args.symbol, args.tf, config.PRODUCT_TYPE, args.days)
    print(f"  {len(df)} velas: {df['dt'].iloc[0]}  ->  {df['dt'].iloc[-1]}")
    move = (df['close'].iloc[-1] / df['close'].iloc[0] - 1) * 100
    print(f"  Movimiento buy&hold del periodo: {move:+.2f}%")

    p = default_params()
    df = add_indicators(df, p)
    df = generate_signals(df, p)
    nsig = df["signal"].notna().sum()
    print(f"  Senales generadas: {nsig}")

    trades, curve, final = run_backtest(df, p, config.INITIAL_EQUITY)
    m = metrics(trades, curve, config.INITIAL_EQUITY, final)
    print_report(f"ESTRATEGIA Trend-Pullback Scalper  |  {args.symbol} {args.tf}", m, config.INITIAL_EQUITY)

    # detalle de comisiones vs resultado (para que se vea el peso de los costos)
    if m["trades"]:
        print(f"\n  >> Las comisiones+funding sumaron ${m['total_fees']+m['total_funding']:.2f} "
              f"({(m['total_fees']+m['total_funding'])/config.INITIAL_EQUITY*100:.1f}% del capital inicial).")


if __name__ == "__main__":
    main()

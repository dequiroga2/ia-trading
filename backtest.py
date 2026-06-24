"""
Motor de backtest realista para futuros perpetuos.
- 1 posicion a la vez (apropiado para $50)
- Entrada en la apertura de la vela SIGUIENTE a la senal (sin lookahead)
- SL/TP intrabar usando high/low. Si ambos caben en la misma vela -> asumimos SL primero (conservador)
- Comisiones reales (maker/taker), slippage, funding cada 8h
- Liquidacion modelada segun apalancamiento
- Stop diario de perdidas
"""
from dataclasses import dataclass, field
import config
from config import (FEE_TAKER, FEE_MAKER, SLIPPAGE_PCT, FUNDING_RATE_PER_8H,
                    RISK_PER_TRADE_PCT, MAX_LEVERAGE, MAINTENANCE_MARGIN,
                    DAILY_MAX_LOSS_PCT)


@dataclass
class Trade:
    side: str
    entry_dt: object
    exit_dt: object
    entry: float
    exit: float
    size: float          # unidades del activo (BTC)
    notional: float
    leverage: float
    fees: float
    funding: float
    pnl: float           # neto (ya descontados fees+funding)
    reason: str          # tp / sl / time / liquidation
    equity_after: float


def _fee(rate_maker_side: bool) -> float:
    return FEE_MAKER if rate_maker_side else FEE_TAKER


def run_backtest(df, params, initial_equity, verbose=False):
    # se leen de config en cada llamada para permitir overrides (sweep/optimizer)
    entry_fee_rate = _fee(config.ENTRY_AS_MAKER)

    equity = initial_equity
    trades = []
    equity_curve = [(df["dt"].iloc[0], equity)]

    i = 0
    n = len(df)
    in_pos = False
    cur_day = None
    day_start_equity = equity
    halted_today = False

    # avanzar bar a bar; cuando hay senal en i, entrar en open de i+1
    while i < n - 1:
        row = df.iloc[i]
        day = row["dt"].date()
        if day != cur_day:
            cur_day = day
            day_start_equity = equity
            halted_today = False

        if equity <= 0:
            break
        if halted_today:
            i += 1
            continue

        sig = row["signal"]
        if sig is None:
            i += 1
            continue

        # ---- ENTRADA en apertura de la vela siguiente ----
        atr = row["atr"]
        if atr <= 0 or atr != atr:  # nan guard
            i += 1
            continue

        entry_idx = i + 1
        entry_open = df["open"].iloc[entry_idx]
        slip = SLIPPAGE_PCT
        if sig == "long":
            entry_price = entry_open * (1 + slip)
            sl = entry_price - params["sl_atr"] * atr
            tp = entry_price + params["tp_atr"] * atr
        else:
            entry_price = entry_open * (1 - slip)
            sl = entry_price + params["sl_atr"] * atr
            tp = entry_price - params["tp_atr"] * atr

        stop_dist = abs(entry_price - sl)
        if stop_dist <= 0:
            i += 1
            continue

        # ---- SIZING por riesgo ----
        risk_amount = equity * RISK_PER_TRADE_PCT
        size = risk_amount / stop_dist                      # unidades del activo
        notional = size * entry_price
        # limitar por apalancamiento maximo
        max_notional = equity * MAX_LEVERAGE
        if notional > max_notional:
            notional = max_notional
            size = notional / entry_price
        leverage = notional / equity
        margin = notional / leverage

        # precio de liquidacion aproximado
        if sig == "long":
            liq = entry_price * (1 - 1 / leverage + MAINTENANCE_MARGIN)
        else:
            liq = entry_price * (1 + 1 / leverage - MAINTENANCE_MARGIN)

        entry_fee = notional * entry_fee_rate

        # ---- recorrer velas hasta salir ----
        exit_price = None
        reason = None
        funding_paid = 0.0
        j = entry_idx
        held = 0
        last_funding_bucket = int(df["ts"].iloc[entry_idx] // (8 * 3600 * 1000))

        while j < n:
            hi = df["high"].iloc[j]
            lo = df["low"].iloc[j]

            # funding al cruzar un limite de 8h
            bucket = int(df["ts"].iloc[j] // (8 * 3600 * 1000))
            if bucket != last_funding_bucket:
                # long paga funding positivo; lo modelamos como costo siempre (conservador)
                funding_paid += notional * FUNDING_RATE_PER_8H
                last_funding_bucket = bucket

            if sig == "long":
                hit_liq = lo <= liq
                hit_sl = lo <= sl
                hit_tp = hi >= tp
                if hit_liq:
                    exit_price = liq; reason = "liquidation"; break
                if hit_sl:
                    exit_price = sl; reason = "sl"; break
                if hit_tp:
                    exit_price = tp; reason = "tp"; break
            else:
                hit_liq = hi >= liq
                hit_sl = hi >= sl
                hit_tp = lo <= tp
                if hit_liq:
                    exit_price = liq; reason = "liquidation"; break
                if hit_sl:
                    exit_price = sl; reason = "sl"; break
                if hit_tp:
                    exit_price = tp; reason = "tp"; break

            held += 1
            if held >= params["max_hold"]:
                exit_price = df["close"].iloc[j]; reason = "time"; break
            j += 1

        if exit_price is None:  # se acabaron los datos con posicion abierta
            exit_price = df["close"].iloc[n - 1]; reason = "eod"; j = n - 1

        # aplicar slippage de salida (salidas a mercado)
        if reason in ("sl", "time", "liquidation", "eod"):
            if sig == "long":
                exit_price *= (1 - SLIPPAGE_PCT)
            else:
                exit_price *= (1 + SLIPPAGE_PCT)
        # el TP puede ejecutarse como orden limite (maker); SL/time/liq son a mercado (taker)
        if reason == "tp" and config.TP_AS_MAKER:
            exit_fee_rate = FEE_MAKER
        elif reason == "tp" and config.EXIT_AS_MAKER:
            exit_fee_rate = FEE_MAKER
        else:
            exit_fee_rate = FEE_TAKER
        exit_fee = abs(size * exit_price) * exit_fee_rate

        if sig == "long":
            gross = size * (exit_price - entry_price)
        else:
            gross = size * (entry_price - exit_price)

        pnl = gross - entry_fee - exit_fee - funding_paid
        # no puedes perder mas que el margen (liquidacion)
        if pnl < -margin:
            pnl = -margin
        equity += pnl

        trades.append(Trade(
            side=sig, entry_dt=df["dt"].iloc[entry_idx], exit_dt=df["dt"].iloc[j],
            entry=entry_price, exit=exit_price, size=size, notional=notional,
            leverage=leverage, fees=entry_fee + exit_fee, funding=funding_paid,
            pnl=pnl, reason=reason, equity_after=equity,
        ))
        equity_curve.append((df["dt"].iloc[j], equity))

        # stop diario
        if equity <= day_start_equity * (1 - DAILY_MAX_LOSS_PCT):
            halted_today = True

        i = j + 1  # continuar despues de cerrar

    return trades, equity_curve, equity

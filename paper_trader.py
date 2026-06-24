"""
Libro de PAPER TRADING (operaciones simuladas en vivo, riesgo CERO).
Sigue las decisiones del motor/IA, simula la operacion con comisiones reales y
lleva el PnL. Persiste en paper/state.json para sobrevivir reinicios.

NO envia ordenes a Bitget. Es para validar la estrategia antes de dinero real.
"""
import os
import json
import threading
from datetime import datetime, timezone

import config

STATE_PATH = os.path.join(os.path.dirname(__file__), "paper", "state.json")
_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


class PaperBook:
    def __init__(self):
        self.equity = config.INITIAL_EQUITY
        self.open = {}          # symbol -> posicion
        self.history = []       # operaciones cerradas
        self.alerts = []        # ultimas alertas (para el portal)
        self._load()

    # ---------- persistencia ----------
    def _load(self):
        if os.path.exists(STATE_PATH):
            try:
                d = json.load(open(STATE_PATH, encoding="utf-8"))
                self.equity = d.get("equity", config.INITIAL_EQUITY)
                self.open = d.get("open", {})
                self.history = d.get("history", [])
                self.alerts = d.get("alerts", [])
            except Exception:
                pass

    def _save(self):
        os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(self.snapshot(), f, ensure_ascii=False, indent=2)

    def snapshot(self):
        wins = [t for t in self.history if t["pnl"] > 0]
        return {
            "equity": round(self.equity, 4),
            "start_equity": config.INITIAL_EQUITY,
            "return_pct": round((self.equity / config.INITIAL_EQUITY - 1) * 100, 2),
            "open": self.open,
            "n_open": len(self.open),
            "n_closed": len(self.history),
            "win_rate": round(len(wins) / len(self.history) * 100, 1) if self.history else 0,
            "history": self.history[-40:],
            "alerts": self.alerts[-25:],
        }

    def add_alert(self, kind, msg):
        self.alerts.append({"ts": _now(), "kind": kind, "msg": msg})
        self.alerts = self.alerts[-100:]

    # ---------- operativa ----------
    def has_open(self, symbol):
        return symbol in self.open

    def open_trade(self, symbol, decision):
        """Abre una posicion simulada a partir de una decision {direction, entry, stop, take_profit, leverage_suggested}."""
        with _lock:
            if symbol in self.open:
                return None
            d = decision
            entry = float(d["entry"]); stop = float(d["stop"]); tp = float(d["take_profit"])
            stop_dist = abs(entry - stop)
            if stop_dist <= 0:
                return None
            risk_amt = self.equity * config.RISK_PER_TRADE_PCT
            size = risk_amt / stop_dist
            lev = max(1, int(d.get("leverage_suggested") or 3))
            notional = size * entry
            if notional > self.equity * lev:
                notional = self.equity * lev
                size = notional / entry
            entry_fee = notional * config.FEE_TAKER
            pos = {
                "symbol": symbol, "direction": d["direction"], "entry": entry,
                "stop": stop, "tp": tp, "size": size, "notional": notional,
                "leverage": lev, "entry_fee": entry_fee,
                "opened_at": _now(), "reasoning": d.get("reasoning", ""),
            }
            self.open[symbol] = pos
            self.add_alert("open",
                f"NUEVA OPORTUNIDAD {d['direction'].upper()} {symbol}\n"
                f"Entrada {entry} | Stop {stop} | Objetivo {tp} | Apal {lev}x\n"
                f"{d.get('reasoning','')}")
            self._save()
            return pos

    def update_price(self, symbol, price):
        """Comprueba si una posicion abierta toca SL o TP al precio actual. Cierra si procede."""
        with _lock:
            pos = self.open.get(symbol)
            if not pos:
                return None
            hit = None
            if pos["direction"] == "long":
                if price <= pos["stop"]: hit = ("sl", pos["stop"])
                elif price >= pos["tp"]: hit = ("tp", pos["tp"])
            else:
                if price >= pos["stop"]: hit = ("sl", pos["stop"])
                elif price <= pos["tp"]: hit = ("tp", pos["tp"])
            if not hit:
                return None
            reason, exit_price = hit
            return self._close(symbol, exit_price, reason)

    def _close(self, symbol, exit_price, reason):
        pos = self.open.pop(symbol)
        size = pos["size"]
        if pos["direction"] == "long":
            gross = size * (exit_price - pos["entry"])
        else:
            gross = size * (pos["entry"] - exit_price)
        exit_fee = abs(size * exit_price) * config.FEE_TAKER
        pnl = gross - pos["entry_fee"] - exit_fee
        self.equity += pnl
        trade = {**pos, "exit": exit_price, "reason": reason,
                 "pnl": round(pnl, 4), "closed_at": _now(),
                 "equity_after": round(self.equity, 4)}
        self.history.append(trade)
        res = "GANANCIA" if pnl > 0 else "PERDIDA"
        self.add_alert("close",
            f"CERRADA {pos['direction'].upper()} {symbol} por {reason.upper()} -> {res}\n"
            f"PnL {pnl:+.2f} USDT | Capital paper: {self.equity:.2f}")
        self._save()
        return trade


# instancia compartida
book = PaperBook()

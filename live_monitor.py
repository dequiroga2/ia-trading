"""
Monitor de precios EN TIEMPO REAL de futuros Bitget (USDT-M perpetuos).
Usa el WebSocket publico de Bitget -> NO necesita API key.

- Se suscribe al canal 'ticker' de varios simbolos
- Reconexion automatica y ping/pong (mantiene la conexion viva 24/7)
- Dashboard que se actualiza solo en la consola

Uso:
    python live_monitor.py
    python live_monitor.py --symbols BTCUSDT,ETHUSDT,SOLUSDT
    python live_monitor.py --duration 30        # corre 30s y sale (para pruebas)
"""
import argparse
import json
import time
import threading
from datetime import datetime, timezone

import websocket  # websocket-client

WS_URL = "wss://ws.bitget.com/v2/ws/public"


class BitgetLiveMonitor:
    def __init__(self, symbols, inst_type="USDT-FUTURES", on_update=None):
        self.symbols = symbols
        self.inst_type = inst_type
        self.on_update = on_update          # callback(symbol, data) opcional
        self.state = {}                     # symbol -> dict ultimo ticker
        self.ws = None
        self.running = False
        self._last_ping = 0
        self._connected_at = None

    # ---------- callbacks websocket ----------
    def _on_open(self, ws):
        self._connected_at = time.time()
        args = [{"instType": self.inst_type, "channel": "ticker", "instId": s}
                for s in self.symbols]
        ws.send(json.dumps({"op": "subscribe", "args": args}))

    def _on_message(self, ws, message):
        if message == "pong":
            return
        try:
            msg = json.loads(message)
        except json.JSONDecodeError:
            return
        if msg.get("event") == "error":
            print(f"[WS error] {msg}")
            return
        data = msg.get("data")
        if not data:
            return
        for d in data:
            sym = d.get("instId")
            if not sym:
                continue
            self.state[sym] = {
                "last": float(d.get("lastPr", 0) or 0),
                "bid": float(d.get("bidPr", 0) or 0),
                "ask": float(d.get("askPr", 0) or 0),
                "high24h": float(d.get("high24h", 0) or 0),
                "low24h": float(d.get("low24h", 0) or 0),
                "chg24h": float(d.get("change24h", 0) or 0) * 100,
                "vol24h": float(d.get("baseVolume", 0) or 0),
                "funding": float(d.get("fundingRate", 0) or 0) * 100,
                "ts": int(d.get("ts", 0) or 0),
            }
            if self.on_update:
                self.on_update(sym, self.state[sym])

    def _on_error(self, ws, err):
        print(f"[WS] error de conexion: {err}")

    def _on_close(self, ws, code, msg):
        print(f"[WS] conexion cerrada ({code}). Reconectando...")

    # ---------- ping keepalive ----------
    def _pinger(self):
        while self.running:
            time.sleep(1)
            if self.ws and (time.time() - self._last_ping) > 25:
                try:
                    self.ws.send("ping")
                    self._last_ping = time.time()
                except Exception:
                    pass

    # ---------- loop principal con reconexion ----------
    def run(self):
        self.running = True
        threading.Thread(target=self._pinger, daemon=True).start()
        while self.running:
            self.ws = websocket.WebSocketApp(
                WS_URL,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self.ws.run_forever(ping_interval=0)  # ping manual arriba
            if self.running:
                time.sleep(2)  # backoff antes de reconectar

    def stop(self):
        self.running = False
        if self.ws:
            self.ws.close()


def _fmt(n, dec=2):
    return f"{n:,.{dec}f}"


def dashboard_loop(monitor: BitgetLiveMonitor, duration=None):
    """Imprime un dashboard que se refresca solo."""
    start = time.time()
    last_print = {}
    while True:
        if duration and (time.time() - start) > duration:
            monitor.stop()
            break
        time.sleep(1)
        if not monitor.state:
            continue
        now = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
        lines = [f"  BITGET FUTUROS - EN VIVO  ({now})",
                 f"  {'SIMBOLO':10} {'ULTIMO':>12} {'BID':>12} {'ASK':>12} {'24h%':>8} {'FUNDING%':>9}"]
        for sym in monitor.symbols:
            s = monitor.state.get(sym)
            if not s:
                lines.append(f"  {sym:10} {'(esperando...)':>12}")
                continue
            arrow = "  "
            prev = last_print.get(sym)
            if prev is not None:
                arrow = "^ " if s["last"] > prev else ("v " if s["last"] < prev else "= ")
            last_print[sym] = s["last"]
            dec = 2 if s["last"] >= 100 else 4
            lines.append(f"  {sym:10} {arrow}{_fmt(s['last'],dec):>10} {_fmt(s['bid'],dec):>12} "
                         f"{_fmt(s['ask'],dec):>12} {s['chg24h']:>+7.2f}% {s['funding']:>+8.4f}")
        # limpiar pantalla y reimprimir
        print("\033[2J\033[H" + "\n".join(lines), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT")
    ap.add_argument("--duration", type=int, default=None, help="segundos a correr (None = infinito)")
    args = ap.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    mon = BitgetLiveMonitor(symbols)
    t = threading.Thread(target=mon.run, daemon=True)
    t.start()
    try:
        dashboard_loop(mon, duration=args.duration)
    except KeyboardInterrupt:
        mon.stop()
        print("\nMonitor detenido.")


if __name__ == "__main__":
    main()

"""
Rastreador de COSTO de la IA en tiempo real.
Registra cada llamada a Claude (modelo, tokens, costo) y lo acumula.
Persiste en paper/cost.json. Lo lee el dashboard del portal.
"""
import os
import json
import threading
from datetime import datetime, timezone

PATH = os.path.join(os.path.dirname(__file__), "paper", "cost.json")
_lock = threading.Lock()

# $ por 1M tokens (input, output)
PRICES = {
    "opus": (5.0, 25.0),
    "sonnet": (3.0, 15.0),
    "haiku": (1.0, 5.0),
    "fable": (10.0, 50.0),
}


def _price(model: str):
    for k, v in PRICES.items():
        if k in model:
            return v
    return (5.0, 25.0)


class CostTracker:
    def __init__(self):
        self.calls = []          # {ts, model, in, out, cost}
        self._load()

    def _load(self):
        if os.path.exists(PATH):
            try:
                self.calls = json.load(open(PATH, encoding="utf-8")).get("calls", [])
            except Exception:
                self.calls = []

    def _save(self):
        os.makedirs(os.path.dirname(PATH), exist_ok=True)
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump({"calls": self.calls[-2000:]}, f)

    def record(self, model, in_tok, out_tok):
        pi, po = _price(model)
        cost = in_tok / 1e6 * pi + out_tok / 1e6 * po
        with _lock:
            self.calls.append({
                "ts": datetime.now(timezone.utc).isoformat(),
                "model": model, "in": in_tok, "out": out_tok, "cost": round(cost, 6),
            })
            self._save()
        return cost

    def summary(self):
        today = datetime.now(timezone.utc).date().isoformat()
        total = sum(c["cost"] for c in self.calls)
        today_cost = sum(c["cost"] for c in self.calls if c["ts"][:10] == today)
        per_model = {}
        for c in self.calls:
            tag = "Opus (a fondo)" if "opus" in c["model"] else (
                  "Haiku (vigilante)" if "haiku" in c["model"] else c["model"])
            m = per_model.setdefault(tag, {"calls": 0, "cost": 0.0, "tokens": 0})
            m["calls"] += 1; m["cost"] += c["cost"]; m["tokens"] += c["in"] + c["out"]
        for m in per_model.values():
            m["cost"] = round(m["cost"], 4)
        # serie acumulada (para la grafica)
        cum, series = 0.0, []
        for c in self.calls[-300:]:
            cum += c["cost"]
            series.append({"ts": c["ts"], "cum": round(cum, 5)})
        return {
            "total": round(total, 4),
            "today": round(today_cost, 4),
            "n_calls": len(self.calls),
            "per_model": per_model,
            "recent": list(reversed(self.calls[-12:])),
            "series": series,
        }


tracker = CostTracker()

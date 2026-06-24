"""Mide el costo REAL de una llamada de la IA (tokens reales) y proyecta el gasto."""
import os, json
import anthropic
import config
from mtf import build_snapshot
from ai_analyst import SYSTEM, TradeDecision

client = anthropic.Anthropic()
snap = build_snapshot(config.SYMBOL)
user = f"Snapshot de {config.SYMBOL}:\n\n{json.dumps(snap, ensure_ascii=False, default=str)}\n\nDecide la mejor accion."

# tokens de entrada (sistema + usuario)
ct = client.messages.count_tokens(model=config.AI_MODEL, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}])
in_tok = ct.input_tokens

# una llamada real para medir tokens de salida (incluye thinking)
resp = client.messages.parse(model=config.AI_MODEL, max_tokens=2000, system=SYSTEM,
                             messages=[{"role": "user", "content": user}],
                             thinking={"type": "adaptive"}, output_format=TradeDecision)
out_tok = resp.usage.output_tokens
real_in = resp.usage.input_tokens

PRICES = {  # $ por 1M tokens (input, output)
    "claude-opus-4-8": (5, 25),
    "claude-haiku-4-5": (1, 5),
}
print(f"Tokens reales -> entrada: {real_in} (estimado {in_tok}) | salida: {out_tok}\n")
print(f"{'modelo':18} {'$/llamada':>10} {'90s 3sym/dia':>14} {'cada15m 1sym/dia':>18} {'/mes 90s':>10}")
for m, (pi, po) in PRICES.items():
    per = real_in/1e6*pi + out_tok/1e6*po
    d_90 = per * (86400/90) * 3          # cada 90s, 3 simbolos
    d_15 = per * (1440/15) * 1           # cada 15 min, 1 simbolo
    mo_90 = d_90 * 30
    print(f"{m:18} {per:>9.4f} {d_90:>13.2f} {d_15:>17.2f} {mo_90:>9.0f}")

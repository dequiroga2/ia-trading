"""
EL CEREBRO: una IA (Claude) que mira el grafico en VIVO en varias temporalidades,
razona combinando todas las estrategias, y decide si hay una oportunidad.

- Construye el contexto multi-timeframe con mtf.build_snapshot()
- Se lo pasa a Claude, que RAZONA y devuelve una decision estructurada + su explicacion
- Si no hay ANTHROPIC_API_KEY, usa el motor de confluencia determinista (mtf.ensemble_decision)

Requiere: variable de entorno ANTHROPIC_API_KEY (para la parte de IA).
"""
import os
import json
from typing import Optional, List
from pydantic import BaseModel, Field

import config
from mtf import build_snapshot, ensemble_decision

try:
    import anthropic
    _HAS_SDK = True
except ImportError:
    _HAS_SDK = False


# ---- esquema de la decision que la IA debe devolver ----
class TradeDecision(BaseModel):
    direction: str = Field(description="'long', 'short' o 'none' (sin operar)")
    confidence: float = Field(description="confianza 0.0 a 1.0")
    entry: Optional[float] = Field(description="precio de entrada sugerido, o null")
    stop: Optional[float] = Field(description="precio de stop-loss, o null")
    take_profit: Optional[float] = Field(description="precio de take-profit, o null")
    leverage_suggested: int = Field(description="apalancamiento sugerido (0 si no operar)")
    timeframe: str = Field(description="temporalidad principal de la operacion, ej '15m'")
    key_factors: List[str] = Field(description="3-5 factores clave (timeframes/estrategias) que sustentan la decision")
    reasoning: str = Field(description="explicacion en español, 2-4 frases, del razonamiento")


SYSTEM = """Eres un analista cuantitativo de futuros cripto en Bitget, experto en scalping y trading intradia.
Operas con capital pequeño (50-100 USDT) y riesgo medio-alto. Tu trabajo es mirar el estado del
mercado en VARIAS temporalidades a la vez y razonar como un trader profesional para decidir si hay
una oportunidad de alta probabilidad AHORA.

Principios NO negociables:
- Las comisiones son reales: 0.06% taker / 0.02% maker por lado. Una operacion a mercado cuesta
  ~0.12% ida+vuelta + slippage. NO entres si el recorrido esperado no supera holgadamente ese costo.
- Opera a favor de la confluencia entre temporalidades. Si los TF altos (1H/4H) y los bajos no
  estan alineados, lo correcto suele ser NO operar ('none').
- Combina las señales de las distintas estrategias (trend_pullback, mean_reversion, donchian_breakout,
  macd_trend, ema_swing). Una sola señal aislada en 1m no es suficiente.
- Stop-loss SIEMPRE definido. Ratio beneficio/riesgo objetivo >= 1.8. Apalancamiento acorde a la
  confianza (3x baja, 5x media, 8x alta), nunca temerario.
- Ante la duda, 'none'. Preservar capital es ganar.

Te dan un snapshot multi-timeframe con precio, tendencia, RSI, ATR%, MACD, señales por estrategia,
soportes/resistencias y un score de confluencia. Razona y devuelve tu decision."""


def _client():
    if not _HAS_SDK:
        return None
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    try:
        return anthropic.Anthropic()
    except Exception:
        return None


def reason(symbol: str) -> dict:
    """Devuelve {snapshot, decision, engine}. Usa Claude si hay clave; si no, el ensemble."""
    snapshot = build_snapshot(symbol)
    client = _client()

    if client is None:
        dec = ensemble_decision(snapshot)
        return {"symbol": symbol, "snapshot": snapshot, "decision": dec, "engine": "ensemble"}

    user = (f"Snapshot del mercado de {symbol} (USDT-M perpetuo) ahora mismo:\n\n"
            f"{json.dumps(snapshot, ensure_ascii=False, default=str)}\n\n"
            f"Analiza la confluencia entre temporalidades y las señales de las estrategias, "
            f"y decide la mejor accion. Devuelve la decision estructurada.")

    kwargs = dict(
        model=config.AI_MODEL,
        max_tokens=2000,
        system=SYSTEM,
        messages=[{"role": "user", "content": user}],
        output_format=TradeDecision,
    )
    if config.AI_THINKING:
        kwargs["thinking"] = {"type": "adaptive"}

    try:
        resp = client.messages.parse(**kwargs)
        dec = resp.parsed_output.model_dump()
        dec["engine"] = config.AI_MODEL
        return {"symbol": symbol, "snapshot": snapshot, "decision": dec, "engine": config.AI_MODEL}
    except Exception as e:
        dec = ensemble_decision(snapshot)
        dec["reasoning"] = f"[IA no disponible: {e}] " + dec["reasoning"]
        return {"symbol": symbol, "snapshot": snapshot, "decision": dec, "engine": "ensemble"}


if __name__ == "__main__":
    out = reason(config.SYMBOL)
    print(f"Motor: {out['engine']}  |  score confluencia: {out['snapshot']['confluence_score']}")
    print(json.dumps(out["decision"], ensure_ascii=False, indent=2, default=str))

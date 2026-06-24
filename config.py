"""
Configuracion central del bot/backtester de futuros Bitget.
Todos los costos son REALES (Bitget USDT-M perpetuos, nivel base de comisiones).
"""

# ----------------------------- MERCADO -----------------------------
SYMBOL = "BTCUSDT"          # par a operar (BTC y ETH son los mas liquidos -> mejor para scalping)
PRODUCT_TYPE = "usdt-futures"
TIMEFRAME = "5m"            # temporalidad base de las velas (1m / 5m / 15m)
BACKTEST_DAYS = 7           # cuantos dias hacia atras descargar para el backtest

# ----------------------------- CAPITAL ------------------------------
INITIAL_EQUITY = 50.0       # capital inicial en USDT

# ----------------------------- COSTOS REALES ------------------------
# Comisiones Bitget USDT-M perpetuos (nivel VIP0 / cuenta base), junio 2026:
#   maker = 0.02%  | taker = 0.06%
# Asumimos lo PEOR por defecto: entrada y salida como TAKER (orden a mercado).
FEE_TAKER = 0.0006          # 0.06% por lado
FEE_MAKER = 0.0002          # 0.02% por lado
ENTRY_AS_MAKER = False      # True = intenta entrar con orden limite (paga 0.02% en vez de 0.06%)
EXIT_AS_MAKER = False       # las salidas por SL casi siempre son taker -> dejar False es realista
TP_AS_MAKER = False         # True = el take-profit se coloca como orden limite (maker 0.02%).
                            #        El stop-loss SIEMPRE es taker (orden a mercado). Esto es realista
                            #        y es la palanca clave para que la alta frecuencia sea viable.

# Slippage estimado por lado (deslizamiento de precio al ejecutar a mercado)
SLIPPAGE_PCT = 0.0002       # 0.02% por lado (conservador para BTC/ETH liquidos)

# Funding: se paga/cobra cada 8h (00:00, 08:00, 16:00 UTC). Tasa media asumida por evento.
FUNDING_RATE_PER_8H = 0.0001  # 0.01% (aprox). Impacto bajo en scalping de minutos.

# ----------------------------- RIESGO -------------------------------
RISK_PER_TRADE_PCT = 0.03   # % del capital arriesgado por operacion (3% = riesgo medio-alto)
MAX_LEVERAGE = 10           # apalancamiento maximo permitido
MAINTENANCE_MARGIN = 0.005  # margen de mantenimiento aprox (0.5%) para calcular liquidacion
MAX_CONCURRENT_POSITIONS = 1  # con $50 solo una posicion a la vez (control de riesgo)
DAILY_MAX_LOSS_PCT = 0.15   # si pierdes 15% del capital en un dia, paras de operar ese dia

# ----------------------------- API (solo para operar en real, NO para backtest) -----
# El backtest NO necesita estas claves (usa datos publicos).
BITGET_API_KEY = ""
BITGET_API_SECRET = ""
BITGET_API_PASSPHRASE = ""
DRY_RUN = True              # True = no envia ordenes reales (paper trading)

# ----------------------------- IA (cerebro que razona) --------------
# La IA usa la API de Claude. Necesita la variable de entorno ANTHROPIC_API_KEY.
# Si NO hay clave, el portal usa el motor de confluencia determinista (gratis, sin IA).
AI_MODEL = "claude-opus-4-8"   # OJO al costo. "claude-haiku-4-5" es ~5x mas barato (recomendado para uso frecuente)
AI_THINKING = True             # razonamiento adaptativo (mas inteligente, algo mas caro)
# SEGURIDAD DE COSTO: por defecto la IA NO corre en bucle. Solo analiza:
#   - una vez al arrancar (para que el panel muestre algo)
#   - cuando pulsas "analizar ahora" en el portal (bajo demanda)
# El motor de confluencia GRATIS (mtf.py) es el que vigila continuamente.
# Pon AI_AUTO_RUN = True solo si entiendes el costo (ver tabla en el README/respuesta).
AI_AUTO_RUN = False
AI_REFRESH_SECONDS = 900       # si AI_AUTO_RUN=True: cada cuanto re-analiza (900s = 15 min)

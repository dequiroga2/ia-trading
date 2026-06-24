# Bot de Futuros Bitget — Backtester (fase 1)

Backtester realista para futuros perpetuos USDT-M de Bitget. Descarga velas
**reales** de la API pública (sin API key) y simula una estrategia incluyendo
**todos los costos**: comisiones maker/taker, slippage, funding y liquidación.

## Instalación
```
pip install -r requirements.txt
```

## Uso
```
python run_backtest.py                          # BTCUSDT 5m, últimos 7 días, $50
python run_backtest.py --symbol ETHUSDT --tf 1H --days 7
python sweep.py                                 # compara configuraciones
```

## Archivos
- `config.py` — capital, costos reales, riesgo, (claves API solo para operar en real)
- `data.py` — descarga + caché de velas Bitget
- `indicators.py` — EMA, RSI, ATR
- `strategy.py` — estrategia "Trend-Pullback Scalper"
- `backtest.py` — motor de simulación (1 posición, SL/TP intrabar, fees, funding, liquidación)
- `run_backtest.py` — ejecuta y reporta
- `sweep.py` — barrido de configuraciones

## Portal web
```
python server.py          # http://127.0.0.1:5000
```
Muestra: gráfica en tiempo real (velas + EMAs), análisis en vivo (señal de cada
estrategia + RSI/ATR/MACD), tickers en vivo y el backtesting completo (120
escenarios) con tabla ordenable y curva de capital. No necesita API key.

## Estrategias (strategies.py)
1. `trend_pullback` — tendencia + retroceso a EMA (intradía)
2. `mean_reversion` — rebote en Bollinger + RSI extremo (rango)
3. `donchian_breakout` — ruptura de N velas (expansión)
4. `macd_trend` — cruce MACD a favor de tendencia (momentum)
5. `ema_swing` — cruce EMA con filtro de tendencia (baja frecuencia)

Genera/actualiza resultados con: `python scenarios.py`

## Conclusiones del backtest (semana 17-24 jun 2026, mercado bajista)
- **El capital $50 vs $100 NO cambia la rentabilidad %** (sizing por % de riesgo
  → todo escala lineal). $100 solo duplica el resultado en dólares.
- Alta frecuencia pura (1m/5m a mercado) PIERDE por comisiones. Con **órdenes
  límite (maker)** mejora mucho.
- Mejores resultados: `macd_trend` SOL 15m maker **+16%** (~26 ops/sem),
  `donchian_breakout` BTC 1H maker **+15%** (PF 2.36, robusto).
- 23 de 120 escenarios fueron rentables tras todos los costos.

> Es UNA semana y un solo régimen. Un positivo aquí NO garantiza el futuro.
> Herramienta de simulación, NO asesoría. El apalancamiento puede liquidar tu capital.

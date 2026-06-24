"""
Envio de alertas: consola + Telegram (opcional, gratis).

Para recibir alertas en tu MOVIL con Telegram:
  1. En Telegram, habla con @BotFather -> /newbot -> te da un TOKEN.
  2. Habla con tu nuevo bot (envíale un "hola").
  3. Consigue tu chat_id: abre https://api.telegram.org/bot<TOKEN>/getUpdates
     y busca "chat":{"id":NUMERO}. Ese numero es tu chat_id.
  4. Pon TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en config.py o como variables de entorno.
Si no configuras Telegram, las alertas igual salen en consola y en el portal.
"""
import os
import requests
import config


def _tg_creds():
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or getattr(config, "TELEGRAM_BOT_TOKEN", "")
    chat = os.environ.get("TELEGRAM_CHAT_ID") or getattr(config, "TELEGRAM_CHAT_ID", "")
    return token, chat


def send_alert(text: str):
    """Imprime en consola y, si hay credenciales, manda a Telegram."""
    print(f"\n🔔 ALERTA:\n{text}\n", flush=True)
    token, chat = _tg_creds()
    if not token or not chat:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        return r.ok
    except Exception as e:
        print(f"[telegram] error: {e}")
        return False

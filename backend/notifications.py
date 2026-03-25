import httpx
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

async def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML"
            })
    except Exception as e:
        logger.error(f"Telegram error: {e}")

async def ask_claude(question: str, bot_stats: dict) -> str:
    if not ANTHROPIC_API_KEY:
        return "No hay API key de Anthropic configurada."
    url = "https://api.anthropic.com/v1/messages"
    system = (
        "Eres el asistente inteligente de un trading bot en Polymarket. "
        "Respondes en español, de forma corta y directa. "
        "Tienes acceso a los stats del bot en tiempo real. "
        "Puedes sugerir cambios de configuración cuando te los pidan."
    )
    context = (
        f"Stats actuales del bot:\n"
        f"- Bankroll: ${bot_stats.get('bankroll', 0):.2f}\n"
        f"- P&L total: ${bot_stats.get('total_pnl', 0):.2f}\n"
        f"- Trades: {bot_stats.get('total_trades', 0)}\n"
        f"- Win rate: {bot_stats.get('win_rate', 0)*100:.1f}%\n"
        f"- Corriendo: {bot_stats.get('is_running', False)}\n"
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 300,
                    "system": system,
                    "messages": [{"role": "user", "content": f"{context}\n\nPregunta: {question}"}]
                }
            )
            data = response.json()
            return data["content"][0]["text"]
    except Exception as e:
        logger.error(f"Claude error: {e}")
        return "Error consultando a Claude."

async def handle_telegram_update(update: dict, bot_stats: dict):
    message = update.get("message", {})
    text = message.get("text", "").strip()
    if not text:
        return
    response = await ask_claude(text, bot_stats)
    await send_telegram(response)

async def notify_trade(direction: str, market_id: str, size: float, edge: float, market_type: str = "BTC"):
    emoji = "🟢" if direction == "UP" else "🔴"
    msg = (
        f"{emoji} <b>TRADE {market_type}</b>\n"
        f"Dirección: <b>{direction}</b>\n"
        f"Monto: <b>${size:.0f}</b>\n"
        f"Edge: <b>{edge*100:.1f}%</b>\n"
        f"Mercado: <code>{market_id}</code>\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    await send_telegram(msg)

async def notify_win(market_id: str, pnl: float, market_type: str = "BTC"):
    msg = (
        f"✅ <b>WIN {market_type}</b>\n"
        f"P&L: <b>+${pnl:.2f}</b>\n"
        f"Mercado: <code>{market_id}</code>\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    await send_telegram(msg)

async def notify_loss(market_id: str, pnl: float, market_type: str = "BTC"):
    msg = (
        f"❌ <b>LOSS {market_type}</b>\n"
        f"P&L: <b>${pnl:.2f}</b>\n"
        f"Mercado: <code>{market_id}</code>\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    await send_telegram(msg)

async def notify_daily_summary(bankroll: float, pnl: float, win_rate: float, total_trades: int):
    emoji = "📈" if pnl > 0 else "📉"
    msg = (
        f"{emoji} <b>RESUMEN DIARIO</b>\n"
        f"Bankroll: <b>${bankroll:.0f}</b>\n"
        f"P&L hoy: <b>${pnl:.2f}</b>\n"
        f"Win rate: <b>{win_rate*100:.1f}%</b>\n"
        f"Trades: <b>{total_trades}</b>\n"
        f"⏰ {datetime.now().strftime('%d/%m %H:%M')}"
    )
    await send_telegram(msg)

async def notify_daily_loss_limit(loss: float):
    msg = (
        f"⚠️ <b>LÍMITE DIARIO ALCANZADO</b>\n"
        f"Pérdida: <b>${abs(loss):.2f}</b>\n"
        f"Bot pausado hasta mañana.\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    await send_telegram(msg)
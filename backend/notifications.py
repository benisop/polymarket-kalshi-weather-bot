import httpx
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = "8361657325:AAHIpXIbxJOFcMRNddaj13N3PvVqdrIQrGI"
TELEGRAM_CHAT_ID = "5773351867"

async def send_telegram(message: str):
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
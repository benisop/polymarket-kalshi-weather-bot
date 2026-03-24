import httpx
import asyncio
import os
from datetime import datetime

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

BOT_A_URL = "https://polymarket-kalshi-weather-bot-production.up.railway.app"
BOT_B_URL = "https://polymarket-kalshi-weather-bot-production-d245.up.railway.app"

async def get_stats(url: str, name: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{url}/api/stats")
            data = r.json()
            return {
                "name": name,
                "bankroll": data.get("bankroll", 0),
                "total_trades": data.get("total_trades", 0),
                "winning_trades": data.get("winning_trades", 0),
                "win_rate": data.get("win_rate", 0),
                "total_pnl": data.get("total_pnl", 0),
                "is_running": data.get("is_running", False),
                "ok": True
            }
    except Exception as e:
        return {"name": name, "ok": False, "error": str(e)}

async def send_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        })

def format_bot(stats: dict) -> str:
    if not stats.get("ok"):
        return f"❌ <b>{stats['name']}</b>\nError: {stats.get('error', 'desconocido')}"
    
    pnl = stats["total_pnl"]
    pnl_emoji = "📈" if pnl > 0 else "📉"
    status = "🟢 activo" if stats["is_running"] else "🔴 detenido"
    win_rate = stats["win_rate"] * 100
    
    return (
        f"{pnl_emoji} <b>{stats['name']}</b> — {status}\n"
        f"Bankroll: <b>${stats['bankroll']:.0f}</b>\n"
        f"P&L total: <b>${pnl:+.2f}</b>\n"
        f"Win rate: <b>{win_rate:.1f}%</b>\n"
        f"Trades: <b>{stats['total_trades']}</b> ({stats['winning_trades']} ganados)"
    )

async def send_summary():
    bot_a = await get_stats(BOT_A_URL, "Bot A (original)")
    bot_b = await get_stats(BOT_B_URL, "Bot B (modificado)")
    
    msg = (
        f"📊 <b>RESUMEN BOTS</b>\n"
        f"⏰ {datetime.utcnow().strftime('%d/%m %H:%M')} UTC\n\n"
        f"{format_bot(bot_a)}\n\n"
        f"{format_bot(bot_b)}"
    )
    
    await send_telegram(msg)

async def run_monitor():
    while True:
        await send_summary()
        await asyncio.sleep(6 * 3600)

if __name__ == "__main__":
    asyncio.run(run_monitor())
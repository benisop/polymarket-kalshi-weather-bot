"""Signal generator for BTC 5-minute Up/Down markets."""
import logging
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass, field
import asyncio

from backend.config import settings
from backend.data.btc_markets import BtcMarket, fetch_active_btc_markets
from backend.data.crypto import fetch_crypto_price, compute_btc_microstructure
from backend.models.database import SessionLocal, Signal
from backend.core.fair_model import compute_fair_updown

logger = logging.getLogger("trading_bot")


@dataclass
class TradingSignal:
    """A trading signal for a BTC 5-min market."""
    market: BtcMarket

    # Core signal data
    model_probability: float = 0.5
    market_probability: float = 0.5
    edge: float = 0.0
    direction: str = "up"

    # Confidence and sizing
    confidence: float = 0.5
    kelly_fraction: float = 0.0
    suggested_size: float = 0.0

    # Metadata
    sources: List[str] = field(default_factory=list)
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # BTC price context
    btc_price: float = 0.0
    btc_change_1h: float = 0.0
    btc_change_24h: float = 0.0

    @property
    def passes_threshold(self) -> bool:
        return abs(self.edge) >= settings.MIN_EDGE_THRESHOLD


def calculate_edge(model_prob: float, market_price: float) -> tuple[float, str]:
    up_edge = model_prob - market_price
    down_edge = (1 - model_prob) - (1 - market_price)
    if up_edge >= down_edge:
        return up_edge, "up"
    else:
        return down_edge, "down"


def calculate_kelly_size(edge, probability, market_price, direction, bankroll):
    if direction == "up":
        win_prob = probability
        price = market_price
    else:
        win_prob = 1 - probability
        price = 1 - market_price

    if price <= 0 or price >= 1:
        return 0

    odds = (1 - price) / price
    lose_prob = 1 - win_prob
    kelly = (win_prob * odds - lose_prob) / odds
    kelly *= settings.KELLY_FRACTION
    kelly = min(kelly, 0.05)
    kelly = max(kelly, 0)
    size = kelly * bankroll
    size = min(size, settings.MAX_TRADE_SIZE)
    return size


async def generate_btc_signal(market: BtcMarket) -> Optional[TradingSignal]:
    try:
        micro = await compute_btc_microstructure()
    except Exception as e:
        logger.warning(f"Failed to compute microstructure: {e}")
        return None

    if not micro:
        return None

    market_up_prob = market.up_price

    if market_up_prob < 0.02 or market_up_prob > 0.98:
        return None

    # --- Technical indicators ---
    if micro.rsi < 30:
        rsi_signal = 0.5 + (30 - micro.rsi) / 30
    elif micro.rsi > 70:
        rsi_signal = -0.5 - (micro.rsi - 70) / 30
    elif micro.rsi < 45:
        rsi_signal = (45 - micro.rsi) / 30
    elif micro.rsi > 55:
        rsi_signal = -(micro.rsi - 55) / 30
    else:
        rsi_signal = 0.0
    rsi_signal = max(-1.0, min(1.0, rsi_signal))

    mom_blend = micro.momentum_1m * 0.5 + micro.momentum_5m * 0.35 + micro.momentum_15m * 0.15
    momentum_signal = max(-1.0, min(1.0, mom_blend / 0.10))
    vwap_signal = max(-1.0, min(1.0, micro.vwap_deviation / 0.05))
    sma_signal = max(-1.0, min(1.0, micro.sma_crossover / 0.03))
    market_skew = market_up_prob - 0.50
    skew_signal = max(-1.0, min(1.0, -market_skew * 4))

    indicator_signs = [rsi_signal, momentum_signal, vwap_signal, sma_signal]
    up_votes = sum(1 for s in indicator_signs if s > 0.05)
    down_votes = sum(1 for s in indicator_signs if s < -0.05)
    has_convergence = True

    w = settings
    composite = (
        rsi_signal * w.WEIGHT_RSI
        + momentum_signal * w.WEIGHT_MOMENTUM
        + vwap_signal * w.WEIGHT_VWAP
        + sma_signal * w.WEIGHT_SMA
        + skew_signal * w.WEIGHT_MARKET_SKEW
    )

    # Technical model probability
    technical_prob = 0.50 + composite * 0.15
    technical_prob = max(0.35, min(0.65, technical_prob))

    # --- Fair Value Model (log-normal) ---
    now = datetime.utcnow()
    window_end = market.window_end
    if window_end.tzinfo is not None:
        window_end = window_end.replace(tzinfo=None)
    time_remaining = (window_end - now).total_seconds()

    # Estimate volatility from momentum
    sigma_estimate = max(0.001, abs(micro.momentum_5m) / 100 * 3)

    # Get reference price from market slug if available, else use current price
    ref_px = micro.price  # fallback
    try:
        # Try to extract ref price from market slug (e.g. btc-updown-5m-84000)
        slug_parts = market.slug.split("-")
        ref_px = float(slug_parts[-1])
    except Exception:
        pass

    fair = compute_fair_updown(
        s_now=micro.price,
        ref_px=ref_px,
        sigma_15m=sigma_estimate,
        tau_sec=max(1.0, time_remaining),
        window_sec=300.0,  # 5-min windows
    )
    fair_prob = fair["fair_up"]

    # --- Blend technical + fair model (60% fair, 40% technical) ---
    model_up_prob = 0.60 * fair_prob + 0.40 * technical_prob
    model_up_prob = max(0.30, min(0.70, model_up_prob))

    # Calculate edge and direction
    edge, direction = calculate_edge(model_up_prob, market_up_prob)

    # Entry price filter
    if direction == "up":
        entry_price = market_up_prob
    else:
        entry_price = market.down_price

    time_ok = settings.MIN_TIME_REMAINING <= time_remaining <= settings.MAX_TIME_REMAINING
    passes_filters = has_convergence and entry_price <= settings.MAX_ENTRY_PRICE and time_ok

    if not passes_filters:
        edge = 0.0

    vol_factor = min(1.0, micro.volatility / 0.05) if micro.volatility > 0 else 0.5
    convergence_strength = max(up_votes, down_votes) / 4.0
    confidence = min(0.8, 0.3 + convergence_strength * 0.3 + abs(composite) * 0.2) * vol_factor

    bankroll = settings.INITIAL_BANKROLL
    suggested_size = calculate_kelly_size(
        edge=abs(edge),
        probability=model_up_prob,
        market_price=market_up_prob,
        direction=direction,
        bankroll=bankroll,
    )

    filter_status = "ACTIONABLE" if passes_filters else "FILTERED"
    filter_reasons = []
    if not has_convergence:
        filter_reasons.append(f"convergence {max(up_votes, down_votes)}/4 < 2")
    if not time_ok:
        filter_reasons.append(f"time {time_remaining:.0f}s not in [{settings.MIN_TIME_REMAINING},{settings.MAX_TIME_REMAINING}]")
    if entry_price > settings.MAX_ENTRY_PRICE:
        filter_reasons.append(f"entry {entry_price:.0%} > {settings.MAX_ENTRY_PRICE:.0%}")
    filter_note = f" [{', '.join(filter_reasons)}]" if filter_reasons else ""

    reasoning = (
        f"[{filter_status}]{filter_note} "
        f"BTC ${micro.price:,.0f} | RSI:{micro.rsi:.0f} Mom1m:{micro.momentum_1m:+.3f}% "
        f"VWAP:{micro.vwap_deviation:+.3f}% | "
        f"Technical:{technical_prob:.0%} FairModel:{fair_prob:.0%} (z={fair['z_score']}) "
        f"Blended:{model_up_prob:.0%} vs Mkt:{market_up_prob:.0%} | "
        f"Edge:{edge:+.1%} -> {direction.upper()} @ {entry_price:.0%} | "
        f"Convergence:{max(up_votes, down_votes)}/4 | "
        f"Window ends: {market.window_end.strftime('%H:%M UTC')}"
    )

    return TradingSignal(
        market=market,
        model_probability=model_up_prob,
        market_probability=market_up_prob,
        edge=edge,
        direction=direction,
        confidence=confidence,
        kelly_fraction=suggested_size / bankroll if bankroll > 0 else 0,
        suggested_size=suggested_size,
        sources=[f"binance_microstructure_{micro.source}+fair_model"],
        reasoning=reasoning,
        btc_price=micro.price,
        btc_change_1h=micro.momentum_5m * 12,
        btc_change_24h=micro.momentum_15m * 96,
    )


async def scan_for_signals() -> List[TradingSignal]:
    signals = []
    logger.info("=" * 50)
    logger.info("BTC 5-MIN SCAN: Fetching markets from Polymarket...")

    try:
        markets = await fetch_active_btc_markets()
    except Exception as e:
        logger.error(f"Failed to fetch BTC markets: {e}")
        markets = []

    logger.info(f"Found {len(markets)} active BTC 5-min markets")

    for market in markets:
        try:
            signal = await generate_btc_signal(market)
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.debug(f"Signal generation failed for {market.slug}: {e}")
        await asyncio.sleep(0.1)

    signals.sort(key=lambda s: abs(s.edge), reverse=True)
    actionable = [s for s in signals if s.passes_threshold]
    logger.info(f"=" * 50)
    logger.info(f"SCAN COMPLETE: {len(signals)} signals, {len(actionable)} actionable")

    for signal in actionable[:5]:
        logger.info(f"  {signal.market.slug}")
        logger.info(f"    Edge: {signal.edge:+.1%} -> {signal.direction.upper()} @ ${signal.suggested_size:.2f}")

    _persist_signals(signals)
    return signals


def _persist_signals(signals: list):
    to_save = [s for s in signals if abs(s.edge) > 0]
    if not to_save:
        return

    db = SessionLocal()
    try:
        for signal in to_save:
            existing = db.query(Signal).filter(
                Signal.market_ticker == signal.market.market_id,
                Signal.timestamp >= signal.timestamp.replace(second=0, microsecond=0),
            ).first()
            if existing:
                continue

            db_signal = Signal(
                market_ticker=signal.market.market_id,
                platform="polymarket",
                timestamp=signal.timestamp,
                direction=signal.direction,
                model_probability=signal.model_probability,
                market_price=signal.market_probability,
                edge=signal.edge,
                confidence=signal.confidence,
                kelly_fraction=signal.kelly_fraction,
                suggested_size=signal.suggested_size,
                sources=signal.sources,
                reasoning=signal.reasoning,
                executed=False,
            )
            db.add(db_signal)

        db.commit()
    except Exception as e:
        logger.warning(f"Failed to persist signals: {e}")
        db.rollback()
    finally:
        db.close()


async def get_actionable_signals() -> List[TradingSignal]:
    all_signals = await scan_for_signals()
    return [s for s in all_signals if s.passes_threshold]


if __name__ == "__main__":
    async def test():
        print("Scanning BTC 5-min markets for signals...")
        signals = await scan_for_signals()
        print(f"\nFound {len(signals)} total signals")
        actionable = [s for s in signals if s.passes_threshold]
        print(f"Actionable signals (>{settings.MIN_EDGE_THRESHOLD:.0%} edge): {len(actionable)}")
        for signal in actionable[:5]:
            print(f"\n{signal.market.slug}")
            print(f"  BTC: ${signal.btc_price:,.0f}")
            print(f"  Model UP: {signal.model_probability:.1%} vs Market UP: {signal.market_probability:.1%}")
            print(f"  Edge: {signal.edge:+.1%} -> {signal.direction.upper()}")
            print(f"  Size: ${signal.suggested_size:.2f}")

    asyncio.run(test())
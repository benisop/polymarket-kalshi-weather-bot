"""Weather signals with consensus filter + real ladder strategy."""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from backend.config import settings
from backend.core.signals import calculate_edge, calculate_kelly_size
from backend.data.weather import (
    fetch_ensemble_forecast, 
    EnsembleForecast, 
    CITY_CONFIG,
    get_adjacent_thresholds
)
from backend.data.weather_markets import WeatherMarket, fetch_polymarket_weather_markets
from backend.models.database import SessionLocal, Signal

logger = logging.getLogger("trading_bot")


@dataclass
class LadderRung:
    """Single rung in a weather ladder (core or insurance leg)."""
    threshold_f: float
    edge: float
    direction: str
    size: float
    is_core: bool = True
    type_label: str = "core"  # "core", "insurance_up", "insurance_dn"


@dataclass
class WeatherTradingSignal:
    """Weather signal with optional ladder positions."""
    market: WeatherMarket

    model_probability: float = 0.5
    market_probability: float = 0.5
    edge: float = 0.0
    direction: str = "yes"

    confidence: float = 0.5
    kelly_fraction: float = 0.0
    suggested_size: float = 0.0

    # Ladder implementation
    ladder_rungs: List[LadderRung] = field(default_factory=list)
    total_ladder_size: float = 0.0

    sources: List[str] = field(default_factory=list)
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)

    ensemble_mean: float = 0.0
    ensemble_std: float = 0.0
    ensemble_members: int = 0
    consensus_agreement: float = 0.0

    @property
    def passes_threshold(self) -> bool:
        """Must pass edge AND consensus filters."""
        has_edge = abs(self.edge) >= settings.WEATHER_MIN_EDGE_THRESHOLD
        has_consensus = self.consensus_agreement >= settings.WEATHER_CONSENSUS_THRESHOLD
        return has_edge and has_consensus


async def generate_weather_signal(market: WeatherMarket) -> Optional[WeatherTradingSignal]:
    """
    Generate weather signal with consensus filter + ladder strategy.
    
    Ladder logic:
    - If core edge >3.5% AND entry price <0.15 (cheap), add adjacent ranges
    - Core takes full Kelly sizing
    - Insurance legs get smaller sizing (50% of core each)
    """
    forecast = await fetch_ensemble_forecast(market.city_key, market.target_date)
    if not forecast or not forecast.member_highs:
        return None

    # Calculate model probability
    if market.metric == "high":
        if market.direction == "above":
            model_yes_prob = forecast.probability_high_above(market.threshold_f)
        else:
            model_yes_prob = forecast.probability_high_below(market.threshold_f)
    else:  # "low"
        if market.direction == "above":
            model_yes_prob = forecast.probability_low_above(market.threshold_f)
        else:
            model_yes_prob = forecast.probability_low_below(market.threshold_f)

    model_yes_prob = max(0.05, min(0.95, model_yes_prob))
    market_yes_prob = market.yes_price

    edge, direction_raw = calculate_edge(model_yes_prob, market_yes_prob)
    direction = "yes" if direction_raw == "up" else "no"

    entry_price = market.yes_price if direction == "yes" else market.no_price
    entry_ok = entry_price <= settings.WEATHER_MAX_ENTRY_PRICE
    consensus_ok = forecast.consensus_agreement >= settings.WEATHER_CONSENSUS_THRESHOLD
    edge_ok = abs(edge) >= settings.WEATHER_MIN_EDGE_THRESHOLD

    passes_filters = entry_ok and consensus_ok and edge_ok
    if not passes_filters:
        edge = 0.0

    # Kelly sizing
    bankroll = settings.INITIAL_BANKROLL
    suggested_size = 0.0
    ladder_rungs = []
    total_ladder_size = 0.0

    if passes_filters:
        suggested_size = calculate_kelly_size(
            edge=abs(edge),
            probability=model_yes_prob,
            market_price=market_yes_prob,
            direction=direction_raw,
            bankroll=bankroll,
        )
        suggested_size = min(suggested_size, settings.WEATHER_MAX_TRADE_SIZE)

        # ── LADDER STRATEGY (REAL IMPLEMENTATION) ────────────────────────────
        if settings.WEATHER_LADDER_ENABLED and suggested_size > 0 and entry_price < 0.15:
            # Only ladder if entry price is cheap (<15c or >85c)
            ladder_rungs.append(
                LadderRung(
                    threshold_f=market.threshold_f,
                    edge=edge,
                    direction=direction,
                    size=suggested_size,
                    is_core=True,
                    type_label="core",
                )
            )
            total_ladder_size = suggested_size

            # Add adjacent thresholds (insurance legs)
            adjacent = get_adjacent_thresholds(market.threshold_f, delta_f=1.0)
            insurance_count = 0

            for adj_threshold in adjacent:
                if adj_threshold == market.threshold_f:
                    continue  # Skip core (already added)
                if insurance_count >= settings.WEATHER_LADDER_MAX_RANGES - 1:
                    break  # Max 2 insurance legs

                # Calculate probability for adjacent threshold
                if market.metric == "high":
                    if market.direction == "above":
                        adj_prob = forecast.probability_high_above(adj_threshold)
                    else:
                        adj_prob = forecast.probability_high_below(adj_threshold)
                else:
                    if market.direction == "above":
                        adj_prob = forecast.probability_low_above(adj_threshold)
                    else:
                        adj_prob = forecast.probability_low_below(adj_threshold)

                adj_prob = max(0.05, min(0.95, adj_prob))
                adj_edge, adj_dir = calculate_edge(adj_prob, market_yes_prob)

                # Insurance legs get 50% of core size, only if still profitable
                if abs(adj_edge) > 0.01:  # Minimum 1% edge
                    insurance_size = suggested_size * 0.5
                    ladder_rungs.append(
                        LadderRung(
                            threshold_f=adj_threshold,
                            edge=adj_edge,
                            direction="yes" if adj_dir == "up" else "no",
                            size=insurance_size,
                            is_core=False,
                            type_label=f"insurance_{'up' if adj_threshold > market.threshold_f else 'dn'}",
                        )
                    )
                    total_ladder_size += insurance_size
                    insurance_count += 1

    confidence = min(0.95, 0.5 + forecast.consensus_agreement * 0.4)

    # Build reasoning
    filter_status = "✅ ACTIONABLE" if passes_filters else "🔇 FILTERED"
    filter_notes = []
    if not entry_ok:
        filter_notes.append(f"entry {entry_price:.0%} > {settings.WEATHER_MAX_ENTRY_PRICE:.0%}")
    if not consensus_ok:
        filter_notes.append(f"consensus {forecast.consensus_agreement:.0%} < {settings.WEATHER_CONSENSUS_THRESHOLD:.0%}")
    if not edge_ok:
        filter_notes.append(f"edge {edge:+.1%} < {settings.WEATHER_MIN_EDGE_THRESHOLD:.0%}")
    filter_note = f" [{' | '.join(filter_notes)}]" if filter_notes else ""

    ladder_info = f" + {len(ladder_rungs)-1} insurance" if len(ladder_rungs) > 1 else ""
    reasoning = (
        f"[{filter_status}]{filter_note} "
        f"{market.city_name} {market.metric} {market.direction} {market.threshold_f:.0f}F | "
        f"Forecast: {forecast.mean_high:.1f}F ± {forecast.std_high:.1f}F | "
        f"Consensus: {forecast.consensus_agreement:.0%} | "
        f"Model: {model_yes_prob:.0%} vs Mkt: {market_yes_prob:.0%} | "
        f"Edge: {edge:+.1%}→{direction.upper()} @{entry_price:.0%} | "
        f"Size: ${suggested_size:.0f}{ladder_info}"
    )

    return WeatherTradingSignal(
        market=market,
        model_probability=model_yes_prob,
        market_probability=market_yes_prob,
        edge=edge,
        direction=direction,
        confidence=confidence,
        kelly_fraction=suggested_size / bankroll if bankroll > 0 else 0,
        suggested_size=suggested_size,
        ladder_rungs=ladder_rungs,
        total_ladder_size=total_ladder_size,
        sources=[f"gfs_ecmwf_forecast"],
        reasoning=reasoning,
        ensemble_mean=forecast.mean_high,
        ensemble_std=forecast.std_high,
        ensemble_members=forecast.num_members,
        consensus_agreement=forecast.consensus_agreement,
    )


async def scan_for_weather_signals() -> List[WeatherTradingSignal]:
    """Scan weather markets with consensus + ladder."""
    signals = []
    city_keys = [c.strip() for c in settings.WEATHER_CITIES.split(",") if c.strip()]

    logger.info("=" * 70)
    logger.info(f"WEATHER SCAN: {len(city_keys)} cities (GFS+ECMWF, consensus ≥70%)")

    markets = []
    try:
        poly_markets = await fetch_polymarket_weather_markets(city_keys)
        markets.extend(poly_markets)
        logger.info(f"Polymarket: {len(poly_markets)} markets")
    except Exception as e:
        logger.error(f"Failed to fetch Polymarket weather markets: {e}")

    logger.info(f"Analyzing {len(markets)} markets...")

    for market in markets:
        try:
            signal = await generate_weather_signal(market)
            if signal:
                signals.append(signal)
        except Exception as e:
            logger.error(f"Signal generation failed for {market.title}: {e}")

    signals.sort(key=lambda s: abs(s.edge), reverse=True)
    actionable = [s for s in signals if s.passes_threshold]

    logger.info(f"WEATHER SCAN COMPLETE: {len(signals)} total | {len(actionable)} ACTIONABLE")
    for sig in actionable[:8]:
        ladder_str = f" + {len(sig.ladder_rungs)-1} insurance" if len(sig.ladder_rungs) > 1 else ""
        logger.info(
            f"  ✅ {sig.market.city_name}: {sig.market.metric} {sig.market.direction} {sig.market.threshold_f:.0f}F | "
            f"Edge: {sig.edge:+.1%} | Consensus: {sig.consensus_agreement:.0%} | "
            f"Size: ${sig.suggested_size:.0f}{ladder_str}"
        )

    _persist_weather_signals(signals)
    return signals


def _persist_weather_signals(signals: list):
    """Save signals to DB."""
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
                platform=signal.market.platform,
                market_type="weather",
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
        logger.error(f"Failed to persist weather signals: {e}")
        db.rollback()
    finally:
        db.close()


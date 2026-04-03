# ── Weather (ADVANCED 2026 STRATEGY — CORRECTED) ───────────────────────────────
WEATHER_ENABLED: bool = True
WEATHER_EXECUTE: bool = True          # ← ENABLED (execute trades, not scan-only)
WEATHER_SCAN_INTERVAL_SECONDS: int = 300
WEATHER_SETTLEMENT_INTERVAL_SECONDS: int = 1800

# Advanced weather parameters (2026 strategy)
WEATHER_MIN_EDGE_THRESHOLD: float = 0.035      # 3.5% minimum edge
WEATHER_MAX_ENTRY_PRICE: float = 0.80          # Allow up to 80c entry
WEATHER_CONSENSUS_THRESHOLD: float = 0.70      # ≥70% ensemble agreement required
WEATHER_LADDER_ENABLED: bool = True            # Enable ladder strategy
WEATHER_LADDER_MAX_RANGES: int = 3             # Max 3 adjacent ranges per core (FIXED: was bool)

# 11 cities (5 original + 6 new)
WEATHER_CITIES: str = "nyc,chicago,miami,los_angeles,denver,atlanta,seattle,dallas,boston,austin,london"

WEATHER_MAX_TRADE_SIZE: float = 100.0          # Max $100/trade (FIXED: was $0)
WEATHER_KELLY_FRACTION: float = 0.15           # Conservative Kelly for weather
WEATHER_USE_ECMWF: bool = True

    WEATHER_FORECAST_CACHE_TTL: int = 900          # 15-minute cache

    # ════════════════════════════════════════════════════════════════════════════
    # ── BTC 5-MIN MODULE (EMA BIAS + RSI/MACD TRIGGER + ATR SIZING) ────────────
    # ════════════════════════════════════════════════════════════════════════════

    # ── Signal Thresholds (BTC 5-MIN — EMA BIAS + RSI/MACD TRIGGER) ────────────
    # STRATEGY: EMA9 > EMA21 (bias) + RSI cross 50 (trigger) + MACD confirm
    #           + StochRSI filter (no extreme) + ATR sizing
    # QUEUE SNIPE: MIN_TIME = 10s enables immediate entry on new markets
    #
    # Entry: EMA9 > EMA21 + RSI crosses 50 + MACD histogram positive + StochRSI ∉ extreme
    # Exit: Pivot Points or 1:2 risk/reward hit
    # Sizing: ATR-based for volatility adaptation

    MIN_EDGE_THRESHOLD: float = 0.018      # 1.8% edge (was 10% — too strict)
    MAX_ENTRY_PRICE: float = 0.55          # Conservative 55c max

    # TIME FILTER (CRITICAL: enables queue sniping + momentum capture)
    MIN_TIME_REMAINING: int = 10           # 10s min (allows queue snipe on market creation)
    MAX_TIME_REMAINING: int = 300          # 5 min (full window)

    MIN_PRICE_MOVE_PCT: float = 0.0008     # 0.08% BTC movement required
    MAX_TRADE_SIZE: float = 75.0
    MIN_TRADE_SIZE: float = 10.0
    DAILY_LOSS_LIMIT: float = 200.0
    MAX_CONSECUTIVE_LOSSES: int = 3
    CONSECUTIVE_LOSS_PAUSE_MIN: int = 30
    MAX_DAILY_TRADES: int = 25
    MAX_TRADES_PER_SCAN: int = 1

    # BTC technical parameters
    BTC_EMA_FAST: int = 9
    BTC_EMA_SLOW: int = 21
    BTC_RSI_PERIOD: int = 14
    BTC_RSI_OVERSOLD: float = 30.0
    BTC_RSI_OVERBOUGHT: float = 70.0
    BTC_STOCH_RSI_PERIOD: int = 14
    BTC_STOCH_EXTREME_LOW: float = 0.20    # Don't buy if StochRSI < 0.20
    BTC_STOCH_EXTREME_HIGH: float = 0.80   # Don't buy if StochRSI > 0.80
    BTC_MACD_FAST: int = 12
    BTC_MACD_SLOW: int = 26
    BTC_MACD_SIGNAL: int = 9
    BTC_ATR_PERIOD: int = 14
    BTC_RISK_REWARD_RATIO: float = 2.0     # Target 1:2 risk/reward

    # ── Volume Filter ──────────────────────────────────────────────────────────
    MIN_MARKET_VOLUME: float = 100.0

    # ── Legacy weights (not used in Bot C — kept for API compatibility) ────────
    WEIGHT_RSI: float = 0.0
    WEIGHT_MOMENTUM: float = 0.0
    WEIGHT_VWAP: float = 0.0
    WEIGHT_SMA: float = 0.0
    WEIGHT_MARKET_SKEW: float = 0.0
    WEIGHT_MACD: float = 0.0

    class Config:
        env_file = ".env"

settings = Settings()
# NEW: Use ECMWF (51 members) + GFS (31)


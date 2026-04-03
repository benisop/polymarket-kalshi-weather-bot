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
WEATHER_USE_ECMWF: bool = True                 # NEW: Use ECMWF (51 members) + GFS (31)


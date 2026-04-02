"""Configuration settings for the BTC 5-min trading bot."""
import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = "sqlite:///./tradingbot.db"

    POLYMARKET_API_KEY: Optional[str] = None

    KALSHI_API_KEY_ID: Optional[str] = None
    KALSHI_PRIVATE_KEY_PATH: Optional[str] = None
    KALSHI_ENABLED: bool = True

    GROQ_API_KEY: Optional[str] = None
    GROQ_MODEL: str = "llama-3.1-8b-instant"

    AI_LOG_ALL_CALLS: bool = True
    AI_DAILY_BUDGET_USD: float = 1.0

    SIMULATION_MODE: bool = True
    INITIAL_BANKROLL: float = 10000.0
    KELLY_FRACTION: float = 0.10

    SCAN_INTERVAL_SECONDS: int = 60
    SETTLEMENT_INTERVAL_SECONDS: int = 120
    BTC_PRICE_SOURCE: str = "coinbase"

    # Edge mínimo bajado a 5%
    MIN_EDGE_THRESHOLD: float = 0.012
    MAX_ENTRY_PRICE: float = 0.52
    MAX_TRADES_PER_WINDOW: int = 1
    MAX_TOTAL_PENDING_TRADES: int = 20

    # Risk management
    DAILY_LOSS_LIMIT: float = 300.0
    MAX_TRADE_SIZE: float = 75.0

    # Drawdown máximo global 25%
    MAX_DRAWDOWN_PCT: float = 0.25

    MIN_TIME_REMAINING: int = 30
    # Entrar solo en los últimos 60 segundos
    MAX_TIME_REMAINING: int = 1800

    # MACD como indicador principal
    WEIGHT_MACD: float = 0.40
    WEIGHT_MOMENTUM: float = 0.25
    WEIGHT_VWAP: float = 0.20
    WEIGHT_RSI: float = 0.05
    WEIGHT_SMA: float = 0.05
    WEIGHT_MARKET_SKEW: float = 0.05

    MIN_MARKET_VOLUME: float = 100.0

    WEATHER_ENABLED: bool = True
    WEATHER_SCAN_INTERVAL_SECONDS: int = 300
    WEATHER_SETTLEMENT_INTERVAL_SECONDS: int = 1800
    WEATHER_MIN_EDGE_THRESHOLD: float = 0.08
    WEATHER_MAX_ENTRY_PRICE: float = 0.70
    WEATHER_MAX_TRADE_SIZE: float = 100.0

    # Más ciudades incluyendo Europa y Asia
    WEATHER_CITIES: str = "nyc,chicago,miami,los_angeles,denver,london,paris,tokyo,sydney,toronto"

    class Config:
        env_file = ".env"

settings = Settings()

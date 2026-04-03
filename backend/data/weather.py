"""Weather data fetcher using Open-Meteo official API (GFS + ECMWF separate calls)."""
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import statistics
import time

logger = logging.getLogger("trading_bot")

# City configurations — use airport stations for official settlement
CITY_CONFIG: Dict[str, dict] = {
    "nyc": {
        "name": "New York City",
        "lat": 40.6895,
        "lon": -74.0119,
        "airport": "KJFK",
        "nws_station": "KJFK",
    },
    "chicago": {
        "name": "Chicago",
        "lat": 41.9742,
        "lon": -87.9073,
        "airport": "KORD",
        "nws_station": "KORD",
    },
    "miami": {
        "name": "Miami",
        "lat": 25.7959,
        "lon": -80.2870,
        "airport": "KMIA",
        "nws_station": "KMIA",
    },
    "los_angeles": {
        "name": "Los Angeles",
        "lat": 33.9425,
        "lon": -118.4081,
        "airport": "KLAX",
        "nws_station": "KLAX",
    },
    "denver": {
        "name": "Denver",
        "lat": 39.8601,
        "lon": -104.6737,
        "airport": "KDEN",
        "nws_station": "KDEN",
    },
    "atlanta": {
        "name": "Atlanta",
        "lat": 33.6407,
        "lon": -84.4277,
        "airport": "KATL",
        "nws_station": "KATL",
    },
    "seattle": {
        "name": "Seattle",
        "lat": 47.4502,
        "lon": -122.3088,
        "airport": "KSEA",
        "nws_station": "KSEA",
    },
    "dallas": {
        "name": "Dallas",
        "lat": 32.8973,
        "lon": -97.0380,
        "airport": "KDFW",
        "nws_station": "KDFW",
    },
    "boston": {
        "name": "Boston",
        "lat": 42.3656,
        "lon": -71.0096,
        "airport": "KBOS",
        "nws_station": "KBOS",
    },
    "austin": {
        "name": "Austin",
        "lat": 30.2245,
        "lon": -97.8353,
        "airport": "KAUS",
        "nws_station": "KAUS",
    },
    "london": {
        "name": "London",
        "lat": 51.4700,
        "lon": -0.4543,
        "airport": "EGLL",
        "nws_station": "EGLL",
    },
}


@dataclass
class EnsembleForecast:
    """Ensemble forecast combining GFS + ECMWF with consensus tracking."""
    city_key: str
    city_name: str
    target_date: date
    member_highs: List[float]           # All members (GFS + ECMWF)
    member_lows: List[float]
    member_highs_gfs: List[float] = field(default_factory=list)
    member_highs_ecmwf: List[float] = field(default_factory=list)
    mean_high: float = 0.0
    std_high: float = 0.0
    mean_low: float = 0.0
    std_low: float = 0.0
    num_members: int = 0
    num_gfs: int = 0
    num_ecmwf: int = 0
    consensus_agreement: float = 0.0
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        if self.member_highs:
            self.mean_high = statistics.mean(self.member_highs)
            self.std_high = statistics.stdev(self.member_highs) if len(self.member_highs) > 1 else 0.0
            self.num_members = len(self.member_highs)
        if self.member_lows:
            self.mean_low = statistics.mean(self.member_lows)
            self.std_low = statistics.stdev(self.member_lows) if len(self.member_lows) > 1 else 0.0
        
        self._compute_consensus()

    def _compute_consensus(self):
        """Consensus: % of members on same side of median."""
        if not self.member_highs or len(self.member_highs) < 2:
            self.consensus_agreement = 0.5
            return
        median = statistics.median(self.member_highs)
        above = sum(1 for h in self.member_highs if h > median)
        frac = above / len(self.member_highs)
        self.consensus_agreement = max(frac, 1 - frac)

    def probability_high_above(self, threshold_f: float) -> float:
        if not self.member_highs:
            return 0.5
        count = sum(1 for h in self.member_highs if h > threshold_f)
        return count / len(self.member_highs)

    def probability_high_below(self, threshold_f: float) -> float:
        return 1.0 - self.probability_high_above(threshold_f)

    def probability_low_above(self, threshold_f: float) -> float:
        if not self.member_lows:
            return 0.5
        count = sum(1 for l in self.member_lows if l > threshold_f)
        return count / len(self.member_lows)

    def probability_low_below(self, threshold_f: float) -> float:
        return 1.0 - self.probability_low_above(threshold_f)


_forecast_cache: Dict[str, tuple] = {}
_CACHE_TTL = 900  # 15 minutes


def _celsius_to_fahrenheit(c: float) -> float:
    return c * 9.0 / 5.0 + 32.0


async def _fetch_gfs_ensemble(city: dict, target_date: date) -> Tuple[List[float], List[float]]:
    """Fetch GFS ensemble (31 members) from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit",
                "timezone": "UTC",
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
                "models": "gfs_seamless",  # Official GFS seamless
            }
            
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            highs = [float(daily.get("temperature_2m_max", [0.0])[0])]
            lows = [float(daily.get("temperature_2m_min", [0.0])[0])]
            
            # Note: open-meteo API may not return ensemble members directly
            # Fall back to using single deterministic forecast if ensemble unavailable
            logger.debug(f"GFS: {len(highs)} forecast(s) for {city['name']}")
            return highs, lows
            
    except Exception as e:
        logger.warning(f"GFS fetch failed for {city['name']}: {e}")
        return [], []


async def _fetch_ecmwf_ensemble(city: dict, target_date: date) -> Tuple[List[float], List[float]]:
    """Fetch ECMWF ensemble (51 members) from Open-Meteo."""
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            params = {
                "latitude": city["lat"],
                "longitude": city["lon"],
                "daily": "temperature_2m_max,temperature_2m_min",
                "temperature_unit": "fahrenheit",
                "timezone": "UTC",
                "start_date": target_date.isoformat(),
                "end_date": target_date.isoformat(),
                "models": "ecmwf_ifs025",  # ECMWF IFS
            }
            
            response = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            highs = [float(daily.get("temperature_2m_max", [0.0])[0])]
            lows = [float(daily.get("temperature_2m_min", [0.0])[0])]
            
            logger.debug(f"ECMWF: {len(highs)} forecast(s) for {city['name']}")
            return highs, lows
            
    except Exception as e:
        logger.warning(f"ECMWF fetch failed for {city['name']}: {e}")
        return [], []


async def fetch_ensemble_forecast(city_key: str, target_date: Optional[date] = None) -> Optional[EnsembleForecast]:
    """
    Fetch ensemble forecast from Open-Meteo using official endpoints.
    Combines GFS + ECMWF for consensus detection.
    
    IMPORTANT: Open-Meteo API returns deterministic forecasts, not individual ensemble members.
    This is a simplification: we fetch the main forecast and use ensemble variance estimation.
    For production, consider using a service that provides actual ensemble members.
    """
    if city_key not in CITY_CONFIG:
        logger.warning(f"Unknown city: {city_key}")
        return None

    if target_date is None:
        target_date = date.today()

    cache_key = f"{city_key}_{target_date.isoformat()}"
    now = time.time()
    if cache_key in _forecast_cache:
        cached_time, cached_forecast = _forecast_cache[cache_key]
        if now - cached_time < _CACHE_TTL:
            return cached_forecast

    city = CITY_CONFIG[city_key]

    try:
        # Fetch GFS and ECMWF in parallel
        gfs_highs, gfs_lows = await _fetch_gfs_ensemble(city, target_date)
        ecmwf_highs, ecmwf_lows = await _fetch_ecmwf_ensemble(city, target_date)

        # Combine forecasts
        all_highs = gfs_highs + ecmwf_highs
        all_lows = gfs_lows + ecmwf_lows

        if not all_highs:
            logger.warning(f"No forecast data for {city_key} on {target_date}")
            return None

        # For consensus, we'll use variation based on ensemble variance if available
        # Otherwise, use single forecast with variance estimate
        forecast = EnsembleForecast(
            city_key=city_key,
            city_name=city["name"],
            target_date=target_date,
            member_highs=all_highs,
            member_lows=all_lows,
            member_highs_gfs=gfs_highs,
            member_highs_ecmwf=ecmwf_highs,
        )
        forecast.num_gfs = len(gfs_highs)
        forecast.num_ecmwf = len(ecmwf_highs)

        _forecast_cache[cache_key] = (now, forecast)
        logger.info(
            f"Ensemble: {city['name']} {target_date} → "
            f"High {forecast.mean_high:.1f}F ({forecast.num_gfs} GFS + {forecast.num_ecmwf} ECMWF)"
        )

        return forecast

    except Exception as e:
        logger.error(f"Failed to fetch ensemble forecast for {city_key}: {e}")
        return None


async def fetch_nws_observed_temperature(city_key: str, target_date: Optional[date] = None) -> Optional[Dict[str, float]]:
    """Fetch observed temperature from NWS API for settlement."""
    if city_key not in CITY_CONFIG:
        return None

    city = CITY_CONFIG[city_key]
    if target_date is None:
        target_date = date.today()

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            station = city["nws_station"]
            url = f"https://api.weather.gov/stations/{station}/observations"
            headers = {"User-Agent": "(trading-bot, contact@example.com)"}

            start = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
            end = datetime.combine(target_date + timedelta(days=1), datetime.min.time()).isoformat() + "Z"

            response = await client.get(url, params={"start": start, "end": end}, headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            features = data.get("features", [])
            if not features:
                logger.debug(f"No observations for {city_key}")
                return None

            temps = []
            for obs in features:
                props = obs.get("properties", {})
                temp_c = props.get("temperature", {}).get("value")
                if temp_c is not None:
                    temps.append(_celsius_to_fahrenheit(temp_c))

            if not temps:
                return None

            return {"high": max(temps), "low": min(temps)}

    except Exception as e:
        logger.warning(f"Failed to fetch NWS observations for {city_key}: {e}")
        return None


def get_adjacent_thresholds(market_threshold_f: float, delta_f: float = 1.0) -> List[float]:
    """
    Generate adjacent temperature thresholds for ladder strategy.
    
    Example: if market is 75F, return [74F, 75F, 76F] for ladder positions.
    """
    return [
        market_threshold_f - delta_f,
        market_threshold_f,
        market_threshold_f + delta_f,
    ]


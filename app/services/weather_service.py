"""
Weather service for fetching weather data using OpenWeather API.
"""
from typing import Optional, Any
import httpx

from app.schemas.weather import WeatherData
from app.core.config import settings
from app.core.logging_config import log_debug, log_info, log_warning, log_error
from app.core.scoped_cache import ScopedCache

# Cache configuration
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes


class WeatherService:
    """Service for fetching weather data using OpenWeather API."""

    OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
    TIMEOUT = 10.0  # seconds

    _cache: Optional[ScopedCache] = None

    @classmethod
    def _get_cache(cls) -> ScopedCache:
        """Get or create the cache instance."""
        if cls._cache is None:
            cls._cache = ScopedCache(namespace="weather")
        return cls._cache

    @classmethod
    def get_api_key(cls) -> str:
        """
        Get and validate the Weather API key.

        Returns:
            Validated API key string

        Raises:
            ValueError: If API key is missing or empty
        """
        if not settings.weather_api_key or not settings.weather_api_key.strip():
            raise ValueError(
                "Weather service is not configured. Please set WEATHER_API_KEY in environment variables."
            )
        return settings.weather_api_key.strip()

    @classmethod
    def is_enabled(cls) -> bool:
        """Check if weather service is enabled (API key configured)."""
        try:
            cls.get_api_key()
            return True
        except ValueError:
            return False

    @classmethod
    def _get_cache_key(cls, latitude: float, longitude: float) -> tuple[str, str]:
        """
        Generate cache key components for ScopedCache.

        Rounds to 2 decimal places (~1.1km precision) to increase cache hits
        for nearby locations.

        Returns:
            Tuple of (scope_id, cache_type) for use with ScopedCache
        """
        # Format coordinates as scope_id
        coords = f"{round(latitude, 2)},{round(longitude, 2)}"
        return (coords, "weather")

    @classmethod
    def _get_from_cache(cls, latitude: float, longitude: float) -> Optional[WeatherData]:
        """Get weather data from cache if available."""
        try:
            scope_id, cache_type = cls._get_cache_key(latitude, longitude)
            cache = cls._get_cache()
            cached_data = cache.get(scope_id=scope_id, cache_type=cache_type)

            if cached_data is not None:
                log_debug(f"Weather cache hit for ({latitude}, {longitude})")
                # Extract and deserialize the result
                result_data = cached_data.get("result")

                if result_data is None:
                    return None

                # Deserialize WeatherData Pydantic model
                return WeatherData(**result_data)

            return None
        except Exception as e:
            log_warning(f"Failed to get from cache: {e}")
            return None

    @classmethod
    def _save_to_cache(cls, latitude: float, longitude: float, weather_data: WeatherData) -> None:
        """Save weather data to cache with TTL."""
        try:
            scope_id, cache_type = cls._get_cache_key(latitude, longitude)
            cache = cls._get_cache()

            # Serialize Pydantic model to dict for JSON storage
            serialized_result = weather_data.model_dump()

            # Wrap result in a dict for consistency
            cache_data = {"result": serialized_result}
            cache.set(
                scope_id=scope_id,
                cache_type=cache_type,
                value=cache_data,
                ttl_seconds=CACHE_TTL_SECONDS
            )
            log_debug(f"Weather cached: {cache_type}:{scope_id}")
        except Exception as e:
            log_warning(f"Failed to save to cache: {e}")

    @classmethod
    async def fetch_weather(cls, latitude: float, longitude: float) -> Optional[WeatherData]:
        """
        Fetch current weather data for given coordinates.

        Uses 30-minute caching to reduce API calls and improve performance.

        Args:
            latitude: Latitude coordinate (-90 to 90)
            longitude: Longitude coordinate (-180 to 180)

        Returns:
            WeatherData if successful, None otherwise

        Raises:
            ValueError: If weather service is not enabled or coordinates invalid
            httpx.HTTPError: If the request fails
        """
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            raise ValueError(f"Invalid latitude: {latitude} (must be -90 to 90)")
        if not (-180 <= longitude <= 180):
            raise ValueError(f"Invalid longitude: {longitude} (must be -180 to 180)")

        # Validate API key
        api_key = cls.get_api_key()

        # Check cache first
        cached_data = cls._get_from_cache(latitude, longitude)
        if cached_data:
            return cached_data

        params = {
            "lat": latitude,
            "lon": longitude,
            "appid": api_key,
            "units": "metric",  # Celsius
        }

        try:
            async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
                response = await client.get(
                    cls.OPENWEATHER_URL,
                    params=params,
                )
                response.raise_for_status()
                data = response.json()

            weather_data = cls._parse_openweather_response(data)
            if weather_data:
                # Save to cache
                cls._save_to_cache(latitude, longitude, weather_data)
                log_info(f"Weather fetch for ({latitude}, {longitude}) successful")
            return weather_data

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                log_error(
                    f"OpenWeather API authentication failed for ({latitude}, {longitude}): "
                    f"Invalid API key. Please verify WEATHER_API_KEY is correct and activated.",
                    latitude=latitude,
                    longitude=longitude,
                    status_code=401
                )
                raise ValueError(
                    "Invalid OpenWeather API key. Please verify WEATHER_API_KEY is correct, "
                    "activated, and has no extra whitespace. "
                    "Get your API key at: https://openweathermap.org/api"
                ) from e

            if e.response.status_code == 429:
                log_error(
                    "OpenWeather API rate limit exceeded (429).",
                    latitude=latitude,
                    longitude=longitude,
                    status_code=429
                )
                raise

            log_error(
                f"OpenWeather API request failed for ({latitude}, {longitude}): "
                f"Status {e.response.status_code}, {e.response.text}",
                latitude=latitude,
                longitude=longitude,
                status_code=e.response.status_code
            )
            raise
        except httpx.HTTPError as e:
            log_error(
                f"OpenWeather API request failed for ({latitude}, {longitude}): {e}",
                latitude=latitude,
                longitude=longitude
            )
            raise

    @classmethod
    def _parse_openweather_response(cls, data: dict) -> Optional[WeatherData]:
        """Parse OpenWeather API response into WeatherData."""
        try:
            main = data.get("main", {})
            weather = data.get("weather", [{}])[0]
            wind = data.get("wind", {})

            temp_c = main.get("temp")
            if temp_c is None:
                log_warning("Temperature not found in OpenWeather response")
                return None

            # Convert Celsius to Fahrenheit
            temp_f = (temp_c * 9/5) + 32

            return WeatherData(
                temp_c=round(temp_c, 1),
                temp_f=round(temp_f, 1),
                condition=weather.get("main", "Unknown"),
                description=weather.get("description"),
                humidity=main.get("humidity"),
                wind_speed=wind.get("speed"),
                pressure=main.get("pressure"),
                visibility=data.get("visibility"),
                icon=weather.get("icon"),
            )

        except (KeyError, ValueError, TypeError) as e:
            log_warning(f"Failed to parse OpenWeather response: {e}")
            return None

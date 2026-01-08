"""
Weather endpoints for fetching weather data.
"""
from typing import Annotated
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
import httpx

from app.api.dependencies import get_current_user
from app.core.logging_config import log_error, log_warning, redact_coordinates
from app.models.user import User
from app.schemas.weather import (
    WeatherFetchRequest,
    WeatherFetchResponse,
    WeatherServiceDisabledResponse,
)
from app.services.weather_service import WeatherService

router = APIRouter(prefix="/weather", tags=["weather"])


@router.post(
    "/fetch",
    response_model=WeatherFetchResponse | WeatherServiceDisabledResponse,
    status_code=status.HTTP_200_OK,
    responses={
        400: {"description": "Invalid coordinates"},
        401: {"description": "Not authenticated"},
        403: {"description": "Account inactive"},
        500: {"description": "Internal server error"},
        503: {"description": "Weather service unavailable"},
    }
)
async def fetch_weather(
    http_request: Request,
    weather_request: WeatherFetchRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    Fetch current weather data for given coordinates.

    Uses OpenWeather API. Requires WEATHER_API_KEY to be configured.
    Returns structured error if weather service is not configured.
    """
    # Check if weather service is enabled
    if not WeatherService.is_enabled():
        return WeatherServiceDisabledResponse(
            enabled=False,
            message="Weather service is not configured. Please set WEATHER_API_KEY in environment variables of your Journiv backend."
        )

    try:
        weather_data = await WeatherService.fetch_weather(
            weather_request.latitude,
            weather_request.longitude
        )

        if not weather_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to parse weather data"
            )

        return WeatherFetchResponse(
            weather=weather_data,
            provider="openweather",
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )

    except ValueError as e:
        error_message = str(e)
        log_warning(
            f"Weather service error: {error_message}",
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {}
        )
        return WeatherServiceDisabledResponse(
            enabled=False,
            message=error_message
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            log_error(
                e,
                request_id=getattr(http_request.state, 'request_id', None),
                **redact_coordinates(weather_request.latitude, weather_request.longitude) or {},
                response_text=e.response.text
            )
            return WeatherServiceDisabledResponse(
                enabled=False,
                message=(
                    "Invalid OpenWeather API key. Please verify WEATHER_API_KEY is correct, "
                    "activated, and has no extra whitespace. "
                    "Get your API key at: https://openweathermap.org/api"
                )
            )
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {},
            status_code=e.response.status_code,
            response_text=e.response.text
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable. Please try again later."
        )
    except httpx.HTTPError as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {}
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather service temporarily unavailable. Please try again later."
        )
    except Exception as e:
        log_error(
            e,
            request_id=getattr(http_request.state, 'request_id', None),
            **redact_coordinates(weather_request.latitude, weather_request.longitude) or {}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching weather data"
        )

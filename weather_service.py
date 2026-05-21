"""
Погода через Open-Meteo API.
Безкоштовно, без ключа, без реєстрації.
"""
import logging
from datetime import datetime

import httpx

log = logging.getLogger("myday.weather")

# Координати українських міст
CITIES = {
    "Київ": {"lat": 50.45, "lon": 30.52},
    "Львів": {"lat": 49.84, "lon": 24.03},
    "Одеса": {"lat": 46.48, "lon": 30.73},
    "Харків": {"lat": 49.99, "lon": 36.23},
    "Дніпро": {"lat": 48.46, "lon": 35.05},
    "Запоріжжя": {"lat": 47.84, "lon": 35.14},
    "Вінниця": {"lat": 49.23, "lon": 28.47},
    "Полтава": {"lat": 49.59, "lon": 34.55},
    "Чернігів": {"lat": 51.49, "lon": 31.29},
    "Тернопіль": {"lat": 49.55, "lon": 25.59},
    "Івано-Франківськ": {"lat": 48.92, "lon": 24.71},
    "Рівне": {"lat": 50.62, "lon": 26.25},
    "Луцьк": {"lat": 50.75, "lon": 25.34},
    "Ужгород": {"lat": 48.62, "lon": 22.29},
    "Чернівці": {"lat": 48.29, "lon": 25.94},
    "Хмельницький": {"lat": 49.42, "lon": 26.99},
    "Суми": {"lat": 50.91, "lon": 34.80},
    "Житомир": {"lat": 50.25, "lon": 28.66},
    "Кропивницький": {"lat": 48.51, "lon": 32.26},
    "Миколаїв": {"lat": 46.97, "lon": 32.00},
    "Херсон": {"lat": 46.64, "lon": 32.62},
}

# Cache: store last fetch to avoid spamming API
_cache: dict = {"data": None, "city": None, "fetched_at": 0}
CACHE_TTL = 1800  # 30 minutes


async def get_weather(city: str = "Київ") -> dict:
    """
    Fetch weather for given Ukrainian city.
    Returns dict with current conditions and daily forecast.
    Caches for 30 minutes.
    """
    import time
    now = time.time()

    # Return cached if fresh
    if (
        _cache["data"]
        and _cache["city"] == city
        and (now - _cache["fetched_at"]) < CACHE_TTL
    ):
        return _cache["data"]

    coords = CITIES.get(city, CITIES["Київ"])

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "current": "temperature_2m,apparent_temperature,rain,wind_speed_10m,weather_code",
        "daily": (
            "temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max,"
            "sunrise,sunset,weather_code"
        ),
        "timezone": "Europe/Kyiv",
        "forecast_days": 2,
    }

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.error("Open-Meteo request failed: %s", e)
        raise

    current = data.get("current", {})
    daily = data.get("daily", {})

    result = {
        "temp": round(current.get("temperature_2m", 0)),
        "feels_like": round(current.get("apparent_temperature", 0)),
        "rain": current.get("rain", 0) > 0,
        "wind": round(current.get("wind_speed_10m", 0)),
        "weather_code": current.get("weather_code", 0),
        "high": round(daily.get("temperature_2m_max", [0])[0]),
        "low": round(daily.get("temperature_2m_min", [0])[0]),
        "rain_chance": daily.get("precipitation_probability_max", [0])[0],
        "sunrise": _extract_time(daily.get("sunrise", [""])[0]),
        "sunset": _extract_time(daily.get("sunset", [""])[0]),
        "tomorrow_high": round(daily.get("temperature_2m_max", [0, 0])[1]) if len(daily.get("temperature_2m_max", [])) > 1 else None,
        "tomorrow_low": round(daily.get("temperature_2m_min", [0, 0])[1]) if len(daily.get("temperature_2m_min", [])) > 1 else None,
        "tomorrow_rain": daily.get("precipitation_probability_max", [0, 0])[1] if len(daily.get("precipitation_probability_max", [])) > 1 else None,
        "description": _weather_code_to_text(current.get("weather_code", 0)),
    }

    # Update cache
    _cache["data"] = result
    _cache["city"] = city
    _cache["fetched_at"] = now

    return result


def _extract_time(iso_str: str) -> str:
    """Extract HH:MM from ISO datetime string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M")
    except Exception:
        return iso_str[-5:] if len(iso_str) >= 5 else ""


def _weather_code_to_text(code: int) -> str:
    """Convert WMO weather code to Ukrainian text."""
    codes = {
        0: "ясно",
        1: "переважно ясно",
        2: "мінлива хмарність",
        3: "хмарно",
        45: "туман",
        48: "туман з інеєм",
        51: "мряка",
        53: "мряка",
        55: "сильна мряка",
        61: "невеликий дощ",
        63: "дощ",
        65: "сильний дощ",
        66: "крижаний дощ",
        67: "сильний крижаний дощ",
        71: "невеликий сніг",
        73: "сніг",
        75: "сильний сніг",
        77: "снігові зерна",
        80: "невеликий дощ",
        81: "дощ",
        82: "злива",
        85: "невеликий сніг",
        86: "сильний сніг",
        95: "гроза",
        96: "гроза з градом",
        99: "гроза з сильним градом",
    }
    return codes.get(code, "невідомо")

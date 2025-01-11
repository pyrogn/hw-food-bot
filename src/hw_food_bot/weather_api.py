import json
import logging
import os

from aiolimiter import AsyncLimiter
from cachetools.func import ttl_cache
from dotenv import find_dotenv, load_dotenv
from niquests import AsyncSession

rate_limit = AsyncLimiter(max_rate=10, time_period=59)
load_dotenv(find_dotenv())


logger = logging.getLogger(__name__)

WEATHER_API_URL = "http://api.openweathermap.org/data/2.5/weather"
API_KEY = os.environ.get("OPEN_WEATHER_TOKEN")


# TTL: 10 hours
@ttl_cache(maxsize=1024, ttl=10 * 60 * 60)
async def get_current_weather(city: str) -> float | None:
    params = {"q": city, "appid": API_KEY, "units": "metric"}

    if rate_limit.has_capacity():
        async with rate_limit:
            logger.info("call for weather of: " + city)
            async with AsyncSession() as s:
                response = await s.get(WEATHER_API_URL, params=params)
    else:
        logger.info("weather api is over the limit")
        return None
    data = response.json()

    if response.status_code != 200:  # noqa: PLR2004
        logger.error("error while getting weather: " + json.dumps(data))
        return None

    return data["main"]["temp"]

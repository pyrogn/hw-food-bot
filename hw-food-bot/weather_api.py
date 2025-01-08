import httpx

WEATHER_API_URL = "http://api.openweathermap.org/data/2.5/weather"


# асинхронный вызов
async def get_weather_async(city, api_key):
    params = {"q": city, "appid": api_key, "units": "metric"}

    async with httpx.AsyncClient() as client:
        response = await client.get(WEATHER_API_URL, params=params)
        data = response.json()

        if response.status != 200:  # noqa: PLR2004
            return None

        return data["main"]["temp"]

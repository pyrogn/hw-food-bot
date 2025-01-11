import json
import logging
from functools import lru_cache

from aiolimiter import AsyncLimiter
from niquests import AsyncSession
from pydantic.dataclasses import dataclass

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.DEBUG
)
logger = logging.getLogger(__name__)


rate_limit = AsyncLimiter(max_rate=10, time_period=59)


@dataclass
class FoodInfo:
    product_name: str
    calories: float = 0


@lru_cache(maxsize=1024)
async def get_food_info(product_name: str) -> FoodInfo | None:
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    if rate_limit.has_capacity():
        async with rate_limit:
            logger.info("food api call of: " + product_name)
            async with AsyncSession() as s:
                response = await s.get(url)
    else:
        logger.info("food api is over limit")
        return None

    if response.status_code == 200:  # noqa: PLR2004
        data = response.json()
        products = data.get("products", [])
        if products:  # Проверяем, есть ли найденные продукты
            chosen_product = products[0]
            for product in products:
                if product.get("nutriments", {}).get("energy-kcal_100g", 0) != 0:
                    chosen_product = product
                    break
            return FoodInfo(
                product_name=chosen_product.get("product_name", "Неизвестно"),
                calories=chosen_product.get("nutriments", {}).get("energy-kcal_100g", 0),
            )
        return None
    logger.error(f"Ошибка: {response.status_code}, {json.dumps(response.json())}")
    return None

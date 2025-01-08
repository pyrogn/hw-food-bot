import httpx


async def get_food_info(product_name) -> float | None:
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

    if response.status_code == 200:  # noqa: PLR2004
        data = response.json()
        products = data.get("products", [])
        if products:  # Проверяем, есть ли найденные продукты
            chosen_product = products[0]
            for product in products:
                if product.get("nutriments", {}).get("energy-kcal_100g", 0) != 0:
                    chosen_product = product
                    break
            return {
                "name": chosen_product.get("product_name", "Неизвестно"),
                "calories": chosen_product.get("nutriments", {}).get("energy-kcal_100g", 0),
            }
        return None
    print(f"Ошибка: {response.status_code}")
    return None

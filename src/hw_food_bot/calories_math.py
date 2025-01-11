from pydantic.dataclasses import dataclass

from hw_food_bot.food_api import FoodInfo, get_food_info
from hw_food_bot.weather_api import get_current_weather

ACTIVITIES_1M_CAL_BURN = {
    "бег": 100,
    "программирование": 99,
    "прогулка": 60,
    "активная активность": 150,
    "неактивная активность": 50,
}


@dataclass
class UserProfile:
    weight: float
    height: float
    age: int
    activity_min: int
    city: str


@dataclass
class UserDailyGoals:
    water_goal: float
    calories_goal: float


@dataclass
class UserProgress:
    logged_water: int = 0
    logged_calories: float = 0
    burned_calories: float = 0


class WeatherService:
    @staticmethod
    async def get_weather(city: str) -> float | None:
        return await get_current_weather(city)


class FoodService:
    @staticmethod
    async def get_food_info(product_name: str) -> FoodInfo | None:
        return await get_food_info(product_name)


class UserManager:
    def __init__(
        self,
        profile: UserProfile,
        weather_service: WeatherService,
        food_service: FoodService,
    ):
        self.profile = profile
        self.progress = UserProgress()
        self.weather_service = weather_service
        self.food_service = food_service
        self.goals = None
        self.current_weather = None

    @classmethod
    async def create(
        cls,
        profile: UserProfile,
        weather_service: WeatherService = WeatherService(),
        food_service: FoodService = FoodService(),
    ):
        instance = cls(profile, weather_service, food_service)
        instance.goals = await instance.calculate_goals()
        return instance

    async def calculate_goals(self) -> UserDailyGoals:
        """Вычисление формулы для целей"""
        self.current_weather = await self.weather_service.get_weather(self.profile.city)
        water_bonus = 500 if self.current_weather and self.current_weather > 25 else 0  # noqa: PLR2004

        water_goal = self.profile.weight * 30 + (self.profile.activity_min / 30 * 500) + water_bonus
        calorie_goal = (
            10 * self.profile.weight + 6.25 * self.profile.height - 5 * self.profile.age + 200
        )

        return UserDailyGoals(water_goal=water_goal, calories_goal=calorie_goal)

    async def log_food(self, product_name: str, grams: int) -> str:
        food_info = await self.food_service.get_food_info(product_name)
        if not food_info:
            return "Информация о еде не найдена."

        calories = food_info.calories * grams / 100
        self.progress.logged_calories += calories
        return f"Залоггировано {calories:.2f} ккал {grams}г {product_name}."

    def log_water(self, amount: int) -> str:
        self.progress.logged_water += amount
        return f"Залоггировано {amount} мл воды. Всего выпито: {self.progress.logged_water} мл."

    def log_activity(self, activity: str, minutes: int) -> str:
        if activity not in ACTIVITIES_1M_CAL_BURN:
            return f"Неверная активность '{activity}'."

        calories_activity = ACTIVITIES_1M_CAL_BURN[activity]
        burned_calories = calories_activity * minutes
        self.progress.burned_calories += burned_calories
        return (
            f"Сожжено {burned_calories:.2f} ккал после занятий {minutes} минут "
            f"от активности {activity}."
        )

    def get_progress(self) -> str:
        water_remaining = max(self.goals.water_goal - self.progress.logged_water, 0)
        calories_remaining = max(
            self.goals.calories_goal
            + self.progress.burned_calories
            - self.progress.logged_calories,
            0,
        )
        if self.current_weather:
            weather_type = "жарко" if self.current_weather > 25 else "нормально"
            weather_report = (
                f"Сейчас в городе {self.profile.city} {self.current_weather} °C - {weather_type}"
            )
        else:
            weather_report = "Город не найден"

        return (
            f"Вода: {self.progress.logged_water} мл / {self.goals.water_goal:.2f} мл "
            f"(осталось: <b>{water_remaining:.2f} мл</b>)\n"
            f"Калории: потреблено {self.progress.logged_calories:.2f} ккал, "
            f"Сожжено активностью {self.progress.burned_calories:.2f} ккал \n"
            f"Цель: {self.goals.calories_goal:.2f} ккал "
            f"(осталось: <b>{calories_remaining:.2f} ккал</b>)\n"
            f"{weather_report}"
        )

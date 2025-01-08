from telegram import Update
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters

from .motivation import get_random_quote

# Хранилище данных пользователей
users = {}


async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "Привет! Я помогу вам рассчитать дневные нормы воды и калорий, а также отслеживать питание и тренировки."
        "Используйте команду /set_profile для настройки вашего профиля."
    )


async def set_profile(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    users[user_id] = {}
    context.user_data["profile_step"] = "weight"
    await update.message.reply_text("Введите ваш вес (в кг):")


async def handle_profile_input(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    step = context.user_data.get("profile_step")

    if not step:
        await update.message.reply_text("Пожалуйста, начните с команды /set_profile.")
        return

    if step == "weight":
        users[user_id]["weight"] = int(update.message.text)
        context.user_data["profile_step"] = "height"
        await update.message.reply_text("Введите ваш рост (в см):")

    elif step == "height":
        users[user_id]["height"] = int(update.message.text)
        context.user_data["profile_step"] = "age"
        await update.message.reply_text("Введите ваш возраст:")

    elif step == "age":
        users[user_id]["age"] = int(update.message.text)
        context.user_data["profile_step"] = "activity"
        await update.message.reply_text("Сколько минут активности у вас в день?")

    elif step == "activity":
        users[user_id]["activity"] = int(update.message.text)
        context.user_data["profile_step"] = "city"
        await update.message.reply_text("В каком городе вы находитесь?")

    elif step == "city":
        users[user_id]["city"] = update.message.text
        context.user_data.pop("profile_step")
        weight = users[user_id]["weight"]
        activity = users[user_id]["activity"]

        # Расчёт норм воды и калорий
        water_goal = weight * 30 + (500 if activity > 30 else 0)
        calorie_goal = (
            10 * weight + 6.25 * users[user_id]["height"] - 5 * users[user_id]["age"] + 200
        )

        users[user_id]["water_goal"] = water_goal
        users[user_id]["calorie_goal"] = calorie_goal
        users[user_id]["logged_water"] = 0
        users[user_id]["logged_calories"] = 0
        users[user_id]["burned_calories"] = 0

        await update.message.reply_text(
            f"Профиль сохранён! \n\nВаша дневная норма воды: {water_goal} мл.\nВаша дневная норма калорий: {calorie_goal} ккал."
        )


async def log_water(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text(
            "Пожалуйста, настройте профиль с помощью команды /set_profile."
        )
        return

    try:
        amount = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /log_water <количество>")
        return

    users[user_id]["logged_water"] += amount
    remaining = users[user_id]["water_goal"] - users[user_id]["logged_water"]
    await update.message.reply_text(
        f"Записано: {amount} мл воды. Осталось до цели: {remaining if remaining > 0 else 0} мл."
    )


async def check_progress(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text(
            "Пожалуйста, настройте профиль с помощью команды /set_profile."
        )
        return

    user_data = users[user_id]
    water_progress = f"Выпито: {user_data['logged_water']} мл из {user_data['water_goal']} мл."
    calorie_progress = (
        f"Потреблено: {user_data['logged_calories']} ккал из {user_data['calorie_goal']} ккал.\n"
        f"Сожжено: {user_data['burned_calories']} ккал."
    )
    await update.message.reply_text(
        f"📊 Прогресс:\n\nВода:\n{water_progress}\n\nКалории:\n{calorie_progress}"
    )


async def motivation(update: Update, context: CallbackContext):
    await update.message.reply_text(get_random_quote)


async def help(update: Update, context: CallbackContext):
    help_text = """This is bot for tracking kkal and water.
    There are available commands:
    - /start (start this bot)
    - /set_profile (set profile or reset profile)
    - /log_water [Milliliters] (add)
    - /check_progress (see current progress for the day)
    - /log_food [Food Name] (track consumed food)
    - /help (get this help message)
    - /motivation
    """
    await update.message.reply_text(help_text)


async def main():
    application = Application.builder().token("TOKEN").build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("set_profile", set_profile))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profile_input))
    application.add_handler(CommandHandler("log_water", log_water))
    application.add_handler(CommandHandler("check_progress", check_progress))
    application.add_handler(CommandHandler("help"))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

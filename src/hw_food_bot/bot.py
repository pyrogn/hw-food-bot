"""Telegram bot logic"""

import inspect
import logging
import os
from typing import Any

from dotenv import find_dotenv, load_dotenv
from pydantic.dataclasses import dataclass
from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackContext,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

from hw_food_bot.calories_math import ACTIVITIES_1M_CAL_BURN, UserManager, UserProfile
from hw_food_bot.motivation import get_random_quote
from hw_food_bot.setup_logging import setup_logging

log_level = os.getenv("LOG_LEVEL", "INFO")
setup_logging(log_level)


load_dotenv(find_dotenv())
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Хранилище данных пользователей
users: dict[str, UserManager] = {}
FOOD_GRAMS = range(1)
CHOOSING_ACTIVITY, ENTERING_MINUTES = range(1, 3)


def get_command_args(text: str) -> str:
    return text.split(" ", 1)[1]


async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        f"Привет, {update.effective_user.first_name}!\n"
        "Я помогу вам рассчитать дневные нормы воды и калорий, "
        "а также отслеживать питание и тренировки.\n"
        "<b>Используйте команду /set_profile для настройки вашего профиля.</b>\n"
        "Полная помощь доступна в команде /help",
        parse_mode=ParseMode.HTML,
    )


@dataclass
class ProfileField:
    """Шаблон вопроса и состояния PTB для вопросов пользователю"""

    name: str
    prompt: str
    validation_type: type
    next_state: int
    units: str = ""


class ProfileSetup:
    """Генерация вопросов для сбора информации о пользователе."""

    WEIGHT, HEIGHT, AGE, ACTIVITY, CITY = range(5)

    FIELDS = {
        WEIGHT: ProfileField("weight", "Введите ваш вес", float, HEIGHT, "кг"),
        HEIGHT: ProfileField("height", "Введите ваш рост", float, AGE, "см"),
        AGE: ProfileField("age", "Введите ваш возраст", int, ACTIVITY, "лет"),
        ACTIVITY: ProfileField(
            "activity", "Сколько минут активности у вас в день?", int, CITY, "мин/день"
        ),
        CITY: ProfileField(
            "city",
            "В каком городе вы находитесь? (лучше отвечать как `Moscow, RU`)",
            str,
            ConversationHandler.END,
        ),
    }

    @staticmethod
    async def validate_input(text: str, expected_type: type) -> tuple[bool, Any]:
        """Неполноценная валидация, приведение типов."""
        try:
            if expected_type is str:
                return True, text
            value = expected_type(text)
            if expected_type in (int, float) and value <= 0:
                return False, None
            return True, value
        except ValueError:
            return False, None

    @staticmethod
    async def handle_profile_field(
        update: Update, context: CallbackContext, current_state: int
    ) -> int:
        field = ProfileSetup.FIELDS[current_state]
        is_valid, value = await ProfileSetup.validate_input(
            update.message.text, field.validation_type
        )

        if not is_valid:
            await update.message.reply_text(
                f"Пожалуйста, введите корректное значение для {field.name}."
            )
            return current_state

        context.user_data[field.name] = value

        if field.next_state == ConversationHandler.END:
            await ProfileSetup.save_profile(update, context)
            return ConversationHandler.END

        next_field = ProfileSetup.FIELDS[field.next_state]
        await update.message.reply_text(next_field.prompt)
        return field.next_state

    @staticmethod
    async def start_profile_setup(update: Update, context: CallbackContext) -> int:
        first_field = ProfileSetup.FIELDS[ProfileSetup.WEIGHT]
        await update.message.reply_text(first_field.prompt)
        return ProfileSetup.WEIGHT

    @staticmethod
    async def save_profile(update: Update, context: CallbackContext) -> None:
        user_id = update.effective_user.id
        user = await UserManager.create(
            profile=UserProfile(
                weight=context.user_data["weight"],
                height=context.user_data["height"],
                age=context.user_data["age"],
                activity_min=context.user_data["activity"],
                city=context.user_data["city"],
            )
        )
        users[user_id] = user

        profile_summary = user.get_progress()

        await update.message.reply_text(
            f"Профиль успешно настроен!\nПрогресс:\n{profile_summary}",
            parse_mode=ParseMode.HTML,
        )


def create_profile_handler() -> ConversationHandler:
    """Хендлер для /setup_profile"""
    return ConversationHandler(
        entry_points=[CommandHandler("set_profile", ProfileSetup.start_profile_setup)],
        states={
            state: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    lambda u, c, s=state: ProfileSetup.handle_profile_field(u, c, s),
                )
            ]
            for state in ProfileSetup.FIELDS
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


async def log_water(update: Update, context: CallbackContext):
    """Залоггировать воду одной командой."""
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text(
            "Пожалуйста, настройте профиль с помощью команды /set_profile."
        )
        return

    try:
        amount = int(get_command_args(update.message.text))
    except (IndexError, ValueError):
        await update.message.reply_text("Использование: /log_water <объем> мл")
        return

    output = users[user_id].log_water(amount)
    await update.message.reply_text(output)


async def log_food_start(update: Update, context: CallbackContext):
    """Спросить, сколько еды съели"""
    logging.debug("start logging food")
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text(
            "Пожалуйста, настройте профиль с помощью команды /set_profile."
        )
        return ConversationHandler.END
    context.user_data["food_name"] = get_command_args(update.message.text)
    await update.message.reply_text(f"Сколько грамм вы съели {context.user_data['food_name']}?")
    return FOOD_GRAMS


async def log_food_grams(update: Update, context: CallbackContext):
    """Залоггировать объем еды и найти калорийность."""
    user_id = update.effective_user.id
    food_name = context.user_data["food_name"]
    try:
        grams = float(update.message.text)
        response = await users[user_id].log_food(food_name, grams)

        await update.message.reply_text(response)
    except Exception as e:
        await update.message.reply_text("Не удалось обработать запрос. Попробуйте ещё раз.")
        print(e)
    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext):
    """Завершить текущий conversion как fallback."""
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


def create_activity_buttons():
    buttons = [[activity] for activity in ACTIVITIES_1M_CAL_BURN]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)


async def start_log_activity(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text(
            "Пожалуйста, настройте профиль с помощью команды /set_profile."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Выберите активность:",
        reply_markup=create_activity_buttons(),
    )
    return CHOOSING_ACTIVITY


async def process_activity_choice(update: Update, context: CallbackContext):
    activity = update.message.text

    if activity not in ACTIVITIES_1M_CAL_BURN:
        await update.message.reply_text("Пожалуйста, выберите активность из предложенного списка.")
        return CHOOSING_ACTIVITY

    context.user_data["chosen_activity"] = activity
    await update.message.reply_text(f"Сколько минут вы занимались активностью '{activity}'?")
    return ENTERING_MINUTES


async def process_minutes(update: Update, context: CallbackContext):
    """Обработать кол-во минут активности."""
    try:
        minutes = int(update.message.text)
        if minutes <= 0:
            await update.message.reply_text("Пожалуйста, введите положительное число минут.")
            return ENTERING_MINUTES

        activity = context.user_data.get("chosen_activity")
        user_id = update.effective_user.id

        response = users[user_id].log_activity(activity, minutes)

        await update.message.reply_text(response)
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Пожалуйста, введите корректное число минут.")
        return ENTERING_MINUTES


async def check_progress(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text(
            "Пожалуйста, настройте профиль с помощью команды /set_profile."
        )
        return

    progress = users[user_id].get_progress()
    await update.message.reply_text(progress, parse_mode=ParseMode.HTML)


async def motivation(update: Update, context: CallbackContext):
    """Доля мотивации"""
    await update.message.reply_text(f"<i>{get_random_quote()}</i>", parse_mode=ParseMode.HTML)


async def help(update: Update, context: CallbackContext):
    help_text = inspect.cleandoc(
        """Бот для трекинга полезностей.
        Доступные команды:
        - /start - Начать общение
        - /set_profile - Создать профиль с физическими характеристиками
        - /check_progress - Посмотреть текущий прогресс
        - /log_water - Залоггировать воду
        - /log_food - Залоггировать еду
        - /log_activity - Залоггировать активность
        - /motivation - Получить дозу кринжовой мотивации
        - /cancel - Отменить текущую команду (если есть коммуникация)
        - /help - Получить справку
        """
    )
    await update.message.reply_text(help_text)


def create_activity_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("log_activity", start_log_activity)],
        states={
            CHOOSING_ACTIVITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_activity_choice)
            ],
            ENTERING_MINUTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_minutes)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


def create_food_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("log_food", log_food_start)],
        states={
            FOOD_GRAMS: [MessageHandler(filters.TEXT & ~filters.COMMAND, log_food_grams)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


async def default_fallback(update: Update, context: CallbackContext):
    quote = get_random_quote()
    text = (
        "Такой команды нет. Для помощи обратитесь в /help.\nНо вот цитата все равно:\n"
        f"<i>{quote}</i>"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


if __name__ == "__main__":
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("log_water", log_water))
    application.add_handler(create_profile_handler())
    application.add_handler(create_activity_handler())
    application.add_handler(create_food_handler())
    application.add_handler(CommandHandler("check_progress", check_progress))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(CommandHandler("motivation", motivation))
    application.add_handler(MessageHandler(filters.ALL, default_fallback))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

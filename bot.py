import asyncio
import io
import logging
import sqlite3
import threading
import time
from datetime import datetime

import pytz
import schedule
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from PIL import Image

from config import TOKEN
from db import db_setup, get_all_users, save_user
from weather import get_current_weather

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class UserData(StatesGroup):
    name = State()
    age = State()
    timezone = State()


class WeatherState(StatesGroup):
    city = State()


async def send_daily_notifications():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, timezone FROM users")
    users = cursor.fetchall()
    conn.close()

    for user_id, timezone in users:
        try:
            local_tz = pytz.timezone(timezone)
            local_now = datetime.now(local_tz)

            if local_now.hour == 22 and local_now.minute == 00:
                await bot.send_message(user_id, "Не забудьте проверить уведомления!")
                logging.info(f"Уведомление отправлено пользователю {user_id}")
        except Exception as e:
            logging.error(
                f"Ошибка при отправке уведомления пользователю {user_id}: {e}"
            )


def schedule_notifications(loop):
    schedule.every().day.at("22:00").do(
        lambda: asyncio.run_coroutine_threadsafe(send_daily_notifications(), loop)
    )
    while True:
        schedule.run_pending()
        time.sleep(60)


@dp.message_handler(commands=["start"], state="*")
async def start(message: types.Message, state: FSMContext):
    await state.finish()
    await UserData.name.set()
    await message.answer("Добро пожаловать в наш бот!\nКак тебя зовут?")


@dp.message_handler(state=UserData.name)
async def process_name(message: types.Message, state: FSMContext):
    try:
        name = message.text.strip()
        if not name.isalpha():
            raise ValueError("Имя должно содержать только буквы.")
        async with state.proxy() as data:
            data["name"] = name
        await UserData.age.set()
        await message.answer("Сколько тебе лет?")
    except ValueError as e:
        logging.error(f"Ошибка при обработке имени: {e}")
        await message.answer(f"Ошибка: {e}")
    except Exception as e:
        logging.error(f"Неизвестная ошибка при обработке имени: {e}")
        await message.answer("Произошла ошибка, попробуйте позже.")


@dp.message_handler(state=UserData.age)
async def process_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
        async with state.proxy() as data:
            data["age"] = age
            await message.answer(
                "Пожалуйста, выберите ваш часовой пояс:",
                reply_markup=get_timezone_keyboard(),
            )
            await UserData.timezone.set()
    except ValueError:
        await message.answer("Пожалуйста, введите ваш возраст в числовом формате.")
    except Exception as e:
        logging.error(f"Ошибка при обработке возраста: {e}")
        await message.answer("Произошла ошибка, попробуйте позже.")


def get_timezone_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    timezones = pytz.all_timezones
    for timezone in timezones:
        keyboard.add(types.KeyboardButton(timezone))
    return keyboard


@dp.message_handler(state=UserData.timezone)
async def process_timezone(message: types.Message, state: FSMContext):
    timezone = message.text.strip()
    if timezone not in pytz.all_timezones:
        await message.answer(
            "Некорректный часовой пояс. Пожалуйста, выберите корректный часовой пояс."
        )
        return

    async with state.proxy() as data:
        user_id = message.from_user.id
        name = data["name"]
        age = data["age"]
        save_user(user_id, name, age, timezone)

    await message.answer(f"Привет, {data['name']}! Как ты сегодня?")
    await state.finish()


@dp.message_handler(commands=["users"])
async def list_users(message: types.Message):
    users = get_all_users()
    if users:
        response = "Список пользователей:\n"
        print(users)
        for user in users:
            response += f"ID: {user[1]}, Имя: {user[2]}, Возраст: {user[3]}, Часовой пояс: {user[4]}\n"
    else:
        response = "Пользователи не найдены."
    await message.answer(response)


@dp.message_handler(commands=["weather"])
async def weather(message: types.Message):
    await message.answer("Введите название города:")
    await WeatherState.city.set()


@dp.message_handler(state=WeatherState.city)
async def get_weather(message: types.Message, state: FSMContext):
    city = message.text
    weather_data = get_current_weather(city)
    if weather_data:
        weather_description = weather_data["weather"][0]["description"]
        temperature = weather_data["main"]["temp"]
        humidity = weather_data["main"]["humidity"]
        wind_speed = weather_data["wind"]["speed"]
        response = (
            f"Погода в {city}:\n"
            f"Описание: {weather_description}\n"
            f"Температура: {temperature}°C\n"
            f"Влажность: {humidity}%\n"
            f"Скорость ветра: {wind_speed} м/с"
        )
    else:
        response = "Не удалось получить данные о погоде."
    await message.answer(response)
    await state.finish()


@dp.message_handler(commands=["help"])
async def help(message: types.Message):
    await message.answer(
        "Доступные команды:\n/start\n/help\n/echo\n/photo\n/users\n/weather"
    )


@dp.message_handler(commands=["echo"])
async def cmd_echo(message: types.Message):
    user_message = message.get_args()
    if user_message:
        await message.answer(user_message)
    else:
        await message.answer("Пожалуйста, введите текст после команды /echo.")


@dp.message_handler(commands=["photo"])
async def photo(message: types.Message):
    await message.answer("Пожалуйста, отправьте фото.")


@dp.message_handler(content_types=["photo"])
async def handle_photo(message: types.Message):
    photo = message.photo[-1]
    file_info = await bot.get_file(photo.file_id)
    file = await bot.download_file(file_info.file_path)
    image = Image.open(io.BytesIO(file.read()))
    width, height = image.size
    await message.answer(f"Размер изображения: {width} x {height} пикселей")


@dp.message_handler(content_types=["text"], state="*")
async def inline_buttons(message: types.Message):
    keyboard = types.InlineKeyboardMarkup()
    key_1 = types.InlineKeyboardButton(text="Выбор 1", callback_data="1")
    key_2 = types.InlineKeyboardButton(text="Выбор 2", callback_data="2")
    keyboard.add(key_1, key_2)
    await message.answer("Пожалуйста, выберите:", reply_markup=keyboard)


@dp.callback_query_handler(text=["1", "2"])
async def button(callback_query: types.CallbackQuery):
    code = callback_query.data
    if code == "1":
        await callback_query.message.edit_text("Вы выбрали Выбор 1")
    elif code == "2":
        await callback_query.message.edit_text("Вы выбрали Выбор 2")


if __name__ == "__main__":
    db_setup()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    threading.Thread(target=schedule_notifications, args=(loop,), daemon=True).start()

    executor.start_polling(dp, skip_updates=True)

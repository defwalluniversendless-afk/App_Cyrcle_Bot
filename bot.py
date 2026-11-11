"""Бот для запуска мини-приложения «Круг» в Telegram (aiogram 3).

Что делает:
  /start и /app  -> сообщение с кнопкой «Открыть Круг» (открывает мини-апп)
  кнопка меню    -> слева от поля ввода у всех пользователей открывает мини-апп

Переменные окружения (или файл .env):
  BOT_TOKEN   токен бота от @BotFather
  WEBAPP_URL  https-адрес, где лежит index.html мини-приложения
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]  # например https://имя.github.io/krug-app/?v=1

dp = Dispatcher()


def open_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Открыть Круг", web_app=WebAppInfo(url=WEBAPP_URL))]]
    )


@dp.message(CommandStart())
@dp.message(Command("app"))
async def start(message: Message) -> None:
    await message.answer(
        "Привет! Это Круг — платформа для саморазвития.\nНажми кнопку, чтобы начать.",
        reply_markup=open_kb(),
    )


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN)
    # Кнопка меню для всех чатов с ботом
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Круг", web_app=WebAppInfo(url=WEBAPP_URL))
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

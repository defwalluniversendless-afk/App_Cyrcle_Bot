"""Бот «Круг»: курсы с уроками, тестами в мини-аппе и проверкой подписки (aiogram 3).

Сценарий: /start -> выбор курса -> урок (видео) -> «Я просмотрел» -> кнопка теста
(мини-апп) -> по завершении теста бот сам присылает следующий урок.
Перед каждым действием бот тихо проверяет, что человек состоит в закрытом канале.

Переменные окружения (.env):
  BOT_TOKEN    токен ЭТОГО бота (не бота с подписками!)
  WEBAPP_URL   адрес мини-аппа «Круг» (index.html)
  TESTS_URL    адрес файла с тестами (tests.html)
  CHANNEL_ID   id закрытого канала, например -1001234567890. Бот должен быть админом канала
  ADMIN_ID     твой Telegram id: присланное тобой видео бот вернёт как file_id
"""
import asyncio
import json
import logging
import os
from urllib.parse import urlencode

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    MenuButtonWebApp,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from courses import COURSES

BOT_TOKEN = os.environ["BOT_TOKEN"]
WEBAPP_URL = os.environ["WEBAPP_URL"]
TESTS_URL = os.environ["TESTS_URL"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PAY_TEXT = "У вас закончилась подписка. Чтобы оплатить, перейдите в @habirov_cyrcle_bot"

dp = Dispatcher()


# ---------- проверка подписки ----------
async def is_member(bot: Bot, user_id: int):
    """True / False, либо None если Telegram не дал ответ."""
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
    except Exception:
        logging.exception("get_chat_member failed")
        return None
    return m.status in ("creator", "administrator", "member") or (
        m.status == "restricted" and getattr(m, "is_member", False)
    )


async def guard(bot: Bot, user_id: int, chat_id: int) -> bool:
    """Тихая проверка. Пишет человеку только если доступа нет."""
    ok = await is_member(bot, user_id)
    if ok:
        return True
    text = PAY_TEXT if ok is False else "Не получилось проверить доступ. Попробуйте ещё раз через минуту."
    await bot.send_message(chat_id, text, reply_markup=ReplyKeyboardRemove())
    return False


# ---------- клавиатуры и отправка уроков ----------
def menu_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=c["title"], callback_data=f"c:{cid}")] for cid, c in COURSES.items()]
    rows.append([InlineKeyboardButton(text="Открыть Круг", web_app=WebAppInfo(url=WEBAPP_URL))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def test_url(test: str, cid: str, i: int) -> str:
    q = urlencode({"test": test, "c": cid, "i": i, "k": 1})
    return TESTS_URL + ("&" if "?" in TESTS_URL else "?") + q


async def send_lesson(bot: Bot, chat_id: int, cid: str, i: int) -> None:
    lesson = COURSES[cid]["lessons"][i]
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Я просмотрел ✅", callback_data=f"w:{cid}:{i}")]]
    )
    if lesson.get("video"):
        # protect_content запрещает пересылку и сохранение видео
        await bot.send_video(chat_id, lesson["video"], caption=lesson["text"], reply_markup=kb, protect_content=True)
    else:
        await bot.send_message(chat_id, lesson["text"], reply_markup=kb, protect_content=True)


async def send_next(bot: Bot, chat_id: int, cid: str, i: int) -> None:
    if i + 1 < len(COURSES[cid]["lessons"]):
        await send_lesson(bot, chat_id, cid, i + 1)
    else:
        await bot.send_message(chat_id, f"Курс «{COURSES[cid]['title']}» пройден. Поздравляю!", reply_markup=menu_kb())


# ---------- хендлеры ----------
@dp.message(CommandStart())
@dp.message(Command("app"))
async def start(message: Message, bot: Bot) -> None:
    if not await guard(bot, message.from_user.id, message.chat.id):
        return
    await message.answer("Привет! Какой курс хотите пройти?", reply_markup=menu_kb())


@dp.callback_query(F.data.startswith("c:"))
async def pick_course(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    if not await guard(bot, cb.from_user.id, cb.message.chat.id):
        return
    cid = cb.data.split(":")[1]
    if cid in COURSES:
        await send_lesson(bot, cb.message.chat.id, cid, 0)


@dp.callback_query(F.data.startswith("w:"))
async def watched(cb: CallbackQuery, bot: Bot) -> None:
    await cb.answer()
    chat_id = cb.message.chat.id
    if not await guard(bot, cb.from_user.id, chat_id):
        return
    _, cid, i = cb.data.split(":")
    i = int(i)
    try:  # убираем кнопку, чтобы не нажимали дважды
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    test = COURSES[cid]["lessons"][i].get("test")
    if not test:
        return await send_next(bot, chat_id, cid, i)
    # Кнопка в обычной клавиатуре: только так мини-апп может вернуть боту «тест пройден»
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пройти тест", web_app=WebAppInfo(url=test_url(test, cid, i)))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await bot.send_message(chat_id, "Отлично! Теперь короткий тест. Он поможет лучше понять себя.", reply_markup=kb)


@dp.message(F.web_app_data)
async def test_done(message: Message, bot: Bot) -> None:
    if not await guard(bot, message.from_user.id, message.chat.id):
        return
    try:
        d = json.loads(message.web_app_data.data)
        cid, i = d["c"], int(d["i"])
        COURSES[cid]["lessons"][i]
    except Exception:
        return await message.answer("Не удалось засчитать тест. Нажмите /start и попробуйте ещё раз.")
    await message.answer("Тест пройден ✅", reply_markup=ReplyKeyboardRemove())
    await send_next(bot, message.chat.id, cid, i)


# Админ присылает видео -> бот отвечает file_id для courses.py
@dp.message(F.from_user.id == ADMIN_ID, F.video | F.document | F.video_note | F.audio)
async def get_file_id(message: Message) -> None:
    f = message.video or message.document or message.video_note or message.audio
    await message.answer(f"file_id:\n<code>{f.file_id}</code>", parse_mode="HTML")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN)
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Круг", web_app=WebAppInfo(url=WEBAPP_URL)))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

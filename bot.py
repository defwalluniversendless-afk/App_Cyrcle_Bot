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
  PORT         порт веб-сервера для мини-аппа (по умолчанию 8080)
  ALLOW_ORIGIN откуда разрешены запросы мини-аппа к серверу (по умолчанию *;
               если приложение на GitHub Pages, укажи https://имя.github.io)

Веб-сервер отдаёт мини-аппу /api/me (есть ли подписка) и, если рядом лежат
index.html и bgm.mp3, сам раздаёт приложение по адресу /.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from aiohttp import web

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
PORT = int(os.environ.get("PORT", "8080"))
ALLOW_ORIGIN = os.environ.get("ALLOW_ORIGIN", "*")
BASE = Path(__file__).resolve().parent
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


# ---------- веб-часть для мини-аппа: статус подписки ----------
def check_init_data(init_data: str, max_age: int = 86400):
    """Проверяет подпись Telegram. Возвращает данные пользователя или None.
    Так id человека нельзя подделать в браузере."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        got = pairs.pop("hash", "")
        if not got:
            return None
        check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        return json.loads(pairs["user"])
    except Exception:
        return None


_sub_cache: dict = {}


@web.middleware
async def cors(request, handler):
    resp = web.Response(status=204) if request.method == "OPTIONS" else await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = ALLOW_ORIGIN
    resp.headers["Access-Control-Allow-Headers"] = "X-Init-Data, Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return resp


async def api_me(request: web.Request) -> web.Response:
    user = check_init_data(request.headers.get("X-Init-Data", ""))
    if not user:
        return web.json_response({"ok": False}, status=401)
    uid = user["id"]
    hit = _sub_cache.get(uid)
    if hit and time.time() - hit[0] < 60:
        return web.json_response({"ok": True, "active": hit[1]})
    res = await is_member(request.app["bot"], uid)  # True / False / None
    if res is None:  # Telegram не ответил: не кэшируем, считаем «не знаем»
        return web.json_response({"ok": False}, status=503)
    _sub_cache[uid] = (time.time(), bool(res))
    return web.json_response({"ok": True, "active": bool(res)})


def static(f: Path, headers: dict):
    async def handler(request: web.Request) -> web.StreamResponse:
        return web.FileResponse(f, headers=headers)
    return handler


def make_web(bot: Bot) -> web.Application:
    app = web.Application(middlewares=[cors])
    app["bot"] = bot
    app.add_routes([web.get("/api/me", api_me)])
    for route, name, extra in (("/", "index.html", {"Cache-Control": "no-cache"}), ("/index.html", "index.html", {"Cache-Control": "no-cache"}), ("/bgm.mp3", "bgm.mp3", {})):
        f = BASE / name
        if f.exists():  # раздаём только эти два файла, не всю папку
            app.add_routes([web.get(route, static(f, extra))])
    return app


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = Bot(BOT_TOKEN)
    await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="Круг", web_app=WebAppInfo(url=WEBAPP_URL)))
    runner = web.AppRunner(make_web(bot))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logging.info("Веб-сервер мини-аппа на порту %s", PORT)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

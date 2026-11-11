# Круг в Telegram: мини-апп + бот

В папке:
- `index.html` и `bgm.mp3` — само приложение (держи их в одной папке)
- `bot.py`, `requirements.txt`, `.env.example` — бот, который открывает мини-апп

Один и тот же `index.html` работает и в Telegram, и в обычном браузере.
В Telegram он сам определяет, что запущен как мини-апп, и включает свои режимы.

## Что меняется внутри Telegram
- Имя берётся из Telegram, поэтому почту вводить не нужно. Остаётся выбор аватара.
- Прогресс хранится в облаке Telegram (CloudStorage) и открывается на любом устройстве этого пользователя.
- Вибрация идёт через Telegram. На iPhone она работает, в отличие от обычного Safari.
- Меню и фон окрашены в чёрный, а свайп вниз, который закрывает мини-апп, отключён, чтобы не мешал вращать логотип.
- Вместо страницы «Бета-тест» открывается экран «Коснись, чтобы войти». Касание нужно, чтобы запустились звук и музыка.

## Запуск за 4 шага

**1. Выложи приложение на https.** Telegram открывает мини-аппы только по https.
Проще всего GitHub Pages:
1. Создай новый репозиторий, например `krug-app`.
2. Загрузи туда `index.html` и `bgm.mp3`.
3. Settings → Pages → Branch `main`, папка `/ (root)` → Save.
4. Через минуту адрес будет `https://ИМЯ.github.io/krug-app/`.

Подойдут и Netlify, Vercel, Cloudflare Pages: перетащи папку, получишь адрес.

**2. Бот.** Можно использовать уже существующий бот `@Habirov_cyrcle_bot` или создать новый у @BotFather (`/newbot`).

**3. Запусти `bot.py`.** Скопируй `.env.example` в `.env` и впиши `BOT_TOKEN` и `WEBAPP_URL`. Затем:
```
pip install -r requirements.txt
python bot.py
```
Запускать нужно один раз и держать включённым, как и твоего бота с подписками. Если запускаешь на Bothost, добавь два значения в переменные окружения.

**4. Проверь.** Открой бота, нажми /start → «Открыть Круг».
Кнопка «Круг» слева от поля ввода тоже откроет мини-апп.

Чтобы приложение открывалось по короткой ссылке `t.me/имя_бота/имя`, в @BotFather: `/newapp`, выбери бота и укажи адрес.

## Если вставляешь в уже работающий бот
Бот с подпиской на Bothost уже запущен, поэтому отдельный `bot.py` нужен только для нового бота. В существующий достаточно добавить кнопку.

aiogram 3:
```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
    text="Открыть Круг", web_app=WebAppInfo(url="https://ИМЯ.github.io/krug-app/?v=1"))]])
await message.answer("Открой приложение", reply_markup=kb)
```

python-telegram-bot:
```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
kb = InlineKeyboardMarkup([[InlineKeyboardButton(
    "Открыть Круг", web_app=WebAppInfo("https://ИМЯ.github.io/krug-app/?v=1"))]])
await update.message.reply_text("Открой приложение", reply_markup=kb)
```

## Обновление приложения
Telegram кэширует страницу. После каждой загрузки нового `index.html` увеличивай число в адресе: `?v=2`, `?v=3`, и обнови `WEBAPP_URL` в боте.

## Что можно добавить дальше
- Проверку `initData` на сервере (подпись Telegram), если появятся платные уроки или общая база.
- Привязку мини-аппа к подписке из бота, чтобы закрытые курсы открывались только платным подписчикам.

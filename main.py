import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    MessageEntity
)
from aiohttp import web

# -------------------- Конфиг --------------------
# Имя переменной окружения должно быть строкой, а не токеном
BOT_TOKEN = os.getenv("BOT_TOKEN")  # В Render создайте переменную "BOT_TOKEN"

# Если токен не найден, проверяем альтернативные имена
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")  # Проверяем другие возможные имена
if not BOT_TOKEN:
    BOT_TOKEN = os.getenv("TOKEN")

# Если токен все еще не найден, выводим ошибку
if not BOT_TOKEN:
    print("ОШИБКА: Не найден токен бота!")
    print("Создайте переменную окружения BOT_TOKEN в настройках Render")
    # Для локального тестирования можно временно указать токен прямо в коде:
    # BOT_TOKEN = "8367850036:AAFlwAwCeCMG1fC8e1kT1pUuFCZtC1Zis4A"
    exit(1)

PORT = int(os.getenv("PORT", 8000))  # Render сам задает порт
DOMAIN = os.getenv("DOMAIN", "stars-prok.onrender.com")  # твой публичный домен Render

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"

# Premium emoji IDs
EMOJI_1 = "5447508713181034519"
EMOJI_2 = "5422858869372104873"
EMOJI_3 = "5458774648621643551"

bot = Bot(BOT_TOKEN)  # Используем правильную переменную
dp = Dispatcher()

# -------------------- Главное меню --------------------
@dp.message(F.text.in_({"/start", "/menu"}))
async def send_welcome(message: Message):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Баланс"), KeyboardButton(text="🤝 Партнеры")],
            [KeyboardButton(text="🎮 Играть")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "<b>🏠 Главное меню</b>\n\n<blockquote>Выберите раздел:</blockquote>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

# -------------------- Баланс --------------------
@dp.message(F.text == "Баланс")
async def show_balance(message: Message):
    text = "[] 0,00   [] 0,00   [] 0,00"
    entities = [
        MessageEntity(type="custom_emoji", offset=0, length=2, custom_emoji_id=EMOJI_1),
        MessageEntity(type="custom_emoji", offset=9, length=2, custom_emoji_id=EMOJI_2),
        MessageEntity(type="custom_emoji", offset=18, length=2, custom_emoji_id=EMOJI_3)
    ]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit"),
                InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw")
            ]
        ]
    )
    await bot.send_message(
        chat_id=message.chat.id,
        text=text,
        entities=entities,
        reply_markup=markup
    )

# -------------------- Партнеры --------------------
@dp.message(F.text == "🤝 Партнеры")
async def partners(message: Message):
    await message.answer(
        "<b>🤝 Партнеры</b>\n\n<blockquote>В разработке</blockquote>",
        parse_mode="HTML"
    )

# -------------------- Игры --------------------
@dp.message(F.text == "🎮 Играть")
async def games(message: Message):
    await message.answer(
        "<b>🎮 Играть</b>\n\n<blockquote>В разработке</blockquote>",
        parse_mode="HTML"
    )

# -------------------- Callback --------------------
@dp.callback_query(F.data == "deposit")
async def deposit(call):
    await call.answer("Пополнение в разработке")

@dp.callback_query(F.data == "withdraw")
async def withdraw(call):
    await call.answer("Вывод в разработке")

# -------------------- Webhook --------------------
async def handle(request: web.Request):
    update = await request.json()
    await dp.feed_update(update)
    return web.Response(text="ok")

async def on_startup(app):
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    print("Webhook установлен:", WEBHOOK_URL)
    print(f"Бот запущен с токеном: {BOT_TOKEN[:10]}...")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

# -------------------- Запуск aiohttp --------------------
app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_shutdown)

if __name__ == "__main__":
    print(f"Запуск бота на порту {PORT}...")
    web.run_app(app, host="0.0.0.0", port=PORT)

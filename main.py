import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from aiohttp import web
import json

# -------------------- Конфиг --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    print("ОШИБКА: Не найден токен бота!")
    exit(1)

PORT = int(os.getenv("PORT", 10000))
DOMAIN = os.getenv("DOMAIN", "stars-prok.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"https://{DOMAIN}{WEBHOOK_PATH}"

bot = Bot(BOT_TOKEN)
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
    # Способ 1: Прямая вставка кастомных эмоджи через Unicode escape
    # Конвертируем emoji_id в Unicode символ
    emoji1 = chr(0x1F4B2)  # 💲 (замените на нужный если требуется)
    emoji2 = chr(0x1F48E)  # 💎
    emoji3 = chr(0x2744)   # ❄️
    
    # Способ 2: Использовать bot.send_message с entities напрямую
    from aiogram.types import MessageEntity
    
    balance_text = "💰 Баланс\n\n💲 0,00\n💎 0,00\n❄️ 0,00"
    
    entities = [
        MessageEntity(
            type="custom_emoji",
            offset=11,
            length=1,
            custom_emoji_id="5447508713181034519"
        ),
        MessageEntity(
            type="custom_emoji",
            offset=19,
            length=1,
            custom_emoji_id="5422858869372104873"
        ),
        MessageEntity(
            type="custom_emoji",
            offset=27,
            length=1,
            custom_emoji_id="5458774648621643551"
        )
    ]
    
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📥 Пополнить", callback_data="deposit"),
                InlineKeyboardButton(text="📤 Вывести", callback_data="withdraw")
            ]
        ]
    )
    
    # ВАЖНО: Используем bot.send_message напрямую, а не message.answer
    await bot.send_message(
        chat_id=message.chat.id,
        text=balance_text,
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
        "<b>🎮 Игры</b>\n\n<blockquote>В разработке</blockquote>",
        parse_mode="HTML"
    )

# -------------------- Callback --------------------
@dp.callback_query(F.data == "deposit")
async def deposit(call):
    await call.answer("Пополнение в разработке")

@dp.callback_query(F.data == "withdraw")
async def withdraw(call):
    await call.answer("Вывод в разработке")

# -------------------- Webhook обработчик --------------------
async def handle(request: web.Request):
    try:
        data = await request.json()
        from aiogram.types import Update
        update = Update(**data)
        await dp.feed_update(bot, update)
        return web.Response(text="OK")
    except Exception as e:
        print(f"Ошибка обработки webhook: {e}")
        return web.Response(text="Error", status=500)

async def on_startup(app):
    await bot.delete_webhook()
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

# -------------------- Запуск aiohttp --------------------
app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle)
app.on_startup.append(on_startup)
app.on_cleanup.append(on_shutdown)

if __name__ == "__main__":
    print(f"🚀 Запуск бота на порту {PORT}...")
    web.run_app(app, host="0.0.0.0", port=PORT)

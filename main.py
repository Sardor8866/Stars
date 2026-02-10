import telebot
from telebot import types
import threading
import time
import json
import os
from flask import Flask, request
import requests

# Настройки вебхука для Render
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://stars-prok.onrender.com')  # Замените на ваш URL
WEBHOOK_PATH = '/webhook'
SECRET_TOKEN = os.getenv('SECRET_TOKEN', 'YOUR_SECRET_TOKEN')  # Для безопасности

# Инициализация Flask
app = Flask(__name__)

# Инициализация бота
bot = telebot.TeleBot('8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo')

ADMIN_CHAT_ID = 8118184388

# Инициализация модулей
try:
    from games import BettingGame, BET_TYPES, MIN_BET
    from referrals import ReferralSystem
    
    game = BettingGame(bot)
    referral_system = ReferralSystem(bot, game)
    game.set_referral_system(referral_system)
    print("✅ Модули игр и рефералов загружены")
except Exception as e:
    print(f"❌ Ошибка загрузки модулей: {e}")
    import sys
    sys.exit(1)

# Словарь для хранения связи username -> user_id
username_to_id = {}

def update_username_mapping(user_id, username):
    """Обновляет связь между username и user_id"""
    if username:
        username_to_id[username] = user_id

def save_user_info(user_id, username, first_name):
    """Сохраняет информацию о пользователе"""
    # В реферальной системе
    referral_system.save_user_info(user_id, username, first_name)

    # В словаре username_to_id
    if username:
        username_to_id[username] = user_id

    # В файле
    try:
        with open('user_mappings.json', 'r', encoding='utf-8') as f:
            user_mappings = json.load(f)
    except:
        user_mappings = {}

    user_mappings[str(user_id)] = {
        'username': username or '',
        'first_name': first_name or '',
        'last_seen': time.time()
    }

    with open('user_mappings.json', 'w', encoding='utf-8') as f:
        json.dump(user_mappings, f, indent=4, ensure_ascii=False)

def load_user_mappings():
    """Загружает сохраненные маппинги"""
    global username_to_id
    try:
        with open('user_mappings.json', 'r', encoding='utf-8') as f:
            user_mappings = json.load(f)

        for user_id_str, user_data in user_mappings.items():
            username = user_data.get('username', '')
            if username:
                username_to_id[username] = int(user_id_str)

        print(f"✅ Загружено {len(username_to_id)} маппингов пользователей")
    except:
        print("ℹ️ Файл user_mappings.json не найден, создадим новый")

load_user_mappings()

# ========== ХЕНДЛЕРЫ БОТА ==========

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    # Реферальная ссылка
    if len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        if ref_code.startswith('ref'):
            try:
                referrer_id = int(ref_code[3:])
                referral_system.register_referral(
                    referee_id=message.from_user.id,
                    referrer_id=referrer_id,
                    referee_username=message.from_user.username,
                    referee_first_name=message.from_user.first_name
                )
            except Exception as e:
                print(f"❌ Ошибка обработки реферальной ссылки: {e}")

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("👛Баланс")
    btn2 = types.KeyboardButton("🤝 Партнеры")
    btn3 = types.KeyboardButton("🎮 Играть")
    markup.add(btn1, btn2, btn3)

    welcome_text = "<b>🏠 Главное меню</b>\n<blockquote>Выберите раздел:</blockquote>"
    bot.send_message(message.chat.id, welcome_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "👛Баланс")
def show_profile(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)

    user_id = message.from_user.id
    balance = game.get_balance(user_id)
    profile_text = f"""
<blockquote><b>👛Баланс</b></blockquote>
<blockquote><b><code>💲{balance:.2f}</code> <code>💎0,00</code></b></blockquote>
    """
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("📥 Пополнить", callback_data="deposit")
    btn2 = types.InlineKeyboardButton("📤 Вывести", callback_data="withdraw")
    markup.add(btn1, btn2)
    
    image_url = "https://iimg.su/i/u0SuFd"
    try:
        bot.send_photo(message.chat.id, photo=image_url, caption=profile_text, 
                      parse_mode='HTML', reply_markup=markup)
    except:
        bot.send_message(message.chat.id, profile_text, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🤝 Партнеры")
def show_partners(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    referral_system.show_menu(message)

@bot.message_handler(func=lambda message: message.text == "🎮 Играть")
def show_games(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    game.show_games_menu(message)

@bot.message_handler(commands=['add'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Использование: /add username сумма")
            return

        username = parts[1].replace('@', '').lower()
        amount = float(parts[2])

        if username in username_to_id:
            user_id = username_to_id[username]
            game.add_balance(user_id, amount)
            bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю @{username} (ID: {user_id})")
            print(f"💰 Админ добавил {amount} USDT пользователю @{username} (ID: {user_id})")
        else:
            try:
                user_id = int(username)
                game.add_balance(user_id, amount)
                bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю ID: {user_id}")
                print(f"💰 Админ добавил {amount} USDT пользователю ID: {user_id}")
            except ValueError:
                bot.reply_to(message, f"❌ Пользователь @{username} не найден.")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")
        print(f"❌ Ошибка в /add: {e}")

@bot.message_handler(commands=['addid'])
def admin_add_balance_by_id(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Использование: /addid user_id сумма")
            return
        user_id = int(parts[1])
        amount = float(parts[2])
        game.add_balance(user_id, amount)
        bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю ID: {user_id}")
        print(f"💰 Админ добавил {amount} USDT пользователю ID: {user_id}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['find'])
def admin_find_user(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Использование: /find username или /find id")
            return

        search = parts[1]

        if search.startswith('@'):
            search = search[1:]

        if search in username_to_id:
            user_id = username_to_id[search]
            balance = game.get_balance(user_id)
            bot.reply_to(message, f"✅ Найден: @{search}\nID: {user_id}\nБаланс: {balance:.2f} USDT")
            return

        try:
            user_id = int(search)
            balance = game.get_balance(user_id)
            username = None
            for uname, uid in username_to_id.items():
                if uid == user_id:
                    username = uname
                    break

            if username:
                bot.reply_to(message, f"✅ Найден: ID: {user_id}\nUsername: @{username}\nБаланс: {balance:.2f} USDT")
            else:
                bot.reply_to(message, f"✅ Найден: ID: {user_id}\nUsername: не известен\nБаланс: {balance:.2f} USDT")
        except ValueError:
            bot.reply_to(message, f"❌ Пользователь @{search} не найден")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    total_users = len(game.user_balances)
    total_balance = sum(game.user_balances.values())
    ref_stats = referral_system.get_stats(ADMIN_CHAT_ID)

    stats_text = f"""
<b>📊 Статистика бота</b>
👥 Всего пользователей: <b>{total_users}</b>
💰 Общий баланс: <b>{total_balance:.2f} USDT</b>
📝 Известных username: <b>{len(username_to_id)}</b>

<b>👥 Реферальная система:</b>
├ Приглашено: <b>{ref_stats['total_refs']} чел.</b>
├ Доступно: <b>{ref_stats['available']:.2f} USDT</b>
└ Выведено: <b>{ref_stats['withdrawn']:.2f} USDT</b>
    """
    bot.reply_to(message, stats_text, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def handle_deposit(call):
    bot.answer_callback_query(call.id, "📥 Пополнение в разработке", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    bot.answer_callback_query(call.id, "📤 Вывод в разработке", show_alert=True)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)

    if referral_system.process_withdraw(message):
        return

    if game.process_bet_amount(message):
        return

# Обработчик callback для игр
def handle_game_callbacks(call):
    if call.data == "game_dice":
        game.show_dice_menu(call)
    elif call.data == "bet_dice_exact":
        game.show_exact_numbers(call)
    elif call.data.startswith("bet_dice_"):
        bet_type = call.data.replace("bet_dice_", "")
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_basketball":
        game.show_basketball_menu(call)
    elif call.data.startswith("bet_basketball_"):
        bet_type = call.data.replace("bet_basketball_", "")
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_football":
        game.show_football_menu(call)
    elif call.data.startswith("bet_football_"):
        bet_type = call.data.replace("bet_football_", "")
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_darts":
        game.show_darts_menu(call)
    elif call.data.startswith("bet_darts_"):
        bet_type = call.data.replace("bet_darts_", "")
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_bowling":
        game.show_bowling_menu(call)
    elif call.data.startswith("bet_bowling_"):
        bet_type = call.data.replace("bet_bowling_", "")
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)

def handle_referral_callbacks(call):
    if call.data == "ref_menu":
        referral_system.show_menu(call)
    elif call.data == "ref_list":
        referral_system.show_ref_list(call)
    elif call.data == "ref_withdraw":
        referral_system.show_withdraw(call)
    elif call.data == "ref_share":
        referral_system.show_share(call)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    update_username_mapping(call.from_user.id, call.from_user.username)
    save_user_info(call.from_user.id, call.from_user.username, call.from_user.first_name)

    if call.data == "menu":
        send_welcome(call.message)
    elif call.data in ["ref_menu", "ref_list", "ref_withdraw", "ref_share"]:
        handle_referral_callbacks(call)
    else:
        handle_game_callbacks(call)

# ========== ВЕБХУК ЭНДПОИНТЫ ==========

@app.route('/')
def index():
    return "🤖 Бот работает! Статус: ONLINE"

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'OK', 200

def set_webhook():
    """Устанавливает вебхук на Render"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        
        webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
        print(f"🔄 Устанавливаю вебхук: {webhook_url}")
        
        bot.set_webhook(
            url=webhook_url,
            secret_token=SECRET_TOKEN
        )
        print("✅ Вебхук успешно установлен!")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки вебхука: {e}")
        return False

# ========== ЗАПУСК ПРИЛОЖЕНИЯ ==========

if __name__ == "__main__":
    print("🤖 Бот запускается...")
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print("💡 Команды для администратора:")
    print("/add username сумма - пополнить баланс по username")
    print("/addid user_id сумма - пополнить баланс по ID")
    print("/find username/id - найти пользователя")
    print("/stats - статистика бота")
    print("🎯 Доступные игры: 🎲 Кубик, 🏀 Баскетбол, ⚽ Футбол, 🎯 Дартс, 🎳 Боулинг")
    print("👥 Реферальная система: 5% от выигрышей рефералов, минимальный вывод 1 USDT")
    
    # Устанавливаем вебхук при запуске
    if set_webhook():
        print("🚀 Приложение готово к работе!")
        
        # Запускаем Flask на порту 10000 (стандартный для Render)
        port = int(os.getenv('PORT', 10000))
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        print("❌ Не удалось установить вебхук")
        # Fallback: запускаем polling для разработки
        print("🔄 Запускаю polling как fallback...")
        bot.polling(none_stop=True, timeout=30)

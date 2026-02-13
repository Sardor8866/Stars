import telebot
from telebot import types
import threading
import time
import json
import os
from flask import Flask, request
import requests
from datetime import datetime, timedelta

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = '8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo'
ADMIN_CHAT_ID = 8118184388
WEBHOOK_URL = "https://stars-prok.onrender.com"
MINIAPP_URL = "https://eloquent-narwhal-62b8dc.netlify.app"
CRYPTOBOT_TOKEN = "477733:AAzooy5vcnCpJuGgTZc1Rdfbu71bqmrRMgr"

# ========== ОТКЛЮЧЕНИЕ ВСЕХ ПРОКСИ ==========
os.environ['NO_PROXY'] = '*'
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ[proxy_var] = ''

import requests as req_lib
from telebot import apihelper

session = req_lib.Session()
session.trust_env = False
apihelper.session = session
apihelper.proxy = None

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN, skip_pending=True, num_threads=5)

# Инициализация Flask для вебхуков
app = Flask(__name__)

# Словарь для отслеживания платежей
pending_payments = {}

# Инициализация модулей
try:
    from games import BettingGame, BET_TYPES, MIN_BET, CHANNEL_ID
    from referrals import ReferralSystem
    
    game = BettingGame(bot)
    referral_system = ReferralSystem(bot, game)
    game.set_referral_system(referral_system)
    # Метод set_miniapp_url не нужен - используем константу MINIAPP_URL из games.py
    
    print("✅ Модули игр и рефералов загружены")
    print(f"📢 Канал для игр: {CHANNEL_ID}")
    
except Exception as e:
    print(f"❌ Ошибка загрузки модулей: {e}")
    import traceback
    traceback.print_exc()
    import sys
    sys.exit(1)

# Словарь для хранения связи username -> user_id
username_to_id = {}

def update_username_mapping(user_id, username):
    if username:
        username_to_id[username] = user_id

def save_user_info(user_id, username, first_name):
    referral_system.save_user_info(user_id, username, first_name)
    if username:
        username_to_id[username] = user_id

    try:
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
    except Exception as e:
        pass

def load_user_mappings():
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
        pass

load_user_mappings()

# ========== CRYPTOBOT API ФУНКЦИИ ==========

def create_invoice(amount, description, user_id):
    url = "https://pay.crypt.bot/api/createInvoice"
    
    payload = {
        "amount": amount,
        "currency_type": "crypto",
        "asset": "USDT",
        "description": description,
        "paid_btn_name": "callback",
        "paid_btn_url": f"{WEBHOOK_URL}/payment_success",
        "payload": json.dumps({"user_id": user_id})
    }
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
    }
    
    try:
        response = req_lib.post(url, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get("ok"):
            return result["result"]
        else:
            return None
    except Exception as e:
        return None

def check_invoice_status(invoice_id):
    url = "https://pay.crypt.bot/api/getInvoices"
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN
    }
    
    params = {
        "invoice_ids": invoice_id
    }
    
    try:
        response = req_lib.get(url, params=params, headers=headers)
        response.raise_for_status()
        result = response.json()
        
        if result.get("ok") and result.get("result", {}).get("items"):
            return result["result"]["items"][0]["status"]
        return None
    except Exception as e:
        return None

# ========== ФУНКЦИИ ОБРАБОТКИ ПЛАТЕЖЕЙ ==========

def monitor_payment(invoice_id, user_id, game_type, outcome, amount):
    start_time = datetime.now()
    timeout = timedelta(minutes=3)
    check_interval = 5
    
    while datetime.now() - start_time < timeout:
        status = check_invoice_status(invoice_id)
        
        if status == "paid":
            if invoice_id in pending_payments:
                del pending_payments[invoice_id]
            
            publish_game_to_channel(user_id, game_type, outcome, amount)
            return True
        
        time.sleep(check_interval)
    
    if invoice_id in pending_payments:
        del pending_payments[invoice_id]
    
    try:
        bot.send_message(
            user_id,
            "⏰ Время оплаты истекло. Попробуйте снова.",
            parse_mode='HTML'
        )
    except:
        pass
    
    return False

def publish_game_to_channel(user_id, game_type, outcome, amount):
    try:
        try:
            user = bot.get_chat(user_id)
            nickname = f"@{user.username}" if user.username else user.first_name
        except:
            nickname = f"User {user_id}"
        
        success = game.add_game_to_queue(user_id, nickname, amount, game_type, outcome)
        
        if success:
            bot.send_message(
                user_id,
                f"✅ <b>Ставка принята!</b>\n\n"
                f"🎮 Игра: <code>{game_type}</code>\n"
                f"🎯 Исход: <code>{outcome}</code>\n"
                f"💰 Сумма: <code>{amount:.2f}$</code>\n\n"
                f"Игра будет опубликована в канале в порядке очереди.",
                parse_mode='HTML'
            )
        else:
            bot.send_message(
                user_id,
                "❌ Ошибка при создании игры. Попробуйте позже.",
                parse_mode='HTML'
            )
        
    except Exception as e:
        pass

# ========== ВЕБХУКИ ==========

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '', 200

@app.route('/create_bet', methods=['POST'])
def create_bet():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        game_type = data.get('game')
        outcome = data.get('outcome')
        amount = float(data.get('amount'))
        
        if amount < MIN_BET:
            return {
                'success': False,
                'error': f'Минимальная ставка: {MIN_BET}$'
            }
        
        description = f"Ставка {amount}$ на {game_type}"
        invoice = create_invoice(amount, description, user_id)
        
        if not invoice:
            return {
                'success': False,
                'error': 'Не удалось создать счет'
            }
        
        invoice_id = invoice['invoice_id']
        pending_payments[invoice_id] = {
            'user_id': user_id,
            'game': game_type,
            'outcome': outcome,
            'amount': amount,
            'timestamp': datetime.now()
        }
        
        threading.Thread(
            target=monitor_payment,
            args=(invoice_id, user_id, game_type, outcome, amount),
            daemon=True
        ).start()
        
        return {
            'success': True,
            'pay_url': invoice['pay_url'],
            'invoice_id': invoice_id
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

@app.route('/payment_success', methods=['POST'])
def payment_success():
    try:
        data = request.get_json()
        return {'ok': True}
    except Exception as e:
        return {'ok': False}

@app.route('/health', methods=['GET'])
def health():
    return {
        'status': 'ok',
        'pending_payments': len(pending_payments),
        'users': len(game.user_balances),
        'queue_size': game.game_queue.get_queue_size() if hasattr(game, 'game_queue') else 0
    }

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========

@bot.message_handler(commands=['start'])
def start_command(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    if ' ' in message.text:
        args = message.text.split()[1]
        if args.startswith('ref'):
            try:
                referrer_id = int(args[3:])
                referral_system.register_referral(
                    referee_id=message.from_user.id,
                    referrer_id=referrer_id,
                    referee_username=message.from_user.username,
                    referee_first_name=message.from_user.first_name
                )
            except Exception as e:
                pass

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("👛Баланс")
    btn2 = types.KeyboardButton("🤝 Партнеры")
    btn3 = types.KeyboardButton("🎮 Играть")
    markup.add(btn1, btn2, btn3)

    welcome_text = """
<b>🏠 Главное меню</b>
<blockquote>Выберите раздел:</blockquote>
    """
    bot.send_message(message.chat.id, welcome_text,
                     parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "👛Баланс")
def show_profile(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

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
        bot.send_photo(message.chat.id,
                       photo=image_url,
                       caption=profile_text,
                       parse_mode='HTML',
                       reply_markup=markup)
    except:
        bot.send_message(message.chat.id, profile_text,
                         parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🤝 Партнеры")
def show_partners(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    referral_system.show_menu(message)

@bot.message_handler(func=lambda message: message.text == "🎮 Играть")
def show_play_menu(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    try:
        game.show_games_menu(message)
    except Exception as e:
        bot.send_message(
            message.chat.id,
            "❌ Ошибка при открытии меню игр. Попробуйте позже."
        )

@bot.message_handler(commands=['add'])
def admin_add_balance(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    try:
        parts = message.text.split()
        if len(parts) < 3:
            bot.reply_to(message, "❌ Использование: /add username сумма")
            return
        username = parts[1].replace('@', '')
        amount = float(parts[2])
        if username in username_to_id:
            user_id = username_to_id[username]
            game.add_balance(user_id, amount)
            bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю @{username}")
        else:
            bot.reply_to(message, f"❌ Пользователь @{username} не найден")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

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
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return

    total_users = len(game.user_balances)
    total_balance = sum(game.user_balances.values())
    ref_stats = referral_system.get_stats(ADMIN_CHAT_ID)
    queue_size = game.game_queue.get_queue_size() if hasattr(game, 'game_queue') else 0

    stats_text = f"""
<b>📊 Статистика бота</b>
👥 Всего пользователей: <b>{total_users}</b>
💰 Общий баланс: <b>{total_balance:.2f} USDT</b>
📝 Известных username: <b>{len(username_to_id)}</b>
⏳ Ожидают оплаты: <b>{len(pending_payments)}</b>
🎮 Очередь игр: <b>{queue_size}</b>

<b>👥 Реферальная система:</b>
├ Приглашено: <b>{ref_stats['total_refs']} чел.</b>
├ Доступно: <b>{ref_stats['available']:.2f} USDT</b>
└ Выведено: <b>{ref_stats['withdrawn']:.2f} USDT</b>
    """
    bot.reply_to(message, stats_text, parse_mode='HTML')

@bot.message_handler(commands=['test_channel'])
def test_channel(message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    
    try:
        test_msg = bot.send_message(CHANNEL_ID, "🧪 Тестовое сообщение от бота")
        bot.reply_to(message, f"✅ Бот может отправлять сообщения в канал!")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}\n\nУбедитесь что бот добавлен в канал {CHANNEL_ID} как администратор")

@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def handle_deposit(call):
    update_username_mapping(call.from_user.id, call.from_user.username)
    save_user_info(
        call.from_user.id,
        call.from_user.username,
        call.from_user.first_name
    )
    bot.answer_callback_query(call.id, "📥 Пополнение в разработке", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    update_username_mapping(call.from_user.id, call.from_user.username)
    save_user_info(
        call.from_user.id,
        call.from_user.username,
        call.from_user.first_name
    )
    bot.answer_callback_query(call.id, "📤 Вывод в разработке", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data in ["ref_menu", "ref_list", "ref_withdraw", "ref_share"])
def handle_referral_callbacks(call):
    try:
        update_username_mapping(call.from_user.id, call.from_user.username)
        save_user_info(
            call.from_user.id,
            call.from_user.username,
            call.from_user.first_name
        )
        
        if call.data == "ref_menu":
            referral_system.show_menu(call)
        elif call.data == "ref_list":
            referral_system.show_ref_list(call)
        elif call.data == "ref_withdraw":
            referral_system.show_withdraw(call)
        elif call.data == "ref_share":
            referral_system.show_share(call)
            
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Произошла ошибка", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("game_"))
def handle_game_selection(call):
    try:
        update_username_mapping(call.from_user.id, call.from_user.username)
        save_user_info(
            call.from_user.id,
            call.from_user.username,
            call.from_user.first_name
        )
        
        if call.data == "game_dice":
            game.show_dice_menu(call)
        elif call.data == "game_basketball":
            game.show_basketball_menu(call)
        elif call.data == "game_football":
            game.show_football_menu(call)
        elif call.data == "game_darts":
            game.show_darts_menu(call)
        elif call.data == "game_bowling":
            game.show_bowling_menu(call)
            
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Произошла ошибка", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data.startswith("bet_"))
def handle_bet_selection(call):
    try:
        update_username_mapping(call.from_user.id, call.from_user.username)
        save_user_info(
            call.from_user.id,
            call.from_user.username,
            call.from_user.first_name
        )
        
        parts = call.data.split('_', 2)
        if len(parts) >= 3:
            bet_type = parts[2]
            game.request_amount(call, bet_type)
        elif call.data == "bet_dice_exact":
            game.show_exact_number_menu(call)
            
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        bot.answer_callback_query(call.id, "❌ Произошла ошибка", show_alert=True)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    
    if game.process_bet_amount(message):
        return
    
    if hasattr(referral_system, 'process_withdraw') and referral_system.process_withdraw(message):
        return

# ========== ЗАПУСК ==========

def setup_webhook():
    webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
    
    try:
        bot.remove_webhook()
        time.sleep(1)
        
        bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"]
        )
        
        print(f"✅ Вебхук установлен: {webhook_url}")
        return True
    except Exception as e:
        print(f"❌ Ошибка установки вебхука: {e}")
        return False

if __name__ == "__main__":
    print("🤖 Бот запускается в режиме вебхуков...")
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print(f"🌐 Webhook URL: {WEBHOOK_URL}")
    print(f"📱 MiniApp URL: {MINIAPP_URL}")
    print(f"📢 Канал для игр: {CHANNEL_ID}")
    
    try:
        test_msg = bot.send_message(CHANNEL_ID, "🚀 Бот запущен и готов к играм!")
        print(f"✅ Бот может отправлять сообщения в канал")
    except Exception as e:
        print(f"⚠️ ВНИМАНИЕ: Бот НЕ может отправлять сообщения в канал {CHANNEL_ID}!")
        print(f"⚠️ Ошибка: {e}")
        print(f"⚠️ Добавьте бота в канал как администратора!")
    
    if setup_webhook():
        port = int(os.environ.get('PORT', 5000))
        print(f"🚀 Flask сервер запускается на порту {port}")
        app.run(host='0.0.0.0', port=port)
    else:
        print("❌ Не удалось настроить вебхук")

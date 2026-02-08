import telebot
from telebot import types
import threading
import requests
import time
import json
import re
import os
import traceback
from flask import Flask, request, jsonify
from waitress import serve

# Импортируем модули
from games import BettingGame, BET_TYPES, MIN_BET, CHANNEL_LINK, PAYMENTS_CHANNEL_ID
from referrals import ReferralSystem

# Инициализация бота
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo')
bot = telebot.TeleBot(BOT_TOKEN)

# Конфигурация CryptoBot API
CRYPTOBOT_TOKEN = os.environ.get('CRYPTOBOT_TOKEN', "477733:AAzooy5vcnCpJuGgTZc1Rdfbu71bqmrRMgr")
CRYPTO_API_URL = "https://pay.crypt.bot/api"
ADMIN_CHAT_ID = 8118184388

# URL сервера (для Render.com)
SERVER_URL = os.environ.get('SERVER_URL', 'https://stars-prok.onrender.com')

# Ссылка на многоразовый счет (создан вручную через @CryptoBot)
MULTI_USE_INVOICE_LINK = "https://t.me/send?start=IVNg7XnKzxBs"

# Инициализация модулей
game = BettingGame(bot)
referral_system = ReferralSystem(bot, game)

# Связываем их между собой
game.set_referral_system(referral_system)

# Словарь для хранения связи username -> user_id
username_to_id = {}

# Множество для отслеживания обработанных платежей
processed_payments = set()

# Flask приложение
app = Flask(__name__)

def ensure_file_exists(filename, default_content=[]):
    """Создает файл если он не существует"""
    if not os.path.exists(filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(default_content, f, indent=4, ensure_ascii=False)
            print(f"✅ Создан файл {filename}")
        except Exception as e:
            print(f"❌ Ошибка создания файла {filename}: {e}")

def log_error(error_type, message, exc=None):
    """Логирует ошибки в файл"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    log_entry = {
        'timestamp': timestamp,
        'type': error_type,
        'message': message,
        'traceback': traceback.format_exc() if exc else None
    }
    
    try:
        with open('error_log.json', 'a', encoding='utf-8') as f:
            json.dump(log_entry, f, ensure_ascii=False)
            f.write('\n')
    except:
        pass
    
    print(f"❌ [{timestamp}] {error_type}: {message}")
    if exc:
        print(f"📋 Traceback: {traceback.format_exc()}")

def save_user_info(user_id, username, first_name):
    """Сохраняет информацию о пользователе во всех местах"""
    try:
        referral_system.save_user_info(user_id, username, first_name)

        if username:
            username_to_id[username.lower()] = user_id

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
        log_error("USER_SAVE_ERROR", f"Ошибка сохранения пользователя {user_id}: {e}", e)

def load_user_mappings():
    """Загружает сохраненные маппинги пользователей"""
    global username_to_id
    try:
        with open('user_mappings.json', 'r', encoding='utf-8') as f:
            user_mappings = json.load(f)

        for user_id_str, user_data in user_mappings.items():
            username = user_data.get('username', '')
            if username:
                username_to_id[username.lower()] = int(user_id_str)

        print(f"✅ Загружено {len(username_to_id)} маппингов пользователей")
    except Exception as e:
        print("ℹ️ Файл user_mappings.json не найден или поврежден")
        username_to_id = {}

def load_processed_payments():
    """Загружает уже обработанные платежи из файла"""
    global processed_payments
    try:
        with open('processed_payments.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            processed_payments = set(data)
        print(f"✅ Загружено {len(processed_payments)} обработанных платежей")
    except:
        print("ℹ️ Файл processed_payments.json не найден, создаем новый")
        processed_payments = set()

def save_processed_payment(payment_id):
    """Сохраняет ID обработанного платежа"""
    try:
        processed_payments.add(payment_id)
        with open('processed_payments.json', 'w', encoding='utf-8') as f:
            json.dump(list(processed_payments), f, indent=4)
    except Exception as e:
        log_error("PAYMENT_SAVE_ERROR", f"Ошибка сохранения платежа {payment_id}: {e}", e)

def process_pending_payments():
    """Обрабатывает сохраненные платежи из файла"""
    try:
        if not os.path.exists('pending_payments.json'):
            print("ℹ️ Файл pending_payments.json не найден")
            ensure_file_exists('pending_payments.json', [])
            return 0
        
        with open('pending_payments.json', 'r', encoding='utf-8') as f:
            pending_payments = json.load(f)
        
        print(f"🔍 Найдено {len(pending_payments)} платежей в pending_payments.json")
        
        new_processed = 0
        updated_payments = []
        
        for payment in pending_payments:
            if payment.get('processed', False):
                updated_payments.append(payment)
                continue
            
            payment_id = payment.get('payment_id')
            payment_data = payment.get('payment_data', {})
            bet_type = payment.get('bet_type')
            
            username = payment_data.get('username')
            amount = payment_data.get('amount', 0)
            comment = payment_data.get('comment', '')
            
            print(f"\n🔍 Обрабатываю сохраненный платеж {payment_id}:")
            print(f"   Username: @{username}")
            print(f"   Сумма: {amount}")
            print(f"   Комментарий: '{comment}'")
            print(f"   Тип ставки: {bet_type}")
            
            # Проверяем минимальную сумму
            if amount < MIN_BET:
                print(f"⚠️ Игнорируем малый платёж: {amount} USDT (мин: {MIN_BET})")
                payment['processed'] = True
                updated_payments.append(payment)
                continue
            
            # Ищем user_id по username
            user_id = None
            if username and username.lower() in username_to_id:
                user_id = username_to_id[username.lower()]
                print(f"✅ Найден user_id: {user_id} для @{username}")
            else:
                print(f"⚠️ Не найден user_id для @{username}")
                print(f"   Доступные username: {list(username_to_id.keys())[:10]}...")
            
            if not user_id:
                print(f"❌ Пропускаем платеж - user_id не найден")
                updated_payments.append(payment)
                continue
            
            # Получаем никнейм пользователя
            nickname = f"Игрок_{user_id}"
            try:
                user_info = bot.get_chat(user_id)
                nickname = user_info.first_name or nickname
                if user_info.last_name:
                    nickname += f" {user_info.last_name}"
                print(f"✅ Никнейм: {nickname}")
            except Exception as e:
                print(f"⚠️ Не удалось получить информацию о пользователе: {e}")
            
            # Создаем игру
            print(f"🎮 Создаю игру для {nickname}...")
            success = game.create_game_from_payment(user_id, username, amount, bet_type, nickname)
            
            if success:
                payment['processed'] = True
                new_processed += 1
                save_processed_payment(payment_id)
                print(f"✅ Успешно создана игра для платежа {payment_id}")
                
                # Уведомляем админа
                try:
                    bot.send_message(
                        ADMIN_CHAT_ID,
                        f"🎮 Новая ставка!\n\n"
                        f"👤 Пользователь: {nickname} (@{username})\n"
                        f"💰 Сумма: {amount} USDT\n"
                        f"🎯 Ставка: {bet_type}\n"
                        f"📅 Время: {time.strftime('%H:%M:%S')}",
                        parse_mode='HTML'
                    )
                    print(f"📨 Уведомление отправлено админу")
                except Exception as e:
                    print(f"⚠️ Не удалось отправить уведомление админу: {e}")
            else:
                print(f"❌ Ошибка создания игры для платежа {payment_id}")
            
            updated_payments.append(payment)
        
        # Сохраняем обновленный список
        with open('pending_payments.json', 'w', encoding='utf-8') as f:
            json.dump(updated_payments, f, indent=4, ensure_ascii=False)
        
        if new_processed > 0:
            print(f"\n✅ Обработано {new_processed} новых платежей из pending_payments.json")
        else:
            print(f"\nℹ️ Новых платежей для обработки не найдено")
        
        return new_processed
        
    except Exception as e:
        log_error("PENDING_PAYMENTS_ERROR", f"Ошибка обработки pending_payments: {e}", e)
        return 0

# Flask роуты
@app.route('/')
def index():
    return jsonify({
        "status": "Bot is running",
        "timestamp": time.time(),
        "processed_payments": len(processed_payments),
        "known_users": len(username_to_id)
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": time.time(),
        "processed_payments": len(processed_payments),
        "known_users": len(username_to_id)
    }), 200

@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Обработчик вебхука от Telegram"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data().decode('utf-8')
            update = telebot.types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return '', 200
        else:
            return 'Invalid content type', 400
    except Exception as e:
        log_error("WEBHOOK_ERROR", f"Ошибка обработки Telegram webhook: {e}", e)
        return 'Error', 500

@app.route('/check_payments', methods=['POST'])
def manual_check():
    """Ручная проверка платежей (для тестирования)"""
    try:
        result = process_pending_payments()
        return jsonify({
            "status": "ok",
            "processed_new": result,
            "processed_total": len(processed_payments)
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/debug', methods=['GET'])
def debug_info():
    """Отладочная информация"""
    # Создаем файлы если их нет
    ensure_file_exists('pending_payments.json', [])
    ensure_file_exists('processed_payments.json', [])
    ensure_file_exists('balances.json', {})
    
    # Проверяем размеры файлов
    files_info = {}
    for filename in ['user_mappings.json', 'processed_payments.json', 'pending_payments.json', 'balances.json']:
        if os.path.exists(filename):
            files_info[filename] = os.path.getsize(filename)
        else:
            files_info[filename] = 0
    
    return jsonify({
        "username_to_id_count": len(username_to_id),
        "processed_payments_count": len(processed_payments),
        "files": files_info,
        "timestamp": time.time(),
        "server_url": SERVER_URL
    })

# Загружаем сохраненные данные при запуске
ensure_file_exists('pending_payments.json', [])
ensure_file_exists('processed_payments.json', [])
ensure_file_exists('balances.json', {})
ensure_file_exists('error_log.json', [])

load_user_mappings()
load_processed_payments()

# Обрабатываем накопленные платежи при запуске
print("\n🔍 Проверяю накопленные платежи...")
initial_processed = process_pending_payments()
if initial_processed > 0:
    print(f"✅ При запуске обработано {initial_processed} платежей")
else:
    print(f"ℹ️ Новых платежей при запуске не найдено")

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    try:
        print(f"👋 Команда /start от {message.from_user.id} (@{message.from_user.username})")
        
        save_user_info(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )

        # Проверяем реферальную ссылку
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

        welcome_text = """
<b>🏠 Главное меню</b>
<blockquote>Выберите раздел:</blockquote>
        """
        bot.send_message(message.chat.id, welcome_text,
                         parse_mode='HTML', reply_markup=markup)
        
        print(f"✅ Главное меню отправлено {message.from_user.id}")
    except Exception as e:
        log_error("START_COMMAND_ERROR", f"Ошибка в команде /start: {e}", e)

@bot.message_handler(func=lambda message: message.text == "👛Баланс")
def show_profile(message):
    try:
        print(f"💰 Запрос баланса от {message.from_user.id}")
        
        save_user_info(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )

        user_id = message.from_user.id
        balance = game.get_balance(user_id)
        
        instruction_text = f"""
<b>💳 Как сделать ставку через многоразовый счёт:</b>

1. Нажмите кнопку "💳 Сделать ставку" ниже
2. В открывшемся окне CryptoBot:
   • Введите сумму (минимум {MIN_BET} USDT)
   • В комментарии укажите ТИП СТАВКИ и свой username:
     <code>тип_ставки @ваш_username</code>

3. Оплатите счёт
4. Игра автоматически появится в канале!

<b>📝 Примеры комментариев:</b>
• <code>куб_чет @{message.from_user.username}</code>
• <code>баскет_гол @{message.from_user.username}</code>
• <code>футбол_мимо @{message.from_user.username}</code>

<b>🎯 Доступные ставки:</b>
• Кубик: куб_чет, куб_нечет, куб_мал, куб_бол, куб_1-куб_6
• Баскетбол: баскет_гол, баскет_мимо, баскет_3очка
• Футбол: футбол_гол, футбол_мимо
• Дартс: дартс_белое, дартс_красное, дартс_мимо, дартс_центр
• Боулинг: боулинг_победа, боулинг_поражение, боулинг_страйк

<b>👛 Ваш баланс: <code>{balance:.2f} USDT</code></b>
<b>📝 Ваш username для комментария: @{message.from_user.username}</b>
"""

        markup = types.InlineKeyboardMarkup(row_width=1)
        btn1 = types.InlineKeyboardButton("💳 Сделать ставку", url=MULTI_USE_INVOICE_LINK)
        markup.add(btn1)
        
        image_url = "https://iimg.su/i/u0SuFd"
        bot.send_photo(message.chat.id,
                       photo=image_url,
                       caption=instruction_text,
                       parse_mode='HTML',
                       reply_markup=markup)
        
        print(f"✅ Баланс отправлен {message.from_user.id}: {balance} USDT")
    except Exception as e:
        log_error("BALANCE_ERROR", f"Ошибка показа баланса: {e}", e)

@bot.message_handler(func=lambda message: message.text == "🤝 Партнеры")
def show_partners(message):
    try:
        print(f"🤝 Запрос партнеров от {message.from_user.id}")
        save_user_info(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )
        referral_system.show_menu(message)
    except Exception as e:
        log_error("PARTNERS_ERROR", f"Ошибка показа партнеров: {e}", e)

@bot.message_handler(func=lambda message: message.text == "🎮 Играть")
def show_games(message):
    try:
        print(f"🎮 Запрос игр от {message.from_user.id}")
        save_user_info(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )
        game.show_games_menu(message)
    except Exception as e:
        log_error("GAMES_ERROR", f"Ошибка показа игр: {e}", e)

# Обработчик сообщений из канала с платежами
@bot.message_handler(func=lambda message: message.chat.id == PAYMENTS_CHANNEL_ID)
def handle_payment_channel(message):
    """Обрабатывает сообщения из канала с платежами"""
    try:
        print(f"\n📩 Получено сообщение из канала платежей (ID: {message.message_id})")
        print(f"📝 Текст сообщения:\n{message.text}")
        
        # Пробуем обработать как платеж
        if game.process_payment_from_channel(message):
            print(f"✅ Сообщение {message.message_id} распознано как платеж")
            
            # Немедленно обрабатываем накопленные платежи
            processed = process_pending_payments()
            print(f"✅ Обработано {processed} платежей после нового сообщения")
        else:
            print(f"⚠️ Сообщение {message.message_id} не распознано как платеж")
            
    except Exception as e:
        log_error("CHANNEL_HANDLER_ERROR", f"Ошибка обработки сообщения из канала: {e}", e)

@bot.message_handler(commands=['add'])
def admin_add_balance(message):
    try:
        if message.from_user.id != ADMIN_CHAT_ID:
            return
        
        print(f"➕ Админ команда /add от {message.from_user.id}")
        
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
            print(f"✅ Админ добавил {amount} USDT @{username}")
        else:
            try:
                user_id = int(username)
                game.add_balance(user_id, amount)
                bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю ID: {user_id}")
                print(f"✅ Админ добавил {amount} USDT ID: {user_id}")
            except ValueError:
                bot.reply_to(message, f"❌ Пользователь @{username} не найден.")
                print(f"❌ Пользователь @{username} не найден")

    except Exception as e:
        log_error("ADD_BALANCE_ERROR", f"Ошибка команды /add: {e}", e)
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['check'])
def admin_check_payments(message):
    """Админ команда для ручной проверки платежей"""
    try:
        if message.from_user.id != ADMIN_CHAT_ID:
            return
        
        print(f"🔍 Админ проверяет платежи")
        
        bot.reply_to(message, "🔄 Проверяю платежи...")
        processed = process_pending_payments()
        bot.reply_to(message, f"✅ Проверка завершена!\nОбработано новых: {processed} платежей\nВсего: {len(processed_payments)} платежей")
        
    except Exception as e:
        log_error("CHECK_PAYMENTS_ERROR", f"Ошибка команды /check: {e}", e)

@bot.message_handler(commands=['debug'])
def admin_debug(message):
    """Отладочная информация для админа"""
    try:
        if message.from_user.id != ADMIN_CHAT_ID:
            return
        
        # Создаем файлы если их нет
        ensure_file_exists('pending_payments.json', [])
        ensure_file_exists('processed_payments.json', [])
        ensure_file_exists('balances.json', {})
        
        # Проверяем файлы
        files_info = []
        for filename in ['user_mappings.json', 'processed_payments.json', 'pending_payments.json', 'balances.json']:
            exists = os.path.exists(filename)
            size = os.path.getsize(filename) if exists else 0
            files_info.append(f"{filename}: {'✅' if exists else '❌'} ({size} байт)")
        
        # Проверяем pending_payments.json
        pending_info = "Нет данных"
        if os.path.exists('pending_payments.json'):
            try:
                with open('pending_payments.json', 'r', encoding='utf-8') as f:
                    pending_data = json.load(f)
                    pending_processed = len([p for p in pending_data if p.get('processed', False)])
                    pending_total = len(pending_data)
                    pending_info = f"{pending_total} всего, {pending_processed} обработано, {pending_total - pending_processed} ожидает"
            except:
                pending_info = "Ошибка чтения"
        
        debug_text = f"""
<b>🔧 Отладочная информация:</b>

<b>📊 Статистика:</b>
👥 Пользователей: {len(username_to_id)}
💰 Обработано платежей: {len(processed_payments)}
⏳ Pending платежей: {pending_info}

<b>📁 Файлы:</b>
{chr(10).join(files_info)}

<b>🔍 Примеры username:</b>
{chr(10).join([f'@{k} → {v}' for k, v in list(username_to_id.items())[:5]])}
"""
        
        bot.reply_to(message, debug_text, parse_mode='HTML')
        
    except Exception as e:
        log_error("DEBUG_ERROR", f"Ошибка команды /debug: {e}", e)

@bot.message_handler(commands=['stats'])
def admin_stats(message):
    try:
        if message.from_user.id != ADMIN_CHAT_ID:
            return

        print(f"📊 Админ запросил статистику")

        total_users = len(game.user_balances)
        total_balance = sum(game.user_balances.values())
        ref_stats = referral_system.get_stats(ADMIN_CHAT_ID)

        # Получаем количество pending платежей
        pending_count = 0
        try:
            if os.path.exists('pending_payments.json'):
                with open('pending_payments.json', 'r', encoding='utf-8') as f:
                    pending_payments = json.load(f)
                    pending_count = len([p for p in pending_payments if not p.get('processed', False)])
        except Exception as e:
            print(f"⚠️ Ошибка чтения pending_payments: {e}")

        stats_text = f"""
<b>📊 Статистика бота</b>
👥 Всего пользователей: <b>{total_users}</b>
💰 Общий баланс: <b>{total_balance:.2f} USDT</b>
📝 Известных username: <b>{len(username_to_id)}</b>
💳 Обработано платежей: <b>{len(processed_payments)}</b>
⏳ Ожидающих обработки: <b>{pending_count}</b>

<b>👥 Реферальная система:</b>
├ Приглашено: <b>{ref_stats['total_refs']} чел.</b>
├ Доступно: <b>{ref_stats['available']:.2f} USDT</b>
└ Выведено: <b>{ref_stats['withdrawn']:.2f} USDT</b>
        """
        bot.reply_to(message, stats_text, parse_mode='HTML')
        
    except Exception as e:
        log_error("STATS_ERROR", f"Ошибка команды /stats: {e}", e)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    try:
        save_user_info(
            message.from_user.id,
            message.from_user.username,
            message.from_user.first_name
        )

        if referral_system.process_withdraw(message):
            return

        if game.process_bet_amount(message):
            return
            
    except Exception as e:
        log_error("TEXT_HANDLER_ERROR", f"Ошибка обработки текста: {e}", e)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        save_user_info(
            call.from_user.id,
            call.from_user.username,
            call.from_user.first_name
        )

        if call.data == "menu":
            send_welcome(call.message)
        
        # Реферальные callback-ы
        elif call.data in ["ref_menu", "ref_list", "ref_withdraw", "ref_share"]:
            if call.data == "ref_menu":
                referral_system.show_menu(call)
            elif call.data == "ref_list":
                referral_system.show_ref_list(call)
            elif call.data == "ref_withdraw":
                referral_system.show_withdraw(call)
            elif call.data == "ref_share":
                referral_system.show_share(call)
        
        # Игровые callback-ы - КУБИК
        elif call.data == "game_dice":
            game.show_dice_menu(call)
        elif call.data == "bet_dice_exact":
            game.show_exact_numbers(call)
        elif call.data.startswith("bet_dice_"):
            bet_type = call.data.replace("bet_dice_", "")
            if bet_type in BET_TYPES:
                game.request_amount(call, bet_type)
        
        # БАСКЕТБОЛ
        elif call.data == "game_basketball":
            game.show_basketball_menu(call)
        elif call.data.startswith("bet_basketball_"):
            bet_type = call.data.replace("bet_basketball_", "")
            if bet_type in BET_TYPES:
                game.request_amount(call, bet_type)
        
        # ФУТБОЛ
        elif call.data == "game_football":
            game.show_football_menu(call)
        elif call.data.startswith("bet_football_"):
            bet_type = call.data.replace("bet_football_", "")
            if bet_type in BET_TYPES:
                game.request_amount(call, bet_type)
        
        # ДАРТС
        elif call.data == "game_darts":
            game.show_darts_menu(call)
        elif call.data.startswith("bet_darts_"):
            bet_type = call.data.replace("bet_darts_", "")
            if bet_type in BET_TYPES:
                game.request_amount(call, bet_type)
        
        # БОУЛИНГ
        elif call.data == "game_bowling":
            game.show_bowling_menu(call)
        elif call.data.startswith("bet_bowling_"):
            bet_type = call.data.replace("bet_bowling_", "")
            if bet_type in BET_TYPES:
                game.request_amount(call, bet_type)
                
    except Exception as e:
        log_error("CALLBACK_ERROR", f"Ошибка обработки callback: {e}", e)

def setup_telegram_webhook():
    """Настраивает Telegram webhook"""
    try:
        webhook_url = f"{SERVER_URL}/webhook/telegram"
        
        # Удаляем старый вебхук
        bot.remove_webhook()
        time.sleep(1)
        
        # Устанавливаем новый
        bot.set_webhook(url=webhook_url)
        
        # Проверяем установку
        webhook_info = bot.get_webhook_info()
        
        print(f"✅ Telegram webhook установлен")
        print(f"   URL: {webhook_info.url}")
        print(f"   Pending: {webhook_info.pending_update_count}")
        
        return True
        
    except Exception as e:
        log_error("WEBHOOK_SETUP_ERROR", f"Ошибка установки Telegram webhook: {e}", e)
        return False

def run_flask():
    """Запускает Flask сервер"""
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Запуск Flask сервера на порту {port}")
    print(f"🌐 URL: {SERVER_URL}")
    
    # Проверяем доступность порта
    try:
        serve(app, host='0.0.0.0', port=port)
    except Exception as e:
        log_error("FLASK_ERROR", f"Ошибка запуска Flask: {e}", e)

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print(f"💰 Минимальная ставка: {MIN_BET} USDT")
    print(f"🌐 Server URL: {SERVER_URL}")
    print(f"🔗 Многоразовый счет: {MULTI_USE_INVOICE_LINK}")
    print(f"📺 Канал с платежами ID: {PAYMENTS_CHANNEL_ID}")
    
    # Проверяем подключение к боту
    print("\n🤖 Проверка подключения к Telegram API...")
    try:
        bot_info = bot.get_me()
        print(f"✅ Бот подключен: @{bot_info.username} ({bot_info.first_name})")
    except Exception as e:
        print(f"❌ Ошибка подключения к Telegram: {e}")
    
    print("\n🚀 Запуск Flask сервера...")
    # Запускаем Flask сервер (он будет работать в основном потоке)
    run_flask()

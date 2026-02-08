import telebot
from telebot import types
import threading
import requests
import time
import json
import re
import os
from flask import Flask, request, jsonify
from waitress import serve

# Импортируем модули
from games import BettingGame, BET_TYPES, MIN_BET, CHANNEL_LINK
from referrals import ReferralSystem

# Инициализация бота
bot = telebot.TeleBot('8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo')

# Конфигурация CryptoBot API
CRYPTOBOT_TOKEN = "477733:AAzooy5vcnCpJuGgTZc1Rdfbu71bqmrRMgr"
CRYPTO_API_URL = "https://pay.crypt.bot/api"
ADMIN_CHAT_ID = 8118184388

# Вебхук секрет
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'your-secret-token-here')

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

def save_user_info(user_id, username, first_name):
    """Сохраняет информацию о пользователе во всех местах"""
    # 1. В реферальной системе
    referral_system.save_user_info(user_id, username, first_name)

    # 2. В словаре username_to_id
    if username:
        username_to_id[username] = user_id

    # 3. В файле для постоянного хранения
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
        print(f"⚠️ Ошибка сохранения user_mappings: {e}")

def load_user_mappings():
    """Загружает сохраненные маппинги пользователей"""
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

def parse_payment_comment(comment):
    """Парсит комментарий к платежу - ТОЛЬКО ТИП СТАВКИ"""
    if not comment:
        return None, None, None
    
    # Убираем лишние пробелы
    comment = comment.strip().lower()
    
    # Убираем username если есть
    comment = re.sub(r'@\w+', '', comment).strip()
    
    # Разбиваем на части
    parts = re.split(r'\s+', comment)
    
    # Ищем тип ставки в любой части
    for part in parts:
        # Проверяем точное совпадение
        if part in BET_TYPES:
            return None, part, None
        
        # Пробуем с дефисом
        if '-' in part:
            variant = part.replace('-', '_')
            if variant in BET_TYPES:
                return None, variant, None
        
        # Пробуем с подчеркиванием
        if '_' in part:
            variant = part.replace('_', '-')
            if variant in BET_TYPES:
                return None, variant, None
    
    # Если не нашли, пробуем комбинацию слов
    if len(parts) >= 2:
        combined = f"{parts[0]}_{parts[1]}"
        if combined in BET_TYPES:
            return None, combined, None
        
        combined2 = f"{parts[0]}-{parts[1]}".replace('-', '_')
        if combined2 in BET_TYPES:
            return None, combined2, None
    
    return None, None, None

def extract_username_from_comment(comment):
    """Извлекает username из комментария"""
    if not comment:
        return None
    
    # Ищем @username в комментарии
    username_match = re.search(r'@(\w+)', comment)
    if username_match:
        return username_match.group(1).lower()
    
    return None

def process_invoice_payment(payment_data):
    """Обрабатывает оплаченный инвойс"""
    try:
        payment_id = payment_data.get('invoice_id') or payment_data.get('payment_id')
        
        if not payment_id or payment_id in processed_payments:
            return
        
        # Получаем данные платежа
        amount = float(payment_data.get('amount', 0))
        asset = payment_data.get('asset', 'USDT')
        comment = payment_data.get('comment', '').strip()
        
        print(f"\n🔍 Вебхук: Платёж {payment_id}:")
        print(f"   Сумма: {amount} {asset}")
        print(f"   Комментарий: '{comment}'")
        
        # Проверяем минимальную сумму
        if amount < MIN_BET:
            print(f"⚠️ Игнорируем малый платёж: {amount} USDT (мин: {MIN_BET})")
            processed_payments.add(payment_id)
            return
        
        # Извлекаем username из комментария
        username = extract_username_from_comment(comment)
        if not username:
            print(f"⚠️ Не найден username в комментарии: '{comment}'")
            processed_payments.add(payment_id)
            return
        
        # Парсим тип ставки
        _, bet_type, _ = parse_payment_comment(comment)
        
        if not bet_type:
            print(f"⚠️ Не удалось определить тип ставки из комментария: '{comment}'")
            
            # Отправляем сообщение об ошибке если username найден
            if username in username_to_id:
                user_id = username_to_id[username]
                try:
                    bot.send_message(
                        user_id,
                        f"❌ <b>Ошибка в комментарии к платежу!</b>\n\n"
                        f"Не удалось определить тип ставки из: <code>{comment}</code>\n\n"
                        f"<b>Правильный формат комментария:</b>\n"
                        f"<code>тип_ставки @ваш_username</code>\n\n"
                        f"<b>Примеры:</b>\n"
                        f"• <code>куб_чет @{username}</code>\n"
                        f"• <code>баскет_гол @{username}</code>\n"
                        f"• <code>футбол_мимо @{username}</code>\n\n"
                        f"<b>Ваш username:</b> @{username}",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            processed_payments.add(payment_id)
            return
        
        # Проверяем тип ставки
        if bet_type not in BET_TYPES:
            print(f"⚠️ Неизвестный тип ставки: '{bet_type}'")
            processed_payments.add(payment_id)
            return
        
        bet_config = BET_TYPES[bet_type]
        
        # Ищем user_id по username
        user_id = None
        if username in username_to_id:
            user_id = username_to_id[username]
        else:
            print(f"⚠️ Username '@{username}' не найден в базе")
            processed_payments.add(payment_id)
            return
        
        # Получаем информацию о пользователе
        nickname = f"Игрок_{user_id}"
        try:
            user_info = bot.get_chat(user_id)
            nickname = user_info.first_name or nickname
            if user_info.last_name:
                nickname += f" {user_info.last_name}"
            
            # Сохраняем информацию
            save_user_info(
                user_id,
                user_info.username,
                user_info.first_name
            )
            
            print(f"✅ Пользователь найден: {nickname} (@{user_info.username})")
        except Exception as e:
            print(f"⚠️ Не удалось получить информацию о пользователе {user_id}: {e}")
        
        # Создаём игру
        game_data = {
            'user_id': user_id,
            'nickname': nickname,
            'amount': amount,
            'bet_type': bet_type,
            'bet_config': bet_config,
            'from_bot': True
        }
        
        game.game_queue.add_game(game_data)
        
        # Отправляем уведомление пользователю
        try:
            queue_size = game.game_queue.get_queue_size() - 1
            queue_msg = f"\n⏳ Ваша игра в очереди. Перед вами {queue_size} игр(ы)" if queue_size > 0 else ""
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗 Смотреть в канале", url=CHANNEL_LINK))
            
            bot.send_message(
                user_id,
                f"✅ <b>Ставка принята!</b>\n\n"
                f"💰 <b>Сумма:</b> {amount:.2f} USDT\n"
                f"🎯 <b>Ставка:</b> {bet_config['name']}\n"
                f"📈 <b>Коэффициент:</b> x{bet_config['multiplier']}\n"
                f"💎 <b>Возможный выигрыш:</b> {amount * bet_config['multiplier']:.2f} USDT{queue_msg}\n\n"
                f"Следите за игрой в <a href='{CHANNEL_LINK}'>нашем канале</a>",
                parse_mode='HTML',
                reply_markup=markup
            )
            print(f"✅ Ставка создана для {user_id} ({nickname}): {amount} USDT на {bet_type}")
        except Exception as e:
            print(f"⚠️ Не удалось отправить уведомление пользователю {user_id}: {e}")
        
        processed_payments.add(payment_id)
        
        # Сохраняем в лог
        try:
            with open('payment_log.json', 'a', encoding='utf-8') as f:
                log_entry = {
                    'payment_id': payment_id,
                    'user_id': user_id,
                    'username': username,
                    'amount': amount,
                    'bet_type': bet_type,
                    'nickname': nickname,
                    'comment': comment,
                    'timestamp': time.time(),
                    'date': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'source': 'webhook'
                }
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except:
            pass
        
    except Exception as e:
        print(f"❌ Ошибка обработки платежа из вебхука: {e}")
        import traceback
        traceback.print_exc()

# ВЕБХУК РОУТЫ
@app.route('/')
def index():
    return jsonify({"status": "Bot is running", "timestamp": time.time()})

@app.route('/webhook/cryptobot', methods=['POST'])
def cryptobot_webhook():
    """Обработчик вебхука от CryptoBot"""
    try:
        # Проверяем секретный токен
        secret_token = request.headers.get('Crypto-Pay-Api-Secret')
        if secret_token != WEBHOOK_SECRET:
            print(f"⚠️ Неверный секретный токен вебхука")
            return jsonify({"status": "error", "message": "Invalid token"}), 403
        
        data = request.json
        print(f"📥 Получен вебхук от CryptoBot: {json.dumps(data, indent=2)}")
        
        # Проверяем тип события
        update_type = data.get('update_type')
        
        if update_type == 'invoice_paid':
            payment_data = data.get('payload', {})
            # Обрабатываем в отдельном потоке
            threading.Thread(target=process_invoice_payment, args=(payment_data,)).start()
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print(f"❌ Ошибка обработки вебхука: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Обработчик вебхука от Telegram"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Invalid content type', 400

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()}), 200

# Загружаем сохраненные маппинги при запуске
load_user_mappings()

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
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

@bot.message_handler(func=lambda message: message.text == "👛Баланс")
def show_profile(message):
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    user_id = message.from_user.id
    balance = game.get_balance(user_id)
    
    # Обновленная инструкция с ВЕБХУКАМИ
    instruction_text = f"""
<b>💳 Как сделать ставку через многоразовый счёт:</b>

1. Нажмите кнопку "💳 Сделать ставку" ниже
2. В открывшемся окне CryptoBot:
   • Введите сумму (минимум {MIN_BET} USDT)
   • В комментарии укажите:
     <code>тип_ставки @ваш_username</code>

3. Оплатите счёт
4. Ставка создастся автоматически через вебхук!

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
    # Используем многоразовую ссылку
    MULTI_USE_INVOICE_LINK = "https://t.me/CryptoBot?start=invoice-XXXXXXXXXX"
    btn1 = types.InlineKeyboardButton("💳 Сделать ставку", url=MULTI_USE_INVOICE_LINK)
    btn2 = types.InlineKeyboardButton("🔄 Проверить платежи", callback_data="check_payments")
    markup.add(btn1, btn2)
    
    image_url = "https://iimg.su/i/u0SuFd"
    bot.send_photo(message.chat.id,
                   photo=image_url,
                   caption=instruction_text,
                   parse_mode='HTML',
                   reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🤝 Партнеры")
def show_partners(message):
    """Показывает меню реферальной системы"""
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
    referral_system.show_menu(message)

@bot.message_handler(func=lambda message: message.text == "🎮 Играть")
def show_games(message):
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )
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
    """Поиск пользователя по username или ID"""
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
💳 Обработано платежей: <b>{len(processed_payments)}</b>

<b>👥 Реферальная система:</b>
├ Приглашено: <b>{ref_stats['total_refs']} чел.</b>
├ Доступно: <b>{ref_stats['available']:.2f} USDT</b>
└ Выведено: <b>{ref_stats['withdrawn']:.2f} USDT</b>
    """
    bot.reply_to(message, stats_text, parse_mode='HTML')

@bot.message_handler(commands=['payments'])
def show_payments(message):
    """Показывает последние платежи"""
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    
    try:
        text = "<b>💳 Обработанные платежи:</b>\n\n"
        
        # Читаем из лога последние платежи
        try:
            with open('payment_log.json', 'r', encoding='utf-8') as f:
                lines = f.readlines()[-10:]  # Последние 10 платежей
                
            for i, line in enumerate(reversed(lines), 1):
                try:
                    payment = json.loads(line.strip())
                    payment_id = payment.get('payment_id', 'N/A')
                    amount = payment.get('amount', 0)
                    username = payment.get('username', 'N/A')
                    bet_type = payment.get('bet_type', 'N/A')
                    date = payment.get('date', 'N/A')
                    source = payment.get('source', 'unknown')
                    
                    text += f"{i}. 💸 <code>{amount} USDT</code>\n"
                    text += f"   👤 @{username}\n"
                    text += f"   🎯 {bet_type}\n"
                    text += f"   📅 {date}\n"
                    text += f"   📍 {source}\n\n"
                except:
                    pass
        except:
            text += "📭 Нет данных о платежах\n\n"
        
        text += f"<b>Всего обработано:</b> {len(processed_payments)} платежей"
        
        bot.reply_to(message, text, parse_mode='HTML')
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def handle_game_callbacks(call, game):
    """Обработчик callback-кнопок игр"""
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
    """Обработчик callback-кнопок реферальной системы"""
    if call.data == "ref_menu":
        referral_system.show_menu(call)
    elif call.data == "ref_list":
        referral_system.show_ref_list(call)
    elif call.data == "ref_withdraw":
        referral_system.show_withdraw(call)
    elif call.data == "ref_share":
        referral_system.show_share(call)

def handle_bet_amount_input(message, game):
    """Обработчик ввода суммы ставки"""
    return game.process_bet_amount(message)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    # Сначала проверяем, не является ли это выводом реферальных средств
    if referral_system.process_withdraw(message):
        return

    # Затем проверяем, не является ли это ставкой
    if handle_bet_amount_input(message, game):
        return

@bot.callback_query_handler(func=lambda call: call.data == "check_payments")
def handle_check_payments(call):
    """Проверяет статус платежей"""
    try:
        payments_count = len(processed_payments)
        bot.answer_callback_query(
            call.id,
            f"✅ Обработано платежей: {payments_count}\nВебхуки работают!",
            show_alert=True
        )
    except:
        bot.answer_callback_query(call.id, "✅ Платежи обрабатываются через вебхуки")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    save_user_info(
        call.from_user.id,
        call.from_user.username,
        call.from_user.first_name
    )

    if call.data == "menu":
        send_welcome(call.message)

    # Реферальные callback-ы
    elif call.data in ["ref_menu", "ref_list", "ref_withdraw", "ref_share"]:
        handle_referral_callbacks(call)

    # Проверка платежей
    elif call.data == "check_payments":
        handle_check_payments(call)

    # Игровые callback-ы
    else:
        handle_game_callbacks(call, game)

def setup_cryptobot_webhook():
    """Настраивает вебхук в CryptoBot"""
    try:
        # Получаем URL вебхука
        webhook_url = "https://stars-prok.onrender.com/webhook/cryptobot"
        
        headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
        
        payload = {
            'url': webhook_url,
            'secret_token': WEBHOOK_SECRET
        }
        
        response = requests.post(
            f'{CRYPTO_API_URL}/setWebhook',
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ok'):
                print(f"✅ Вебхук CryptoBot установлен: {webhook_url}")
                return True
            else:
                print(f"⚠️ Ошибка CryptoBot API: {result.get('error')}")
        else:
            print(f"❌ HTTP ошибка: {response.status_code}")
        
        return False
        
    except Exception as e:
        print(f"❌ Ошибка установки вебхука CryptoBot: {e}")
        return False

def setup_telegram_webhook():
    """Настраивает вебхук в Telegram"""
    try:
        # Получаем URL вебхука
        webhook_url = "https://stars-prok.onrender.com/webhook/telegram"
        
        # Удаляем старый вебхук
        bot.remove_webhook()
        time.sleep(1)
        
        # Устанавливаем новый
        bot.set_webhook(url=webhook_url)
        
        print(f"✅ Вебхук Telegram установлен: {webhook_url}")
        print(f"✅ Токен бота: {bot.token[:10]}...")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка установки вебхука Telegram: {e}")
        return False

def run_flask():
    """Запускает Flask сервер"""
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Запуск Flask сервера на порту {port}")
    print(f"🌐 Ссылка: https://stars-prok.onrender.com")
    serve(app, host='0.0.0.0', port=port)

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 БОТ ЗАПУЩЕН С ВЕБХУКАМИ")
    print("=" * 50)
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print(f"💰 Минимальная ставка: {MIN_BET} USDT")
    
    # Загружаем данные пользователей
    load_user_mappings()
    
    # Настраиваем вебхук Telegram
    print("📱 Настройка вебхука Telegram...")
    if setup_telegram_webhook():
        print("✅ Вебхук Telegram успешно настроен")
    else:
        print("⚠️ Не удалось настроить вебхук Telegram")
    
    # Настраиваем вебхук CryptoBot
    print("💳 Настройка вебхука CryptoBot...")
    if setup_cryptobot_webhook():
        print("✅ Вебхук CryptoBot успешно настроен")
    else:
        print("⚠️ Не удалось настроить вебхук CryptoBot. Платежи не будут приходить!")
    
    print("\n" + "=" * 50)
    print("💡 ИНСТРУКЦИЯ ДЛЯ СТАВОК ЧЕРЕЗ ВЕБХУКИ:")
    print("=" * 50)
    print("1. Нажмите кнопку '💳 Сделать ставку'")
    print(f"2. Введите сумму (минимум {MIN_BET} USDT)")
    print("3. В комментарии укажите: 'тип_ставки @ваш_username'")
    print("4. Пример: 'куб_чет @ваш_username'")
    print("5. Оплатите счёт")
    print("6. CryptoBot отправит вебхук → бот создаст ставку!")
    print("=" * 50)
    
    # Запускаем Flask сервер
    run_flask()

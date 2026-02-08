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
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo')
bot = telebot.TeleBot(BOT_TOKEN)

# Конфигурация CryptoBot API
CRYPTOBOT_TOKEN = os.environ.get('CRYPTOBOT_TOKEN', "477733:AAzooy5vcnCpJuGgTZc1Rdfbu71bqmrRMgr")
CRYPTO_API_URL = "https://pay.crypt.bot/api"
ADMIN_CHAT_ID = 8118184388

# URL сервера (для Render.com)
SERVER_URL = os.environ.get('SERVER_URL', 'https://stars-prok.onrender.com')

# Ссылка на многоразовый счет (создан вручную через @CryptoBot)
MULTI_USE_INVOICE_LINK = "https://t.me/send?start=IVNg7XnKzxBs"  # ЗАМЕНИ НА СВОЮ!

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

def load_processed_payments():
    """Загружает уже обработанные платежи из файла"""
    global processed_payments
    try:
        with open('processed_payments.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            processed_payments = set(data)
        print(f"✅ Загружено {len(processed_payments)} обработанных платежей")
    except:
        print("ℹ️ Файл processed_payments.json не найден, создадим новый")

def save_processed_payment(payment_id):
    """Сохраняет ID обработанного платежа"""
    processed_payments.add(payment_id)
    try:
        with open('processed_payments.json', 'w', encoding='utf-8') as f:
            json.dump(list(processed_payments), f, indent=4)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения processed_payments: {e}")

def parse_payment_comment(comment):
    """Парсит комментарий к платежу - ТОЛЬКО ТИП СТАВКИ"""
    if not comment:
        return None, None, None
    
    comment = comment.strip().lower()
    comment = re.sub(r'@\w+', '', comment).strip()
    
    parts = re.split(r'\s+', comment)
    
    for part in parts:
        if part in BET_TYPES:
            return None, part, None
        
        if '-' in part:
            variant = part.replace('-', '_')
            if variant in BET_TYPES:
                return None, variant, None
        
        if '_' in part:
            variant = part.replace('_', '-')
            if variant in BET_TYPES:
                return None, variant, None
    
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
    
    username_match = re.search(r'@(\w+)', comment)
    if username_match:
        return username_match.group(1).lower()
    
    return None

def process_invoice_payment(invoice):
    """Обрабатывает оплаченный инвойс"""
    try:
        payment_id = str(invoice.get('invoice_id'))
        
        if payment_id in processed_payments:
            return
        
        # Получаем данные платежа
        amount = float(invoice.get('amount', 0))
        asset = invoice.get('asset', 'USDT')
        comment = invoice.get('comment', '').strip()
        paid_at = invoice.get('paid_at')
        
        print(f"\n🔍 Новый платёж {payment_id}:")
        print(f"   Сумма: {amount} {asset}")
        print(f"   Комментарий: '{comment}'")
        print(f"   Время: {paid_at}")
        
        # Проверяем минимальную сумму
        if amount < MIN_BET:
            print(f"⚠️ Игнорируем малый платёж: {amount} USDT (мин: {MIN_BET})")
            save_processed_payment(payment_id)
            return
        
        # Извлекаем username из комментария
        username = extract_username_from_comment(comment)
        if not username:
            print(f"⚠️ Не найден username в комментарии: '{comment}'")
            save_processed_payment(payment_id)
            return
        
        # Парсим тип ставки
        _, bet_type, _ = parse_payment_comment(comment)
        
        if not bet_type:
            print(f"⚠️ Не удалось определить тип ставки из комментария: '{comment}'")
            
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
            
            save_processed_payment(payment_id)
            return
        
        # Проверяем тип ставки
        if bet_type not in BET_TYPES:
            print(f"⚠️ Неизвестный тип ставки: '{bet_type}'")
            save_processed_payment(payment_id)
            return
        
        bet_config = BET_TYPES[bet_type]
        
        # Ищем user_id по username
        user_id = None
        if username in username_to_id:
            user_id = username_to_id[username]
        else:
            print(f"⚠️ Username '@{username}' не найден в базе")
            save_processed_payment(payment_id)
            return
        
        # Получаем информацию о пользователе
        nickname = f"Игрок_{user_id}"
        try:
            user_info = bot.get_chat(user_id)
            nickname = user_info.first_name or nickname
            if user_info.last_name:
                nickname += f" {user_info.last_name}"
            
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
        
        save_processed_payment(payment_id)
        
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
                    'source': 'api_check'
                }
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
        except:
            pass
        
    except Exception as e:
        print(f"❌ Ошибка обработки платежа: {e}")
        import traceback
        traceback.print_exc()

def check_new_payments():
    """
    Проверяет новые платежи через CryptoBot API
    Вызывается периодически в фоновом потоке
    """
    try:
        headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
        
        # Получаем последние оплаченные инвойсы
        response = requests.get(
            f'{CRYPTO_API_URL}/getInvoices',
            headers=headers,
            params={
                'asset': 'USDT',
                'status': 'paid',  # Только оплаченные
                'count': 100  # Последние 100
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('ok'):
                invoices = data['result'].get('items', [])
                
                new_payments = 0
                for invoice in invoices:
                    invoice_id = str(invoice.get('invoice_id'))
                    
                    # Пропускаем уже обработанные
                    if invoice_id in processed_payments:
                        continue
                    
                    # Обрабатываем новый платеж
                    process_invoice_payment(invoice)
                    new_payments += 1
                
                if new_payments > 0:
                    print(f"✅ Обработано новых платежей: {new_payments}")
            else:
                print(f"⚠️ Ошибка CryptoBot API: {data.get('error')}")
        else:
            print(f"❌ HTTP ошибка при проверке платежей: {response.status_code}")
    
    except Exception as e:
        print(f"❌ Ошибка проверки платежей: {e}")

def payment_checker_loop():
    """
    Бесконечный цикл проверки платежей
    Запускается в отдельном потоке
    """
    print("🔄 Запущен мониторинг платежей (каждые 15 сек)")
    
    while True:
        try:
            check_new_payments()
            time.sleep(15)  # Проверяем каждые 15 секунд
        except Exception as e:
            print(f"❌ Ошибка в цикле проверки платежей: {e}")
            time.sleep(30)  # При ошибке ждем дольше

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
        print(f"❌ Ошибка обработки Telegram webhook: {e}")
        return 'Error', 500

@app.route('/check_payments', methods=['POST'])
def manual_check():
    """Ручная проверка платежей (для тестирования)"""
    try:
        check_new_payments()
        return jsonify({
            "status": "ok",
            "processed_total": len(processed_payments)
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Загружаем сохраненные данные при запуске
load_user_mappings()
load_processed_payments()

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
    
    instruction_text = f"""
<b>💳 Как сделать ставку через многоразовый счёт:</b>

1. Нажмите кнопку "💳 Сделать ставку" ниже
2. В открывшемся окне CryptoBot:
   • Введите сумму (минимум {MIN_BET} USDT)
   • В комментарии укажите:
     <code>тип_ставки @ваш_username</code>

3. Оплатите счёт
4. Бот проверит платёж через 15-30 секунд!

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

@bot.message_handler(func=lambda message: message.text == "🤝 Партнеры")
def show_partners(message):
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
        else:
            try:
                user_id = int(username)
                game.add_balance(user_id, amount)
                bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю ID: {user_id}")
            except ValueError:
                bot.reply_to(message, f"❌ Пользователь @{username} не найден.")

    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['check'])
def admin_check_payments(message):
    """Админ команда для ручной проверки платежей"""
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    
    bot.reply_to(message, "🔄 Проверяю платежи...")
    check_new_payments()
    bot.reply_to(message, f"✅ Проверка завершена!\nОбработано всего: {len(processed_payments)} платежей")

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

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    if referral_system.process_withdraw(message):
        return

    if game.process_bet_amount(message):
        return

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
        print(f"❌ Ошибка установки Telegram webhook: {e}")
        return False

def run_flask():
    """Запускает Flask сервер"""
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Запуск Flask сервера на порту {port}")
    print(f"🌐 URL: {SERVER_URL}")
    serve(app, host='0.0.0.0', port=port)

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 БОТ ЗАПУЩЕН")
    print("=" * 60)
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print(f"💰 Минимальная ставка: {MIN_BET} USDT")
    print(f"🌐 Server URL: {SERVER_URL}")
    print(f"🔗 Многоразовый счет: {MULTI_USE_INVOICE_LINK}")
    
    # Загружаем данные
    load_user_mappings()
    load_processed_payments()
    
    # Настраиваем Telegram webhook
    print("\n📱 Настройка Telegram webhook...")
    if setup_telegram_webhook():
        print("✅ Telegram webhook успешно настроен!")
    else:
        print("⚠️ Не удалось настроить Telegram webhook")
    
    # Проверяем CryptoBot API
    print("\n💳 Проверка CryptoBot API...")
    try:
        headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
        response = requests.get(f'{CRYPTO_API_URL}/getMe', headers=headers, timeout=5)
        if response.status_code == 200 and response.json().get('ok'):
            app_info = response.json()['result']
            print(f"✅ CryptoBot API подключен: {app_info.get('name', 'N/A')}")
        else:
            print("⚠️ Проблема с CryptoBot API токеном!")
    except Exception as e:
        print(f"❌ Не удалось проверить CryptoBot API: {e}")
    
    print("\n" + "=" * 60)
    print("💡 ИНСТРУКЦИЯ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ:")
    print("=" * 60)
    print("1. Нажать кнопку '💳 Сделать ставку'")
    print(f"2. Ввести сумму (минимум {MIN_BET} USDT)")
    print("3. В комментарии: 'тип_ставки @username'")
    print("4. Пример: 'куб_чет @myusername'")
    print("5. Оплатить счёт")
    print("6. Бот проверит платёж через 15-30 сек!")
    print("=" * 60)
    
    # Запускаем поток проверки платежей
    payment_thread = threading.Thread(target=payment_checker_loop, daemon=True)
    payment_thread.start()
    print("\n✅ Поток проверки платежей запущен!")
    
    print("\n🚀 Запуск Flask сервера...")
    # Запускаем Flask сервер (он будет работать в основном потоке)
    run_flask()

import telebot
from telebot import types
import threading
import time
import json
import os

# ========== ОТКЛЮЧЕНИЕ ВСЕХ ПРОКСИ ==========
# Удаляем все переменные окружения прокси
os.environ['NO_PROXY'] = '*'
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ[proxy_var] = ''

# Отключаем прокси для requests и telebot
import requests
from telebot import apihelper

session = requests.Session()
session.trust_env = False  # Игнорировать переменные окружения
apihelper.session = session
apihelper.proxy = None

# Инициализация бота с увеличенными таймаутами
bot = telebot.TeleBot(
    '8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo',
    skip_pending=True,
    num_threads=5
)

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
        print(f"📝 Сохранен username: @{username} -> ID: {user_id}")

def save_user_info(user_id, username, first_name):
    """Сохраняет информацию о пользователе во всех местах"""
    # 1. В реферальной системе
    referral_system.save_user_info(user_id, username, first_name)

    # 2. В словаре username_to_id
    if username:
        username_to_id[username] = user_id

    # 3. В файле для постоянного хранения
    try:
        # Загружаем существующие данные
        try:
            with open('user_mappings.json', 'r', encoding='utf-8') as f:
                user_mappings = json.load(f)
        except:
            user_mappings = {}

        # Обновляем данные
        user_mappings[str(user_id)] = {
            'username': username or '',
            'first_name': first_name or '',
            'last_seen': time.time()
        }

        # Сохраняем
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

        # Заполняем username_to_id
        for user_id_str, user_data in user_mappings.items():
            username = user_data.get('username', '')
            if username:
                username_to_id[username] = int(user_id_str)

        print(f"✅ Загружено {len(username_to_id)} маппингов пользователей")
    except:
        print("ℹ️ Файл user_mappings.json не найден, создадим новый")

# Загружаем сохраненные маппинги при запуске
load_user_mappings()

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

@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    update_username_mapping(message.from_user.id, message.from_user.username)

    # Сохраняем информацию о пользователе
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
                referrer_id = int(ref_code[3:])  # Убираем 'ref' и получаем ID

                # Регистрируем реферала с защитой
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
    update_username_mapping(message.from_user.id, message.from_user.username)

    # Сохраняем информацию о пользователе
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
    """Показывает меню реферальной системы"""
    update_username_mapping(message.from_user.id, message.from_user.username)

    # Сохраняем информацию о пользователе
    save_user_info(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    referral_system.show_menu(message)

@bot.message_handler(func=lambda message: message.text == "🎮 Играть")
def show_games(message):
    update_username_mapping(message.from_user.id, message.from_user.username)

    # Сохраняем информацию о пользователе
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
            # Пробуем найти по ID если username не найден
            try:
                user_id = int(username)
                if user_id in game.user_balances or True:  # Можно добавлять новым пользователям
                    game.add_balance(user_id, amount)
                    bot.reply_to(message, f"✅ Добавлено {amount} USDT пользователю ID: {user_id}")
                    print(f"💰 Админ добавил {amount} USDT пользователю ID: {user_id}")
                else:
                    bot.reply_to(message, f"❌ Пользователь @{username} не найден. Используйте /addid для добавления по ID")
            except ValueError:
                bot.reply_to(message, f"❌ Пользователь @{username} не найден. Используйте /addid для добавления по ID")

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

        # Пробуем найти по username
        if search.startswith('@'):
            search = search[1:]

        # Ищем в username_to_id
        if search in username_to_id:
            user_id = username_to_id[search]
            balance = game.get_balance(user_id)
            bot.reply_to(message, f"✅ Найден: @{search}\nID: {user_id}\nБаланс: {balance:.2f} USDT")
            return

        # Пробуем найти по ID
        try:
            user_id = int(search)
            balance = game.get_balance(user_id)
            # Пробуем найти username
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

    # Статистика рефералов
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
    """Обработчик кнопки пополнения - показывает сообщение 'В разработке'"""
    update_username_mapping(call.from_user.id, call.from_user.username)

    # Сохраняем информацию о пользователе
    save_user_info(
        call.from_user.id,
        call.from_user.username,
        call.from_user.first_name
    )

    bot.answer_callback_query(call.id, "📥 Пополнение в разработке", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    """Обработчик кнопки вывода - показывает сообщение 'В разработке'"""
    update_username_mapping(call.from_user.id, call.from_user.username)

    # Сохраняем информацию о пользователе
    save_user_info(
        call.from_user.id,
        call.from_user.username,
        call.from_user.first_name
    )

    bot.answer_callback_query(call.id, "📤 Вывод в разработке", show_alert=True)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    update_username_mapping(message.from_user.id, message.from_user.username)

    # Сохраняем информацию о пользователе
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

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    update_username_mapping(call.from_user.id, call.from_user.username)

    # Сохраняем информацию о пользователе
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

    # Игровые callback-ы
    else:
        handle_game_callbacks(call, game)

if __name__ == "__main__":
    print("🤖 Бот запущен...")
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print("💡 Команды для администратора:")
    print("/add username сумма - пополнить баланс по username")
    print("/addid user_id сумма - пополнить баланс по ID")
    print("/find username/id - найти пользователя")
    print("/stats - статистика бота")
    print("🎯 Доступные игры: 🎲 Кубик, 🏀 Баскетбол, ⚽ Футбол, 🎯 Дартс, 🎳 Боулинг")
    print("👥 Реферальная система: 5% от выигрышей рефералов, минимальный вывод 1 USDT")

    # Бесконечный цикл с перезапуском при ошибках
    restart_count = 0
    max_restarts = 10
    
    while restart_count < max_restarts:
        try:
            print(f"🔄 Запуск бота (попытка {restart_count + 1}/{max_restarts})...")
            
            # Принудительно удаляем вебхук (если был)
            try:
                bot.remove_webhook()
                time.sleep(0.5)
                print("✅ Вебхук удален (если был)")
            except:
                pass
            
            # Оптимизированный polling БЕЗ вебхуков
            bot.polling(
                none_stop=True,
                timeout=60,
                long_polling_timeout=60,
                interval=5,
                skip_pending=True,
                allowed_updates=["message", "callback_query"]
            )
            
        except KeyboardInterrupt:
            print("\n🛑 Бот остановлен пользователем")
            break
        except Exception as e:
            restart_count += 1
            print(f"❌ Ошибка в работе бота: {type(e).__name__}: {e}")
            
            if "ConnectionError" in str(type(e).__name__):
                print("⚠️ Проблема с интернет-соединением!")
                print("📡 Проверьте:")
                print("1. Доступность интернета на сервере")
                print("2. Доступность api.telegram.org")
                print("3. Блокировки в вашем регионе")
                
                # Быстрая проверка сети
                try:
                    import subprocess
                    result = subprocess.run(['ping', '-c', '2', '8.8.8.8'], 
                                          capture_output=True, text=True)
                    if result.returncode == 0:
                        print("✅ Интернет есть, проблема с Telegram")
                    else:
                        print("❌ Нет интернет-соединения")
                except:
                    pass
            
            print(f"⏳ Перезапуск через 5 секунд...")
            
            if restart_count >= max_restarts:
                print("🚨 Достигнуто максимальное количество перезапусков")
                print("⚠️ Проверьте:")
                print("1. Токен бота: правильность и статус в @BotFather")
                print("2. Сеть: ping api.telegram.org")
                print("3. Регион: Telegram может быть заблокирован")
                break
                
            time.sleep(5) вот мейн пй это было геймс пй который я скинул

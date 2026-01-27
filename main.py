import telebot
from telebot import types
import sqlite3
import json
import time
import threading
from datetime import datetime, timedelta
import random
import string
import re
import html
from flask import Flask, request, jsonify

# ========== НАСТРОЙКИ ==========
TOKEN = "8337396229:AAES7rHlibutnscXOHk7t6XB2fK2CUni5eE"
WEBHOOK_URL = "https://stars-prok.onrender.com"
WEBHOOK_PATH = f"/webhook/{TOKEN}"
PORT = 8080

# НАСТРОЙКИ АДМИНА
MIN_WITHDRAWAL = 1
REFERRAL_REWARD = 0.1
DAILY_BONUS_AMOUNT = 0.1
CURRENCY = "USDT"

# Контакт разработчика
DEVELOPER_USERNAME = "kenzooov"

# Инициализация бота
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Инициализация Flask приложения
app = Flask(__name__)

# ID администратора
ADMIN_IDS = [8118184388]

# Глобальные переменные для каналов
REQUIRED_CHANNELS = []  # Каналы с обязательной подпиской

# Хранение капчи
user_captcha = {}  # {user_id: {'correct_emoji': emoji, 'attempts': 0, 'solved': False, 'last_solved': timestamp}}
user_last_check = {}  # {user_id: timestamp} - для отслеживания 24 часов

# Список эмоджи для капчи
EMOJI_LIST = ['😀', '😂', '😍', '😎', '🤔', '😴', '🥳', '🤯', '😱', '🤮', 
              '👻', '💀', '👽', '🤖', '🎃', '👾', '🤠', '😈', '👑', '💩',
              '🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🐯',
              '🦁', '🐮', '🐷', '🐸', '🐵', '🐔', '🐧', '🐦', '🐤', '🦆',
              '🦅', '🦉', '🦇', '🐺', '🐗', '🐴', '🦄', '🐝', '🪱', '🐛',
              '🦋', '🐌', '🐞', '🐜', '🪰', '🪲', '🪳', '🦟', '🦗', '🕷️',
              '🦂', '🐢', '🐍', '🦎', '🦖', '🦕', '🐙', '🦑', '🦐', '🦞',
              '🦀', '🐡', '🐠', '🐟', '🐬', '🐳', '🐋', '🦈', '🐊', '🐅',
              '🐆', '🦓', '🦍', '🦧', '🦣', '🐘', '🦛', '🦏', '🐪', '🐫',
              '🦒', '🦘', '🦬', '🐃', '🐂', '🐄', '🐎', '🐖', '🐏', '🐑',
              '🦙', '🐐', '🦌', '🐕', '🐩', '🦮', '🐕‍🦺', '🐈', '🐈‍⬛', '🪶',
              '🐓', '🦃', '🦤', '🦚', '🦜', '🦢', '🦩', '🕊️', '🐇', '🦝',
              '🦨', '🦡', '🦫', '🦦', '🦥', '🐁', '🐀', '🐿️', '🦔', '🐾',
              '🐉', '🐲', '🌵', '🎄', '🌲', '🌳', '🌴', '🌱', '🌿', '☘️',
              '🍀', '🎍', '🪴', '🎋', '🍃', '🍂', '🍁', '🍄', '🐚', '🪨',
              '🌾', '💐', '🌷', '🌹', '🥀', '🌺', '🌸', '🌼', '🌻', '🌞',
              '🌝', '🌛', '🌜', '🌚', '🌕', '🌖', '🌗', '🌘', '🌑', '🌒',
              '🌓', '🌔', '🌙', '🌎', '🌍', '🌏', '🪐', '💫', '⭐', '🌟',
              '✨', '⚡', '☄️', '💥', '🔥', '🌪️', '🌈', '☀️', '🌤️', '⛅',
              '🌥️', '☁️', '🌦️', '🌧️', '⛈️', '🌩️', '🌨️', '❄️', '☃️', '⛄',
              '🌬️', '💨', '💧', '💦', '☔', '☂️', '🌊', '🌫️', '🍏', '🍎',
              '🍐', '🍊', '🍋', '🍌', '🍉', '🍇', '🍓', '🫐', '🍈', '🍒',
              '🍑', '🥭', '🍍', '🥥', '🥝', '🍅', '🍆', '🥑', '🥦', '🥬',
              '🥒', '🌶️', '🫑', '🌽', '🥕', '🫒', '🧄', '🧅', '🥔', '🍠',
              '🥐', '🥯', '🍞', '🥖', '🥨', '🧀', '🥚', '🍳', '🧈', '🥞',
              '🧇', '🥓', '🥩', '🍗', '🍖', '🦴', '🌭', '🍔', '🍟', '🍕',
              '🫓', '🥪', '🥙', '🧆', '🌮', '🌯', '🫔', '🥗', '🥘', '🫕',
              '🥫', '🍝', '🍜', '🍲', '🍛', '🍣', '🍱', '🥟', '🦪', '🍤',
              '🍙', '🍚', '🍘', '🍥', '🥠', '🥮', '🍢', '🍡', '🍧', '🍨',
              '🍦', '🥧', '🧁', '🍰', '🎂', '🍮', '🍭', '🍬', '🍫', '🍿',
              '🍩', '🍪', '🌰', '🥜', '🍯', '🥛', '🍼', '🫖', '☕', '🍵',
              '🧃', '🥤', '🍶', '🍺', '🍻', '🥂', '🍷', '🥃', '🍸', '🍹',
              '🧉', '🍾', '🧊', '🥄', '🍴', '🍽️', '🥣', '🥡', '🥢', '🧂']

# ========== УТИЛИТЫ ==========
def sanitize_text(text):
    """Очистка текста от проблемных символов"""
    if not text:
        return ""
    text = ''.join(char for char in text if char.isprintable())
    text = html.escape(text)
    text = ' '.join(text.split())
    return text

# ========== ФУНКЦИИ ДЛЯ КАПЧИ ==========
def generate_emoji_captcha():
    """Генерация капчи с эмоджи"""
    # Выбираем случайный эмоджи
    correct_emoji = random.choice(EMOJI_LIST)
    
    # Создаем список из 4 эмоджи (1 правильный + 3 случайных)
    emoji_options = [correct_emoji]
    
    # Добавляем 3 случайных уникальных эмоджи (не совпадающих с правильным)
    while len(emoji_options) < 4:
        random_emoji = random.choice(EMOJI_LIST)
        if random_emoji not in emoji_options:
            emoji_options.append(random_emoji)
    
    # Перемешиваем варианты
    random.shuffle(emoji_options)
    
    # Запоминаем индекс правильного ответа
    correct_index = emoji_options.index(correct_emoji)
    
    return correct_emoji, emoji_options, correct_index

def check_captcha_required(user_id):
    """Проверка, требуется ли капча пользователю"""
    # Пропускаем админов
    if user_id in ADMIN_IDS:
        return False
    
    current_time = datetime.now()
    
    # Если пользователя нет в словаре капчи
    if user_id not in user_captcha:
        return True
    
    # Если капча не решена
    if not user_captcha[user_id].get('solved', False):
        return True
    
    # Проверяем, прошло ли 24 часа с последнего решения капчи
    last_solved = user_captcha[user_id].get('last_solved')
    if last_solved:
        try:
            last_solved_time = datetime.strptime(last_solved, '%Y-%m-%d %H:%M:%S.%f') if '.' in last_solved else datetime.strptime(last_solved, '%Y-%m-%d %H:%M:%S')
            if current_time >= last_solved_time + timedelta(hours=24):
                # Сбрасываем капчу через 24 часа
                user_captcha[user_id]['solved'] = False
                return True
        except:
            # Если ошибка парсинга времени, сбрасываем капчу
            user_captcha[user_id]['solved'] = False
            return True
    
    return False

def create_captcha_keyboard(emoji_options):
    """Создание клавиатуры для капчи"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    # Создаем кнопки с эмоджи
    buttons = []
    for i, emoji in enumerate(emoji_options):
        buttons.append(types.InlineKeyboardButton(
            emoji,
            callback_data=f"captcha_{i}"
        ))
    
    # Располагаем кнопки в 2 ряда
    for i in range(0, 4, 2):
        keyboard.add(buttons[i], buttons[i + 1])
    
    return keyboard

def show_captcha(chat_id, user_id):
    """Показать капчу пользователю"""
    correct_emoji, emoji_options, correct_index = generate_emoji_captcha()
    
    user_captcha[user_id] = {
        'correct_emoji': correct_emoji,
        'correct_index': correct_index,
        'emoji_options': emoji_options,
        'attempts': 0,
        'solved': False,
        'last_solved': None
    }
    
    captcha_text = f"<b>🔒 ВЫБЕРИТЕ ЭМОДЖИ:</b>\n\n<b>{correct_emoji}</b>"
    
    bot.send_message(
        chat_id,
        captcha_text,
        parse_mode='HTML',
        reply_markup=create_captcha_keyboard(emoji_options)
    )

# ========== ФУНКЦИИ ДЛЯ USDT ==========
def format_usdt(amount):
    """Форматирование суммы USDT"""
    if amount == int(amount):
        return f"{int(amount)} {CURRENCY}"
    else:
        return f"{amount:.3f} {CURRENCY}"

def format_usdt_short(amount):
    """Краткое форматирование суммы USDT"""
    if amount >= 1:
        return f"{amount:.2f}" if amount != int(amount) else f"{int(amount)}"
    else:
        return f"{amount:.3f}"

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С КАНАЛАМИ ==========
def check_user_subscription(user_id, channel_id):
    """Проверка подписки пользователя на канал"""
    try:
        member = bot.get_chat_member(channel_id, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Ошибка при проверке подписки: {e}")
        return False

def check_all_subscriptions(user_id):
    """Проверка ВСЕХ обязательных подписок для пользователя"""
    if not REQUIRED_CHANNELS:
        return True, []  # Нет обязательных каналов

    not_subscribed = []
    all_subscribed = True

    # Проверяем только обязательные каналы
    for channel in REQUIRED_CHANNELS:
        is_subscribed = check_user_subscription(user_id, channel['channel_id'])

        if not is_subscribed:
            all_subscribed = False
            not_subscribed.append(channel)

    return all_subscribed, not_subscribed

def check_access_required(user_id):
    """Проверка всех требований для доступа"""
    # Сначала проверяем капчу
    if check_captcha_required(user_id):
        return 'captcha'
    
    # Затем проверяем подписки
    if not REQUIRED_CHANNELS:
        return 'ok'

    all_subscribed, not_subscribed = check_all_subscriptions(user_id)
    
    if all_subscribed:
        return 'ok'
    else:
        return 'subscription'

def check_subscription_required(user_id):
    """Проверка обязательных подписок"""
    if not REQUIRED_CHANNELS:
        return True, None

    all_subscribed, not_subscribed = check_all_subscriptions(user_id)

    if all_subscribed:
        return True, None
    else:
        # Формируем сообщение с каналами
        channels_text = """<b>📺 ПОДПИСКИ</b>

Для доступа к боту подпишитесь на каналы ниже:

<b>🔐 ОБЯЗАТЕЛЬНЫЕ:</b>\n"""

        # Показываем обязательные каналы
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            channels_text += f"• {safe_name} 📌\n"

        channels_text += """\n✅ <b>Подпишитесь и нажмите 'Проверить'</b>"""

        keyboard = types.InlineKeyboardMarkup()

        # Добавляем кнопки для всех обязательных каналов
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            if 'channel_username' in channel and channel['channel_username']:
                username = channel['channel_username'].replace('@', '')
                if username:
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"📺 {safe_name}",
                            url=f"https://t.me/{username}"
                        )
                    )
            elif 'channel_link' in channel and channel['channel_link']:
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"📺 {safe_name}",
                        url=channel['channel_link']
                    )
                )

        keyboard.add(
            types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription_after")
        )

        return False, (channels_text, keyboard)

# ========== ФУНКЦИИ ДЛЯ БАЗЫ ДАННЫХ ==========
def init_db():
    """Инициализация базы данных для USDT"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            referred_by INTEGER DEFAULT NULL,
            balance REAL DEFAULT 0,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_daily_bonus TIMESTAMP DEFAULT NULL,
            referral_paid INTEGER DEFAULT 0,
            FOREIGN KEY (referred_by) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            type TEXT,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            withdrawal_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            amount REAL,
            status TEXT DEFAULT 'pending',
            admin_message TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_name TEXT UNIQUE NOT NULL,
            setting_value REAL NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            channel_username TEXT,
            channel_name TEXT NOT NULL,
            channel_link TEXT NOT NULL DEFAULT '',
            channel_type TEXT NOT NULL DEFAULT 'required',
            is_active BOOLEAN DEFAULT 1,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    default_settings = [
        ('min_withdrawal', MIN_WITHDRAWAL, 'Минимальная сумма вывода в USDT'),
        ('referral_reward', REFERRAL_REWARD, 'Награда за реферала в USDT'),
        ('daily_bonus', DAILY_BONUS_AMOUNT, 'Ежедневный бонус в USDT'),
    ]

    for name, value, desc in default_settings:
        cursor.execute('''
            INSERT OR IGNORE INTO settings (setting_name, setting_value, description)
            VALUES (?, ?, ?)
        ''', (name, value, desc))

    conn.commit()
    conn.close()

def load_channels_from_db():
    """Загрузка каналов из базы данных при запуске"""
    global REQUIRED_CHANNELS
    REQUIRED_CHANNELS = []  # Очищаем список перед загрузкаой

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT channel_id, channel_username, channel_name, channel_link FROM channels WHERE is_active = 1 AND channel_type = 'required'")
    channels = cursor.fetchall()

    for ch in channels:
        channel_data = {
            'channel_id': ch[0],
            'channel_username': ch[1],
            'channel_name': sanitize_text(ch[2]),
            'channel_link': ch[3] if ch[3] else ch[1],
        }
        REQUIRED_CHANNELS.append(channel_data)

    conn.close()
    print(f"📺 Загружено {len(REQUIRED_CHANNELS)} обязательных каналов")

def get_setting(name, default=0):
    """Получение настройки"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT setting_value FROM settings WHERE setting_name = ?", (name,))
    result = cursor.fetchone()
    conn.close()
    return float(result[0]) if result else default

def update_setting(name, value):
    """Обновление настройки"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE settings SET setting_value = ?, updated_at = CURRENT_TIMESTAMP
        WHERE setting_name = ?
    ''', (value, name))
    conn.commit()
    conn.close()

# ========== ФУНКЦИИ ПОЛЬЗОВАТЕЛЯ ==========
def register_user(user_id, username, full_name, referrer_id=None):
    """Регистрация пользователя"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        safe_username = sanitize_text(username) if username else ""
        safe_full_name = sanitize_text(full_name) if full_name else f"User_{user_id}"

        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, referred_by, balance, referral_paid)
            VALUES (?, ?, ?, ?, ?, 0)
        ''', (user_id, safe_username, safe_full_name, referrer_id, 0))

        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, 0, 'registration', 'Регистрация в боте'))

        conn.commit()
        
        # Сразу проверяем реферальный бонус синхронно
        if referrer_id:
            check_and_reward_referrer(user_id)
    else:
        # Если пользователь уже есть, обновляем реферера если нужно
        if referrer_id and not user[3]:  # user[3] это referred_by
            cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
            conn.commit()
            # Сразу проверяем реферальный бонус
            check_and_reward_referrer(user_id)
    
    conn.close()

def check_and_reward_referrer(user_id):
    """Проверяет подписки пользователя и начисляет бонус рефереру если нужно"""
    print(f"🔍 Проверка реферального бонуса для пользователя {user_id}")
    
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Получаем информацию о пользователе и его реферере
    cursor.execute("SELECT referred_by, username, full_name, referral_paid FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        print(f"❌ Пользователь {user_id} не найден в базе")
        return False
    
    referrer_id = result[0]
    username = result[1]
    full_name = result[2]
    referral_paid = result[3]
    
    if not referrer_id:
        conn.close()
        print(f"❌ У пользователя {user_id} нет реферера")
        return False
    
    print(f"🔍 Реферер пользователя {user_id}: {referrer_id}")
    
    # Проверяем, был ли уже начислен бонус
    if referral_paid == 1:
        conn.close()
        print(f"⚠️ Бонус за пользователя {user_id} уже был начислен")
        return False
    
    # Проверяем подписки пользователя
    all_subscribed, not_subscribed = check_all_subscriptions(user_id)
    
    if not all_subscribed:
        conn.close()
        print(f"❌ Пользователь {user_id} не подписан на все каналы")
        return False
    
    print(f"✅ Пользователь {user_id} подписан на все каналы")
    
    # Начисляем бонус рефереру
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
    
    print(f"💰 Начисляем {referral_reward} {CURRENCY} рефереру {referrer_id} за пользователя {user_id}")
    
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (referral_reward, referrer_id))
    cursor.execute("UPDATE users SET referral_paid = 1 WHERE user_id = ?", (user_id,))
    
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (?, ?, ?, ?)
    ''', (referrer_id, referral_reward, 'referral_bonus', f'Награда за приглашение пользователя {user_id}'))
    
    conn.commit()
    
    # Получаем новый баланс реферера
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (referrer_id,))
    new_balance_result = cursor.fetchone()
    new_balance = new_balance_result[0] if new_balance_result else 0
    
    conn.close()
    
    # Уведомляем реферера
    try:
        bot.send_message(
            referrer_id,
            f"""🎉 <b>НОВЫЙ РЕФЕРАЛ!</b>

По вашей ссылке зарегистрировался новый пользователь и подписался на все каналы!

<b>Детали:</b>
👤 Пользователь: {full_name}
💰 Начислено: {format_usdt(referral_reward)}
📈 Ваш баланс: {format_usdt(new_balance)}

Продолжайте приглашать друзей для увеличения заработка! 💸🚀""",
            parse_mode='HTML'
        )
        print(f"✅ Уведомление отправлено рефереру {referrer_id}")
    except Exception as e:
        print(f"❌ Не удалось отправить уведомление рефереру {referrer_id}: {e}")
    
    # Уведомляем пользователя
    try:
        bot.send_message(
            user_id,
            f"""✅ <b>ВЫ ПОДПИСАЛИСЬ НА ВСЕ КАНАЛЫ!</b>

Ваш реферер получил вознаграждение за вашу регистрацию: {format_usdt(referral_reward)}

Спасибо за участие в программе! 🎉""",
            parse_mode='HTML'
        )
        print(f"✅ Уведомление отправлено пользователю {user_id}")
    except Exception as e:
        print(f"❌ Не удалось отправить уведомление пользователю {user_id}: {e}")
    
    return True

def check_all_users_subscriptions():
    """Проверяет подписки всех пользователей и начисляет реферальные бонусы"""
    print("🔍 Запускаю проверку всех реферальных бонусов...")
    
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Получаем всех пользователей с реферерами и неоплаченными бонусами
    cursor.execute('''
        SELECT user_id, referred_by FROM users 
        WHERE referred_by IS NOT NULL AND referral_paid = 0
    ''')
    users_with_referrers = cursor.fetchall()
    conn.close()
    
    print(f"🔍 Найдено {len(users_with_referrers)} пользователей с неоплаченными реферальными бонусами")
    
    rewarded_count = 0
    for user_id, referrer_id in users_with_referrers:
        if check_and_reward_referrer(user_id):
            rewarded_count += 1
    
    print(f"🎁 Проверено {len(users_with_referrers)} пользователей, начислено {rewarded_count} бонусов")

def get_user_info(user_id):
    """Получение информации о пользователе"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.user_id, u.username, u.full_name, u.referred_by, u.balance,
               u.registration_date, COUNT(r.user_id) as referrals_count,
               u.last_daily_bonus, u.referral_paid
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by
        WHERE u.user_id = ?
        GROUP BY u.user_id, u.username, u.full_name, u.referred_by, u.balance, u.registration_date, u.last_daily_bonus, u.referral_paid
    ''', (user_id,))

    user = cursor.fetchone()
    conn.close()

    if user:
        safe_username = sanitize_text(user[1]) if user[1] else ""
        safe_full_name = sanitize_text(user[2]) if user[2] else f"User_{user_id}"

        return {
            'user_id': user[0],
            'username': safe_username,
            'full_name': safe_full_name,
            'referred_by': user[3],
            'balance': user[4],
            'referrals_count': user[6] if user[6] else 0,
            'last_daily_bonus': user[7],
            'referral_paid': user[8]
        }
    return None

def get_user_total_withdrawn(user_id):
    """Получение общей суммы выведенных средств пользователя"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT SUM(amount) FROM withdrawals 
        WHERE user_id = ? AND status = 'approved'
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    return result[0] if result and result[0] else 0

# ========== ФУНКЦИИ ДЛЯ ЕЖЕДНЕВНОГО БОНУСА ==========
def can_claim_daily_bonus(user_id):
    """Проверка, может ли пользователь получить ежедневный бонус"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT last_daily_bonus FROM users WHERE user_id = ?
    ''', (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result or not result[0]:
        return True, None
    
    last_claim = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S')
    now = datetime.now()
    
    if now >= last_claim + timedelta(hours=24):
        return True, None
    else:
        next_claim = last_claim + timedelta(hours=24)
        remaining_time = next_claim - now
        hours = int(remaining_time.total_seconds() // 3600)
        minutes = int((remaining_time.total_seconds() % 3600) // 60)
        return False, f"{hours:02d}:{minutes:02d}"

def claim_daily_bonus(user_id):
    """Выдача ежедневного бонуса пользователю"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    daily_bonus = get_setting('daily_bonus', DAILY_BONUS_AMOUNT)
    
    cursor.execute("UPDATE users SET balance = balance + ?, last_daily_bonus = CURRENT_TIMESTAMP WHERE user_id = ?", 
                  (daily_bonus, user_id))
    
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (?, ?, ?, ?)
    ''', (user_id, daily_bonus, 'daily_bonus', 'Ежедневный бонус'))
    
    conn.commit()
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()[0]
    
    conn.close()
    
    return daily_bonus, new_balance

# ========== ФУНКЦИИ ВЫВОДА ==========
def create_withdrawal(user_id, username, amount):
    """Создание заявки на вывод"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    user_balance = cursor.fetchone()

    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

    if not user_balance or user_balance[0] < amount:
        conn.close()
        return False, f"Недостаточно {CURRENCY} на балансе"

    if amount < min_withdrawal:
        conn.close()
        return False, f"Мин. сумма: {format_usdt(min_withdrawal)}"

    safe_username = sanitize_text(username)
    cursor.execute('''
        INSERT INTO withdrawals (user_id, username, amount, status)
        VALUES (?, ?, ?, 'pending')
    ''', (user_id, safe_username, amount))

    withdrawal_id = cursor.lastrowid

    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))

    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (?, ?, ?, ?)
    ''', (user_id, -amount, 'withdrawal', f'Заявка на вывод {format_usdt(amount)}'))

    conn.commit()
    conn.close()

    return True, f"Заявка на вывод {format_usdt(amount)} создана"

def get_user_withdrawals(user_id, limit=10):
    """Получение истории выводов пользователя"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT withdrawal_id, amount, status, created_at, processed_at, admin_message
        FROM withdrawals
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    ''', (user_id, limit))

    withdrawals = cursor.fetchall()
    conn.close()

    result = []
    for w in withdrawals:
        safe_admin_message = sanitize_text(w[5]) if w[5] else None
        result.append({
            'id': w[0],
            'amount': w[1],
            'status': w[2],
            'created_at': w[3],
            'processed_at': w[4],
            'admin_message': safe_admin_message
        })

    return result

# ========== РЕФЕРАЛЬНАЯ СИСТЕМА ==========
def generate_referral_link(user_id):
    """Генерация реферальной ссылки"""
    try:
        bot_username = bot.get_me().username
        return f"https://t.me/{bot_username}?start=ref_{user_id}"
    except:
        return f"https://t.me/ваш_бот?start=ref_{user_id}"

def get_top_referrers(limit=10):
    """Получение топ пользователей ПО КОЛИЧЕСТВУ РЕФЕРАЛОВ"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.user_id, u.username, u.full_name, u.balance, 
               COUNT(r.user_id) as referrals_count
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by
        GROUP BY u.user_id, u.username, u.full_name, u.balance
        HAVING COUNT(r.user_id) > 0
        ORDER BY referrals_count DESC, u.balance DESC
        LIMIT ?
    ''', (limit,))

    top_users = cursor.fetchall()
    conn.close()

    return top_users

def get_bot_stats():
    """Получение статистики бота"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(balance) FROM users")
    total_balance = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'approved'")
    withdrawn_total = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'approved'")
    approved_withdrawals = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
    pending_withdrawals = cursor.fetchone()[0]

    conn.close()

    return {
        'total_users': total_users,
        'total_balance': total_balance,
        'withdrawn_total': withdrawn_total,
        'approved_withdrawals': approved_withdrawals,
        'pending_withdrawals': pending_withdrawals
    }

# ========== КЛАВИАТУРЫ ==========
def create_main_menu():
    """Главное меню - 5 кнопок"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "👤Профиль",
        "👨‍💻Информация о проекте",
        "💸Заработать",
        "🎁Ежедневный бонус",
        "🆘Тех. поддержка"
    ]
    keyboard.add(*buttons)
    return keyboard

def create_referral_keyboard(user_id):
    """Упрощенная клавиатура для реферальной ссылки"""
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    referral_link = generate_referral_link(user_id)
    share_text = f"Привет! Присоединяйся к крутому боту! За каждого друга дают {format_usdt(get_setting('referral_reward', REFERRAL_REWARD))}! 👇"

    import urllib.parse
    encoded_text = urllib.parse.quote(share_text)

    keyboard.add(
        types.InlineKeyboardButton(
            "📱 Поделиться",
            url=f"https://t.me/share/url?url={referral_link}&text={encoded_text}"
        )
    )

    return keyboard

def create_withdrawal_keyboard():
    """Клавиатура для вывода средств"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    standard_amounts = [1, 2, 5, 10, 20, 50]

    buttons = []
    for amount in standard_amounts:
        buttons.append(types.InlineKeyboardButton(
            f"{format_usdt_short(amount)} {CURRENCY}",
            callback_data=f"withdraw_{amount}"
        ))
    
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.add(buttons[i], buttons[i + 1])
        else:
            keyboard.add(buttons[i])

    keyboard.add(types.InlineKeyboardButton(
        "💎 Другая сумма",
        callback_data="withdraw_custom"
    ))

    return keyboard

# ========== ОСНОВНЫЕ КОМАНДЫ С КАПЧЕЙ ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    
    # Проверяем требования для доступа
    access_status = check_access_required(user_id)
    
    if access_status == 'captcha':
        # Показываем капчу
        show_captcha(message.chat.id, user_id)
        return
    
    elif access_status == 'subscription':
        # Показываем каналы для подписки
        is_subscribed, subscription_data = check_subscription_required(user_id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return
    
    # Если дошли сюда, значит доступ разрешен
    username = sanitize_text(message.from_user.username) if message.from_user.username else ""
    full_name = sanitize_text(message.from_user.full_name) if message.from_user.full_name else f"User_{user_id}"
    
    referrer_id = None
    if len(message.text.split()) > 1:
        start_param = message.text.split()[1]
        
        if start_param.startswith('ref_'):
            try:
                referrer_id = int(start_param.split('_')[1])
                if referrer_id == user_id:
                    referrer_id = None
                else:
                    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
                    cursor = conn.cursor()
                    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
                    referrer_exists = cursor.fetchone()
                    conn.close()

                    if not referrer_exists:
                        referrer_id = None
            except ValueError:
                referrer_id = None

    # Регистрируем пользователя
    register_user(user_id, username, full_name, referrer_id)

    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

    welcome_text = f"""✨ <b>ДОБРО ПОЖАЛОВАТЬ</b>

✨ <b>Добро пожаловать, {full_name}!</b>

За каждого приглашенного друга: {format_usdt(referral_reward)}

Средства зачисляются автоматически после подписки на все каналы.

Приглашай друзей и зарабатывай!

<b>👇 НАВИГАЦИЯ:</b>
Используйте кнопки ниже:"""

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.message_handler(commands=['checkmyref'])
def check_my_ref_command(message):
    """Проверить мои реферальные бонусы"""
    user_id = message.from_user.id
    
    # Проверяем требования для доступа
    access_status = check_access_required(user_id)
    
    if access_status == 'captcha':
        show_captcha(message.chat.id, user_id)
        return
    elif access_status == 'subscription':
        is_subscribed, subscription_data = check_subscription_required(user_id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return
    
    # Запускаем проверку реферального бонуса
    result = check_and_reward_referrer(user_id)
    
    if result:
        bot.send_message(
            message.chat.id,
            """✅ <b>ПРОВЕРКА ЗАВЕРШЕНА</b>

✅ <b>Реферальный бонус начислен вашему рефереру!</b>

Если вы подписались на все каналы, ваш реферер получил вознаграждение.""",
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            """ℹ️ <b>ПРОВЕРКА ЗАВЕРШЕНА</b>

ℹ️ <b>Реферальный бонус:</b>

Возможные причины:
1. Реферальный бонус уже был начислен ранее
2. Вы не подписаны на все обязательные каналы
3. У вас нет реферера

Подпишитесь на все каналы и попробуйте снова.""",
            parse_mode='HTML'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('captcha_'))
def handle_captcha_callback(call):
    """Обработчик капчи"""
    user_id = call.from_user.id
    
    if user_id not in user_captcha:
        bot.answer_callback_query(call.id, "❌ Капча устарела, начните заново")
        return
    
    selected_index = int(call.data.replace('captcha_', ''))
    captcha_data = user_captcha[user_id]
    
    if selected_index == captcha_data['correct_index']:
        # Правильный ответ
        user_captcha[user_id]['solved'] = True
        user_captcha[user_id]['last_solved'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        
        try:
            bot.edit_message_text(
                "✅ <b>Капча пройдена!</b>",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        except:
            pass
        
        # Проверяем подписки
        if REQUIRED_CHANNELS:
            all_subscribed, not_subscribed = check_all_subscriptions(user_id)
            if not all_subscribed:
                # Показываем каналы для подписки
                is_subscribed, subscription_data = check_subscription_required(user_id)
                if not is_subscribed:
                    channels_text, keyboard = subscription_data
                    bot.send_message(
                        call.message.chat.id,
                        channels_text,
                        parse_mode='HTML',
                        reply_markup=keyboard
                    )
                    return
        
        # Регистрируем пользователя если еще не зарегистрирован
        username = sanitize_text(call.from_user.username) if call.from_user.username else ""
        full_name = sanitize_text(call.from_user.full_name) if call.from_user.full_name else f"User_{user_id}"
        
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            # Регистрируем пользователя
            cursor.execute('''
                INSERT INTO users (user_id, username, full_name, balance, referral_paid)
                VALUES (?, ?, ?, ?, 0)
            ''', (user_id, username, full_name, 0))
            
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 0, 'registration', 'Регистрация через капчу'))
            
            conn.commit()
        else:
            # Проверяем реферальный бонус для существующего пользователя
            check_and_reward_referrer(user_id)
        
        conn.close()
        
        # Показываем главное меню
        referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
        welcome_text = f"""✨ <b>ДОБРО ПОЖАЛОВАТЬ</b>

✨ <b>Добро пожаловать, {full_name}!</b>

За каждого приглашенного друга: {format_usdt(referral_reward)}

Средства зачисляются автоматически после подписки на все каналы.

Приглашай друзей и зарабатывай!

<b>👇 НАВИГАЦИЯ:</b>
Используйте кнопки ниже:"""

        bot.send_message(
            call.message.chat.id,
            welcome_text,
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )
    else:
        # Неправильный ответ
        captcha_data['attempts'] += 1
        
        if captcha_data['attempts'] >= 3:
            # Слишком много попыток - новая капча
            bot.answer_callback_query(call.id, "❌ Неправильно! Новая капча")
            show_captcha(call.message.chat.id, user_id)
        else:
            bot.answer_callback_query(call.id, "❌ Неправильно, попробуйте еще раз")

# ========== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ ==========
@bot.message_handler(func=lambda message: message.text in ["👤Профиль", "👨‍💻Информация о проекте", "💸Заработать", "🎁Ежедневный бонус", "🆘Тех. поддержка"])
def handle_main_menu(message):
    user_id = message.from_user.id
    
    # Проверяем требования для доступа
    access_status = check_access_required(user_id)
    
    if access_status == 'captcha':
        # Показываем капчу
        show_captcha(message.chat.id, user_id)
        return
    
    elif access_status == 'subscription':
        # Показываем каналы для подписки
        is_subscribed, subscription_data = check_subscription_required(user_id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return
    
    # Если доступ разрешен, обрабатываем команду
    if message.text == "👤Профиль":
        profile_command(message)
    elif message.text == "👨‍💻Информация о проекте":
        project_info_command(message)
    elif message.text == "💸Заработать":
        invite_command(message)
    elif message.text == "🎁Ежедневный бонус":
        daily_bonus_command(message)
    elif message.text == "🆘Тех. поддержка":
        support_command(message)

def profile_command(message):
    user_id = message.from_user.id
    
    user_info = get_user_info(user_id)
    
    if user_info:
        total_withdrawn = get_user_total_withdrawn(user_id)
        ref_count = user_info['referrals_count']
        
        profile_text = f"""<b>👤Ваш профиль:</b>

🆔Ваш ID: <code>{user_info['user_id']}</code>  
💰Ваш баланс: {format_usdt(user_info['balance'])}

<blockquote>Выведено: {format_usdt(total_withdrawn)}</blockquote>

<b>👥Число приглашённых рефералов: {ref_count}</b>"""

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton(
                "✨Подать заявку на вывод",
                callback_data="go_to_withdraw"
            )
        )

        bot.send_message(
            message.chat.id,
            profile_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Пользователь не найден. Нажмите /start",
            parse_mode='HTML'
        )

def project_info_command(message):
    """Информация о проекте как на скрине с кнопками"""
    user_id = message.from_user.id
    
    stats = get_bot_stats()
    
    info_text = f"""<b>👨‍💻Информация о проекте:</b>

💸Выплачено всего: {format_usdt(stats['withdrawn_total'])}
👥Пользователей: {stats['total_users']} шт."""

    # Создаем клавиатуру с кнопками "Топ" и "Разработчик"
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🏆 Топ", callback_data="show_top"),
        types.InlineKeyboardButton("👨‍💻 Разработчик", url=f"https://t.me/{DEVELOPER_USERNAME}")
    )

    bot.send_message(
        message.chat.id,
        info_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data == "show_top")
def show_top_callback(call):
    """Показать топ рефереров"""
    top_users = get_top_referrers(10)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

    if top_users:
        top_text = f"""<b>🏆 Топ 10 рефереров:</b>

Награда за реферала: {format_usdt(referral_reward)}\n\n"""

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

        for i, user in enumerate(top_users):
            if i < len(medals):
                medal = medals[i]
            else:
                medal = f"{i+1}."

            safe_username = sanitize_text(user[1]) if user[1] else ""
            safe_full_name = sanitize_text(user[2]) if user[2] else f"User_{user[0]}"

            username = f"@{safe_username}" if safe_username else safe_full_name
            referrals = user[4] if user[4] else 0
            earned = referrals * referral_reward

            top_text += f'{medal} <b>{username}</b>\n'
            top_text += f'Рефералов: {referrals} | Заработано: {format_usdt(earned)}\n\n'

        top_text += '<b>🎯 Приглашайте друзей и попадите в топ!</b>'
    else:
        top_text = f"""<b>🏆 Топ рефереров</b>

Пока никто не пригласил друзей. Будьте первым!

Награда за реферала: {format_usdt(referral_reward)}"""

    try:
        bot.edit_message_text(
            top_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML'
        )
    except:
        bot.send_message(
            call.message.chat.id,
            top_text,
            parse_mode='HTML'
        )

def invite_command(message):
    user_id = message.from_user.id
    
    user_info = get_user_info(user_id)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

    if user_info:
        referral_link = generate_referral_link(user_id)
        referrals_count = user_info['referrals_count']
        earned_from_refs = referrals_count * referral_reward

        invite_text = f"""💹 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>

<b>Награда за каждого друга:</b> {format_usdt(referral_reward)}

<b>🔗 Ссылка для приглашения:</b>
<code>{referral_link}</code>

<b>📊 Ваша статистика:</b>
👥 Приглашено: {referrals_count} человек
💰 Заработано: {format_usdt(earned_from_refs)}

<b>💡 Как это работает:</b>
1. Друг переходит по вашей ссылке
2. Регистрируется и подписывается на все каналы
3. <b>Автоматически</b> на ваш баланс поступает {format_usdt(referral_reward)}

Приглашайте друзей и зарабатывайте! 💸"""

        bot.send_message(
            message.chat.id,
            invite_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(user_id)
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ Пользователь не найден. Нажмите /start",
            parse_mode='HTML'
        )

def withdrawal_command(message):
    user_id = message.from_user.id
    user_info = get_user_info(user_id)
    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

    if not user_info:
        bot.send_message(message.chat.id, "❌ Ошибка: пользователь не найден")
        return

    withdrawal_text = f"""<b>Вывод {CURRENCY}</b>

<b>Баланс:</b> {format_usdt(user_info['balance'])}
<b>Мин. сумма:</b> {format_usdt(min_withdrawal)}
<b>Время:</b> до 24 часов

<b>Выберите сумму:</b>"""

    bot.send_message(
        message.chat.id,
        withdrawal_text,
        parse_mode='HTML',
        reply_markup=create_withdrawal_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data == "go_to_withdraw")
def go_to_withdraw_callback(call):
    """Переход к выводу из профиля"""
    user_id = call.from_user.id
    user_info = get_user_info(user_id)
    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка: пользователь не найден", show_alert=True)
        return

    withdrawal_text = f"""<b>Вывод {CURRENCY}</b>

<b>Баланс:</b> {format_usdt(user_info['balance'])}
<b>Мин. сумма:</b> {format_usdt(min_withdrawal)}
<b>Время:</b> до 24 часов

<b>Выберите сумму:</b>"""

    try:
        bot.edit_message_text(
            withdrawal_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=create_withdrawal_keyboard()
        )
    except:
        bot.send_message(
            call.message.chat.id,
            withdrawal_text,
            parse_mode='HTML',
            reply_markup=create_withdrawal_keyboard()
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_'))
def handle_withdrawal_callback(call):
    """Обработчик инлайн1кнопок вывода"""
    user_id = call.from_user.id
    user_info = get_user_info(user_id)
    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

    if not user_info:
        bot.answer_callback_query(call.id, "❌ Ошибка: пользователь не найден")
        return

    action = call.data

    if action == "withdraw_custom":
        msg = bot.send_message(
            call.message.chat.id,
            f"""<b>ВЫВОД {CURRENCY}</b>

<b>Введите сумму для вывода</b>

<b>Требования:</b>
Мин. сумма: {format_usdt(min_withdrawal)}
Введите сумму в {CURRENCY}:""",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_custom_withdrawal)
        bot.answer_callback_query(call.id)
        return

    if action.startswith("withdraw_"):
        try:
            amount_str = action.replace("withdraw_", "")
            amount = float(amount_str) if '.' in amount_str else int(amount_str)
        except:
            bot.answer_callback_query(call.id, "❌ Неверная сумма")
            return

    if user_info['balance'] < amount:
        bot.answer_callback_query(
            call.id,
            f"❌ Недостаточно {CURRENCY}! У вас {format_usdt(user_info['balance'])}",
            show_alert=True
        )
        return

    if amount < min_withdrawal:
        bot.answer_callback_query(
            call.id,
            f"❌ Мин. сумма {format_usdt(min_withdrawal)}",
            show_alert=True
        )
        return

    user_data = {'amount': amount, 'user_id': user_id}

    msg = bot.send_message(
        call.message.chat.id,
        f"""<b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b>

<b>ДЕТАЛИ ВЫВОДА:</b>
Сумма: {format_usdt(amount)}
Ваш баланс: {format_usdt(user_info['balance'])}
После вывода: {format_usdt(user_info['balance'] - amount)}

<b>Введите ваш @username для связи:</b>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_withdrawal_username, user_data)
    bot.answer_callback_query(call.id)

def process_custom_withdrawal(message):
    try:
        amount = float(message.text)

        min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)
        if amount < min_withdrawal:
            bot.send_message(
                message.chat.id,
                f"""❌ <b>ОШИБКА ВЫВОДА</b>

❌ <b>Мин. сумма {format_usdt(min_withdrawal)}!</b>""",
                parse_mode='HTML'
            )
            return

        user_info = get_user_info(message.from_user.id)

        if not user_info:
            bot.send_message(message.chat.id, "❌ Ошибка: пользователь не найден")
            return

        if user_info['balance'] < amount:
            bot.send_message(
                message.chat.id,
                f"""❌ <b>ОШИБКА ВЫВОДА</b>

❌ <b>Недостаточно {CURRENCY}!</b>

<b>ДЕТАЛИ:</b>
Хотите вывести: {format_usdt(amount)}
Ваш баланс: {format_usdt(user_info['balance'])}
Не хватает: {format_usdt(amount - user_info['balance'])}""",
                parse_mode='HTML'
            )
            return

        user_data = {'amount': amount, 'user_id': message.from_user.id}

        msg = bot.send_message(
            message.chat.id,
            f"""<b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b>

<b>ДЕТАЛИ ВЫВОДА:</b>
Сумма: {format_usdt(amount)}
Ваш баланс: {format_usdt(user_info['balance'])}
После вывода: {format_usdt(user_info['balance'] - amount)}

<b>Введите ваш @username для связи:</b>""",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_withdrawal_username, user_data)

    except ValueError:
        bot.send_message(
            message.chat.id,
            """❌ <b>ОШИБКА ВВОДА</b>

❌ <b>Пожалуйста, введите число!</b>""",
            parse_mode='HTML'
        )

def process_withdrawal_username(message, user_data):
    username = sanitize_text(message.text.strip())

    if username.startswith('@'):
        username = username[1:]

    if not username or username == '':
        bot.send_message(
            message.chat.id,
            """❌ <b>ОШИБКА ВВОДА</b>

❌ <b>Пожалуйста, укажите ваш @username!</b>""",
            parse_mode='HTML'
        )
        return

    amount = user_data['amount']
    user_id = user_data['user_id']

    success, message_text = create_withdrawal(user_id, username, amount)

    if success:
        user_info = get_user_info(user_id)

        bot.send_message(
            message.chat.id,
            f"""✅ <b>ЗАЯВКА СОЗДАНА</b>

✅ <b>Заявка на вывод создана!</b>

<b>ДЕТАЛИ:</b>
Сумма: <b>{format_usdt(amount)}</b>
Username: <b>@{username}</b>
Ваш баланс: <b>{format_usdt(user_info['balance'])}</b>
Статус: <b>⏳ На рассмотрении</b>

<b>ИНФОРМАЦИЯ:</b>
Время: до 24 часов
Связь: @{username}

<b>🎯 Следите за статусом!</b>""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )
    else:
        bot.send_message(
            message.chat.id,
            f"""❌ <b>ОШИБКА СОЗДАНИЯ</b>

❌ <b>Ошибка!</b>

{message_text}""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

def support_command(message):
    """🆘Техническая поддержка"""
    user_id = message.from_user.id
    
    support_text = f"""<b>Тех. поддержка</b>

<b>👨‍💻 Техническая поддержка</b>

<b>📞 Связь:</b>
Для связи с поддержкой используйте:
• @{DEVELOPER_USERNAME}
• Отправить сообщение администратору

<b>⏱️ Время ответа:</b>
Обычно в течение 24 часов

<b>⚠️ Проблемы:</b>
• Не работает бот
• Не приходят бонусы
• Проблемы с выводом
• Другие вопросы"""

    bot.send_message(
        message.chat.id,
        support_text,
        parse_mode='HTML'
    )

def daily_bonus_command(message):
    """Обработчик ежедневного бонуса"""
    user_id = message.from_user.id
    
    # Проверяем, может ли пользователь получить бонус
    can_claim, remaining_time = can_claim_daily_bonus(user_id)
    
    daily_bonus_amount = get_setting('daily_bonus', DAILY_BONUS_AMOUNT)
    
    if can_claim:
        # Выдаем бонус
        bonus_amount, new_balance = claim_daily_bonus(user_id)
        
        bonus_text = f"""<b>🎁 ЕЖЕДНЕВНЫЙ БОНУС</b>

✅ <b>Вам начислен ежедневный бонус!</b>

💰 Сумма: {format_usdt(bonus_amount)}
🏦 Новый баланс: {format_usdt(new_balance)}

<b>Возвращайтесь через 24 часа за следующим бонусом!</b> 🎉"""
        
        bot.send_message(
            message.chat.id,
            bonus_text,
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )
    else:
        # Показываем оставшееся время
        bonus_text = f"""<b>🎁 ЕЖЕДНЕВНЫЙ БОНУС</b>

⏳ <b>Вы уже получали бонус сегодня</b>

💰 Сумма бонуса: {format_usdt(daily_bonus_amount)}

<b>Следующий бонус будет доступен через:</b>
⏰ {remaining_time}

<b>Возвращайтесь позже!</b>"""
        
        bot.send_message(
            message.chat.id,
            bonus_text,
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

# ========== CALLBACK ДЛЯ ПРОВЕРКИ ПОДПИСКИ ==========
@bot.callback_query_handler(func=lambda call: call.data == "check_subscription_after")
def check_subscription_after_callback(call):
    """Проверка подписки после нажатия кнопки"""
    user_id = call.from_user.id
    all_subscribed, not_subscribed = check_all_subscriptions(user_id)

    if all_subscribed:
        try:
            bot.edit_message_text(
                """✅ <b>ВСЕ ПОДПИСКИ АКТИВНЫ</b>

✅ <b>Отлично! Вы подписаны на все каналы!</b>

Теперь вы можете пользоваться ботом.""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        except:
            pass

        # Проверяем капчу
        if check_captcha_required(user_id):
            show_captcha(call.message.chat.id, user_id)
            return

        # Регистрируем пользователя если он еще не зарегистрирован
        username = sanitize_text(call.from_user.username) if call.from_user.username else ""
        full_name = sanitize_text(call.from_user.full_name) if call.from_user.full_name else f"User_{user_id}"
        
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        
        # Если пользователь не зарегистрирован, регистрируем
        if not user:
            cursor.execute('''
                INSERT INTO users (user_id, username, full_name, balance, referral_paid)
                VALUES (?, ?, ?, ?, 0)
            ''', (user_id, username, full_name, 0))
            
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 0, 'registration', 'Регистрация через проверку подписок'))
            
            conn.commit()
        
        conn.close()
        
        # Проверяем и начисляем реферальный бонус
        check_and_reward_referrer(user_id)

        # Показываем главное меню
        referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
        welcome_text = f"""✨ <b>ДОБРО ПОЖАЛОВАТЬ</b>

✨ <b>Добро пожаловать, {full_name}!</b>

За каждого приглашенного друга: {format_usdt(referral_reward)}

Средства зачисляются автоматически после подписки на все каналы.

Приглашай друзей и зарабатывай!

<b>👇 НАВИГАЦИЯ:</b>
Используйте кнопки ниже:"""

        bot.send_message(
            call.message.chat.id,
            welcome_text,
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )
    else:
        channels_text = """❌ <b>ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ</b>

❌ <b>Вы еще не подписались на все каналы!</b>

<b>Осталось подписаться:</b>\n\n"""

        keyboard = types.InlineKeyboardMarkup()

        # Добавляем только обязательные каналы
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            channels_text += f"• {safe_name} 📌\n"

            if 'channel_username' in channel and channel['channel_username']:
                username = channel['channel_username'].replace('@', '')
                if username:
                    keyboard.add(
                        types.InlineKeyboardButton(
                            f"📺 {safe_name}",
                            url=f"https://t.me/{username}"
                        )
                    )
            elif 'channel_link' in channel and channel['channel_link']:
                keyboard.add(
                    types.InlineKeyboardButton(
                        f"📺 {safe_name}",
                        url=channel['channel_link']
                    )
                )

        channels_text += """\n✅ <b>После подписки нажмите кнопку ниже</b>"""

        keyboard.add(
            types.InlineKeyboardButton("🔄 Проверить", callback_data="check_subscription_after")
        )

        try:
            bot.edit_message_text(
                channels_text,
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML',
                reply_markup=keyboard
            )
        except:
            pass

# ========== АДМИН ПАНЕЛЬ ==========
@bot.message_handler(commands=['admin'])
def admin_command(message):
    """Команда /admin для доступа к админ панели"""
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return

    admin_text = """<b>АДМИН ПАНЕЛЬ</b>

<b>Добро пожаловать в панель управления!</b>

<b>Выберите действия:</b>
/statistics - 📊 Статистика бота
/mailing - 📢 Рассылка всем
/addbalance - 💵 Добавить баланс
/withdrawals - 💰 Управление выводами
/channels - 📺 Управление каналами
/settings - ⚙️ Настройки
/checkallrefs - 🔍 Проверить все рефералы
/back - ⬅️ Назад"""

    bot.send_message(
        message.chat.id,
        admin_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['checkallrefs'])
def check_all_refs_command(message):
    """Проверить все реферальные бонусы"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    bot.send_message(
        message.chat.id,
        "🔍 Начинаю проверку всех реферальных бонусов...",
        parse_mode='HTML'
    )
    
    check_all_users_subscriptions()
    
    bot.send_message(
        message.chat.id,
        "✅ Проверка всех реферальных бонусов завершена!",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['statistics'])
def bot_stats_command(message):
    """Статистика бота в USDT"""
    if message.from_user.id not in ADMIN_IDS:
        return

    stats = get_bot_stats()
    
    stats_text = f"""<b>СТАТИСТИКА БОТА</b>

<b>👥 ПОЛЬЗОВАТЕЛИ:</b>
Всего: <b>{stats['total_users']}</b>

<b>💰 {CURRENCY}:</b>
На балансах: <b>{format_usdt(stats['total_balance'])}</b>

<b>💸 ВЫВОДЫ:</b>
Одобрено: <b>{stats['approved_withdrawals']}</b> на {format_usdt(stats['withdrawn_total'])}
Ожидает: <b>{stats['pending_withdrawals']}</b>"""

    bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

@bot.message_handler(commands=['addbalance'])
def add_balance_command(message):
    """Добавление баланса вручную"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        f"""<b>ДОБАВЛЕНИЕ БАЛАНСА</b>

Введите ID пользователя и количество {CURRENCY} через пробел:

<b>ПРИМЕР:</b>
<code>123456789 10.5</code>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_balance_manual)

def process_add_balance_manual(message):
    """Обработка добавления баланса"""
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        parts = message.text.split()
        if len(parts) != 2:
            bot.send_message(message.chat.id, "❌ Неверный формат!")
            return

        user_id = int(parts[0])
        amount = float(parts[1])

        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Количество должно быть больше 0!")
            return

        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute("SELECT username, full_name, balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден!")
            return

        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, 'admin_add', f'Добавлено администратором {message.from_user.id}'))

        conn.commit()

        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        new_balance = cursor.fetchone()[0]

        conn.close()

        safe_name = sanitize_text(user[1])
        bot.send_message(
            message.chat.id,
            f"""✅ <b>БАЛАНС ДОБАВЛЕН</b>

<b>👤 ИНФОРМАЦИЯ:</b>
Пользователь: {safe_name}
Username: @{user[0]}
Добавлено: +{format_usdt(amount)}
Новый баланс: {format_usdt(new_balance)}""",
            parse_mode='HTML'
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат данных!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['withdrawals'])
def manage_withdrawals_command(message):
    """Управление выводами"""
    if message.from_user.id not in ADMIN_IDS:
        return

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT w.*, u.full_name, u.balance as user_balance
        FROM withdrawals w
        LEFT JOIN users u ON w.user_id = u.user_id
        WHERE w.status = 'pending'
        ORDER BY w.created_at DESC
        LIMIT 10
    ''')

    withdrawals = cursor.fetchall()
    conn.close()

    if not withdrawals:
        withdrawals_text = """<b>УПРАВЛЕНИЕ ВЫВОДАМИ</b>

<b>Нет ожидающих заявок</b>"""
        bot.send_message(
            message.chat.id,
            withdrawals_text,
            parse_mode='HTML'
        )
        return

    withdrawals_text = """<b>ОЖИДАЮЩИЕ ЗАЯВКИ</b>\n\n"""

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    for w in withdrawals:
        withdrawal_id, user_id, username, amount, status, admin_message, created_at, processed_at, full_name, user_balance = w

        safe_name = sanitize_text(full_name) if full_name else f"User_{user_id}"
        withdrawals_text += f'<b>#{withdrawal_id}</b> - {format_usdt(amount)}\n'
        withdrawals_text += f'👤 {safe_name} (ID: {user_id})\n'
        withdrawals_text += f'💰 Баланс: {format_usdt(user_balance)}\n\n'

        keyboard.add(
            types.InlineKeyboardButton(
                f"✅ #{withdrawal_id} - {format_usdt_short(amount)}",
                callback_data=f"admin_approve_{withdrawal_id}"
            ),
            types.InlineKeyboardButton(
                f"❌ #{withdrawal_id}",
                callback_data=f"admin_reject_{withdrawal_id}"
            )
        )

    bot.send_message(
        message.chat.id,
        withdrawals_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.message_handler(commands=['channels'])
def manage_channels_command(message):
    """Управление каналами"""
    if message.from_user.id not in ADMIN_IDS:
        return

    channels_text = """<b>УПРАВЛЕНИЕ КАНАЛАМИ</b>

<b>📝 КАК ДОБАВИТЬ:</b>
/addchannel - Добавить обязательный канал

<b>🗑️ КАК УДАЛИТЬ:</b>
/removechannel

<b>📋 СПИСОК:</b>
/listchannels

<b>🔍 ПРОВЕРКА:</b>
/checksubs [id_пользователя]"""

    bot.send_message(
        message.chat.id,
        channels_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['addchannel'])
def add_channel_command(message):
    """Добавление обязательного канала"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """<b>ДОБАВЛЕНИЕ КАНАЛА</b>

Отправьте ссылку на канал:
• @username
• https://t.me/username

<i>Бот должен быть администратором!</i>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_channel)

def process_add_channel(message):
    """Обработка добавления канала"""
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        channel_link = sanitize_text(message.text.strip())

        if not channel_link:
            bot.send_message(message.chat.id, "❌ Ссылка не может быть пустой")
            return

        # Извлекаем username из ссылки
        channel_username = None
        channel_name = channel_link

        # Пытаемся получить информацию о канале
        try:
            if channel_link.startswith('@'):
                username = channel_link[1:]
                chat = bot.get_chat(f"@{username}")
            elif 't.me/' in channel_link:
                if '/' in channel_link:
                    username = channel_link.split('/')[-1].replace('@', '')
                else:
                    username = channel_link.replace('https://t.me/', '').replace('@', '')
                chat = bot.get_chat(f"@{username}")
            else:
                raise Exception("Не стандартная ссылка Telegram")

            channel_id = chat.id
            channel_name = sanitize_text(chat.title) if chat.title else channel_link

            if channel_link.startswith('@'):
                channel_username = channel_link
            else:
                channel_username = f"@{username}"

            # Проверяем права бота
            try:
                bot.get_chat_member(channel_id, bot.get_me().id)
            except:
                bot.send_message(
                    message.chat.id,
                    f"""❌ <b>ОШИБКА ПРАВ</b>

❌ Бот не является администратором в канале <b>{channel_name}</b>

Добавьте бота как администратора и попробуйте снова.""",
                    parse_mode='HTML'
                )
                return

        except Exception as e:
            bot.send_message(
                message.chat.id,
                f"""❌ <b>ОШИБКА ПАРСИНГА</b>

❌ Не удалось получить информацию о канале: {str(e)}

Для обязательных каналов используйте правильные ссылки.""",
                parse_mode='HTML'
            )
            return

        # Проверяем, нет ли уже такого канала
        global REQUIRED_CHANNELS
        if any(ch.get('channel_id') == channel_id for ch in REQUIRED_CHANNELS):
            bot.send_message(message.chat.id, "❌ Этот канал уже добавлен как обязательный")
            return

        # Добавляем канал
        channel_data = {
            'channel_id': str(channel_id),
            'channel_username': channel_username,
            'channel_name': channel_name,
            'channel_link': channel_link,
        }
        REQUIRED_CHANNELS.append(channel_data)

        # Сохраняем в базу данных
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO channels (channel_id, channel_username, channel_name, channel_link, channel_type, added_by)
            VALUES (?, ?, ?, ?, 'required', ?)
        ''', (str(channel_id), channel_username, channel_name, channel_link, message.from_user.id))

        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            f"""✅ <b>КАНАЛ ДОБАВЛЕН</b>

<b>📺 ИНФОРМАЦИЯ:</b>
Название: {channel_name}
Ссылка: {channel_link}
ID: {channel_id}
Тип: обязательный (проверяется)

<i>Пользователи должны будут подписаться на этот канал.</i>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['listchannels'])
def list_channels_command(message):
    """Список каналов"""
    if message.from_user.id not in ADMIN_IDS:
        return

    if not REQUIRED_CHANNELS:
        channels_text = """<b>СПИСОК КАНАЛОВ</b>

<b>Список каналов пуст</b>

Добавьте каналы командой /addchannel"""
    else:
        channels_text = """<b>СПИСОК КАНАЛОВ</b>\n\n"""

        for i, ch in enumerate(REQUIRED_CHANNELS, 1):
            safe_name = sanitize_text(ch['channel_name'])
            channels_text += f'{i}. <b>{safe_name}</b>\n'
            channels_text += f'   🔗 {ch["channel_link"]}'
            if ch.get('channel_id'):
                channels_text += f' | 🆔 {ch["channel_id"]}'
            channels_text += '\n\n'

        channels_text += f"<b>ИТОГО:</b> {len(REQUIRED_CHANNELS)} обязательных каналов"

    bot.send_message(
        message.chat.id,
        channels_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['removechannel'])
def remove_channel_command(message):
    """Удаление канала"""
    if message.from_user.id not in ADMIN_IDS:
        return

    if not REQUIRED_CHANNELS:
        bot.send_message(message.chat.id, "❌ Нет каналов для удаления")
        return

    # Показываем список каналов с кнопками
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for ch in REQUIRED_CHANNELS:
        safe_name = sanitize_text(ch['channel_name'])
        keyboard.add(
            types.InlineKeyboardButton(
                f"📺 {safe_name}",
                callback_data=f"remove_channel_{ch['channel_id']}"
            )
        )

    bot.send_message(
        message.chat.id,
        """<b>УДАЛЕНИЕ КАНАЛА</b>

Выберите канал для удаления из списка ниже:""",
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_channel_'))
def remove_channel_callback(call):
    """Обработка удаления канала"""
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return

    try:
        channel_id = call.data.replace('remove_channel_', '')

        # Удаляем из списка
        global REQUIRED_CHANNELS
        channel_to_remove = next((ch for ch in REQUIRED_CHANNELS if ch['channel_id'] == channel_id), None)
        REQUIRED_CHANNELS = [ch for ch in REQUIRED_CHANNELS if ch['channel_id'] != channel_id]

        if channel_to_remove:
            # Удаляем из базы данных
            conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
            conn.commit()
            conn.close()

            safe_name = sanitize_text(channel_to_remove['channel_name'])
            bot.edit_message_text(
                f"""✅ <b>КАНАЛ УДАЛЕН</b>

<b>📺 ИНФОРМАЦИЯ:</b>
Название: {safe_name}
Ссылка: {channel_to_remove['channel_link']}
Тип: обязательный

<i>Канал удален из списка обязательных.</i>""",
                call.message.chat.id,
                call.message.message_id,
                parse_mode='HTML'
            )
        else:
            bot.answer_callback_query(call.id, "Не найдено")

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

@bot.message_handler(commands=['checksubs'])
def check_subs_command(message):
    """Проверка подписок пользователя"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        msg = bot.send_message(
            message.chat.id,
            """<b>ПРОВЕРКА ПОДПИСОК</b>

Отправьте ID пользователя для проверки:""",
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_check_subs)
        return

    try:
        user_id = int(parts[1].strip())
        process_check_subs_id(message.chat.id, user_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат ID")

def process_check_subs(message):
    """Обработка проверки подписок из сообщения"""
    if message.from_user.id not in ADMIN_IDS:
        return

    try:
        user_id = int(message.text.strip())
        process_check_subs_id(message.chat.id, user_id)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат ID")

def process_check_subs_id(chat_id, user_id):
    """Проверка подписок по ID"""
    all_subscribed, not_subscribed = check_all_subscriptions(user_id)

    if all_subscribed:
        bot.send_message(
            chat_id,
            f"""✅ <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

✅ <b>Пользователь {user_id} подписан на все каналы!</b>""",
            parse_mode='HTML'
        )
    else:
        channels_text = "\n".join([f"• {sanitize_text(ch['channel_name'])} ({ch['channel_link']})" for ch in not_subscribed])

        bot.send_message(
            chat_id,
            f"""❌ <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

❌ <b>Пользователь {user_id} не подписан:</b>

{channels_text}""",
            parse_mode='HTML'
        )

@bot.message_handler(commands=['settings'])
def system_settings_command(message):
    """Управление настройками системы"""
    if message.from_user.id not in ADMIN_IDS:
        return

    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
    daily_bonus = get_setting('daily_bonus', DAILY_BONUS_AMOUNT)

    settings_text = f"""<b>НАСТРОЙКИ СИСТЕМЫ</b>

<b>💰 ВЫВОД:</b>
Мин. вывод: <b>{format_usdt(min_withdrawal)}</b>

<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
Награда: <b>{format_usdt(referral_reward)}</b>

<b>🎁 ЕЖЕДНЕВНЫЙ БОНУС:</b>
Сумма: <b>{format_usdt(daily_bonus)}</b>

<b>Изменить настройки:</b>
/set_min_withdrawal [сумма] - Изменить мин. вывод
/set_referral_reward [сумма] - Изменить награду
/set_daily_bonus [сумма] - Изменить ежедневный бонус"""

    bot.send_message(
        message.chat.id,
        settings_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['set_min_withdrawal'])
def set_min_withdrawal_command(message):
    """Изменение минимального вывода"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Использование: /set_min_withdrawal [сумма]")
        return

    try:
        new_value = float(parts[1])
        if new_value < 0:
            bot.send_message(message.chat.id, "❌ Значение не может быть отрицательным!")
            return

        update_setting('min_withdrawal', new_value)

        bot.send_message(
            message.chat.id,
            f"""✅ <b>НАСТРОЙКА ОБНОВЛЕНА</b>

Минимальный вывод изменен на: <b>{format_usdt(new_value)}</b>""",
            parse_mode='HTML'
        )
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное число!")

@bot.message_handler(commands=['set_referral_reward'])
def set_referral_reward_command(message):
    """Изменение награды за реферала"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Использование: /set_referral_reward [сумма]")
        return

    try:
        new_value = float(parts[1])
        if new_value < 0:
            bot.send_message(message.chat.id, "❌ Значение не может быть отрицательным!")
            return

        update_setting('referral_reward', new_value)

        bot.send_message(
            message.chat.id,
            f"""✅ <b>НАСТРОЙКА ОБНОВЛЕНА</b>

Награда за реферала изменена на: <b>{format_usdt(new_value)}</b>""",
            parse_mode='HTML'
        )
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное число!")

@bot.message_handler(commands=['set_daily_bonus'])
def set_daily_bonus_command(message):
    """Изменение ежедневного бонуса"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Использование: /set_daily_bonus [сумма]")
        return

    try:
        new_value = float(parts[1])
        if new_value < 0:
            bot.send_message(message.chat.id, "❌ Значение не может быть отрицательным!")
            return

        update_setting('daily_bonus', new_value)

        bot.send_message(
            message.chat.id,
            f"""✅ <b>НАСТРОЙКА ОБНОВЛЕНА</b>

Ежедневный бонус изменен на: <b>{format_usdt(new_value)}</b>""",
            parse_mode='HTML'
        )
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное число!")

@bot.message_handler(commands=['mailing'])
def mailing_all_command(message):
    """Рассылка всем пользователям"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """<b>РАССЫЛКА ВСЕМ</b>

Отправьте сообщение для рассылки:

<i>Поддерживается HTML разметка</i>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_mailing_all)

def process_mailing_all(message):
    """Обработка рассылки всем"""
    if message.from_user.id not in ADMIN_IDS:
        return

    mailing_text = sanitize_text(message.text)

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"""<b>НАЧАЛО РАССЫЛКИ</b>

⏳ Начинаю рассылку для {len(users)} пользователей...""",
        parse_mode='HTML'
    )

    success_count = 0
    fail_count = 0

    for user in users:
        try:
            bot.send_message(user[0], mailing_text, parse_mode='HTML')
            success_count += 1
            time.sleep(0.05)
        except:
            fail_count += 1

    bot.send_message(
        message.chat.id,
        f"""✅ <b>РАССЫЛКА ЗАВЕРШЕНА</b>

<b>📊 РЕЗУЛЬТАТЫ:</b>
Успешно: {success_count}
Не удалось: {fail_count}""",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['back'])
def back_to_main_menu(message):
    """Возврат в главное меню из админ панели"""
    bot.send_message(
        message.chat.id,
        """<b>ГЛАВНОЕ МЕНЮ</b>

<b>Вы вернулись в главное меню</b>""",
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_approve_'))
def admin_approve_callback(call):
    """Одобрение заявки админом"""
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return

    try:
        withdrawal_id = int(call.data.replace('admin_approve_', ''))

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        msg = bot.send_message(
            call.message.chat.id,
            f"""<b>ОДОБРЕНИЕ #{withdrawal_id}</b>

Введите сообщение для пользователя (или 'нет' если не нужно):""",
            parse_mode='HTML'
        )

        bot.register_next_step_handler(msg, process_approve_withdrawal, withdrawal_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def process_approve_withdrawal(message, withdrawal_id):
    """Обработка одобрения заявки"""
    if message.from_user.id not in ADMIN_IDS:
        return

    admin_message = sanitize_text(message.text) if message.text.lower() != 'нет' else None

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, amount, username FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()

        if withdrawal:
            user_id, amount, username = withdrawal

            cursor.execute('''
                UPDATE withdrawals
                SET status = 'approved', admin_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE withdrawal_id = ?
            ''', (admin_message, withdrawal_id))

            try:
                bot.send_message(
                    user_id,
                    f"""✅ <b>ЗАЯВКА ОДОБРЕНА</b>

✅ <b>Ваша заявка на вывод одобрена!</b>

<b>📋 ДЕТАЛИ:</b>
Сумма: {format_usdt(amount)}
Номер: #{withdrawal_id}
Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{f'<b>💬 СООБЩЕНИЕ:</b>\n{admin_message}' if admin_message else ''}""",
                    parse_mode='HTML'
                )
            except:
                pass

            conn.commit()

            bot.send_message(
                message.chat.id,
                f"""✅ <b>ЗАЯВКА ОДОБРЕНА</b>

✅ <b>Заявка #{withdrawal_id} одобрена!</b>""",
                parse_mode='HTML'
            )
        else:
            bot.send_message(message.chat.id, "❌ Заявка не найдена!")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_reject_'))
def admin_reject_callback(call):
    """Отклонение заявки админом"""
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Нет прав")
        return

    try:
        withdrawal_id = int(call.data.replace('admin_reject_', ''))

        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        msg = bot.send_message(
            call.message.chat.id,
            f"""<b>ОТКЛОНЕНИЕ #{withdrawal_id}</b>

Введите причину отклонения:""",
            parse_mode='HTML'
        )

        bot.register_next_step_handler(msg, process_reject_withdrawal, withdrawal_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def process_reject_withdrawal(message, withdrawal_id):
    """Обработка отклонения заявки"""
    if message.from_user.id not in ADMIN_IDS:
        return

    reject_reason = sanitize_text(message.text)

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, amount, username FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()

        if withdrawal:
            user_id, amount, username = withdrawal

            cursor.execute('''
                UPDATE withdrawals
                SET status = 'rejected', admin_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE withdrawal_id = ?
            ''', (reject_reason, withdrawal_id))

            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, 0, 'withdrawal_rejected', f'Заявка на вывод #{withdrawal_id} отклонена. {CURRENCY} не возвращаются'))

            try:
                bot.send_message(
                    user_id,
                    f"""❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>

❌ <b>Ваша заявка на вывод отклонена</b>

<b>📋 ДЕТАЛИ:</b>
Сумма: {format_usdt(amount)}
Номер: #{withdrawal_id}
Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}

⚠️ <b>{CURRENCY} НЕ возвращаются на баланс</b>

<b>💬 ПРИЧИНА:</b>
{reject_reason}""",
                    parse_mode='HTML'
                )
            except:
                pass

            conn.commit()

            bot.send_message(
                message.chat.id,
                f"""❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>

❌ <b>Заявка #{withdrawal_id} отклонена!</b>

⚠️ {CURRENCY} не возвращены пользователю.""",
                parse_mode='HTML'
            )
        else:
            bot.send_message(message.chat.id, "❌ Заявка не найдена!")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

# ========== WEBHOOK НАСТРОЙКИ ==========
@app.route('/')
def index():
    return "✅ Бот работает! Используются вебхуки."

@app.route(WEBHOOK_PATH, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Bad request', 400

def set_webhook():
    """Установка вебхука"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f"{WEBHOOK_URL}{WEBHOOK_PATH}")
        print(f"✅ Вебхук установлен: {WEBHOOK_URL}{WEBHOOK_PATH}")
    except Exception as e:
        print(f"❌ Ошибка установки вебхука: {e}")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 USDT РЕФЕРАЛЬНЫЙ БОТ С КАПЧЕЙ")
    print("=" * 50)

    init_db()
    load_channels_from_db()

    try:
        bot_info = bot.get_me()
        print(f"👤 Бот: @{bot_info.username}")
        print(f"🌐 Вебхук: {WEBHOOK_URL}{WEBHOOK_PATH}")
        print(f"💵 Валюта: {CURRENCY}")
        print(f"🔒 Капча: включена (каждые 24 часа)")
        print(f"💰 Мин. вывод: {get_setting('min_withdrawal', MIN_WITHDRAWAL)} {CURRENCY}")
        print(f"🎁 Награда за реферала: {get_setting('referral_reward', REFERRAL_REWARD)} {CURRENCY}")
        print(f"🎁 Ежед. бонус: {get_setting('daily_bonus', DAILY_BONUS_AMOUNT)} {CURRENCY}")
        print(f"📺 Каналов: {len(REQUIRED_CHANNELS)} обязательных")
        print(f"👑 Админов: {len(ADMIN_IDS)}")
        print(f"👨‍💻 Разработчик: @{DEVELOPER_USERNAME}")

        set_webhook()

        # Проверяем все реферальные бонусы при запуске
        print("🔍 Проверяю все реферальные бонусы...")
        check_all_users_subscriptions()

    except Exception as e:
        print(f"⚠️ Ошибка: {e}")

    print("=" * 50)

    app.run(host='0.0.0.0', port=PORT)

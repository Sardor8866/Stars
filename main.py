import telebot
from telebot import types
import sqlite3
import json
import time
import threading
from datetime import datetime
import random
import string
import re
import html
from flask import Flask, request, jsonify
from channel import WithdrawalChannel  # Импортируем модуль канала

# ========== НАСТРОЙКИ ==========
TOKEN = "8337396229:AAES7rHlibutnscXOHk7t6XB2fK2CUni5eE"
WEBHOOK_URL = "https://stars-prok.onrender.com"  # ⚠️ ЗАМЕНИ на свой URL!
WEBHOOK_PATH = f"/webhook/{TOKEN}"
PORT = 8080

# НАСТРОЙКИ АДМИНА (МОЖНО МЕНЯТЬ)
MIN_WITHDRAWAL = 1  # Минимальная сумма вывода в USDT
REFERRAL_REWARD = 0.1  # Награда за реферала в USDT
REFERRAL_WELCOME_BONUS = 0  # Приветственный бонус реферала в USDT
CURRENCY = "USDT"  # Валюта

# Инициализация бота
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# Инициализация Flask приложения
app = Flask(__name__)

# Инициализация канала для уведомлений
withdrawal_channel = WithdrawalChannel(TOKEN)

# ID канала для уведомлений (замените на свой)
WITHDRAWAL_CHANNEL_ID = "-1002990005205"  # Пример ID канала

# Установка канала для уведомлений
withdrawal_channel.set_channel(WITHDRAWAL_CHANNEL_ID)

# ID администратора (замените на свой)
ADMIN_IDS = [8118184388]  # Замените на ваш ID телеграм

# Глобальные переменные для каналов
REQUIRED_CHANNELS = []  # Каналы с обязательной подпиской (проверяются)
SIMPLE_LINKS = []    # Простые ссылки (любые ссылки, не проверяются)

# Словарь для хранения соответствия withdrawal_id -> message_id в канале
withdrawal_messages = {}

# ========== УТИЛИТЫ ==========
def sanitize_text(text):
    """Очистка текста от проблемных символов"""
    if not text:
        return ""

    # Удаляем непечатаемые символы
    text = ''.join(char for char in text if char.isprintable())

    # Заменяем проблемные HTML-сущности
    text = html.escape(text)

    # Удаляем лишние пробелы
    text = ' '.join(text.split())

    return text

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

def check_subscription_required(user_id):
    """Проверка обязательных подписок"""
    if not REQUIRED_CHANNELS:
        return True, None

    all_subscribed, not_subscribed = check_all_subscriptions(user_id)

    if all_subscribed:
        return True, None
    else:
        # Формируем сообщение с ВСЕМИ каналами и ссылками
        all_items = get_all_items_for_user()

        channels_text = """<b>📺 ПОДПИСКИ</b>

Для доступа к боту подпишитесь на каналы ниже:

<b>🔐 ОБЯЗАТЕЛЬНЫЕ:</b>\n"""

        # Показываем сначала обязательные каналы
        for channel in REQUIRED_CHANNELS:
            safe_name = sanitize_text(channel['channel_name'])
            channels_text += f"• {safe_name} 📌\n"

        # Затем показываем простые ссылки
        if SIMPLE_LINKS:
            channels_text += "\n<b>🔗 РЕКОМЕНДУЕМ:</b>\n"
            for link_item in SIMPLE_LINKS:
                safe_name = sanitize_text(link_item['channel_name'])
                channels_text += f"• {safe_name} 🔗\n"

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

        # Добавляем кнопки для простых ссылок
        for link_item in SIMPLE_LINKS:
            safe_name = sanitize_text(link_item['channel_name'])
            keyboard.add(
                types.InlineKeyboardButton(
                    f"🔗 {safe_name}",
                    url=link_item['channel_link']
                )
            )

        keyboard.add(
            types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription_after")
        )

        return False, (channels_text, keyboard)

def get_all_items_for_user():
    """Получить все каналы и ссылки для показа пользователю"""
    # Объединяем все и перемешиваем
    all_items = REQUIRED_CHANNELS + SIMPLE_LINKS
    random.shuffle(all_items)
    return all_items

def get_all_items_for_admin():
    """Получить все каналы и ссылки с указанием типа для админа"""
    all_items = []
    for ch in REQUIRED_CHANNELS:
        all_items.append({**ch, 'type': 'required'})
    for ch in SIMPLE_LINKS:
        all_items.append({**ch, 'type': 'simple'})
    return all_items

# ========== ФУНКЦИИ ДЛЯ ЧЕКОВ ==========
def init_checks_db():
    """Инициализация таблицы для чеков"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS checks (
            check_id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_code TEXT UNIQUE NOT NULL,
            amount REAL NOT NULL,  -- Изменено на REAL для USDT
            max_activations INTEGER NOT NULL,
            current_activations INTEGER DEFAULT 0,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            description TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS check_activations (
            activation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            check_code TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,  -- Изменено на REAL для USDT
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    conn.commit()
    conn.close()

def generate_check_code(length=8):
    """Генерация уникального кода чека"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def create_check(amount, max_activations, created_by, description=None):
    """Создание нового чека"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    check_code = generate_check_code()
    while True:
        cursor.execute("SELECT check_code FROM checks WHERE check_code = ?", (check_code,))
        if not cursor.fetchone():
            break
        check_code = generate_check_code()

    cursor.execute('''
        INSERT INTO checks (check_code, amount, max_activations, created_by, description)
        VALUES (?, ?, ?, ?, ?)
    ''', (check_code, amount, max_activations, created_by, description))

    conn.commit()
    conn.close()

    return check_code

def activate_check(check_code, user_id):
    """Активация чека пользователем"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Проверяем существование чека
    cursor.execute('''
        SELECT amount, max_activations, current_activations, is_active
        FROM checks WHERE check_code = ?
    ''', (check_code,))

    check_data = cursor.fetchone()

    if not check_data:
        conn.close()
        return False, "Чек не найден"

    amount, max_activations, current_activations, is_active = check_data

    if not is_active:
        conn.close()
        return False, "Чек деактивирован"

    if current_activations >= max_activations:
        conn.close()
        return False, "Достигнут лимит активаций"

    # Проверяем, активировал ли уже этот пользователь этот чек
    cursor.execute('''
        SELECT activation_id FROM check_activations
        WHERE check_code = ? AND user_id = ?
    ''', (check_code, user_id))

    if cursor.fetchone():
        conn.close()
        return False, "Вы уже активировали этот чек"

    # Активируем чек
    cursor.execute('''
        UPDATE checks
        SET current_activations = current_activations + 1
        WHERE check_code = ?
    ''', (check_code,))

    # Начисляем USDT пользователю
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

    # Записываем активацию
    cursor.execute('''
        INSERT INTO check_activations (check_code, user_id, amount)
        VALUES (?, ?, ?)
    ''', (check_code, user_id, amount))

    # Записываем транзакцию
    cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (?, ?, ?, ?)
    ''', (user_id, amount, 'check_activation', f'Активация чека {check_code}'))

    conn.commit()
    conn.close()

    return True, f"🎉 Чек активирован! +{format_usdt(amount)}"

def get_check_info(check_code):
    """Получение информации о чеке"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.check_code, c.amount, c.max_activations, c.current_activations,
               c.created_at, c.is_active, c.description,
               u.full_name as creator_name
        FROM checks c
        LEFT JOIN users u ON c.created_by = u.user_id
        WHERE c.check_code = ?
    ''', (check_code,))

    check_data = cursor.fetchone()
    conn.close()

    if not check_data:
        return None

    return {
        'check_code': check_data[0],
        'amount': check_data[1],
        'max_activations': check_data[2],
        'current_activations': check_data[3],
        'created_at': check_data[4],
        'is_active': bool(check_data[5]),
        'description': check_data[6],
        'creator_name': check_data[7]
    }

def get_all_checks(limit=50):
    """Получение всех чеков"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.check_code, c.amount, c.max_activations, c.current_activations,
               c.created_at, c.is_active, c.description,
               u.full_name as creator_name
        FROM checks c
        LEFT JOIN users u ON c.created_by = u.user_id
        ORDER BY c.created_at DESC
        LIMIT ?
    ''', (limit,))

    checks = cursor.fetchall()
    conn.close()

    result = []
    for check in checks:
        result.append({
            'check_code': check[0],
            'amount': check[1],
            'max_activations': check[2],
            'current_activations': check[3],
            'created_at': check[4],
            'is_active': bool(check[5]),
            'description': check[6],
            'creator_name': check[7]
        })

    return result

def deactivate_check(check_code):
    """Деактивация чека"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("UPDATE checks SET is_active = 0 WHERE check_code = ?", (check_code,))

    conn.commit()
    conn.close()

    return True

# ========== ОБНОВЛЕННЫЕ ФУНКЦИИ БАЗЫ ДАННЫХ ==========
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
            balance REAL DEFAULT 0,  -- Изменено на REAL для хранения USDT
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referred_by) REFERENCES users(user_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,  -- Изменено на REAL
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
            amount REAL,  -- Изменено на REAL
            status TEXT DEFAULT 'pending',
            admin_message TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP DEFAULT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    # Таблица для настроек
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_name TEXT UNIQUE NOT NULL,
            setting_value REAL NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Инициализация настроек
    default_settings = [
        ('min_withdrawal', MIN_WITHDRAWAL, 'Минимальная сумма вывода в USDT'),
        ('referral_reward', REFERRAL_REWARD, 'Награда за реферала в USDT'),
        ('referral_welcome_bonus', REFERRAL_WELCOME_BONUS, 'Приветственный бонус реферала в USDT'),
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
    global REQUIRED_CHANNELS, SIMPLE_LINKS

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Сначала создаем таблицу если её нет
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT,
            channel_username TEXT,
            channel_name TEXT NOT NULL,
            channel_link TEXT NOT NULL DEFAULT '',
            channel_type TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Проверяем наличие колонки channel_link
    cursor.execute("PRAGMA table_info(channels)")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]

    if 'channel_link' not in column_names:
        cursor.execute("ALTER TABLE channels ADD COLUMN channel_link TEXT NOT NULL DEFAULT ''")

    cursor.execute("SELECT channel_id, channel_username, channel_name, channel_link, channel_type FROM channels WHERE is_active = 1")
    channels = cursor.fetchall()

    for ch in channels:
        channel_data = {
            'channel_id': ch[0],
            'channel_username': ch[1],
            'channel_name': sanitize_text(ch[2]),
            'channel_link': ch[3] if ch[3] else ch[1],  # Если нет прямой ссылки, используем username
            'type': ch[4]
        }
        if ch[4] == 'required':
            REQUIRED_CHANNELS.append(channel_data)
        else:
            SIMPLE_LINKS.append(channel_data)

    conn.close()
    print(f"📺 Загружено {len(REQUIRED_CHANNELS)} обязательных каналов и {len(SIMPLE_LINKS)} простых ссылок")

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

# ========== ОБНОВЛЕННЫЕ ФУНКЦИИ ПОЛЬЗОВАТЕЛЯ ==========
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

def register_user(user_id, username, full_name, referrer_id=None):
    """Регистрация пользователя с проверкой дублирования реферальных начислений"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        safe_username = sanitize_text(username) if username else ""
        safe_full_name = sanitize_text(full_name) if full_name else f"User_{user_id}"

        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, referred_by, balance)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, safe_username, safe_full_name, referrer_id, 0))
        conn.commit()

        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, 0, 'registration', 'Регистрация в боте'))

        conn.commit()

        if referrer_id:
            try:
                bot.send_message(
                    referrer_id,
                    f"""✨ <b>НОВЫЙ РЕФЕРАЛ</b>

🎉 <b>Новый реферал зарегистрировался!</b>

<b>👤 Информация:</b>
Пользователь: {safe_full_name}

<b>📢 Бонусы будут начислены после подписки на все каналы.</b>""",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление рефереру: {e}")

    else:
        if referrer_id and not user[3]:
            cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
            current_referrer = cursor.fetchone()[0]

            if not current_referrer:
                # Обновляем реферера
                cursor.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (referrer_id, user_id))
                conn.commit()

                safe_full_name = sanitize_text(full_name) if full_name else f"User_{user_id}"
                try:
                    bot.send_message(
                        referrer_id,
                        f"""✨ <b>НОВЫЙ РЕФЕРАЛ</b>

🎉 <b>Новый реферал зарегистрировался!</b>

<b>👤 Информация:</b>
Пользователь: {safe_full_name}

<b>📢 Бонусы будут начислены после подписки на все каналы.</b>""",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Не удалось отправить уведомление рефереру: {e}")

    conn.close()

def get_user_info(user_id):
    """Получение информации о пользователе"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT u.user_id, u.username, u.full_name, u.referred_by, u.balance,
               u.registration_date, COUNT(r.user_id) as referrals_count
        FROM users u
        LEFT JOIN users r ON u.user_id = r.referred_by
        WHERE u.user_id = ?
        GROUP BY u.user_id, u.username, u.full_name, u.referred_by, u.balance, u.registration_date
    ''', (user_id,))

    user = cursor.fetchone()
    conn.close()

    if user:
        reg_date = user[5]
        if reg_date:
            if isinstance(reg_date, str):
                reg_date_str = reg_date[:10] if len(reg_date) >= 10 else reg_date
            else:
                reg_date_str = str(reg_date)[:10]
        else:
            reg_date_str = "Неизвестно"

        safe_username = sanitize_text(user[1]) if user[1] else ""
        safe_full_name = sanitize_text(user[2]) if user[2] else f"User_{user_id}"

        return {
            'user_id': user[0],
            'username': safe_username,
            'full_name': safe_full_name,
            'referred_by': user[3],
            'balance': user[4],
            'registration_date': reg_date_str,
            'referrals_count': user[6] if user[6] else 0
        }
    return None

# ========== ОБНОВЛЕННАЯ ФУНКЦИЯ ВЫВОДА ==========
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

    # Вставляем заявку на вывод
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

    # Получаем время создания
    cursor.execute("SELECT created_at FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
    created_at = cursor.fetchone()[0]

    conn.close()

    # Отправляем уведомление в канал
    withdrawal_data = {
        'withdrawal_id': withdrawal_id,
        'user_id': user_id,
        'username': safe_username,
        'amount': amount,
        'created_at': created_at[:19] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    # Отправляем уведомление в канал
    message_id = withdrawal_channel.send_withdrawal_notification(withdrawal_data)

    # Сохраняем ID сообщения
    if message_id:
        withdrawal_messages[withdrawal_id] = message_id

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

def get_transactions(user_id, limit=10):
    """Получение истории транзакций"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT amount, type, description, timestamp
        FROM transactions
        WHERE user_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (user_id, limit))

    transactions = cursor.fetchall()
    conn.close()

    result = []
    for t in transactions:
        safe_desc = sanitize_text(t[2]) if t[2] else ""
        result.append({
            'amount': t[0],
            'type': t[1],
            'description': safe_desc,
            'timestamp': t[3]
        })

    return result

def create_main_menu():
    """Главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "👤 Профиль",
        "🔗 Пригласить",
        "💰 Вывод",
        "📊 Статистика",
        "🏆 Топ",
        "🎫 Чек",
        "📋 Заявки"
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
    
    # Добавляем кнопки по 2 в ряд
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.add(buttons[i], buttons[i + 1])
        else:
            keyboard.add(buttons[i])

    # Кнопка для кастомной суммы
    keyboard.add(types.InlineKeyboardButton(
        "💎 Другая сумма",
        callback_data="withdraw_custom"
    ))

    return keyboard

# ========== ОБНОВЛЕННЫЙ ОБРАБОТЧИК РЕФЕРАЛЬНЫХ БОНУСОВ ==========
def check_and_award_referral_bonus(user_id):
    """Проверяет и начисляет реферальные бонусы после подписки на все каналы"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # Получаем информацию о пользователе
    cursor.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    if result and result[0]:  # Если у пользователя есть реферер
        referrer_id = result[0]

        # Получаем настройки
        referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

        # Проверяем, были ли уже начислены бонусы за этого реферала
        cursor.execute('''
            SELECT transaction_id FROM transactions
            WHERE user_id = ? AND type = 'referral_bonus'
            AND description LIKE ?
        ''', (referrer_id, f'%приглашение пользователя {user_id}%'))

        existing_bonus = cursor.fetchone()

        # Если бонусы еще не начислялись - начисляем только рефереру
        if not existing_bonus:
            # Начисляем рефереру
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (referral_reward, referrer_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (referrer_id, referral_reward, 'referral_bonus', f'Бонус {format_usdt(referral_reward)} за приглашение пользователя {user_id}'))

            conn.commit()

            # Отправляем уведомление рефереру
            try:
                cursor.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
                user_name = cursor.fetchone()[0] or f"User_{user_id}"

                bot.send_message(
                    referrer_id,
                    f"""✨ <b>НОВЫЙ РЕФЕРАЛ</b>

🎉 <b>Поздравляем!</b>

Приглашенный вами пользователь подписался на все каналы!

<b>👤 Информация:</b>
Пользователь: {sanitize_text(user_name)}

<b>✅ Начисление:</b>
Вам начислено: +{format_usdt(referral_reward)}

🎯 <b>Продолжайте приглашать друзей!</b>""",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление рефереру: {e}")

    conn.close()

# ========== ОБРАБОТЧИКИ ==========
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

        # Показываем главное меню
        bot.send_message(
            call.message.chat.id,
            """✨ <b>ДОБРО ПОЖАЛОВАТЬ</b>

🎉 <b>Добро пожаловать в бот!</b>

Выберите действие из меню ниже:""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

        # Проверяем и начисляем реферальные бонусы
        check_and_award_referral_bonus(user_id)
    else:
        # Показываем все каналы снова
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

        # Добавляем простые ссылки (для рекомендаций)
        for link_item in SIMPLE_LINKS:
            safe_name = sanitize_text(link_item['channel_name'])
            keyboard.add(
                types.InlineKeyboardButton(
                    f"🔗 {safe_name}",
                    url=link_item['channel_link']
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
def create_admin_keyboard():
    """Клавиатура админ панели с новыми настройками"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📊 Статистика",
        "📢 Рассылка",
        "📺 Каналы",
        "💰 Выводы",
        "💵 Баланс",
        "🎫 Чеки",
        "⚙️ Настройки",
        "⬅️ Назад"
    ]
    keyboard.add(*buttons)
    return keyboard

@bot.message_handler(commands=['admin'])
def admin_command(message):
    """Команда /admin для доступа к админ панели"""
    if message.from_user.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Нет доступа")
        return

    admin_text = """⚙️ <b>АДМИН ПАНЕЛЬ</b>

<b>Добро пожаловать в панель управления!</b>

<b>Выберите раздел:</b>"""

    bot.send_message(
        message.chat.id,
        admin_text,
        parse_mode='HTML',
        reply_markup=create_admin_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статистика" and message.from_user.id in ADMIN_IDS)
def bot_stats_command(message):
    """Статистика бота в USDT"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM users WHERE referred_by IS NOT NULL")
        ref_users = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(balance) FROM users")
        total_balance = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'approved'")
        approved_withdrawals = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'approved'")
        withdrawn_total = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'")
        pending_withdrawals = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(amount) FROM withdrawals WHERE status = 'pending'")
        pending_total = cursor.fetchone()[0] or 0

        cursor.execute("SELECT COUNT(*) FROM checks")
        total_checks = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM check_activations")
        total_check_activations = cursor.fetchone()[0]

        cursor.execute("SELECT SUM(amount) FROM check_activations")
        total_check_amount = cursor.fetchone()[0] or 0

        # Получаем настройки
        min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)
        referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
        welcome_bonus = get_setting('referral_welcome_bonus', REFERRAL_WELCOME_BONUS)

        stats_text = f"""📊 <b>СТАТИСТИКА БОТА</b>

<b>👥 ПОЛЬЗОВАТЕЛИ:</b>
├ Всего: <b>{total_users}</b>
└ По реф: <b>{ref_users}</b>

<b>💰 {CURRENCY}:</b>
├ На балансах: <b>{format_usdt(total_balance)}</b>
└ Средний: <b>{format_usdt(total_balance/total_users if total_users > 0 else 0)}</b>

<b>💸 ВЫВОДЫ:</b>
├ Одобрено: <b>{approved_withdrawals}</b> на {format_usdt(withdrawn_total)}
└ Ожидает: <b>{pending_withdrawals}</b> на {format_usdt(pending_total)}

<b>⚙️ НАСТРОЙКИ:</b>
├ Мин. вывод: <b>{format_usdt(min_withdrawal)}</b>
├ Награда: <b>{format_usdt(referral_reward)}</b>
└ Бонус: <b>{format_usdt(welcome_bonus)}</b>

<b>📺 КАНАЛЫ:</b>
├ Всего: <b>{len(REQUIRED_CHANNELS) + len(SIMPLE_LINKS)}</b>
├ Обязат: <b>{len(REQUIRED_CHANNELS)}</b>
└ Простые: <b>{len(SIMPLE_LINKS)}</b>

<b>🎫 ЧЕКИ:</b>
├ Всего: <b>{total_checks}</b>
├ Акт-ций: <b>{total_check_activations}</b>
└ Выдано: <b>{format_usdt(total_check_amount)}</b>"""

        bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
    finally:
        conn.close()

@bot.message_handler(func=lambda message: message.text == "📢 Рассылка" and message.from_user.id in ADMIN_IDS)
def mailing_all_command(message):
    """Рассылка всем пользователям"""
    msg = bot.send_message(
        message.chat.id,
        """📢 <b>РАССЫЛКА ВСЕМ</b>

Отправьте сообщение для рассылки:

<i>Поддерживается HTML разметка</i>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_mailing_all)

def process_mailing_all(message):
    """Обработка рассылки всем"""
    mailing_text = sanitize_text(message.text)

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    bot.send_message(
        message.chat.id,
        f"""✨ <b>НАЧАЛО РАССЫЛКИ</b>

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
├ Успешно: {success_count}
└ Не удалось: {fail_count}

<i>Рассылка выполнена</i>""",
        parse_mode='HTML',
        reply_markup=create_admin_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📺 Каналы" and message.from_user.id in ADMIN_IDS)
def manage_channels_command(message):
    """Управление каналами и ссылками"""
    channels_text = """📺 <b>УПРАВЛЕНИЕ КАНАЛАМИ</b>

<b>📝 КАК ДОБАВИТЬ:</b>
├ /addchannel_required - Обязательный канал
└ /addlink_simple - Простая ссылка

<b>🗑️ КАК УДАЛИТЬ:</b>
/removechannel

<b>📋 СПИСОК:</b>
/listchannels

<b>🔍 ПРОВЕРКА:</b>
/checksubs"""

    bot.send_message(
        message.chat.id,
        channels_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['addchannel_required'])
def add_channel_required_command(message):
    """Добавление обязательного канала"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """➕ <b>ДОБАВЛЕНИЕ КАНАЛА</b>

Отправьте ссылку на канал:
• @username
• https://t.me/username

<i>Бот должен быть администратором!</i>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_channel, 'required')

@bot.message_handler(commands=['addlink_simple'])
def add_link_simple_command(message):
    """Добавление простой ссылки"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """➕ <b>ДОБАВЛЕНИЕ ССЫЛКИ</b>

Отправьте:
1. Ссылку
2. Название

<b>📋 ПРИМЕР:</b>
<code>https://t.me/my_channel
Мой канал</code>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_link_simple)

def process_add_link_simple(message):
    """Обработка добавления простой ссылки"""
    try:
        parts = message.text.split('\n')

        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Отправьте ссылку и название с новой строки")
            return

        channel_link = sanitize_text(parts[0].strip())
        channel_name = sanitize_text(parts[1].strip())

        if not channel_link or not channel_name:
            bot.send_message(message.chat.id, "❌ Ссылка и название не могут быть пустыми")
            return

        # Проверяем, есть ли уже такая ссылка
        global SIMPLE_LINKS
        if any(ch['channel_link'] == channel_link for ch in SIMPLE_LINKS):
            bot.send_message(message.chat.id, "❌ Эта ссылка уже добавлена")
            return

        # Добавляем простую ссылку
        link_data = {
            'channel_id': None,  # У простых ссылок нет ID
            'channel_username': None,
            'channel_name': channel_name,
            'channel_link': channel_link,
            'type': 'simple'
        }

        SIMPLE_LINKS.append(link_data)

        # Сохраняем в базу данных
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_username TEXT,
                channel_name TEXT NOT NULL,
                channel_link TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавляем колонку channel_link если её нет
        try:
            cursor.execute("SELECT channel_link FROM channels LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE channels ADD COLUMN channel_link TEXT NOT NULL DEFAULT ''")

        cursor.execute('''
            INSERT INTO channels (channel_id, channel_username, channel_name, channel_link, channel_type, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (None, None, channel_name, channel_link, 'simple', message.from_user.id))

        conn.commit()
        conn.close()

        bot.send_message(
            message.chat.id,
            f"""✅ <b>ССЫЛКА ДОБАВЛЕНА</b>

<b>🔗 ИНФОРМАЦИЯ:</b>
├ Название: {channel_name}
├ Ссылка: {channel_link}
└ Тип: простая ссылка

<i>Пользователи увидят эту ссылку в списке.</i>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

def process_add_channel(message, channel_type):
    """Обработка добавления канала"""
    try:
        channel_link = sanitize_text(message.text.strip())

        if not channel_link:
            bot.send_message(message.chat.id, "❌ Ссылка не может быть пустой")
            return

        # Извлекаем username из ссылки
        channel_username = None
        channel_name = channel_link  # По умолчанию используем ссылку как имя

        # Пытаемся получить информацию о канале
        try:
            if channel_link.startswith('@'):
                username = channel_link[1:]
                chat = bot.get_chat(f"@{username}")
            elif 't.me/' in channel_link:
                # Извлекаем username из ссылки
                if '/' in channel_link:
                    username = channel_link.split('/')[-1].replace('@', '')
                else:
                    username = channel_link.replace('https://t.me/', '').replace('@', '')
                chat = bot.get_chat(f"@{username}")
            else:
                # Если это не стандартная ссылка на Telegram
                raise Exception("Не стандартная ссылка Telegram")

            channel_id = chat.id
            channel_name = sanitize_text(chat.title) if chat.title else channel_link

            if channel_link.startswith('@'):
                channel_username = channel_link
            else:
                channel_username = f"@{username}"

            # Для обязательных каналов проверяем права бота
            if channel_type == 'required':
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
            # Если не удалось получить информацию о канале, используем как простую ссылку
            if channel_type == 'required':
                bot.send_message(
                    message.chat.id,
                    f"""❌ <b>ОШИБКА ПАРСИНГА</b>

❌ Не удалось получить информацию о канале: {str(e)}

Для обязательных каналов используйте правильные ссылки.""",
                    parse_mode='HTML'
                )
                return
            else:
                # Для простых ссылок используем как есть
                channel_id = None
                channel_username = None

        # Добавляем канал в соответствующий список
        channel_data = {
            'channel_id': channel_id,
            'channel_username': channel_username,
            'channel_name': channel_name,
            'channel_link': channel_link,
            'type': channel_type
        }

        if channel_type == 'required':
            global REQUIRED_CHANNELS
            # Проверяем, нет ли уже такого канала
            if any(ch['channel_id'] == channel_id for ch in REQUIRED_CHANNELS if ch['channel_id']):
                bot.send_message(message.chat.id, "❌ Этот канал уже добавлен как обязательный")
                return
            REQUIRED_CHANNELS.append(channel_data)
        else:
            global SIMPLE_LINKS
            # Проверяем, нет ли уже такой ссылки
            if any(ch['channel_link'] == channel_link for ch in SIMPLE_LINKS):
                bot.send_message(message.chat.id, "❌ Эта ссылка уже добавлена")
                return
            SIMPLE_LINKS.append(channel_data)

        # Сохраняем в базу данных
        conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_username TEXT,
                channel_name TEXT NOT NULL,
                channel_link TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 1,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавляем колонку channel_link если её нет
        try:
            cursor.execute("SELECT channel_link FROM channels LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE channels ADD COLUMN channel_link TEXT NOT NULL DEFAULT ''")

        cursor.execute('''
            INSERT OR REPLACE INTO channels (channel_id, channel_username, channel_name, channel_link, channel_type, added_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (channel_id, channel_username, channel_name, channel_link, channel_type, message.from_user.id))

        conn.commit()
        conn.close()

        type_text = "обязательный (проверяется)" if channel_type == 'required' else "простая ссылка (не проверяется)"
        bot.send_message(
            message.chat.id,
            f"""✅ <b>УСПЕШНО ДОБАВЛЕНО</b>

<b>📺 ИНФОРМАЦИЯ:</b>
├ Название: {channel_name}
├ Ссылка: {channel_link}
└ Тип: {type_text}

<i>Пользователи увидят это в списке.</i>""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['listchannels'])
def list_channels_command(message):
    """Список каналов и ссылок"""
    if message.from_user.id not in ADMIN_IDS:
        return

    all_items = get_all_items_for_admin()

    if not all_items:
        channels_text = """📋 <b>СПИСОК КАНАЛОВ</b>

📭 <b>Список каналов и ссылок пуст</b>

Добавьте каналы или ссылки."""
    else:
        channels_text = """📋 <b>СПИСОК КАНАЛОВ</b>\n\n"""

        # Разделяем по типам
        required_channels = [ch for ch in all_items if ch['type'] == 'required']
        simple_links = [ch for ch in all_items if ch['type'] == 'simple']

        if required_channels:
            channels_text += "<b>🔐 ОБЯЗАТЕЛЬНЫЕ:</b>\n"
            for i, ch in enumerate(required_channels, 1):
                safe_name = sanitize_text(ch['channel_name'])
                channels_text += f'{i}. <b>{safe_name}</b>\n'
                channels_text += f'   🔗 {ch["channel_link"]}'
                if ch.get('channel_id'):
                    channels_text += f' | 🆔 {ch["channel_id"]}'
                channels_text += '\n\n'

        if simple_links:
            channels_text += "<b>🔗 ПРОСТЫЕ:</b>\n"
            for i, ch in enumerate(simple_links, 1):
                safe_name = sanitize_text(ch['channel_name'])
                channels_text += f'{i}. <b>{safe_name}</b>\n'
                channels_text += f'   🔗 {ch["channel_link"]}\n\n'

        channels_text += f"<b>📊 ИТОГО:</b> {len(all_items)}"

    bot.send_message(
        message.chat.id,
        channels_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['removechannel'])
def remove_channel_command(message):
    """Удаление канала или ссылки"""
    if message.from_user.id not in ADMIN_IDS:
        return

    all_items = get_all_items_for_admin()

    if not all_items:
        bot.send_message(message.chat.id, "❌ Нет каналов или ссылок для удаления")
        return

    # Показываем список каналов с кнопками
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    for ch in all_items:
        safe_name = sanitize_text(ch['channel_name'])
        channel_type = "🔐" if ch['type'] == 'required' else "🔗"
        # Используем channel_link как идентификатор для удаления
        keyboard.add(
            types.InlineKeyboardButton(
                f"{channel_type} {safe_name}",
                callback_data=f"remove_channel_{ch['channel_link']}_{ch['type']}"
            )
        )

    bot.send_message(
        message.chat.id,
        """➖ <b>УДАЛЕНИЕ</b>

Выберите что удалить из списка ниже:""",
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_channel_'))
def remove_channel_callback(call):
    """Обработка удаления канала или ссылки"""
    try:
        parts = call.data.replace('remove_channel_', '').split('_')
        channel_link = '_'.join(parts[:-1])  # Восстанавливаем ссылку
        channel_type = parts[-1]

        # Удаляем из соответствующего списка
        if channel_type == 'required':
            global REQUIRED_CHANNELS
            channel_to_remove = next((ch for ch in REQUIRED_CHANNELS if ch['channel_link'] == channel_link), None)
            REQUIRED_CHANNELS = [ch for ch in REQUIRED_CHANNELS if ch['channel_link'] != channel_link]
        else:
            global SIMPLE_LINKS
            channel_to_remove = next((ch for ch in SIMPLE_LINKS if ch['channel_link'] == channel_link), None)
            SIMPLE_LINKS = [ch for ch in SIMPLE_LINKS if ch['channel_link'] != channel_link]

        if channel_to_remove:
            # Удаляем из базы данных
            conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_link = ?", (channel_link,))
            conn.commit()
            conn.close()

            safe_name = sanitize_text(channel_to_remove['channel_name'])
            bot.edit_message_text(
                f"""✅ <b>УДАЛЕНО УСПЕШНО</b>

<b>📺 ИНФОРМАЦИЯ:</b>
├ Название: {safe_name}
├ Ссылка: {channel_link}
└ Тип: {'обязательный' if channel_type == 'required' else 'простая ссылка'}""",
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

    msg = bot.send_message(
        message.chat.id,
        """👥 <b>ПРОВЕРКА ПОДПИСОК</b>

Отправьте ID пользователя для проверки:""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_check_subs)

def process_check_subs(message):
    """Обработка проверки подписок"""
    try:
        user_id = int(message.text.strip())
        all_subscribed, not_subscribed = check_all_subscriptions(user_id)

        if all_subscribed:
            bot.send_message(
                message.chat.id,
                f"""✅ <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

✅ <b>Пользователь {user_id} подписан на все каналы!</b>""",
                parse_mode='HTML'
            )
        else:
            channels_text = "\n".join([f"• {sanitize_text(ch['channel_name'])} ({ch['channel_link']})" for ch in not_subscribed])

            bot.send_message(
                message.chat.id,
                f"""❌ <b>РЕЗУЛЬТАТ ПРОВЕРКИ</b>

❌ <b>Пользователь {user_id} не подписан:</b>

{channels_text}""",
                parse_mode='HTML'
            )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат ID")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "💵 Баланс" and message.from_user.id in ADMIN_IDS)
def add_balance_command(message):
    """Добавление баланса вручную"""
    msg = bot.send_message(
        message.chat.id,
        f"""➕ <b>ДОБАВЛЕНИЕ БАЛАНСА</b>

Введите ID пользователя и количество {CURRENCY} через пробел:

<b>📋 ПРИМЕР:</b>
<code>123456789 10.5</code>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_add_balance_manual)

def process_add_balance_manual(message):
    """Обработка добавления баланса"""
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

        # Проверяем существование пользователя
        cursor.execute("SELECT username, full_name, balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()

        if not user:
            bot.send_message(message.chat.id, "❌ Пользователь не найден!")
            return

        # Добавляем баланс
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))

        # Записываем транзакцию
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, 'admin_add', f'Добавлено администратором {message.from_user.id}'))

        conn.commit()

        # Получаем обновленные данные
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        new_balance = cursor.fetchone()[0]

        conn.close()

        # Уведомляем пользователя
        try:
            safe_name = sanitize_text(user[1])
            bot.send_message(
                user_id,
                f"""✨ <b>БОНУС НАЧИСЛЕН</b>

🎁 <b>Вам начислен бонус!</b>

<b>💰 ИНФОРМАЦИЯ:</b>
├ Добавлено: <b>{format_usdt(amount)}</b>
└ Новый баланс: {format_usdt(new_balance)}

🎯 <b>Теперь вы можете выводить {CURRENCY}!</b>""",
                parse_mode='HTML'
            )
        except:
            pass

        safe_name = sanitize_text(user[1])
        bot.send_message(
            message.chat.id,
            f"""✅ <b>БАЛАНС ДОБАВЛЕН</b>

<b>👤 ИНФОРМАЦИЯ:</b>
├ Пользователь: {safe_name}
├ Username: @{user[0]}
├ Добавлено: +{format_usdt(amount)}
└ Новый баланс: {format_usdt(new_balance)}""",
            parse_mode='HTML'
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат данных!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "💰 Выводы" and message.from_user.id in ADMIN_IDS)
def manage_withdrawals_command(message):
    """Управление выводами"""
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
        withdrawals_text = """💰 <b>УПРАВЛЕНИЕ ВЫВОДАМИ</b>

📭 <b>Нет ожидающих заявок</b>"""
        bot.send_message(
            message.chat.id,
            withdrawals_text,
            parse_mode='HTML'
        )
        return

    withdrawals_text = """💰 <b>ОЖИДАЮЩИЕ ЗАЯВКИ</b>\n\n"""

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

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_approve_'))
def admin_approve_callback(call):
    """Одобрение заявки админом"""
    try:
        withdrawal_id = int(call.data.replace('admin_approve_', ''))

        # Удаляем сообщение с кнопками
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        msg = bot.send_message(
            call.message.chat.id,
            f"""💬 <b>ОДОБРЕНИЕ #{withdrawal_id}</b>

Введите сообщение для пользователя (или 'нет' если не нужно):""",
            parse_mode='HTML'
        )

        bot.register_next_step_handler(msg, process_approve_withdrawal, withdrawal_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def process_approve_withdrawal(message, withdrawal_id):
    """Обработка одобрения заявки"""
    admin_message = sanitize_text(message.text) if message.text.lower() != 'нет' else None

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, amount, username, created_at FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()

        if withdrawal:
            user_id, amount, username, created_at = withdrawal

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
├ Сумма: {format_usdt(amount)}
├ Номер: #{withdrawal_id}
└ Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}
{f'<b>💬 СООБЩЕНИЕ:</b>\n{admin_message}' if admin_message else ''}""",
                    parse_mode='HTML'
                )
            except:
                pass

            conn.commit()

            # Обновляем сообщение в канале
            if withdrawal_id in withdrawal_messages:
                channel_data = {
                    'withdrawal_id': withdrawal_id,
                    'user_id': user_id,
                    'username': username,
                    'amount': amount,
                    'created_at': created_at[:19] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                withdrawal_channel.update_withdrawal_status(
                    withdrawal_messages[withdrawal_id],
                    channel_data,
                    'approved',
                    admin_message
                )

            bot.send_message(
                message.chat.id,
                f"""✅ <b>ЗАЯВКА ОДОБРЕНА</b>

✅ <b>Заявка #{withdrawal_id} одобрена!</b>""",
                parse_mode='HTML',
                reply_markup=create_admin_keyboard()
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
    try:
        withdrawal_id = int(call.data.replace('admin_reject_', ''))

        # Удаляем сообщение с кнопками
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass

        msg = bot.send_message(
            call.message.chat.id,
            f"""💬 <b>ОТКЛОНЕНИЕ #{withdrawal_id}</b>

Введите причину отклонения:""",
            parse_mode='HTML'
        )

        bot.register_next_step_handler(msg, process_reject_withdrawal, withdrawal_id)

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

def process_reject_withdrawal(message, withdrawal_id):
    """Обработка отклонения заявки - НЕ ВОЗВРАЩАЕМ USDT"""
    reject_reason = sanitize_text(message.text)

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT user_id, amount, username, created_at FROM withdrawals WHERE withdrawal_id = ?", (withdrawal_id,))
        withdrawal = cursor.fetchone()

        if withdrawal:
            user_id, amount, username, created_at = withdrawal

            cursor.execute('''
                UPDATE withdrawals
                SET status = 'rejected', admin_message = ?, processed_at = CURRENT_TIMESTAMP
                WHERE withdrawal_id = ?
            ''', (reject_reason, withdrawal_id))

            # НЕ возвращаем USDT - они сгорают при отклонении заявки

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
├ Сумма: {format_usdt(amount)}
├ Номер: #{withdrawal_id}
└ Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}

⚠️ <b>{CURRENCY} НЕ возвращаются на баланс</b>

<b>💬 ПРИЧИНА:</b>
{reject_reason}""",
                    parse_mode='HTML'
                )
            except:
                pass

            conn.commit()

            # Обновляем сообщение в канале
            if withdrawal_id in withdrawal_messages:
                channel_data = {
                    'withdrawal_id': withdrawal_id,
                    'user_id': user_id,
                    'username': username,
                    'amount': amount,
                    'created_at': created_at[:19] if created_at else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                withdrawal_channel.update_withdrawal_status(
                    withdrawal_messages[withdrawal_id],
                    channel_data,
                    'rejected',
                    reject_reason
                )

            bot.send_message(
                message.chat.id,
                f"""❌ <b>ЗАЯВКА ОТКЛОНЕНА</b>

❌ <b>Заявка #{withdrawal_id} отклонена!</b>

⚠️ {CURRENCY} не возвращены пользователю.""",
                parse_mode='HTML',
                reply_markup=create_admin_keyboard()
            )
        else:
            bot.send_message(message.chat.id, "❌ Заявка не найдена!")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('channel_approve_'))
def channel_approve_callback(call):
    """Одобрение заявки из канала"""
    try:
        withdrawal_id = int(call.data.replace('channel_approve_', ''))

        # Проверяем, является ли пользователь админом
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return

        # Удаляем клавиатуру из сообщения
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except:
            pass

        bot.answer_callback_query(call.id, "✅ Заявка будет одобрена")

        # Перенаправляем в админ-панель для завершения
        bot.send_message(
            call.from_user.id,
            f"""🎯 <b>ОДОБРЕНИЕ #{withdrawal_id}</b>

Перейдите в админ-панель для завершения.""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('channel_reject_'))
def channel_reject_callback(call):
    """Отклонение заявки из канала"""
    try:
        withdrawal_id = int(call.data.replace('channel_reject_', ''))

        # Проверяем, является ли пользователь админом
        if call.from_user.id not in ADMIN_IDS:
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return

        # Удаляем клавиатуру из сообщения
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except:
            pass

        bot.answer_callback_query(call.id, "❌ Заявка будет отклонена")

        # Перенаправляем в админ-панель для завершения
        bot.send_message(
            call.from_user.id,
            f"""🎯 <b>ОТКЛОНЕНИЕ #{withdrawal_id}</b>

Перейдите в админ-панель для завершения.""",
            parse_mode='HTML'
        )

    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}")

@bot.message_handler(func=lambda message: message.text == "🎫 Чеки" and message.from_user.id in ADMIN_IDS)
def manage_checks_command(message):
    """Управление чеками"""
    checks_text = """🎫 <b>УПРАВЛЕНИЕ ЧЕКАМИ</b>

<b>📝 ДОСТУПНЫЕ ДЕЙСТВИЯ:</b>
├ /createcheck - Создать чек
├ /listchecks - Список чеков
├ /checkinfo [код] - Информация
├ /deactivatecheck [код] - Деактивировать
└ /checkstats - Статистика"""

    bot.send_message(
        message.chat.id,
        checks_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['createcheck'])
def create_check_command(message):
    """Создание чека"""
    if message.from_user.id not in ADMIN_IDS:
        return

    msg = bot.send_message(
        message.chat.id,
        """🎫 <b>СОЗДАНИЕ ЧЕКА</b>

Введите данные в формате:

<code>сумма_USDT количество_активаций описание(опционально)</code>

<b>📋 ПРИМЕРЫ:</b>
<code>1 10 Приветственный бонус</code>
<code>0.5 5</code>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_create_check)

def process_create_check(message):
    """Обработка создания чека"""
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.send_message(message.chat.id, "❌ Неверный формат!")
            return

        amount = float(parts[0])
        max_activations = int(parts[1])
        description = sanitize_text(' '.join(parts[2:])) if len(parts) > 2 else None

        if amount <= 0 or max_activations <= 0:
            bot.send_message(message.chat.id, "❌ Сумма и количество должны быть больше 0!")
            return

        # Создаем чек
        check_code = create_check(amount, max_activations, message.from_user.id, description)

        # Формируем ссылку для активации
        try:
            bot_username = bot.get_me().username
            activation_link = f"https://t.me/{bot_username}?start=check_{check_code}"
        except:
            activation_link = f"https://t.me/ваш_бот?start=check_{check_code}"

        response_text = f"""✅ <b>ЧЕК СОЗДАН</b>

<b>📋 ИНФОРМАЦИЯ:</b>
├ Код: <code>{check_code}</code>
├ Сумма: <b>{format_usdt(amount)}</b>
├ Активаций: <b>{max_activations}</b>
└ Описание: <b>{description or 'Не указано'}</b>

<b>🔗 ССЫЛКА:</b>
<code>{activation_link}</code>

<b>📝 КОМАНДА:</b>
<code>/activate {check_code}</code>"""

        bot.send_message(
            message.chat.id,
            response_text,
            parse_mode='HTML'
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат чисел!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

@bot.message_handler(commands=['listchecks'])
def list_checks_command(message):
    """Список всех чеков"""
    if message.from_user.id not in ADMIN_IDS:
        return

    checks = get_all_checks(20)

    if not checks:
        checks_text = """📋 <b>СПИСОК ЧЕКОВ</b>

📭 <b>Список чеков пуст</b>

Создайте первый чек командой /createcheck"""
    else:
        checks_text = """📋 <b>СПИСОК ЧЕКОВ</b>\n\n"""

        for check in checks:
            status = "✅" if check['is_active'] else "❌"
            safe_desc = sanitize_text(check['description']) if check['description'] else ""
            checks_text += f"{status} <b>{check['check_code']}</b>\n"
            checks_text += f"   💰 {format_usdt(check['amount'])} | 👥 {check['current_activations']}/{check['max_activations']}\n"
            if safe_desc:
                checks_text += f"   📝 {safe_desc}\n"
            checks_text += "\n"

    bot.send_message(
        message.chat.id,
        checks_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['checkinfo'])
def check_info_command(message):
    """Информация о чеке"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Укажите код: /checkinfo КОД")
        return

    check_code = parts[1].upper()
    check_info = get_check_info(check_code)

    if not check_info:
        bot.send_message(message.chat.id, f"❌ Чек {check_code} не найден")
        return

    status = "✅ Активен" if check_info['is_active'] else "❌ Деактивирован"
    safe_desc = sanitize_text(check_info['description']) if check_info['description'] else "Не указано"
    safe_creator = sanitize_text(check_info['creator_name']) if check_info['creator_name'] else "Неизвестно"

    check_text = f"""🎫 <b>ИНФОРМАЦИЯ О ЧЕКЕ {check_code}</b>

<b>📋 ОСНОВНАЯ ИНФОРМАЦИЯ:</b>
├ Код: <code>{check_info['check_code']}</code>
├ Сумма: <b>{format_usdt(check_info['amount'])}</b>
├ Активаций: <b>{check_info['current_activations']}/{check_info['max_activations']}</b>
├ Статус: <b>{status}</b>
├ Создал: <b>{safe_creator}</b>
├ Дата: <b>{check_info['created_at']}</b>
└ Описание: <b>{safe_desc}</b>"""

    try:
        bot_username = bot.get_me().username
        activation_link = f"https://t.me/{bot_username}?start=check_{check_code}"
        check_text += f"\n\n<b>🔗 ССЫЛКА:</b>\n<code>{activation_link}</code>"
    except:
        pass

    check_text += f"\n\n<b>📝 КОМАНДА:</b>\n<code>/activate {check_code}</code>"

    bot.send_message(
        message.chat.id,
        check_text,
        parse_mode='HTML'
    )

@bot.message_handler(commands=['deactivatecheck'])
def deactivate_check_command(message):
    """Деактивация чека"""
    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(message.chat.id, "❌ Укажите код: /deactivatecheck КОД")
        return

    check_code = parts[1].upper()

    # Проверяем существование чека
    check_info = get_check_info(check_code)
    if not check_info:
        bot.send_message(message.chat.id, f"❌ Чек {check_code} не найден")
        return

    if not check_info['is_active']:
        bot.send_message(message.chat.id, f"❌ Чек {check_code} уже деактивирован")
        return

    # Деактивируем чек
    deactivate_check(check_code)

    bot.send_message(
        message.chat.id,
        f"""✅ <b>ЧЕК ДЕАКТИВИРОВАН</b>

✅ <b>Чек {check_code} деактивирован!</b>

Теперь его нельзя активировать.""",
        parse_mode='HTML'
    )

@bot.message_handler(commands=['checkstats'])
def check_stats_command(message):
    """Статистика по чекам"""
    if message.from_user.id not in ADMIN_IDS:
        return

    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM checks")
    total_checks = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM checks WHERE is_active = 1")
    active_checks = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(amount * max_activations) FROM checks")
    total_potential = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount * current_activations) FROM checks")
    total_distributed = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM check_activations")
    total_activations = cursor.fetchone()[0]

    conn.close()

    stats_text = f"""📊 <b>СТАТИСТИКА ПО ЧЕКАМ</b>

<b>🎫 ОБЩАЯ:</b>
├ Всего чеков: <b>{total_checks}</b>
├ Активных: <b>{active_checks}</b>
└ Активаций: <b>{total_activations}</b>

<b>💰 РАСПРЕДЕЛЕНИЕ:</b>
├ Потенциально: <b>{format_usdt(total_potential)}</b>
├ Уже выдано: <b>{format_usdt(total_distributed)}</b>
└ Осталось: <b>{format_usdt(total_potential - total_distributed)}</b>

<b>📈 ЭФФЕКТИВНОСТЬ:</b>
├ Процент: <b>{round((total_distributed / total_potential * 100) if total_potential > 0 else 0, 1)}%</b>
└ Средний чек: <b>{format_usdt(total_distributed / total_activations if total_activations > 0 else 0)}</b>"""

    bot.send_message(
        message.chat.id,
        stats_text,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda message: message.text == "⚙️ Настройки" and message.from_user.id in ADMIN_IDS)
def system_settings_command(message):
    """Управление настройками системы"""
    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
    welcome_bonus = get_setting('referral_welcome_bonus', REFERRAL_WELCOME_BONUS)

    settings_text = f"""⚙️ <b>НАСТРОЙКИ СИСТЕМЫ</b>

<b>💰 ВЫВОД:</b>
Мин. вывод: <b>{format_usdt(min_withdrawal)}</b>

<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
├ Награда: <b>{format_usdt(referral_reward)}</b>
└ Бонус рефералу: <b>{format_usdt(welcome_bonus)}</b>

Выберите настройку для изменения:"""

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💰 Мин. вывод", callback_data="setting_min_withdrawal"),
        types.InlineKeyboardButton("🎁 Награда", callback_data="setting_referral_reward"),
        types.InlineKeyboardButton("👋 Бонус", callback_data="setting_welcome_bonus")
    )
    keyboard.add(
        types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_back")
    )

    bot.send_message(
        message.chat.id,
        settings_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('setting_'))
def setting_callback(call):
    """Обработчик изменения настроек"""
    setting_name = call.data.replace('setting_', '')
    setting_names = {
        'min_withdrawal': 'Минимальный вывод',
        'referral_reward': 'Награда за реферала',
        'welcome_bonus': 'Приветственный бонус реферала'
    }

    current_value = get_setting(setting_name)

    msg = bot.send_message(
        call.message.chat.id,
        f"""✏️ <b>ИЗМЕНЕНИЕ НАСТРОЙКИ</b>

Текущее значение <b>{setting_names.get(setting_name, setting_name)}</b>:

<b>{format_usdt(current_value)}</b>

Введите новое значение в {CURRENCY} (число):""",
        parse_mode='HTML'
    )

    bot.register_next_step_handler(msg, process_setting_update, setting_name, call.message.chat.id, call.message.message_id)

def process_setting_update(message, setting_name, chat_id, message_id):
    """Обработка обновления настройки"""
    try:
        new_value = float(message.text)

        if new_value < 0:
            bot.send_message(message.chat.id, "❌ Значение не может быть отрицательным!")
            return

        # Обновляем настройку
        update_setting(setting_name, new_value)

        setting_names = {
            'min_withdrawal': 'Минимальный вывод',
            'referral_reward': 'Награда за реферала',
            'welcome_bonus': 'Приветственный бонус реферала'
        }

        bot.send_message(
            message.chat.id,
            f"""✅ <b>НАСТРОЙКА ОБНОВЛЕНА</b>

<b>📋 ИНФОРМАЦИЯ:</b>
├ Настройка: <b>{setting_names.get(setting_name, setting_name)}</b>
└ Новое значение: <b>{format_usdt(new_value)}</b>

Изменение вступит в силу сразу.""",
            parse_mode='HTML',
            reply_markup=create_admin_keyboard()
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное число!")

@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back_callback(call):
    """Возврат в админ панель"""
    admin_text = """⚙️ <b>АДМИН ПАНЕЛЬ</b>

<b>Добро пожаловать в панель управления!</b>

<b>Выберите раздел:</b>"""

    bot.edit_message_text(
        admin_text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='HTML'
    )

@bot.message_handler(func=lambda message: message.text == "⬅️ Назад" and message.from_user.id in ADMIN_IDS)
def admin_back_to_main_menu(message):
    """Возврат в главное меню из админ панели"""
    bot.send_message(
        message.chat.id,
        """🏠 <b>ГЛАВНОЕ МЕНЮ</b>

🏠 <b>Вы вернулись в главное меню</b>""",
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

# ========== ОСНОВНЫЕ КОМАНДЫ БОТА ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = sanitize_text(message.from_user.username) if message.from_user.username else ""
    full_name = sanitize_text(message.from_user.full_name) if message.from_user.full_name else f"User_{user_id}"

    # Проверяем, активируется ли чек
    if len(message.text.split()) > 1:
        start_param = message.text.split()[1]

        if start_param.startswith('check_'):
            check_code = start_param.replace('check_', '')

            # Сначала регистрируем пользователя
            register_user(user_id, username, full_name, None)

            # Проверяем подписку на каналы
            if REQUIRED_CHANNELS:
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
                else:
                    check_and_award_referral_bonus(user_id)

            # Активируем чек
            success, result_message = activate_check(check_code, user_id)

            if success:
                user_info = get_user_info(user_id)
                if user_info:
                    bot.send_message(
                        message.chat.id,
                        f"""✅ <b>ЧЕК АКТИВИРОВАН</b>

✅ <b>Чек активирован успешно!</b> 🎉

<b>💰 НАЧИСЛЕНИЕ:</b>
{result_message}
Ваш баланс: {format_usdt(user_info['balance'])}

🎯 <b>Теперь вы можете выводить {CURRENCY}!</b>""",
                        parse_mode='HTML'
                    )
                else:
                    bot.send_message(
                        message.chat.id,
                        f"""✅ <b>ЧЕК АКТИВИРОВАН</b>

✅ {result_message}""",
                        parse_mode='HTML'
                    )
            else:
                bot.send_message(
                    message.chat.id,
                    f"""❌ <b>ОШИБКА АКТИВАЦИИ</b>

❌ <b>Не удалось активировать чек:</b>

{result_message}""",
                    parse_mode='HTML'
                )

            # Показываем главное меню
            bot.send_message(
                message.chat.id,
                """🏠 <b>ГЛАВНОЕ МЕНЮ</b>

🏠 <b>Добро пожаловать!</b>

Выберите действие из меню ниже:""",
                parse_mode='HTML',
                reply_markup=create_main_menu()
            )
            return

        elif start_param.startswith('ref_'):
            referrer_id = None
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

            register_user(user_id, username, full_name, referrer_id)

            # После регистрации проверяем подписку на каналы
            if REQUIRED_CHANNELS:
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
                else:
                    check_and_award_referral_bonus(user_id)

                    welcome_text = f"""✨ <b>ДОБРО ПОЖАЛОВАТЬ</b>

✨ <b>Добро пожаловать, {full_name}!</b>

За каждого приглашенного друга ты получишь {format_usdt(get_setting('referral_reward', REFERRAL_REWARD))}

После приглашения, средства будут автоматически зачислены на твой баланс.

Приглашай друзей и зарабатывай!

<b>👇 НАВИГАЦИЯ:</b>
Используйте кнопки ниже:"""

                    bot.send_message(
                        message.chat.id,
                        welcome_text,
                        parse_mode='HTML',
                        reply_markup=create_main_menu()
                    )
                    return

        else:
            register_user(user_id, username, full_name, None)
    else:
        register_user(user_id, username, full_name, None)

    # ПРОВЕРКА ПОДПИСКИ НА КАНАЛЫ ДЛЯ ВСЕХ НОВЫХ ПОЛЬЗОВАТЕЛЕЙ
    if REQUIRED_CHANNELS:
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
        else:
            check_and_award_referral_bonus(user_id)

    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

    welcome_text = f"""✨ <b>ДОБРО ПОЖАЛОВАТЬ</b>

✨ <b>Добро пожаловать, {full_name}!</b>

За каждого приглашенного друга: {format_usdt(referral_reward)}

Средства зачисляются автоматически.

Приглашай друзей и зарабатывай!

<b>👇 НАВИГАЦИЯ:</b>
Используйте кнопки ниже:"""

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "👤 Профиль")
def profile_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)
    
    if user_info:
        # Получаем реальную сумму выведенных средств
        total_withdrawn = get_user_total_withdrawn(message.from_user.id)
        ref_count = user_info['referrals_count']
        
        # КОРОТКИЙ ТЕКСТ ПРОФИЛЯ:
        profile_text = f"""👤 <b>Ваш профиль</b>

<b>🆔 ID:</b> <code>{user_info['user_id']}</code>
<b>💰 Баланс:</b> {format_usdt(user_info['balance'])}
<b>📤 Выведено:</b> {format_usdt(total_withdrawn)}
<b>👥 Приглашено:</b> {ref_count} чел.

🔗 <b>Реф. ссылка:</b>
<code>{generate_referral_link(message.from_user.id)}</code>

<b>🎁 Награда за друга:</b> {format_usdt(get_setting('referral_reward', REFERRAL_REWARD))}"""

        bot.send_message(
            message.chat.id,
            profile_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(message.from_user.id)
        )

@bot.message_handler(func=lambda message: message.text == "🔗 Пригласить")
def invite_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

    if user_info:
        referral_link = generate_referral_link(message.from_user.id)
        referrals_count = user_info['referrals_count']
        earned = referrals_count * referral_reward

        # КОРОТКИЙ ТЕКСТ РЕФЕРАЛКИ:
        invite_text = f"""🎁 <b>Реферальная программа</b>

<b>🎁 Награда:</b> {format_usdt(referral_reward)} за друга

<b>🔗 Ваша ссылка:</b>
<code>{referral_link}</code>

<b>📊 Статистика:</b>
├ Приглашено: {referrals_count} чел.
└ Заработано: {format_usdt(earned)}

💸 <b>Средства зачисляются автоматически!</b>"""

        bot.send_message(
            message.chat.id,
            invite_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(message.from_user.id)
        )

@bot.message_handler(func=lambda message: message.text == "💰 Вывод")
def withdrawal_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)
    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

    if not user_info:
        bot.send_message(message.chat.id, "❌ Ошибка: пользователь не найден")
        return

    # КОРОТКИЙ ТЕКСТ ВЫВОДА:
    withdrawal_text = f"""💰 <b>Вывод {CURRENCY}</b>

<b>💰 Баланс:</b> {format_usdt(user_info['balance'])}
<b>📊 Мин. сумма:</b> {format_usdt(min_withdrawal)}
<b>⏱️ Время:</b> до 24 часов

👇 <b>Выберите сумму:</b>"""

    bot.send_message(
        message.chat.id,
        withdrawal_text,
        parse_mode='HTML',
        reply_markup=create_withdrawal_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('withdraw_'))
def handle_withdrawal_callback(call):
    """Обработчик инлайн-кнопок вывода"""
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
            f"""💎 <b>ВЫВОД {CURRENCY}</b>

<b>💎 Введите сумму для вывода</b>

<b>📋 ТРЕБОВАНИЯ:</b>
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
        f"""📝 <b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b>

<b>💰 ДЕТАЛИ ВЫВОДА:</b>
├ Сумма: {format_usdt(amount)}
├ Ваш баланс: {format_usdt(user_info['balance'])}
└ После вывода: {format_usdt(user_info['balance'] - amount)}

✍️ <b>Введите ваш @username для связи:</b>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_withdrawal_username, user_data)
    bot.answer_callback_query(call.id)

def process_custom_withdrawal(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

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

<b>💰 ДЕТАЛИ:</b>
├ Хотите вывести: {format_usdt(amount)}
├ Ваш баланс: {format_usdt(user_info['balance'])}
└ Не хватает: {format_usdt(amount - user_info['balance'])}""",
                parse_mode='HTML'
            )
            return

        user_data = {'amount': amount, 'user_id': message.from_user.id}

        msg = bot.send_message(
            message.chat.id,
            f"""📝 <b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b>

<b>💰 ДЕТАЛИ ВЫВОДА:</b>
├ Сумма: {format_usdt(amount)}
├ Ваш баланс: {format_usdt(user_info['balance'])}
└ После вывода: {format_usdt(user_info['balance'] - amount)}

✍️ <b>Введите ваш @username для связи:</b>""",
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

<b>📋 ДЕТАЛИ:</b>
├ Сумма: <b>{format_usdt(amount)}</b>
├ Username: <b>@{username}</b>
├ Ваш баланс: <b>{format_usdt(user_info['balance'])}</b>
└ Статус: <b>⏳ На рассмотрении</b>

<b>⏱️ ИНФОРМАЦИЯ:</b>
├ Время: до 24 часов
└ Связь: @{username}

🎯 <b>Следите за статусом в "Заявки"</b>""",
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

@bot.message_handler(func=lambda message: message.text == "🎫 Чек")
def activate_check_menu_command(message):
    """Активация чека из меню"""
    user_id = message.from_user.id

    # Проверка подписки на каналы
    if REQUIRED_CHANNELS:
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

    msg = bot.send_message(
        message.chat.id,
        """🎫 <b>АКТИВАЦИЯ ЧЕКА</b>

Введите код чека:

<b>📋 ПРИМЕР:</b>
<code>ABC123XY</code>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_activate_check_menu)

def process_activate_check_menu(message):
    """Обработка активации чека из меню"""
    user_id = message.from_user.id
    check_code = sanitize_text(message.text.strip().upper())

    if not check_code:
        bot.send_message(
            message.chat.id,
            """❌ <b>ОШИБКА ВВОДА</b>

❌ <b>Введите код чека!</b>""",
            parse_mode='HTML'
        )
        return

    # Активируем чек
    success, result_message = activate_check(check_code, user_id)

    if success:
        user_info = get_user_info(user_id)
        if user_info:
            bot.send_message(
                message.chat.id,
                f"""✅ <b>ЧЕК АКТИВИРОВАН</b>

✅ <b>Чек активирован успешно!</b> 🎉

<b>💰 НАЧИСЛЕНИЕ:</b>
{result_message}
Ваш новый баланс: {format_usdt(user_info['balance'])}

🎯 <b>Теперь вы можете выводить {CURRENCY}!</b>""",
                parse_mode='HTML',
                reply_markup=create_main_menu()
            )
        else:
            bot.send_message(
                message.chat.id,
                f"""✅ <b>ЧЕК АКТИВИРОВАН</b>

✅ {result_message}""",
                parse_mode='HTML',
                reply_markup=create_main_menu()
            )
    else:
        bot.send_message(
            message.chat.id,
            f"""❌ <b>ОШИБКА АКТИВАЦИИ</b>

❌ <b>Не удалось активировать чек:</b>

{result_message}""",
            parse_mode='HTML',
            reply_markup=create_main_menu()
        )

@bot.message_handler(commands=['activate'])
def activate_check_command(message):
    """Активация чека пользователем"""
    user_id = message.from_user.id

    # Проверка подписки на каналы
    if REQUIRED_CHANNELS:
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

    parts = message.text.split()
    if len(parts) < 2:
        bot.send_message(
            message.chat.id,
            """🎫 <b>АКТИВАЦИЯ ЧЕКА</b>

Использование: <code>/activate КОД_ЧЕКА</code>

<b>📋 ПРИМЕР:</b>
<code>/activate ABC123XY</code>""",
            parse_mode='HTML'
        )
        return

    check_code = parts[1].upper()

    # Активируем чек
    success, result_message = activate_check(check_code, user_id)

    if success:
        user_info = get_user_info(user_id)
        if user_info:
            bot.send_message(
                message.chat.id,
                f"""✅ <b>ЧЕК АКТИВИРОВАН</b>

✅ <b>Чек активирован успешно!</b> 🎉

<b>💰 НАЧИСЛЕНИЕ:</b>
{result_message}
Ваш новый баланс: {format_usdt(user_info['balance'])}

🎯 <b>Теперь вы можете выводить {CURRENCY}!</b>""",
                parse_mode='HTML'
            )
        else:
            bot.send_message(
                message.chat.id,
                f"""✅ <b>ЧЕК АКТИВИРОВАН</b>

✅ {result_message}""",
                parse_mode='HTML'
            )
    else:
        bot.send_message(
            message.chat.id,
            f"""❌ <b>ОШИБКА АКТИВАЦИИ</b>

❌ <b>Не удалось активировать чек:</b>

{result_message}""",
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda message: message.text == "📋 Заявки")
def my_withdrawals_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_id = message.from_user.id
    withdrawals = get_user_withdrawals(user_id, 10)

    if not withdrawals:
        withdrawals_text = f"""📋 <b>МОИ ЗАЯВКИ</b>

У вас еще нет заявок.

<b>💰 СОЗДАНИЕ ПЕРВОЙ ЗАЯВКИ:</b>
1. Нажмите "💰 Вывод"
2. Выберите сумму (от {format_usdt(get_setting('min_withdrawal', MIN_WITHDRAWAL))})
3. Укажите ваш @username
4. Ожидайте подтверждения"""
    else:
        withdrawals_text = """📋 <b>МОИ ЗАЯВКИ</b>\n\n"""

        for i, w in enumerate(withdrawals, 1):
            status_emoji = "⏳" if w['status'] == 'pending' else "✅" if w['status'] == 'approved' else "❌"
            status_text = "На рассмотрении" if w['status'] == 'pending' else "Одобрено" if w['status'] == 'approved' else "Отклонено"

            created_date = w['created_at'][:10] if w['created_at'] and len(w['created_at']) >= 10 else "Неизвестно"

            withdrawals_text += f'{i}. <b>{format_usdt(w["amount"])}</b> - {status_emoji} <b>{status_text}</b>\n'
            withdrawals_text += f'   📅 {created_date} | 🆔 #{w["id"]}\n'

            if w['admin_message']:
                withdrawals_text += f'   💬 {w["admin_message"]}\n'

            withdrawals_text += '\n'

    bot.send_message(
        message.chat.id,
        withdrawals_text,
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def stats_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    user_info = get_user_info(message.from_user.id)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
    
    if user_info:
        # Получаем реальные данные о выводах
        total_withdrawn = get_user_total_withdrawn(message.from_user.id)
        
        referrals_count = user_info['referrals_count']
        earned_from_refs = referrals_count * referral_reward
        min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

        stats_text = f"""📊 <b>ВАША СТАТИСТИКА</b>

<b>💰 ФИНАНСЫ:</b>
├ Баланс: {format_usdt(user_info['balance'])}
├ Выведено: {format_usdt(total_withdrawn)}
└ Заработано с реф: {format_usdt(earned_from_refs)}

<b>👥 РЕФЕРАЛЬНАЯ:</b>
├ Приглашено: {referrals_count}
├ Награда: {format_usdt(referral_reward)}
└ До след. награды: 1 друг

<b>💸 ВЫВОД:</b>
├ Мин. сумма: {format_usdt(min_withdrawal)}
└ Доступно: {format_usdt(user_info['balance'])}

🎯 <b>Приглашайте друзей и зарабатывайте {format_usdt(referral_reward)}!</b>"""

        bot.send_message(
            message.chat.id,
            stats_text,
            parse_mode='HTML'
        )

@bot.message_handler(func=lambda message: message.text == "🏆 Топ")
def top_command(message):
    # Проверяем подписку на каналы
    if REQUIRED_CHANNELS:
        is_subscribed, subscription_data = check_subscription_required(message.from_user.id)
        if not is_subscribed:
            channels_text, keyboard = subscription_data
            bot.send_message(
                message.chat.id,
                channels_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            return

    top_users = get_top_referrers(10)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)

    if top_users:
        top_text = f"""🏆 <b>ТОП 10 РЕФЕРЕРОВ</b>

<b>🏆 Топ 10 (по приглашенным)</b>

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
            balance = user[3] if user[3] else 0
            referrals = user[4] if user[4] else 0
            earned = referrals * referral_reward

            top_text += f'{medal} <b>{username}</b>\n'
            top_text += f'<b>👥 Рефералов:</b> {referrals} | <b>💰 Заработано:</b> {format_usdt(earned)}\n\n'

        top_text += '🎯 <b>Приглашайте друзей и попадите в топ!</b>'

        bot.send_message(
            message.chat.id,
            top_text,
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            f"""🏆 <b>ТОП РЕФЕРЕРОВ</b>

🏆 <b>Топ рефереров</b>

Пока никто не пригласил друзей. Будьте первым!

Награда за реферала: {format_usdt(referral_reward)}""",
            parse_mode='HTML'
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_link_"))
def copy_link_callback(call):
    """Обработка кнопки копирования ссылки"""
    if call.data.startswith("copy_link_"):
        user_id = call.data.replace("copy_link_", "")
        try:
            user_id = int(user_id)
            referral_link = generate_referral_link(user_id)

            bot.answer_callback_query(
                call.id,
                f"Ссылка скопирована!",
                show_alert=False
            )

            bot.send_message(
                call.message.chat.id,
                f"""📋 <b>КОПИРОВАНИЕ ССЫЛКИ</b>

<b>📋 Ваша ссылка:</b>

<code>{referral_link}</code>

💡 <b>Скопируйте и отправьте другу</b>""",
                parse_mode='HTML'
            )
        except ValueError:
            bot.answer_callback_query(call.id, "Ошибка", show_alert=True)

@bot.message_handler(commands=['invite'])
def invite_link_command(message):
    user_id = message.from_user.id
    referral_link = generate_referral_link(user_id)

    invite_text = f"""🔗 <b>РЕФЕРАЛЬНАЯ ССЫЛКА</b>

<b>🔗 Ваша ссылка:</b>

<code>{referral_link}</code>"""

    bot.send_message(
        message.chat.id,
        invite_text,
        parse_mode='HTML',
        reply_markup=create_referral_keyboard(user_id)
    )

@bot.message_handler(commands=['withdraw'])
def withdraw_link_command(message):
    withdrawal_command(message)

@bot.message_handler(commands=['profile'])
def profile_link_command(message):
    profile_command(message)

@bot.message_handler(commands=['top'])
def top_link_command(message):
    top_command(message)

@bot.message_handler(commands=['stats'])
def stats_link_command(message):
    stats_command(message)

@bot.message_handler(commands=['mywithdrawals'])
def my_withdrawals_link_command(message):
    my_withdrawals_command(message)

def send_daily_notifications():
    """Функция для отправки уведомлений"""
    while True:
        try:
            conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users")
            users = cursor.fetchall()

            min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

            for user_tuple in users:
                try:
                    user_id = user_tuple[0]
                    user_info = get_user_info(user_id)
                    if user_info and user_info['balance'] >= min_withdrawal:
                        bot.send_message(
                            user_id,
                            f"""💰 <b>ДОСТАТОЧНО {CURRENCY}</b>

<b>💰 У вас достаточно {CURRENCY} для вывода!</b>

<b>💰 ИНФОРМАЦИЯ:</b>
├ Ваш баланс: {format_usdt(user_info['balance'])}
└ Мин. сумма: {format_usdt(min_withdrawal)}

🎯 <b>Вы можете вывести свои {CURRENCY}!</b>
Нажмите "💰 Вывод" в меню""",
                            parse_mode='HTML'
                        )
                except:
                    continue

            conn.close()
        except Exception as e:
            print(f"Ошибка в потоке уведомлений: {e}")

        time.sleep(24 * 3600)

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
    print("🤖 USDT РЕФЕРАЛЬНЫЙ БОТ (ВЕБХУКИ)")
    print("=" * 50)

    init_db()
    init_checks_db()
    load_channels_from_db()

    try:
        bot_info = bot.get_me()
        print(f"👤 Бот: @{bot_info.username}")
        print(f"🌐 Вебхук: {WEBHOOK_URL}{WEBHOOK_PATH}")
        print(f"💵 Валюта: {CURRENCY}")
        print(f"💰 Мин. вывод: {get_setting('min_withdrawal', MIN_WITHDRAWAL)} {CURRENCY}")
        print(f"🎁 Награда: {get_setting('referral_reward', REFERRAL_REWARD)} {CURRENCY}")
        print(f"📺 Каналов: {len(REQUIRED_CHANNELS)} обяз. + {len(SIMPLE_LINKS)} простых")
        print(f"👑 Админов: {len(ADMIN_IDS)}")

        # Устанавливаем вебхук
        set_webhook()

    except Exception as e:
        print(f"⚠️ Ошибка: {e}")

    print("=" * 50)

    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=PORT)

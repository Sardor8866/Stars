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
MIN_WITHDRAWAL = 1  # Минимальная сумма вывода в USDT (ИЗМЕНЕНО НА 1)
REFERRAL_REWARD = 0.035  # Награда за реферала в USDT
REFERRAL_WELCOME_BONUS = 0.1  # Приветственный бонус реферала в USDT
CURRENCY = "USDT"  # Валюта

# Инициализация бота
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

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
                    f"""═══════════════════════════
✨ <b>НОВЫЙ РЕФЕРАЛ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Новый реферал зарегистрировался!</b></blockquote>

<b>👤 Информация о реферале:</b>
<blockquote>Пользователь: {safe_full_name}</blockquote>

<blockquote>📢 <b>Бонусы будут начислены после того, как пользователь подпишется на все обязательные каналы.</b></blockquote>""",
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
                        f"""═══════════════════════════
✨ <b>НОВЫЙ РЕФЕРАЛ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Новый реферал зарегистрировался!</b></blockquote>

<b>👤 Информация о реферале:</b>
<blockquote>Пользователь: {safe_full_name}</blockquote>

<blockquote>📢 <b>Бонусы будут начислены после того, как пользователь подпишется на все обязательные каналы.</b></blockquote>""",
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
        return False, f"Минимальная сумма вывода: {format_usdt(min_withdrawal)}"

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

    return True, f"Заявка на вывод {format_usdt(amount)} успешно создана"

# ========== ОБНОВЛЕННЫЙ ОБРАБОТЧИК ЧЕКОВ ==========
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

    return True, f"🎉 Чек успешно активирован! Получено {format_usdt(amount)}"

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
        welcome_bonus = get_setting('referral_welcome_bonus', REFERRAL_WELCOME_BONUS)

        # Проверяем, были ли уже начислены бонусы за этого реферала
        cursor.execute('''
            SELECT transaction_id FROM transactions
            WHERE user_id = ? AND type = 'referral_bonus'
            AND description LIKE ?
        ''', (referrer_id, f'%приглашение пользователя {user_id}%'))

        existing_bonus = cursor.fetchone()

        # Если бонусы еще не начислялись - начисляем
        if not existing_bonus:
            # Начисляем рефереру
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (referral_reward, referrer_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (referrer_id, referral_reward, 'referral_bonus', f'Бонус {format_usdt(referral_reward)} за приглашение пользователя {user_id}'))

            # Начисляем рефералу приветственный бонус
            cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (welcome_bonus, user_id))
            cursor.execute('''
                INSERT INTO transactions (user_id, amount, type, description)
                VALUES (?, ?, ?, ?)
            ''', (user_id, welcome_bonus, 'welcome_bonus', f'Приветственный бонус {format_usdt(welcome_bonus)} за регистрацию по реферальной ссылке'))

            conn.commit()

            # Отправляем уведомление рефереру
            try:
                cursor.execute("SELECT full_name FROM users WHERE user_id = ?", (user_id,))
                user_name = cursor.fetchone()[0] or f"User_{user_id}"

                bot.send_message(
                    referrer_id,
                    f"""═══════════════════════════
✨ <b>НОВЫЙ РЕФЕРАЛ</b> ✨
═══════════════════════════

<blockquote>🎉 <b>Поздравляем!</b></blockquote>

Приглашенный вами пользователь подписался на все обязательные каналы!

<b>👤 Информация о реферале:</b>
<blockquote>Пользователь: {sanitize_text(user_name)}</blockquote>

<b>✅ Начисление:</b>
<blockquote>Вам начислено: +{format_usdt(referral_reward)}</blockquote>

<blockquote>🎯 <b>Продолжайте приглашать друзей!</b></blockquote>""",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Не удалось отправить уведомление рефереру: {e}")

    conn.close()

# ========== НОВАЯ АДМИН КОМАНДА ДЛЯ УПРАВЛЕНИЯ НАСТРОЙКАМИ ==========
@bot.message_handler(func=lambda message: message.text == "⚙️ Настройки системы" and message.from_user.id in ADMIN_IDS)
def system_settings_command(message):
    """Управление настройками системы"""
    min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)
    referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
    welcome_bonus = get_setting('referral_welcome_bonus', REFERRAL_WELCOME_BONUS)

    settings_text = f"""═══════════════════════════
⚙️ <b>НАСТРОЙКИ СИСТЕМЫ</b> ⚙️
═══════════════════════════

<blockquote><b>Текущие настройки системы:</b></blockquote>

<b>💰 ВЫВОД:</b>
<blockquote>Минимальный вывод: <b>{format_usdt(min_withdrawal)}</b></blockquote>

<b>👥 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
<blockquote>Награда за реферала: <b>{format_usdt(referral_reward)}</b>
Приветственный бонус реферала: <b>{format_usdt(welcome_bonus)}</b></blockquote>

<blockquote>Выберите настройку для изменения:</blockquote>"""

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💰 Мин. вывод", callback_data="setting_min_withdrawal"),
        types.InlineKeyboardButton("🎁 Награда за реферала", callback_data="setting_referral_reward"),
        types.InlineKeyboardButton("👋 Бонус рефералу", callback_data="setting_welcome_bonus")
    )
    keyboard.add(
        types.InlineKeyboardButton("⬅️ Назад в админ-панель", callback_data="admin_back")
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
        f"""═══════════════════════════
✏️ <b>ИЗМЕНЕНИЕ НАСТРОЙКИ</b> ✏️
═══════════════════════════

<blockquote>Текущее значение <b>{setting_names.get(setting_name, setting_name)}</b>:</blockquote>

<blockquote><b>{format_usdt(current_value)}</b></blockquote>

<blockquote>Введите новое значение в {CURRENCY} (число):</blockquote>""",
        parse_mode='HTML'
    )

    bot.register_next_step_handler(msg, process_setting_update, setting_name, call.message.chat.id, call.message.message_id)

def process_setting_update(message, setting_name, chat_id, message_id):
    """Обработка обновления настройки"""
    try:
        new_value = float(message.text)

        if new_value <= 0:
            bot.send_message(message.chat.id, "❌ Значение должно быть больше 0!")
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
            f"""═══════════════════════════
✅ <b>НАСТРОЙКА ОБНОВЛЕНА</b> ✅
═══════════════════════════

<blockquote>✅ <b>Настройка успешно обновлена!</b></blockquote>

<b>📋 ИНФОРМАЦИЯ:</b>
<blockquote>Настройка: <b>{setting_names.get(setting_name, setting_name)}</b>
Новое значение: <b>{format_usdt(new_value)}</b></blockquote>

<blockquote>Изменение вступит в силу сразу.</blockquote>""",
            parse_mode='HTML',
            reply_markup=create_admin_keyboard()
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите корректное число!")

# ========== ОБНОВЛЕННАЯ КЛАВИАТУРА АДМИН ПАНЕЛИ ==========
def create_admin_keyboard():
    """Клавиатура админ панели с новыми настройками"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "📊 Статистика бота",
        "📢 Рассылка всем",
        "📺 Управление каналами",
        "💰 Управление выводами",
        "💵 Добавить баланс",
        "🎫 Управление чеками",
        "⚙️ Настройки системы",  # НОВАЯ КНОПКА
        "⬅️ Главное меню"
    ]
    keyboard.add(*buttons)
    return keyboard

# ========== ОБНОВЛЕННАЯ КОМАНДА ДОБАВЛЕНИЯ БАЛАНСА ==========
@bot.message_handler(func=lambda message: message.text == "💵 Добавить баланс" and message.from_user.id in ADMIN_IDS)
def add_balance_command(message):
    """Добавление баланса вручную"""
    msg = bot.send_message(
        message.chat.id,
        f"""═══════════════════════════
➕ <b>ДОБАВЛЕНИЕ БАЛАНСА</b> ➕
═══════════════════════════

<blockquote>Введите ID пользователя и количество {CURRENCY} через пробел:</blockquote>

<b>📋 ПРИМЕР:</b>
<blockquote><code>123456789 10.5</code></blockquote>""",
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
                f"""═══════════════════════════
✨ <b>БОНУС НАЧИСЛЕН</b> ✨
═══════════════════════════

<blockquote>🎁 <b>Вам начислен бонус!</b></blockquote>

<b>💰 ИНФОРМАЦИЯ:</b>
<blockquote>Администратор добавил вам <b>{format_usdt(amount)}</b>
Новый баланс: {format_usdt(new_balance)}</blockquote>

<blockquote>🎯 <b>Теперь вы можете выводить {CURRENCY}!</b></blockquote>""",
                parse_mode='HTML'
            )
        except:
            pass

        safe_name = sanitize_text(user[1])
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
✅ <b>БАЛАНС ДОБАВЛЕН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Баланс успешно добавлен!</b></blockquote>

<b>👤 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ:</b>
<blockquote>Пользователь: {safe_name} (@{user[0]})</blockquote>

<b>💰 ИНФОРМАЦИЯ О НАЧИСЛЕНИИ:</b>
<blockquote>Добавлено: +{format_usdt(amount)}
Новый баланс: {format_usdt(new_balance)}</blockquote>""",
            parse_mode='HTML'
        )

    except ValueError:
        bot.send_message(message.chat.id, "❌ Неверный формат данных!")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")

# ========== ОБНОВЛЕННЫЙ ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ==========
@bot.message_handler(func=lambda message: message.text == "⭐ Мой профиль")
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
        min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)
        referral_reward = get_setting('referral_reward', REFERRAL_REWARD)
        referral_link = generate_referral_link(message.from_user.id)
        username_display = f"@{user_info['username']}" if user_info['username'] else "не указан"

        profile_text = f"""═══════════════════════════
👤 <b>ВАШ ПРОФИЛЬ</b> 👤
═══════════════════════════

<blockquote>[ ] Ваш ID: {user_info['user_id']}
[ ] Ваш баланс: {format_usdt(user_info['balance'])}</blockquote>

<b>💰 ВЫВОД:</b>
<blockquote>Выведено: 4 {CURRENCY}</blockquote>

<b>📊 РЕФЕРАЛЬНАЯ СТАТИСТИКА:</b>
<blockquote>Число приглашённых рефералов: {user_info['referrals_count']}
Награда за каждого: {format_usdt(referral_reward)}</blockquote>

<b>🔗 РЕФЕРАЛЬНАЯ ССЫЛКА:</b>
<blockquote><code>{referral_link}</code></blockquote>

<blockquote>За каждого приглашенного друга ты получишь {format_usdt(referral_reward)}
После приглашения, средства будут автоматически зачислены на твой баланс.</blockquote>

<blockquote>🎯 <b>Приглашай друзей и поднимай легкие $$$ на свой баланс!</b></blockquote>"""

        bot.send_message(
            message.chat.id,
            profile_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(message.from_user.id)
        )

# ========== ОБНОВЛЕННАЯ КОМАНДА ПРИГЛАШЕНИЯ ==========
@bot.message_handler(func=lambda message: message.text == "🔗 Пригласить друзей")
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

        invite_text = f"""═══════════════════════════
🎁 <b>ПРИГЛАСИТЬ ДРУЗЕЙ</b> 🎁
═══════════════════════════

<blockquote>За каждого приглашенного друга ты получишь {format_usdt(referral_reward)}

После приглашения, средства будут автоматически зачислены на твой баланс.</blockquote>

<b>🔗 Ссылка для приглашения:</b>
<blockquote>{referral_link}</blockquote>

<b>📊 СТАТИСТИКА:</b>
<blockquote>Всего пригласил: {referrals_count} человек
Заработано: {format_usdt(earned)}</blockquote>

<blockquote>Приглашай друзей и поднимай легкие $$$ на свой баланс!</blockquote>"""

        bot.send_message(
            message.chat.id,
            invite_text,
            parse_mode='HTML',
            reply_markup=create_referral_keyboard(message.from_user.id)
        )

# ========== ОБНОВЛЕННАЯ КОМАНДА ВЫВОДА ==========
@bot.message_handler(func=lambda message: message.text == "💰 Вывод звезд")
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

    withdrawal_text = f"""═══════════════════════════
💰 <b>ВЫВОД {CURRENCY}</b> 💰
═══════════════════════════

<blockquote><b>💰 Вывод {CURRENCY}</b></blockquote>

<b>💰 ИНФОРМАЦИЯ О БАЛАНСЕ:</b>
<blockquote>Ваш текущий баланс: {format_usdt(user_info['balance'])}
Минимальная сумма вывода: {format_usdt(min_withdrawal)}
Время обработки: до 24 часов
Необходимо указать: Ваш username для связи</blockquote>

<blockquote>👇 <b>Выберите сумму для вывода:</b></blockquote>"""

    # Создаем клавиатуру вывода
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    # Стандартные суммы
    standard_amounts = [1, 2, 5, 10, 20, 50]

    # Показываем только те суммы, которые больше минимального вывода
    available_amounts = []
    for amount in standard_amounts:
        if amount >= min_withdrawal:
            available_amounts.append(amount)

    # Если доступные суммы есть, показываем их
    if available_amounts:
        buttons = []
        for amount in available_amounts:
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

    bot.send_message(
        message.chat.id,
        withdrawal_text,
        parse_mode='HTML',
        reply_markup=keyboard
    )

# ========== ОБНОВЛЕННЫЙ ОБРАБОТЧИК ВЫВОДА ==========
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
            f"""═══════════════════════════
💎 <b>ВЫВОД {CURRENCY}</b> 💎
═══════════════════════════

<blockquote><b>💎 Введите сумму для вывода</b></blockquote>

<b>📋 ТРЕБОВАНИЯ:</b>
<blockquote>Минимальная сумма вывода: {format_usdt(min_withdrawal)}
Введите сумму в {CURRENCY}:</blockquote>""",
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
            f"❌ Минимальная сумма вывода {format_usdt(min_withdrawal)}",
            show_alert=True
        )
        return

    user_data = {'amount': amount, 'user_id': user_id}

    msg = bot.send_message(
        call.message.chat.id,
        f"""═══════════════════════════
📝 <b>ПОДТВЕРЖДЕНИЕ ВЫВОДА</b> 📝
═══════════════════════════

<blockquote><b>📝 Подтверждение вывода</b></blockquote>

<b>💰 ДЕТАЛИ ВЫВОДА:</b>
<blockquote>Сумма вывода: {format_usdt(amount)}
Ваш баланс: {format_usdt(user_info['balance'])}
Баланс после вывода: {format_usdt(user_info['balance'] - amount)}</blockquote>

<blockquote>✍️ <b>Введите ваш @username для связи:</b></blockquote>""",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_withdrawal_username, user_data)
    bot.answer_callback_query(call.id)

# ========== ОБНОВЛЕННАЯ СТАТИСТИКА БОТА ==========
@bot.message_handler(func=lambda message: message.text == "📊 Статистика бота" and message.from_user.id in ADMIN_IDS)
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

        stats_text = f"""═══════════════════════════
📊 <b>СТАТИСТИКА БОТА</b> 📊
═══════════════════════════

<b>👥 ПОЛЬЗОВАТЕЛИ:</b>
<blockquote>Всего: <b>{total_users}</b> 👤
По реф.ссылкам: <b>{ref_users}</b> 🔗</blockquote>

<b>💰 {CURRENCY}:</b>
<blockquote>Всего на балансах: <b>{format_usdt(total_balance)}</b>
Средний баланс: <b>{format_usdt(total_balance/total_users if total_users > 0 else 0)}</b></blockquote>

<b>💸 ВЫВОДЫ:</b>
<blockquote>Одобрено: <b>{approved_withdrawals}</b> на {format_usdt(withdrawn_total)}
Ожидает: <b>{pending_withdrawals}</b> на {format_usdt(pending_total)}</blockquote>

<b>⚙️ НАСТРОЙКИ:</b>
<blockquote>Мин. вывод: <b>{format_usdt(min_withdrawal)}</b>
Награда за реферала: <b>{format_usdt(referral_reward)}</b>
Бонус рефералу: <b>{format_usdt(welcome_bonus)}</b></blockquote>

<b>📺 КАНАЛЫ И ССЫЛКИ:</b>
<blockquote>Всего элементов: <b>{len(REQUIRED_CHANNELS) + len(SIMPLE_LINKS)}</b>
Обязательных каналов: <b>{len(REQUIRED_CHANNELS)}</b>
Простых ссылок: <b>{len(SIMPLE_LINKS)}</b></blockquote>

<b>🎫 ЧЕКИ:</b>
<blockquote>Всего чеков: <b>{total_checks}</b>
Активаций: <b>{total_check_activations}</b>
Выдано через чеки: <b>{format_usdt(total_check_amount)}</b></blockquote>"""

        bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")
    finally:
        conn.close()

# ========== ОБНОВЛЕННОЕ ГЛАВНОЕ МЕНЮ ==========
def create_main_menu():
    """Главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "👤 Мой профиль",
        "🔗 Пригласить друзей",
        "💰 Вывод USDT",
        "📊 Моя статистика",
        "🏆 Топ рефереров",
        "🎫 Активировать чек",
        "📋 Мои заявки"
    ]
    keyboard.add(*buttons)
    return keyboard

# ========== ОБНОВЛЕННОЕ ПРИВЕТСТВЕННОЕ СООБЩЕНИЕ ==========
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
                        f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ <b>Чек активирован успешно!</b> 🎉</blockquote>

<b>💰 НАЧИСЛЕНИЕ:</b>
<blockquote>{result_message}
Ваш баланс: {format_usdt(user_info['balance'])}</blockquote>

<blockquote>🎯 <b>Теперь вы можете выводить {CURRENCY}!</b></blockquote>""",
                        parse_mode='HTML'
                    )
                else:
                    bot.send_message(
                        message.chat.id,
                        f"""═══════════════════════════
✅ <b>ЧЕК АКТИВИРОВАН</b> ✅
═══════════════════════════

<blockquote>✅ {result_message}</blockquote>""",
                        parse_mode='HTML'
                    )
            else:
                bot.send_message(
                    message.chat.id,
                    f"""═══════════════════════════
❌ <b>ОШИБКА АКТИВАЦИИ</b> ❌
═══════════════════════════

<blockquote>❌ <b>Не удалось активировать чек:</b></blockquote>

{result_message}""",
                    parse_mode='HTML'
                )

            # Показываем главное меню
            bot.send_message(
                message.chat.id,
                """═══════════════════════════
🏠 <b>ГЛАВНОЕ МЕНЮ</b> 🏠
═══════════════════════════

<blockquote>🏠 <b>Добро пожаловать!</b></blockquote>

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

                    welcome_text = f"""═══════════════════════════
✨ <b>ДОБРО ПОЖАЛОВАТЬ</b> ✨
═══════════════════════════

<blockquote>✨ <b>Добро пожаловать, {full_name}!</b></blockquote>

<blockquote>✅ <b>Вы уже подписаны на все обязательные каналы!</b></blockquote>

<b>🎁 РЕФЕРАЛЬНАЯ СИСТЕМА:</b>
<blockquote>За каждого приглашенного друга ты получишь {format_usdt(get_setting('referral_reward', REFERRAL_REWARD))}
После приглашения, средства будут автоматически зачислены на твой баланс.</blockquote>

<b>👇 НАВИГАЦИЯ:</b>
<blockquote>Используйте кнопки ниже для навигации:</blockquote>"""

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

    welcome_text = f"""═══════════════════════════
✨ <b>ДОБРО ПОЖАЛОВАТЬ</b> ✨
═══════════════════════════

<blockquote>✨ <b>Добро пожаловать, {full_name}!</b></blockquote>

<blockquote>За каждого приглашенного друга ты получишь {format_usdt(referral_reward)}</blockquote>

<blockquote>После приглашения, средства будут автоматически зачислены на твой баланс.</blockquote>

<blockquote>Приглашай друзей и поднимай легкие $$$ на свой баланс!</blockquote>

<b>👇 НАВИГАЦИЯ:</b>
<blockquote>Используйте кнопки ниже для навигации:</blockquote>"""

    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

# ========== ОБНОВЛЕННАЯ СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ ==========
@bot.message_handler(func=lambda message: message.text == "📊 Моя статистика")
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
        referrals_count = user_info['referrals_count']
        earned_from_refs = referrals_count * referral_reward
        min_withdrawal = get_setting('min_withdrawal', MIN_WITHDRAWAL)

        stats_text = f"""═══════════════════════════
📊 <b>ВАША СТАТИСТИКА</b> 📊
═══════════════════════════

<b>💰 ФИНАНСОВАЯ ИНФОРМАЦИЯ:</b>
<blockquote>Ваш баланс: {format_usdt(user_info['balance'])}
Заработано с рефералов: {format_usdt(earned_from_refs)}
Всего заработано: {format_usdt(user_info['balance'] + earned_from_refs)}</blockquote>

<b>👥 РЕФЕРАЛЬНАЯ СТАТИСТИКА:</b>
<blockquote>Приглашено друзей: {referrals_count}
Награда за реферала: {format_usdt(referral_reward)}
До следующей награды: 1 друг</blockquote>

<b>💸 ВЫВОД:</b>
<blockquote>Минимальный вывод: {format_usdt(min_withdrawal)}
Доступно для вывода: {format_usdt(user_info['balance'])}</blockquote>

<blockquote>🎯 <b>Приглашайте друзей и зарабатывайте {format_usdt(referral_reward)} за каждого!</b></blockquote>"""

        bot.send_message(
            message.chat.id,
            stats_text,
            parse_mode='HTML'
        )

# ========== ОБНОВЛЕННЫЙ ТОП РЕФЕРЕРОВ ==========
def get_top_referrers(limit=10):
    """Получение топ пользователей ПО КОЛИЧЕСТВУ РЕФЕРАЛОВ В USDT"""
    conn = sqlite3.connect('referral_bot.db', check_same_thread=False)
    cursor = conn.cursor()

    # ИСПРАВЛЕННЫЙ ЗАПРОС - получаем всех пользователей с количеством рефералов
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

@bot.message_handler(func=lambda message: message.text == "🏆 Топ рефереров")
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
        top_text = """═══════════════════════════
🏆 <b>ТОП 10 РЕФЕРЕРОВ</b> 🏆
═══════════════════════════

<blockquote><b>🏆 Топ 10 рефереров (по количеству приглашенных друзей)</b></blockquote>

<blockquote>Награда за каждого реферала: {format_usdt(referral_reward)}</blockquote>\n\n""".format(format_usdt(referral_reward))

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
            top_text += f'<b>👥 Рефералов:</b> {referrals} | <b>💰 Заработано:</b> {format_usdt(earned)}\n'
            top_text += f'<b>💵 Баланс:</b> {format_usdt(balance)}\n\n'

        top_text += '<blockquote>🎯 <b>Приглашайте друзей и попадите в топ!</b></blockquote>'

        bot.send_message(
            message.chat.id,
            top_text,
            parse_mode='HTML'
        )
    else:
        bot.send_message(
            message.chat.id,
            f"""═══════════════════════════
🏆 <b>ТОП РЕФЕРЕРОВ</b> 🏆
═══════════════════════════

<blockquote>🏆 <b>Топ рефереров</b></blockquote>

<blockquote>Пока никто не пригласил друзей. Будьте первым!</blockquote>

<blockquote>Награда за каждого реферала: {format_usdt(referral_reward)}</blockquote>""",
            parse_mode='HTML'
        )

# ========== ИНИЦИАЛИЗАЦИЯ И ЗАПУСК ==========
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 USDT РЕФЕРАЛЬНЫЙ БОТ (ВЕБХУКИ)")
    print("=" * 50)

    init_db()
    init_checks_db()
    load_channels_from_db()

    try:
        bot_info = bot.get_me()
        print(f"👤 Имя бота: @{bot_info.username}")
        print(f"🌐 Вебхук URL: {WEBHOOK_URL}{WEBHOOK_PATH}")
        print(f"💵 Валюта: {CURRENCY}")
        print(f"💰 Мин. вывод: {get_setting('min_withdrawal', MIN_WITHDRAWAL)} {CURRENCY}")
        print(f"🎁 Награда за реферала: {get_setting('referral_reward', REFERRAL_REWARD)} {CURRENCY}")
        print(f"👋 Бонус рефералу: {get_setting('referral_welcome_bonus', REFERRAL_WELCOME_BONUS)} {CURRENCY}")
        print(f"📺 Обязательных каналов: {len(REQUIRED_CHANNELS)}")
        print(f"🔗 Простых ссылок: {len(SIMPLE_LINKS)}")
        print(f"👑 Админов: {len(ADMIN_IDS)}")

        # Устанавливаем вебхук
        set_webhook()

    except Exception as e:
        print(f"⚠️ Не удалось получить информацию о боте: {e}")

    print("=" * 50)

    # Запускаем Flask сервер
    app.run(host='0.0.0.0', port=PORT)

import telebot
from telebot import types
import threading
import time
import json
import os
import sqlite3
from datetime import datetime, timedelta
from collections import OrderedDict

# ========== ОТКЛЮЧЕНИЕ ВСЕХ ПРОКСИ ==========
os.environ['NO_PROXY'] = '*'
for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ[proxy_var] = ''

import requests
from telebot import apihelper
session = requests.Session()
session.trust_env = False
apihelper.session = session
apihelper.proxy = None

# ========== НАСТРОЙКИ ==========
TOKEN = '8400110033:AAH9NyaOW4us1hhiLGVIr9EobgnsRaowWLo'
ADMIN_CHAT_ID = 8118184388

# Инициализация бота
bot = telebot.TeleBot(
    TOKEN,
    skip_pending=True,
    num_threads=5
)

# Словарь для хранения связи username -> user_id
username_to_id = {}

# ========== ИМПОРТ СУЩЕСТВУЮЩИХ МОДУЛЕЙ ==========
try:
    # Импортируем игры из games.py
    from games import BettingGame
    game = BettingGame(bot)
    print("✅ Модуль игр загружен из games.py")
except Exception as e:
    print(f"❌ Ошибка загрузки модуля игр: {e}")
    import sys
    sys.exit(1)

try:
    # Импортируем реферальную систему из referrals.py
    from referrals import ReferralSystem
    referral_system = ReferralSystem(bot, game)
    game.set_referral_system(referral_system)
    print("✅ Модуль рефералов загружен из referrals.py")
except Exception as e:
    print(f"❌ Ошибка загрузки модуля рефералов: {e}")
    referral_system = None

# ========== КЛАСС ДЛЯ ВЕБ-ИНТЕРФЕЙСА ==========
class WebInvoiceSystem:
    """Система обработки счетов из веб-интерфейса"""
    
    def __init__(self, bot, game_system):
        self.bot = bot
        self.game_system = game_system
        self.pending_invoices = OrderedDict()
        self.paid_invoices = OrderedDict()
        self.expired_invoices = OrderedDict()
        self.invoice_counter = 0
        self.secret_key = "lightwin_web_secret_2024"
        
        # Создаем базу данных
        self.init_database()
        
        # Загружаем старые счета
        self.load_invoices()
        
        # Запускаем фоновую проверку
        threading.Thread(target=self._check_invoices_loop, daemon=True).start()
        
        print(f"✅ WebInvoiceSystem запущен. Загружено {len(self.pending_invoices)} счетов")
    
    def init_database(self):
        """Инициализация базы данных"""
        self.conn = sqlite3.connect('web_invoices.db', check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS web_invoices (
                invoice_id TEXT PRIMARY KEY,
                web_user_id TEXT,
                amount REAL,
                game_type TEXT,
                game_name TEXT,
                outcome_name TEXT,
                status TEXT,
                payment_link TEXT,
                created_at TIMESTAMP,
                expires_at TIMESTAMP,
                paid_at TIMESTAMP,
                telegram_user_id INTEGER,
                telegram_username TEXT
            )
        ''')
        
        self.conn.commit()
    
    def load_invoices(self):
        """Загрузка счетов из базы данных"""
        try:
            self.cursor.execute("SELECT * FROM web_invoices WHERE status = 'pending'")
            rows = self.cursor.fetchall()
            
            for row in rows:
                invoice_data = {
                    'invoice_id': row[0],
                    'web_user_id': row[1],
                    'amount': row[2],
                    'game_type': row[3],
                    'game_name': row[4],
                    'outcome_name': row[5],
                    'status': row[6],
                    'payment_link': row[7],
                    'created_at': datetime.fromisoformat(row[8]),
                    'expires_at': datetime.fromisoformat(row[9]),
                    'paid_at': row[10] and datetime.fromisoformat(row[10]),
                    'telegram_user_id': row[11],
                    'telegram_username': row[12]
                }
                
                if invoice_data['status'] == 'pending':
                    self.pending_invoices[invoice_data['invoice_id']] = invoice_data
            
            print(f"📄 Загружено {len(self.pending_invoices)} pending счетов")
            
        except Exception as e:
            print(f"❌ Ошибка загрузки счетов: {e}")
    
    def save_invoice(self, invoice_data):
        """Сохраняет счет в базу данных"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO web_invoices 
                (invoice_id, web_user_id, amount, game_type, game_name, outcome_name, 
                 status, payment_link, created_at, expires_at, paid_at, telegram_user_id, telegram_username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                invoice_data['invoice_id'],
                invoice_data['web_user_id'],
                invoice_data['amount'],
                invoice_data['game_type'],
                invoice_data['game_name'],
                invoice_data['outcome_name'],
                invoice_data['status'],
                invoice_data.get('payment_link', ''),
                invoice_data['created_at'].isoformat(),
                invoice_data['expires_at'].isoformat(),
                invoice_data.get('paid_at', None) and invoice_data['paid_at'].isoformat(),
                invoice_data.get('telegram_user_id'),
                invoice_data.get('telegram_username')
            ))
            self.conn.commit()
        except Exception as e:
            print(f"❌ Ошибка сохранения счета: {e}")
    
    def create_invoice(self, web_user_id, amount, game_type, game_name, outcome_name):
        """Создает новый счет для веб-интерфейса"""
        try:
            # Генерируем уникальный ID счета
            timestamp = int(time.time())
            self.invoice_counter += 1
            invoice_id = f"WEB_{timestamp}_{self.invoice_counter}"
            
            # Создаем данные счета
            invoice_data = {
                'invoice_id': invoice_id,
                'web_user_id': web_user_id,
                'amount': float(amount),
                'game_type': game_type,
                'game_name': game_name,
                'outcome_name': outcome_name,
                'status': 'pending',
                'payment_link': f"https://t.me/light_winbot?start=webpay_{invoice_id}",
                'created_at': datetime.now(),
                'expires_at': datetime.now() + timedelta(minutes=3),
                'paid_at': None,
                'telegram_user_id': None,
                'telegram_username': None
            }
            
            # Сохраняем в pending
            self.pending_invoices[invoice_id] = invoice_data
            
            # Сохраняем в базу
            self.save_invoice(invoice_data)
            
            print(f"📄 Создан счет {invoice_id}: {amount}$ на {game_name} - {outcome_name}")
            print(f"  Веб-пользователь: {web_user_id}")
            print(f"  Ссылка: {invoice_data['payment_link']}")
            
            return invoice_data
            
        except Exception as e:
            print(f"❌ Ошибка создания счета: {e}")
            return None
    
    def process_web_payment(self, invoice_id, telegram_user_id, telegram_username):
        """Обрабатывает оплату счета через веб-интерфейс"""
        if invoice_id not in self.pending_invoices:
            if invoice_id in self.paid_invoices:
                print(f"⚠️ Счет {invoice_id} уже оплачен")
                return "already_paid"
            print(f"❌ Счет {invoice_id} не найден")
            return "not_found"
        
        invoice = self.pending_invoices[invoice_id]
        
        if invoice['status'] != 'pending':
            print(f"⚠️ Счет {invoice_id} уже обработан (статус: {invoice['status']})")
            return "already_processed"
        
        # Проверяем не просрочен ли счет
        if datetime.now() > invoice['expires_at']:
            invoice['status'] = 'expired'
            self.expired_invoices[invoice_id] = invoice
            del self.pending_invoices[invoice_id]
            self.save_invoice(invoice)
            print(f"⌛ Счет {invoice_id} просрочен")
            return "expired"
        
        # Помечаем как оплаченный
        invoice['status'] = 'paid'
        invoice['paid_at'] = datetime.now()
        invoice['telegram_user_id'] = telegram_user_id
        invoice['telegram_username'] = telegram_username
        
        # Перемещаем в paid
        self.paid_invoices[invoice_id] = invoice
        del self.pending_invoices[invoice_id]
        
        # Обновляем в базе
        self.save_invoice(invoice)
        
        # Добавляем баланс пользователю в Telegram
        try:
            self.game_system.add_balance(telegram_user_id, invoice['amount'])
            print(f"✅ Счет {invoice_id} оплачен! Начислено {invoice['amount']} USDT пользователю {telegram_user_id}")
        except Exception as e:
            print(f"❌ Ошибка начисления баланса: {e}")
        
        # Создаем игру в канале используя существующую логику из games.py
        try:
            # Импортируем конфигурацию игр из games.py
            from games import DICE_BET_TYPES, BASKETBALL_BET_TYPES, FOOTBALL_BET_TYPES, DART_BET_TYPES, BOWLING_BET_TYPES
            
            # Объединяем все типы ставок
            all_bet_types = {**DICE_BET_TYPES, **BASKETBALL_BET_TYPES, **FOOTBALL_BET_TYPES, **DART_BET_TYPES, **BOWLING_BET_TYPES}
            
            # Получаем конфигурацию ставки
            bet_config = all_bet_types.get(invoice['game_type'], {
                'name': 'Игра',
                'multiplier': 1.8,
                'values': []
            })
            
            # Создаем данные для игры в формате, который понимает games.py
            game_data = {
                'user_id': telegram_user_id,
                'nickname': telegram_username or f"Пользователь_{telegram_user_id}",
                'amount': invoice['amount'],
                'bet_type': invoice['game_type'],
                'bet_config': bet_config,
                'from_bot': True,
                'invoice_id': invoice_id
            }
            
            # Добавляем игру в очередь (используем существующую очередь из games.py)
            self.game_system.game_queue.add_game(game_data)
            print(f"🎮 Игра добавлена в очередь для счета {invoice_id}")
            
        except Exception as e:
            print(f"❌ Ошибка создания игры: {e}")
        
        # Уведомляем пользователя
        try:
            self.bot.send_message(
                telegram_user_id,
                f"✅ Счет оплачен!\n"
                f"💰 {invoice['amount']:.2f} USDT добавлено на баланс.\n"
                f"🎮 Игра '{invoice['game_name']} - {invoice['outcome_name']}' создается в канале.\n"
                f"📊 Ваш баланс: {self.game_system.get_balance(telegram_user_id):.2f} USDT",
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"⚠️ Не удалось отправить уведомление пользователю {telegram_user_id}: {e}")
        
        return "success"
    
    def get_invoice_status(self, invoice_id):
        """Возвращает статус счета"""
        if invoice_id in self.pending_invoices:
            invoice = self.pending_invoices[invoice_id]
        elif invoice_id in self.paid_invoices:
            invoice = self.paid_invoices[invoice_id]
        elif invoice_id in self.expired_invoices:
            invoice = self.expired_invoices[invoice_id]
        else:
            return None
        
        return {
            'invoice_id': invoice_id,
            'status': invoice['status'],
            'amount': invoice['amount'],
            'game_name': invoice['game_name'],
            'outcome_name': invoice['outcome_name'],
            'created_at': invoice['created_at'].isoformat(),
            'expires_at': invoice['expires_at'].isoformat(),
            'paid_at': invoice.get('paid_at', None) and invoice['paid_at'].isoformat(),
            'payment_link': invoice['payment_link']
        }
    
    def _check_invoices_loop(self):
        """Фоновая проверка счетов"""
        while True:
            try:
                self._check_expired_invoices()
            except Exception as e:
                print(f"❌ Ошибка в фоновой проверке счетов: {e}")
            
            time.sleep(5)
    
    def _check_expired_invoices(self):
        """Проверяет просроченные счета"""
        now = datetime.now()
        expired_ids = []
        
        for invoice_id, invoice in list(self.pending_invoices.items()):
            if now > invoice['expires_at']:
                invoice['status'] = 'expired'
                self.expired_invoices[invoice_id] = invoice
                del self.pending_invoices[invoice_id]
                self.save_invoice(invoice)
                expired_ids.append(invoice_id)
        
        if expired_ids:
            print(f"⌛ Помечено как просроченные: {len(expired_ids)} счетов")
    
    def get_stats(self):
        """Возвращает статистику по счетам"""
        return {
            'pending': len(self.pending_invoices),
            'paid': len(self.paid_invoices),
            'expired': len(self.expired_invoices),
            'total': len(self.pending_invoices) + len(self.paid_invoices) + len(self.expired_invoices)
        }

# Инициализация системы счетов для веб-интерфейса
web_invoice_system = WebInvoiceSystem(bot, game)

# ========== ВЕБ-СЕРВЕР ДЛЯ ОБРАБОТКИ ЗАПРОСОВ ==========
from flask import Flask, request, jsonify
from flask_cors import CORS
import threading as flask_threading

# Создаем Flask приложение в отдельном потоке
web_app = Flask(__name__)
CORS(web_app)  # Разрешаем CORS для веб-интерфейса

# Маппинг веб-игр в систему бота (используя конфигурацию из games.py)
WEB_GAME_MAPPING = {
    'dice': {
        'Нечет': 'куб_нечет',
        'Чет': 'куб_чет',
        'Больше': 'куб_бол',
        'Меньше': 'куб_мал',
        '2Больше': 'куб_2больше',
        '2Меньше': 'куб_2меньше'
    },
    'football': {
        'Гол': 'футбол_гол',
        'Мимо': 'футбол_мимо'
    },
    'basketball': {
        'Гол': 'баскет_гол',
        'Мимо': 'баскет_мимо',
        'Трехочковый': 'баскет_3очка'
    },
    'darts': {
        'Белое': 'дартс_белое',
        'Красное': 'дартс_красное',
        'Центр': 'дартс_центр',
        'Мимо': 'дартс_мимо'
    },
    'bowling': {
        'Поражение': 'боулинг_поражение',
        'Победа': 'боулинг_победа',
        'Страйк': 'боулинг_страйк'
    }
}

GAME_NAMES = {
    'dice': 'Кубик',
    'football': 'Футбол',
    'basketball': 'Баскетбол',
    'darts': 'Дартс',
    'bowling': 'Боулинг'
}

@web_app.route('/')
def index():
    return "LightWin Web API Server", 200

@web_app.route('/api/create_invoice', methods=['POST'])
def api_create_invoice():
    """API для создания счета из веб-интерфейса"""
    try:
        data = request.json
        
        # Проверяем обязательные поля
        required_fields = ['game', 'outcome', 'amount', 'userId']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
        
        game_type = data['game']
        outcome = data['outcome']
        amount = float(data['amount'])
        user_id = data['userId']
        
        # Проверяем минимальную сумму
        if amount < 0.15:
            return jsonify({'error': f'Минимальная сумма ставки: 0.15 USDT'}), 400
        
        # Проверяем существование игры и исхода
        if game_type not in WEB_GAME_MAPPING:
            return jsonify({'error': 'Неверная игра'}), 400
        
        if outcome not in WEB_GAME_MAPPING[game_type]:
            return jsonify({'error': 'Неверный исход'}), 400
        
        # Получаем тип игры для бота
        bot_game_type = WEB_GAME_MAPPING[game_type][outcome]
        game_name = GAME_NAMES.get(game_type, game_type)
        
        # Создаем счет
        invoice_data = web_invoice_system.create_invoice(
            web_user_id=user_id,
            amount=amount,
            game_type=bot_game_type,
            game_name=game_name,
            outcome_name=outcome
        )
        
        if not invoice_data:
            return jsonify({'error': 'Ошибка создания счета'}), 500
        
        return jsonify({
            'success': True,
            'invoice_id': invoice_data['invoice_id'],
            'payment_link': invoice_data['payment_link'],
            'message': 'Счет успешно создан'
        })
        
    except Exception as e:
        print(f"❌ Ошибка в API create_invoice: {e}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@web_app.route('/api/invoice_status/<invoice_id>', methods=['GET'])
def api_invoice_status(invoice_id):
    """API для проверки статуса счета"""
    invoice_status = web_invoice_system.get_invoice_status(invoice_id)
    
    if not invoice_status:
        return jsonify({'error': 'Счет не найден'}), 404
    
    return jsonify(invoice_status)

@web_app.route('/api/stats', methods=['GET'])
def api_stats():
    """API для получения статистики"""
    stats = {
        'invoices': web_invoice_system.get_stats(),
        'users': len(game.user_balances),
        'total_balance': sum(game.user_balances.values())
    }
    return jsonify(stats)

def run_web_server():
    """Запускает веб-сервер"""
    port = int(os.environ.get('PORT', 5000))  # Render сам дает порт
    print(f"🌐 Запуск веб-сервера на порту {port}...")
    web_app.run(host='0.0.0.0', port=port, debug=False, threaded=True)

# Запускаем веб-сервер в отдельном потоке
flask_thread = flask_threading.Thread(target=run_web_server, daemon=True)
flask_thread.start()

# ========== ФУНКЦИИ ОБРАБОТКИ ПОЛЬЗОВАТЕЛЕЙ ==========
def update_username_mapping(user_id, username):
    """Обновляет связь между username и user_id"""
    if username:
        username_to_id[username] = user_id

def save_user_info(user_id, username, first_name):
    """Сохраняет информацию о пользователе"""
    if referral_system:
        referral_system.save_user_info(user_id, username, first_name)
    
    if username:
        username_to_id[username] = user_id
    
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

# Загружаем сохраненные маппинги
load_user_mappings()

# ========== ОБРАБОТЧИКИ КОМАНД ТЕЛЕГРАМ БОТА ==========
@bot.message_handler(commands=['start', 'menu'])
def send_welcome(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    # Проверяем параметры команды /start
    if len(message.text.split()) > 1:
        param = message.text.split()[1]
        
        # Обработка реферальной ссылки
        if param.startswith('ref'):
            try:
                referrer_id = int(param[3:])
                if referral_system:
                    referral_system.register_referral(
                        referee_id=message.from_user.id,
                        referrer_id=referrer_id,
                        referee_username=message.from_user.username,
                        referee_first_name=message.from_user.first_name
                    )
            except:
                pass
        
        # Обработка оплаты веб-счета
        elif param.startswith('webpay_'):
            invoice_id = param[7:]  # Убираем 'webpay_'
            result = web_invoice_system.process_web_payment(
                invoice_id=invoice_id,
                telegram_user_id=message.from_user.id,
                telegram_username=message.from_user.username
            )
            
            if result == "success":
                bot.send_message(
                    message.chat.id,
                    "✅ Оплата успешно обработана! Счет оплачен и игра создана.",
                    parse_mode='HTML'
                )
            elif result == "already_paid":
                bot.send_message(
                    message.chat.id,
                    "ℹ️ Этот счет уже был оплачен ранее.",
                    parse_mode='HTML'
                )
            elif result == "expired":
                bot.send_message(
                    message.chat.id,
                    "❌ Счет просрочен. Пожалуйста, создайте новый счет.",
                    parse_mode='HTML'
                )
            else:
                bot.send_message(
                    message.chat.id,
                    "❌ Счет не найден или произошла ошибка.",
                    parse_mode='HTML'
                )
            
            # Показываем главное меню
            show_main_menu(message)
            return
    
    # Показываем главное меню
    show_main_menu(message)

def show_main_menu(message):
    """Показывает главное меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("👛Баланс")
    btn2 = types.KeyboardButton("🤝 Партнеры")
    btn3 = types.KeyboardButton("🎮 Играть")
    markup.add(btn1, btn2, btn3)
    
    welcome_text = """<b>🏠 Главное меню</b>
<blockquote>Выберите раздел:</blockquote>"""
    bot.send_message(message.chat.id, welcome_text,
                     parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "👛Баланс")
def show_profile(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    user_id = message.from_user.id
    balance = game.get_balance(user_id)
    profile_text = f"""
<blockquote><b>👛Баланс</b></blockquote>
<blockquote><b><code>💲{balance:.2f}</code> <code>💎0,00</code></b></blockquote>"""
    
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
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    if referral_system:
        referral_system.show_menu(message)

@bot.message_handler(func=lambda message: message.text == "🎮 Играть")
def show_games(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    game.show_games_menu(message)

# ========== АДМИН КОМАНДЫ ==========
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
    
    # Статистика веб-счетов
    web_stats = web_invoice_system.get_stats()
    
    stats_text = f"""
<b>📊 Статистика бота</b>
👥 Всего пользователей: <b>{total_users}</b>
💰 Общий баланс: <b>{total_balance:.2f} USDT</b>
📝 Известных username: <b>{len(username_to_id)}</b>

<b>🌐 Веб-интерфейс:</b>
├ Ожидают оплаты: <b>{web_stats['pending']} счетов</b>
├ Оплачено: <b>{web_stats['paid']} счетов</b>
└ Просрочено: <b>{web_stats['expired']} счетов</b>
    """
    
    if referral_system:
        ref_stats = referral_system.get_stats(ADMIN_CHAT_ID)
        stats_text += f"""
<b>👥 Реферальная система:</b>
├ Приглашено: <b>{ref_stats['total_refs']} чел.</b>
├ Доступно: <b>{ref_stats['available']:.2f} USDT</b>
└ Выведено: <b>{ref_stats['withdrawn']:.2f} USDT</b>"""
    
    bot.reply_to(message, stats_text, parse_mode='HTML')

# ========== CALLBACK ОБРАБОТЧИКИ ==========
@bot.callback_query_handler(func=lambda call: call.data == "deposit")
def handle_deposit(call):
    update_username_mapping(call.from_user.id, call.from_user.username)
    save_user_info(call.from_user.id, call.from_user.username, call.from_user.first_name)
    bot.answer_callback_query(call.id, "📥 Пополнение в разработке", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "withdraw")
def handle_withdraw(call):
    update_username_mapping(call.from_user.id, call.from_user.username)
    save_user_info(call.from_user.id, call.from_user.username, call.from_user.first_name)
    bot.answer_callback_query(call.id, "📤 Вывод в разработке", show_alert=True)

def handle_game_callbacks(call):
    """Обработчик callback-кнопок игр - использует функции из games.py"""
    if call.data == "game_dice":
        game.show_dice_menu(call)
    elif call.data == "bet_dice_exact":
        game.show_exact_numbers(call)
    elif call.data.startswith("bet_dice_"):
        bet_type = call.data.replace("bet_dice_", "")
        # Импортируем BET_TYPES из games.py
        from games import BET_TYPES
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_basketball":
        game.show_basketball_menu(call)
    elif call.data.startswith("bet_basketball_"):
        bet_type = call.data.replace("bet_basketball_", "")
        from games import BET_TYPES
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_football":
        game.show_football_menu(call)
    elif call.data.startswith("bet_football_"):
        bet_type = call.data.replace("bet_football_", "")
        from games import BET_TYPES
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_darts":
        game.show_darts_menu(call)
    elif call.data.startswith("bet_darts_"):
        bet_type = call.data.replace("bet_darts_", "")
        from games import BET_TYPES
        if bet_type in BET_TYPES:
            game.request_amount(call, bet_type)
    elif call.data == "game_bowling":
        game.show_bowling_menu(call)
    elif call.data.startswith("bet_bowling_"):
        bet_type = call.data.replace("bet_bowling_", "")
        from games import BET_TYPES
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

def handle_bet_amount_input(message):
    """Обработчик ввода суммы ставки - использует функцию из games.py"""
    return game.process_bet_amount(message)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_text(message):
    update_username_mapping(message.from_user.id, message.from_user.username)
    save_user_info(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    # Проверяем вывод реферальных средств
    if referral_system and referral_system.process_withdraw(message):
        return
    
    # Проверяем ставку
    if handle_bet_amount_input(message):
        return

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    update_username_mapping(call.from_user.id, call.from_user.username)
    save_user_info(call.from_user.id, call.from_user.username, call.from_user.first_name)
    
    if call.data == "menu":
        send_welcome(call.message)
    
    # Реферальные callback-ы
    elif call.data in ["ref_menu", "ref_list", "ref_withdraw", "ref_share"] and referral_system:
        handle_referral_callbacks(call)
    
    # Игровые callback-ы
    else:
        handle_game_callbacks(call)

# ========== ЗАПУСК БОТА ==========
if __name__ == "__main__":
    print("🤖 LightWin Бот запущен...")
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print("🌐 Веб-сервер запущен на порту 5000")
    print("🎮 Игровая логика загружена из games.py")
    print("👥 Реферальная система загружена из referrals.py")
    print("💡 Доступные команды:")
    print("/add username сумма - пополнить баланс")
    print("/addid user_id сумма - пополнить баланс по ID")
    print("/find username/id - найти пользователя")
    print("/stats - статистика бота")
    print("🎯 Игры: 🎲 Кубик, 🏀 Баскетбол, ⚽ Футбол, 🎯 Дартс, 🎳 Боулинг")
    print("🌐 Веб-интерфейс: API доступен на http://localhost:5000/api")
    
    restart_count = 0
    max_restarts = 10
    
    while restart_count < max_restarts:
        try:
            print(f"🔄 Запуск бота (попытка {restart_count + 1}/{max_restarts})...")
            
            try:
                bot.remove_webhook()
                time.sleep(0.5)
            except:
                pass
            
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
            
            if restart_count >= max_restarts:
                print("🚨 Достигнуто максимальное количество перезапусков")
                break
                
            time.sleep(5)

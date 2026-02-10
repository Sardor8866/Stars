from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import requests
import json
import time
import threading
from datetime import datetime, timedelta
import hashlib
import hmac

app = Flask(__name__)
CORS(app)

# Конфигурация
TELEGRAM_BOT_TOKEN = "ВАШ_ТЕЛЕГРАМ_БОТ_ТОКЕН"
TELEGRAM_BOT_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
WEBAPP_URL = "https://ВАШ_ДОМЕН.com"  # URL вашего веб-интерфейса
SECRET_KEY = "ВАШ_СЕКРЕТНЫЙ_КЛЮЧ"

# Хранилище счетов
pending_invoices = {}
invoice_counter = 0

# Соответствие между веб-интерфейсом и системой бота
GAME_MAPPING = {
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

def create_invoice_id():
    """Создает уникальный ID счета"""
    global invoice_counter
    invoice_counter += 1
    timestamp = int(time.time())
    return f"INV_{timestamp}_{invoice_counter}"

def generate_signature(data):
    """Генерирует HMAC подпись для данных"""
    message = json.dumps(data, sort_keys=True)
    return hmac.new(
        SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

@app.route('/')
def index():
    """Главная страница - отдаем HTML"""
    return render_template('index.html')

@app.route('/api/create_invoice', methods=['POST'])
def create_invoice():
    """Создание счета для ставки"""
    try:
        data = request.json
        
        # Проверяем данные
        required_fields = ['game', 'outcome', 'amount', 'userId']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Missing field: {field}'}), 400
        
        game = data['game']
        outcome = data['outcome']
        amount = float(data['amount'])
        user_id = data.get('userId', 'web_user')
        
        # Проверяем минимальную сумму
        MIN_BET = 0.15
        if amount < MIN_BET:
            return jsonify({'error': f'Минимальная сумма ставки: {MIN_BET} USDT'}), 400
        
        # Проверяем существование игры и исхода
        if game not in GAME_MAPPING:
            return jsonify({'error': 'Неверная игра'}), 400
        
        if outcome not in GAME_MAPPING[game]:
            return jsonify({'error': 'Неверный исход'}), 400
        
        # Создаем уникальный ID счета
        invoice_id = create_invoice_id()
        
        # Преобразуем игру и исход в формат бота
        bot_game_type = GAME_MAPPING[game][outcome]
        
        # Создаем данные для счета
        invoice_data = {
            'invoice_id': invoice_id,
            'user_id': user_id,
            'game': game,
            'outcome': outcome,
            'bot_game_type': bot_game_type,
            'amount': amount,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(minutes=3)).isoformat()
        }
        
        # Сохраняем счет
        pending_invoices[invoice_id] = invoice_data
        
        # Генерируем ссылку на оплату в Telegram боте
        # Формат: https://t.me/бот?start=INVOICE_ID
        payment_link = f"https://t.me/light_winbot?start={invoice_id}"
        
        # Здесь вы можете отправить запрос в свой Telegram бот для создания счета
        # Например, через вебхук или прямое API вызов
        
        # Логируем создание счета
        print(f"📄 Создан счет: {invoice_id}")
        print(f"  Игра: {game}, Исход: {outcome}, Сумма: {amount}")
        print(f"  Ссылка на оплату: {payment_link}")
        
        return jsonify({
            'success': True,
            'invoice_id': invoice_id,
            'payment_link': payment_link,
            'message': 'Счет успешно создан. Переадресация на оплату...'
        })
        
    except Exception as e:
        print(f"❌ Ошибка при создании счета: {e}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

@app.route('/api/invoice_status/<invoice_id>', methods=['GET'])
def get_invoice_status(invoice_id):
    """Проверка статуса счета"""
    if invoice_id not in pending_invoices:
        return jsonify({'error': 'Счет не найден'}), 404
    
    invoice = pending_invoices[invoice_id]
    return jsonify({
        'invoice_id': invoice_id,
        'status': invoice['status'],
        'amount': invoice['amount'],
        'game': invoice['game'],
        'outcome': invoice['outcome'],
        'created_at': invoice['created_at'],
        'expires_at': invoice['expires_at']
    })

@app.route('/api/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Вебхук для получения уведомлений от Telegram бота"""
    data = request.json
    
    # Обработка уведомлений от бота о платежах
    if data.get('event') == 'payment_received':
        invoice_id = data.get('invoice_id')
        if invoice_id in pending_invoices:
            pending_invoices[invoice_id]['status'] = 'paid'
            pending_invoices[invoice_id]['paid_at'] = datetime.now().isoformat()
            print(f"✅ Счет {invoice_id} оплачен")
    
    return jsonify({'status': 'ok'})

def check_expired_invoices():
    """Фоновая задача для проверки просроченных счетов"""
    while True:
        try:
            current_time = datetime.now()
            expired_invoices = []
            
            for invoice_id, invoice in pending_invoices.items():
                if invoice['status'] == 'pending':
                    expires_at = datetime.fromisoformat(invoice['expires_at'])
                    if current_time > expires_at:
                        invoice['status'] = 'expired'
                        expired_invoices.append(invoice_id)
                        print(f"⌛ Счет {invoice_id} просрочен")
            
            # Удаляем старые просроченные счета (старше 1 часа)
            one_hour_ago = current_time - timedelta(hours=1)
            for invoice_id, invoice in list(pending_invoices.items()):
                if invoice['status'] in ['expired', 'paid']:
                    created_at = datetime.fromisoformat(invoice['created_at'])
                    if created_at < one_hour_ago:
                        del pending_invoices[invoice_id]
            
        except Exception as e:
            print(f"❌ Ошибка при проверке счетов: {e}")
        
        time.sleep(5)  # Проверяем каждые 5 секунд

if __name__ == '__main__':
    # Запускаем фоновую задачу для проверки счетов
    thread = threading.Thread(target=check_expired_invoices, daemon=True)
    thread.start()
    
    print("🚀 Сервер запущен на http://localhost:5000")
    app.run(debug=True, port=5000)

import telebot
from telebot import types
import json
import os
import time
import threading
from collections import deque
import random

MIN_BET = 0.15
CHANNEL_ID = "@l1ght_win"
CHANNEL_LINK = "https://t.me/l1ght_win"

# Ссылки на изображения для результатов
WIN_IMAGE_URL = "https://iimg.su/i/P9Y9Ke"
LOSE_IMAGE_URL = "https://iimg.su/i/fJCCZ2"
GAMES_MENU_IMAGE_URL = "https://iimg.su/i/d1Lle6"

# Конфигурации для ставок
DICE_BET_TYPES = {
    'куб_нечет': {'name': 'нечетное', 'values': [1, 3, 5], 'multiplier': 1.8},
    'куб_чет': {'name': 'четное', 'values': [2, 4, 6], 'multiplier': 1.8},
    'куб_1': {'name': '1', 'values': [1], 'multiplier': 4.0},
    'куб_2': {'name': '2', 'values': [2], 'multiplier': 4.0},
    'куб_3': {'name': '3', 'values': [3], 'multiplier': 4.0},
    'куб_4': {'name': '4', 'values': [4], 'multiplier': 4.0},
    'куб_5': {'name': '5', 'values': [5], 'multiplier': 4.0},
    'куб_6': {'name': '6', 'values': [6], 'multiplier': 4.0},
    'куб_мал': {'name': 'меньше (1-3)', 'values': [1, 2, 3], 'multiplier': 1.8},
    'куб_бол': {'name': 'больше (4-6)', 'values': [4, 5, 6], 'multiplier': 1.8},
    'куб_2меньше': {'name': '2 меньше (оба < 4)', 'multiplier': 3.6, 'special': True},
    'куб_2больше': {'name': '2 больше (оба > 3)', 'multiplier': 3.6, 'special': True},
}

BASKETBALL_BET_TYPES = {
    'баскет_гол': {'name': 'Гол (2 очка)', 'values': [4, 5], 'multiplier': 1.85},
    'баскет_мимо': {'name': 'Мимо', 'values': [1, 2, 3], 'multiplier': 1.7},
    'баскет_3очка': {'name': '3-очковый', 'values': [5], 'multiplier': 2.75},
}

FOOTBALL_BET_TYPES = {
    'футбол_гол': {'name': 'Гол', 'values': [4, 5], 'multiplier': 1.3},
    'футбол_мимо': {'name': 'Мимо', 'values': [1, 2, 3], 'multiplier': 1.7},
}

DART_BET_TYPES = {
    'дартс_белое': {'name': 'Белое', 'values': [3, 5], 'multiplier': 1.85},
    'дартс_красное': {'name': 'Красное', 'values': [2, 4], 'multiplier': 1.85},
    'дартс_мимо': {'name': 'Мимо', 'values': [1], 'multiplier': 2.2},
    'дартс_центр': {'name': 'Центр', 'values': [6], 'multiplier': 3.35},
}

BOWLING_BET_TYPES = {
    'боулинг_поражение': {'name': 'Поражение ', 'values': [], 'multiplier': 1.8},
    'боулинг_победа': {'name': 'Победа ', 'values': [], 'multiplier': 1.8},
    'боулинг_страйк': {'name': 'Страйк ', 'values': [6], 'multiplier': 3.75},
}

# Общий словарь для обратной совместимости
BET_TYPES = {**DICE_BET_TYPES, **BASKETBALL_BET_TYPES, **FOOTBALL_BET_TYPES, **DART_BET_TYPES, **BOWLING_BET_TYPES}

# Маппинг названий игр из мини-апп на внутренние типы
GAME_TYPE_MAPPING = {
    'dice': 'куб',
    'basketball': 'баскет',
    'football': 'футбол',
    'darts': 'дартс',
    'bowling': 'боулинг'
}

# Маппинг исходов из мини-апп на внутренние типы
OUTCOME_MAPPING = {
    # Кубик
    'нечет': 'нечет',
    'чет': 'чет',
    'меньше': 'мал',
    'больше': 'бол',
    '1': '1',
    '2': '2',
    '3': '3',
    '4': '4',
    '5': '5',
    '6': '6',
    '2 меньше': '2меньше',
    '2 больше': '2больше',
    
    # Баскетбол
    'гол': 'гол',
    'мимо': 'мимо',
    '3-очковый': '3очка',
    
    # Футбол
    # 'гол': 'гол',  # уже есть
    # 'мимо': 'мимо',  # уже есть
    
    # Дартс
    'белое': 'белое',
    'красное': 'красное',
    # 'мимо': 'мимо',  # уже есть
    'центр': 'центр',
    
    # Боулинг
    'поражение': 'поражение',
    'победа': 'победа',
    'страйк': 'страйк',
}

class GameQueue:
    def __init__(self):
        self.queue = deque()
        self.active_game = False
        self.lock = threading.Lock()

    def add_game(self, game_data):
        with self.lock:
            self.queue.append(game_data)

    def start_next_game(self):
        with self.lock:
            if self.active_game or not self.queue:
                return None
            self.active_game = True
            return self.queue.popleft()

    def finish_game(self):
        with self.lock:
            self.active_game = False

    def get_queue_size(self):
        with self.lock:
            return len(self.queue)


class BettingGame:
    def __init__(self, bot):
        self.bot = bot
        self.user_balances = {}
        self.pending_bets = {}
        self.game_queue = GameQueue()
        self.referral_system = None
        self.load_balances()
        threading.Thread(target=self._process_game_queue, daemon=True).start()

    def load_balances(self):
        if os.path.exists('balances.json'):
            try:
                with open('balances.json', 'r') as f:
                    data = json.load(f)
                    self.user_balances = {int(k): float(v) for k, v in data.items()}
                print(f"✅ Загружено {len(self.user_balances)} балансов")
            except Exception as e:
                print(f"❌ Ошибка загрузки балансов: {e}")
                self.user_balances = {}
        else:
            self.user_balances = {}
            print("ℹ️ Файл балансов не найден, создан новый")

    def save_balances(self):
        try:
            data_to_save = {str(k): v for k, v in self.user_balances.items()}
            with open('balances.json', 'w') as f:
                json.dump(data_to_save, f, indent=4)
        except Exception as e:
            print(f"❌ Ошибка сохранения балансов: {e}")

    def get_balance(self, user_id):
        return float(self.user_balances.get(user_id, 0.0))

    def add_balance(self, user_id, amount):
        if user_id not in self.user_balances:
            self.user_balances[user_id] = 0.0
        self.user_balances[user_id] += float(amount)
        self.save_balances()
        print(f"💰 Добавлено {amount} USDT пользователю {user_id}")
        return self.user_balances[user_id]

    def subtract_balance(self, user_id, amount):
        amount_float = float(amount)
        if self.get_balance(user_id) >= amount_float:
            self.user_balances[user_id] = max(0, self.user_balances.get(user_id, 0) - amount_float)
            self.save_balances()
            print(f"💸 Снято {amount_float} USDT у пользователя {user_id}")
            return True
        return False

    def show_games_menu(self, message):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("🎲 Кубик", callback_data="game_dice")
        btn2 = types.InlineKeyboardButton("🏀 Баскетбол", callback_data="game_basketball")
        btn3 = types.InlineKeyboardButton("⚽ Футбол", callback_data="game_football")
        btn4 = types.InlineKeyboardButton("🎯 Дартс", callback_data="game_darts")
        btn5 = types.InlineKeyboardButton("🎳 Боулинг", callback_data="game_bowling")

        markup.row(btn1, btn2)
        markup.row(btn3, btn4)
        markup.row(btn5)

        games_text = f"""
<b>🕹Игры:</b>
        """

        try:
            self.bot.send_photo(
                message.chat.id,
                photo=GAMES_MENU_IMAGE_URL,
                caption=games_text,
                parse_mode='HTML',
                reply_markup=markup
            )
            print(f"✅ Меню игр с изображением отправлено пользователю {message.from_user.id}")
        except Exception as e:
            print(f"❌ Ошибка при отправке изображения меню игр: {e}")
            self.bot.send_message(
                message.chat.id,
                games_text,
                parse_mode='HTML',
                reply_markup=markup
            )

    def show_dice_menu(self, call):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("🎲 Нечет (x1.8)", callback_data="bet_dice_куб_нечет")
        btn2 = types.InlineKeyboardButton("🎲 Чет (x1.8)", callback_data="bet_dice_куб_чет")
        btn3 = types.InlineKeyboardButton("📉 Меньше (x1.8)", callback_data="bet_dice_куб_мал")
        btn4 = types.InlineKeyboardButton("📈 Больше (x1.8)", callback_data="bet_dice_куб_бол")
        btn5 = types.InlineKeyboardButton("🎯 Точное число (x4)", callback_data="bet_dice_exact")
        btn6 = types.InlineKeyboardButton("🎲🎲 2 меньше (x3.6)", callback_data="bet_dice_куб_2меньше")
        btn7 = types.InlineKeyboardButton("🎲🎲 2 больше (x3.6)", callback_data="bet_dice_куб_2больше")
        
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7)
        
        text = f"""
<b>🎲Кубик</b>

<blockquote><b>Выберите тип ставки:</b></blockquote>
        """
        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

    def show_basketball_menu(self, call):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("🏀 Гол (x1.85)", callback_data="bet_basketball_баскет_гол")
        btn2 = types.InlineKeyboardButton("❌ Мимо (x1.7)", callback_data="bet_basketball_баскет_мимо")
        btn3 = types.InlineKeyboardButton("⭐ 3-очковый (x2.75)", callback_data="bet_basketball_баскет_3очка")
        markup.add(btn1, btn2, btn3)
        
        text = f"""
<b>🏀Баскетбол</b>

<blockquote><b>Выберите исход броска:</b></blockquote>
        """
        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

    def show_football_menu(self, call):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("✅ Гол (x1.3)", callback_data="bet_football_футбол_гол")
        btn2 = types.InlineKeyboardButton("❌ Мимо (x1.7)", callback_data="bet_football_футбол_мимо")
        markup.add(btn1, btn2)
        text = """
<b>⚽Футбол</b>

<blockquote><b>Выберите исход удара:</b></blockquote>
        """
        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

    def show_darts_menu(self, call):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("⚪ Белое (x1.85)", callback_data="bet_darts_дартс_белое")
        btn2 = types.InlineKeyboardButton("🔴 Красное (x1.85)", callback_data="bet_darts_дартс_красное")
        btn3 = types.InlineKeyboardButton("❌ Мимо (x2.2)", callback_data="bet_darts_дартс_мимо")
        btn4 = types.InlineKeyboardButton("🎯 Центр (x3.35)", callback_data="bet_darts_дартс_центр")
        markup.add(btn1, btn2, btn3, btn4)
        text = """
<b>🎯Дартс</b>

<blockquote><b>Выберите зону попадания:</b></blockquote>
        """
        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

    def show_bowling_menu(self, call):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("❌ Поражение (x1.8)", callback_data="bet_bowling_боулинг_поражение")
        btn2 = types.InlineKeyboardButton("✅ Победа (x1.8)", callback_data="bet_bowling_боулинг_победа")
        btn3 = types.InlineKeyboardButton("🎳 Страйк (x3.75)", callback_data="bet_bowling_боулинг_страйк")
        markup.add(btn1, btn2, btn3)
        text = """
<b>🎳Боулинг</b>

<blockquote><b>Выберите исход:</b></blockquote>
        """
        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

    def show_exact_numbers(self, call):
        markup = types.InlineKeyboardMarkup(row_width=3)
        for i in range(1, 7):
            markup.add(types.InlineKeyboardButton(f"🎲 {i}", callback_data=f"bet_dice_куб_{i}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="game_dice"))
        text = """
<b>🎲Выберите число (1-6)</b>
        """
        try:
            self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
        except:
            self.bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)

    def request_amount(self, call, bet_type):
        user_id = call.from_user.id
        balance = self.get_balance(user_id)

        if bet_type.startswith('куб_'):
            bet_config = DICE_BET_TYPES[bet_type]
        elif bet_type.startswith('баскет_'):
            bet_config = BASKETBALL_BET_TYPES[bet_type]
        elif bet_type.startswith('футбол_'):
            bet_config = FOOTBALL_BET_TYPES[bet_type]
        elif bet_type.startswith('дартс_'):
            bet_config = DART_BET_TYPES[bet_type]
        elif bet_type.startswith('боулинг_'):
            bet_config = BOWLING_BET_TYPES[bet_type]

        markup = types.InlineKeyboardMarkup()
        if bet_type.startswith('куб_'):
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="game_dice"))
        elif bet_type.startswith('баскет_'):
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="game_basketball"))
        elif bet_type.startswith('футбол_'):
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="game_football"))
        elif bet_type.startswith('дартс_'):
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="game_darts"))
        elif bet_type.startswith('боулинг_'):
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="game_bowling"))

        text = f"""

<blockquote><b>📝Введите сумму ставки</b></blockquote>
        """
        try:
            self.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='HTML', reply_markup=markup)
        except:
            self.bot.send_message(call.message.chat.id, text, parse_mode='HTML', reply_markup=markup)
        self.pending_bets[user_id] = bet_type

    def process_bet_amount(self, message):
        user_id = message.from_user.id
        if user_id not in self.pending_bets:
            return False
        try:
            amount = float(message.text)
            if amount < MIN_BET:
                self.bot.send_message(message.chat.id, f"❌ Минимальная ставка: {MIN_BET} USDT")
                return True
            balance = self.get_balance(user_id)
            if balance < amount:
                self.bot.send_message(
                    message.chat.id,
                    f"❌ <b>Недостаточно средств!</b>\n\nВаш баланс: <code>{balance:.2f} USDT</code>",
                    parse_mode='HTML'
                )
                return True
            bet_type = self.pending_bets[user_id]

            if bet_type.startswith('куб_'):
                bet_config = DICE_BET_TYPES[bet_type]
            elif bet_type.startswith('баскет_'):
                bet_config = BASKETBALL_BET_TYPES[bet_type]
            elif bet_type.startswith('футбол_'):
                bet_config = FOOTBALL_BET_TYPES[bet_type]
            elif bet_type.startswith('дартс_'):
                bet_config = DART_BET_TYPES[bet_type]
            elif bet_type.startswith('боулинг_'):
                bet_config = BOWLING_BET_TYPES[bet_type]

            if not self.subtract_balance(user_id, amount):
                self.bot.send_message(message.chat.id, "❌ Ошибка при снятии средств")
                return True

            nickname = message.from_user.first_name or ""
            if message.from_user.last_name:
                nickname += f" {message.from_user.last_name}"
            nickname = nickname.strip() or message.from_user.username or "Игрок"

            queue_size = self.game_queue.get_queue_size()
            if queue_size > 0:
                queue_message = f"\n⏳ Ваша игра в очереди. Перед вами {queue_size} игр(ы)"
            else:
                queue_message = ""

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🔗Ваша ставка", url=CHANNEL_LINK))

            self.bot.send_message(
                message.chat.id,
                f"✅ Ставка принята! Игра запускается в канале...{queue_message}",
                reply_markup=markup,
                parse_mode='HTML'
            )
            game_data = {
                'user_id': user_id,
                'nickname': nickname,
                'amount': amount,
                'bet_type': bet_type,
                'from_bot': True
            }
            self.game_queue.add_game(game_data)
            del self.pending_bets[user_id]
            return True
        except ValueError:
            self.bot.send_message(message.chat.id, "❌ Введите корректную сумму")
            return True

    def add_game_to_queue(self, user_id, nickname, amount, game_type, outcome):
        """
        Добавляет игру в очередь из API (мини-апп)
        
        Args:
            user_id: ID пользователя
            nickname: Никнейм пользователя
            amount: Сумма ставки
            game_type: Тип игры из мини-апп ('dice', 'basketball', etc.)
            outcome: Исход из мини-апп ('нечет', 'гол', etc.)
        """
        try:
            # Маппим тип игры
            internal_game_prefix = GAME_TYPE_MAPPING.get(game_type.lower())
            if not internal_game_prefix:
                print(f"❌ Неизвестный тип игры: {game_type}")
                return False
            
            # Маппим исход
            internal_outcome = OUTCOME_MAPPING.get(outcome.lower())
            if not internal_outcome:
                print(f"❌ Неизвестный исход: {outcome}")
                return False
            
            # Формируем полный bet_type
            bet_type = f"{internal_game_prefix}_{internal_outcome}"
            
            # Проверяем, что такой bet_type существует
            if bet_type not in BET_TYPES:
                print(f"❌ Неизвестный bet_type: {bet_type}")
                return False
            
            # Добавляем в очередь
            game_data = {
                'user_id': user_id,
                'nickname': nickname,
                'amount': amount,
                'bet_type': bet_type,
                'from_bot': False  # Ставка не из бота, а из мини-апп
            }
            
            self.game_queue.add_game(game_data)
            queue_size = self.game_queue.get_queue_size()
            print(f"✅ Игра добавлена в очередь. Всего в очереди: {queue_size}")
            
            return True
            
        except Exception as e:
            print(f"❌ Ошибка добавления игры в очередь: {e}")
            return False

    def _process_game_queue(self):
        """Обработчик очереди игр"""
        while True:
            try:
                game_data = self.game_queue.start_next_game()
                
                if game_data:
                    print(f"🎮 Обработка игры: {game_data['bet_type']} от {game_data['nickname']}")
                    self._create_channel_game(
                        game_data['user_id'],
                        game_data['nickname'],
                        game_data['amount'],
                        game_data['bet_type'],
                        game_data['from_bot']
                    )
                    self.game_queue.finish_game()
                    time.sleep(3)
                else:
                    time.sleep(1)
                    
            except Exception as e:
                print(f"❌ Ошибка в обработчике очереди: {e}")
                self.game_queue.finish_game()
                time.sleep(3)

    def _create_channel_game(self, user_id, nickname, amount, bet_type, from_bot):
        """Создает игру в канале"""
        try:
            bet_config = BET_TYPES.get(bet_type)
            if not bet_config:
                print(f"❌ Неизвестный тип ставки: {bet_type}")
                return

            bet_name = bet_config['name']
            multiplier = bet_config['multiplier']
            
            # Определяем эмодзи и текст игры
            if bet_type.startswith('куб_'):
                emoji = "🎲"
                game_name = "Кубик"
            elif bet_type.startswith('баскет_'):
                emoji = "🏀"
                game_name = "Баскетбол"
            elif bet_type.startswith('футбол_'):
                emoji = "⚽"
                game_name = "Футбол"
            elif bet_type.startswith('дартс_'):
                emoji = "🎯"
                game_name = "Дартс"
            elif bet_type.startswith('боулинг_'):
                emoji = "🎳"
                game_name = "Боулинг"
            else:
                emoji = "🎮"
                game_name = "Игра"

            potential_win = amount * multiplier

            bet_text = f"""
{emoji} <b>{game_name}</b>

👤 Игрок: <b>{nickname}</b>
🎯 Ставка: <b>{bet_name}</b>
💰 Сумма: <code>{amount:.2f}$</code>
🍀 Коэффициент: <code>x{multiplier}</code>
💎 Возможный выигрыш: <code>{potential_win:.2f}$</code>
            """

            # Отправляем кубик в зависимости от типа игры
            if bet_type.startswith('куб_'):
                if bet_type in ['куб_2меньше', 'куб_2больше']:
                    # Два кубика
                    msg = self.bot.send_message(CHANNEL_ID, bet_text, parse_mode='HTML')
                    dice1 = self.bot.send_dice(CHANNEL_ID, emoji="🎲")
                    time.sleep(0.5)
                    dice2 = self.bot.send_dice(CHANNEL_ID, emoji="🎲")
                    time.sleep(4)
                    self._process_double_dice_result(
                        msg.message_id,
                        dice1.dice.value,
                        dice2.dice.value,
                        user_id,
                        nickname,
                        amount,
                        bet_type,
                        bet_config,
                        from_bot
                    )
                else:
                    # Один кубик
                    msg = self.bot.send_message(CHANNEL_ID, bet_text, parse_mode='HTML')
                    dice_roll = self.bot.send_dice(CHANNEL_ID, emoji="🎲")
                    time.sleep(4)
                    self._send_game_result_with_image(
                        msg.message_id,
                        dice_roll.dice.value,
                        user_id,
                        nickname,
                        amount,
                        bet_type,
                        bet_config,
                        from_bot
                    )
            elif bet_type.startswith('баскет_'):
                msg = self.bot.send_message(CHANNEL_ID, bet_text, parse_mode='HTML')
                dice_roll = self.bot.send_dice(CHANNEL_ID, emoji="🏀")
                time.sleep(5)
                self._send_game_result_with_image(
                    msg.message_id,
                    dice_roll.dice.value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )
            elif bet_type.startswith('футбол_'):
                msg = self.bot.send_message(CHANNEL_ID, bet_text, parse_mode='HTML')
                dice_roll = self.bot.send_dice(CHANNEL_ID, emoji="⚽")
                time.sleep(4)
                self._send_game_result_with_image(
                    msg.message_id,
                    dice_roll.dice.value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )
            elif bet_type.startswith('дартс_'):
                msg = self.bot.send_message(CHANNEL_ID, bet_text, parse_mode='HTML')
                dice_roll = self.bot.send_dice(CHANNEL_ID, emoji="🎯")
                time.sleep(4)
                self._send_game_result_with_image(
                    msg.message_id,
                    dice_roll.dice.value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )
            elif bet_type.startswith('боулинг_'):
                msg = self.bot.send_message(CHANNEL_ID, bet_text, parse_mode='HTML')
                player_roll = self.bot.send_dice(CHANNEL_ID, emoji="🎳")
                time.sleep(3)
                
                if bet_type == 'боулинг_страйк':
                    time.sleep(1)
                    self._send_game_result_with_image(
                        msg.message_id,
                        player_roll.dice.value,
                        user_id,
                        nickname,
                        amount,
                        bet_type,
                        bet_config,
                        from_bot
                    )
                else:
                    bot_roll = self.bot.send_dice(CHANNEL_ID, emoji="🎳")
                    time.sleep(3)
                    player_value = player_roll.dice.value
                    bot_value = bot_roll.dice.value
                    
                    is_win = False
                    if bet_type == 'боулинг_поражение':
                        if player_value < bot_value:
                            is_win = True
                    elif bet_type == 'боулинг_победа':
                        if player_value > bot_value:
                            is_win = True

                    dice_value = player_value if is_win else 0
                    self._send_game_result_with_image(
                        bot_roll.message_id,
                        dice_value,
                        user_id,
                        nickname,
                        amount,
                        bet_type,
                        bet_config,
                        from_bot
                    )

        except Exception as e:
            print(f"❌ Ошибка при создании игры в канале: {e}")

    def _process_double_dice_result(self, dice_message_id, dice1_value, dice2_value, user_id, nickname, amount, bet_type, bet_config, from_bot):
        """Обрабатывает результат для двух кубиков"""
        try:
            is_win = False
            
            if bet_type == 'куб_2меньше':
                is_win = dice1_value < 4 and dice2_value < 4
            elif bet_type == 'куб_2больше':
                is_win = dice1_value > 3 and dice2_value > 3
            
            winnings = 0
            if is_win:
                winnings = amount * bet_config['multiplier']
                if from_bot:
                    self.add_balance(user_id, winnings)
                    print(f"🎉 Победа! Начислено {winnings} USDT пользователю {user_id}")

                    if hasattr(self, 'referral_system') and self.referral_system:
                        referral_bonus = self.referral_system.process_referral_win(user_id, winnings)
                        if referral_bonus > 0:
                            print(f"📈 Начислено {referral_bonus:.2f} USDT рефереру")
            else:
                print(f"😔 Проигрыш. Пользователь {user_id} потерял {amount} USDT")

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💸 Сделать ставку", url=CHANNEL_LINK))

            if is_win:
                result_text = f"""
<b>🎉 Вы выиграли!</b>

<blockquote><b>🍀<i>Выигрыш <code>{winnings:.2f}$</code> был начислен на баланс в боте</i></b></blockquote>

🥳<b>Поздравляем!</b>
"""
                image_url = WIN_IMAGE_URL
            else:
                result_text = f"""
<b>❌вы проиграли!</b>

<blockquote><b><i>Это не повод сдаваться! Пробуй снова и снова до победного!</i></b></blockquote>

🍀<b>Повезет в следующий раз!</b>
"""
                image_url = LOSE_IMAGE_URL

            try:
                self.bot.send_photo(
                    CHANNEL_ID,
                    photo=image_url,
                    caption=result_text,
                    parse_mode='HTML',
                    reply_to_message_id=dice_message_id,
                    reply_markup=markup
                )
            except Exception as e:
                print(f"❌ Ошибка при отправке фото: {e}")
                self.bot.send_message(
                    CHANNEL_ID,
                    result_text,
                    parse_mode='HTML',
                    reply_to_message_id=dice_message_id,
                    reply_markup=markup
                )

        except Exception as e:
            print(f"❌ Ошибка при обработке результата двух кубиков: {e}")

    def _send_game_result_with_image(self, dice_message_id, dice_value, user_id, nickname, amount, bet_type, bet_config, from_bot):
        """Отправляет результат игры с изображением"""
        try:
            is_win = False
            winnings = 0

            if bet_type.startswith('куб_'):
                if 'special' not in bet_config:
                    winning_values = bet_config['values']
                    is_win = dice_value in winning_values
            elif bet_type.startswith('баскет_'):
                winning_values = bet_config['values']
                is_win = dice_value in winning_values
            elif bet_type.startswith('футбол_'):
                winning_values = bet_config['values']
                is_win = dice_value in winning_values
            elif bet_type.startswith('дартс_'):
                winning_values = bet_config['values']
                is_win = dice_value in winning_values
            elif bet_type.startswith('боулинг_'):
                if bet_type == 'боулинг_страйк':
                    is_win = dice_value == 6
                else:
                    is_win = dice_value > 0

            if is_win:
                winnings = amount * bet_config['multiplier']
                if from_bot:
                    self.add_balance(user_id, winnings)
                    print(f"🎉 Победа! Начислено {winnings} USDT пользователю {user_id}")

                    if hasattr(self, 'referral_system') and self.referral_system:
                        referral_bonus = self.referral_system.process_referral_win(user_id, winnings)
                        if referral_bonus > 0:
                            print(f"📈 Начислено {referral_bonus:.2f} USDT рефереру")
            else:
                print(f"😔 Проигрыш. Пользователь {user_id} потерял {amount} USDT")

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💸 Сделать ставку", url=CHANNEL_LINK))

            if is_win:
                result_text = f"""
<b>🎉 Вы выиграли!</b>

<blockquote><b>🍀<i>Выигрыш <code>{winnings:.2f}$</code> был начислен на баланс в боте</i></b></blockquote>

🥳<b>Поздравляем!</b>
"""
                image_url = WIN_IMAGE_URL
            else:
                result_text = f"""
<b>❌вы проиграли!</b>

<blockquote><b><i>Это не повод сдаваться! Пробуй снова и снова до победного!</i></b></blockquote>

🍀<b>Повезет в следующий раз!</b>
"""
                image_url = LOSE_IMAGE_URL

            try:
                self.bot.send_photo(
                    CHANNEL_ID,
                    photo=image_url,
                    caption=result_text,
                    parse_mode='HTML',
                    reply_to_message_id=dice_message_id,
                    reply_markup=markup
                )
            except Exception as e:
                print(f"❌ Ошибка при отправке фото: {e}")
                self.bot.send_message(
                    CHANNEL_ID,
                    result_text,
                    parse_mode='HTML',
                    reply_to_message_id=dice_message_id,
                    reply_markup=markup
                )

        except Exception as e:
            print(f"❌ Ошибка при отправке результата: {e}")

    def set_referral_system(self, referral_system):
        """Устанавливает ссылку на реферальную систему"""
        self.referral_system = referral_system
        print("✅ Реферальная система подключена к играм")

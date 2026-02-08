import telebot
from telebot import types
import json
import os
import time
import threading
from collections import deque

MIN_BET = 0.15
CHANNEL_ID = "@l1ght_win"
CHANNEL_LINK = "https://t.me/l1ght_win"

# Твоя постоянная ссылка на многоразовый счёт
PAYMENT_LINK = "https://t.me/send?start=IVNg7XnKzxBs"

# Ссылки на изображения для результатов
WIN_IMAGE_URL = "https://iimg.su/i/P9Y9Ke"
LOSE_IMAGE_URL = "https://iimg.su/i/fJCCZ2"
# Ссылка для превью меню игр
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
        self.referral_system = None  # Будет установлено из main.py
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

        # Первый ряд: 2 кнопки
        markup.row(btn1, btn2)
        # Второй ряд: 2 кнопки
        markup.row(btn3, btn4)
        # Третий ряд: 1 большая кнопка
        markup.row(btn5)

        games_text = f"""
<b>🕹Игры:</b>
        """

        try:
            # Отправляем изображение с меню игр (ТОЛЬКО В ГЛАВНОМ МЕНЮ)
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
            # Если не получилось отправить с изображением, отправляем просто текст
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
        markup.add(btn1, btn2, btn3, btn4, btn5)
        text = f"""
<b>🎲Кубик</b>

<blockquote><b>Выберите исход:</b></blockquote>
        """
        # Отправляем новое сообщение (без изображения) при выборе игры
        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

    def show_basketball_menu(self, call):
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("✅ Гол (x1.85)", callback_data="bet_basketball_баскет_гол")
        btn2 = types.InlineKeyboardButton("❌ Мимо (x1.7)", callback_data="bet_basketball_баскет_мимо")
        btn3 = types.InlineKeyboardButton("🎯 3-очковый (x2.75)", callback_data="bet_basketball_баскет_3очка")
        markup.add(btn1, btn2, btn3)
        text = """
<b>🏀Баскетбол</b>

<blockquote><b>Выберите исход броска:</b></blockquote>
        """
        # Отправляем новое сообщение (без изображения) при выборе игры
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
        # Отправляем новое сообщение (без изображения) при выборе игры
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
        # Отправляем новое сообщение (без изображения) при выборе игры
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
        # Отправляем новое сообщение (без изображения) при выборе игры
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
                'bet_config': bet_config,
                'from_bot': True
            }
            self.game_queue.add_game(game_data)
            del self.pending_bets[user_id]
            return True
        except ValueError:
            self.bot.send_message(message.chat.id, "❌ Введите корректную сумму (например: 0.5)")
            return True

    def _process_game_queue(self):
        while True:
            game_data = self.game_queue.start_next_game()
            if game_data:
                try:
                    self._create_channel_game(game_data)
                except Exception as e:
                    print(f"❌ Ошибка при обработке игры: {e}")
                finally:
                    self.game_queue.finish_game()
            time.sleep(0.5)

    def _create_channel_game(self, game_data):
        """Создает игру в канале"""
        try:
            user_id = game_data['user_id']
            nickname = game_data['nickname']
            amount = game_data['amount']
            bet_type = game_data['bet_type']
            bet_config = game_data['bet_config']
            from_bot = game_data.get('from_bot', False)

            if bet_type.startswith('куб_'):
                game_type = 'dice'
            elif bet_type.startswith('баскет_'):
                game_type = 'basketball'
            elif bet_type.startswith('футбол_'):
                game_type = 'football'
            elif bet_type.startswith('дартс_'):
                game_type = 'darts'
            else:
                game_type = 'bowling'

            # Экранируем HTML-специальные символы в названии ставки
            bet_name = bet_config['name'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

            # Исправленный текст без ошибок в HTML
            bet_message_text = f"""<blockquote><b>{nickname} ставит {amount:.2f}$ на {bet_name}</b></blockquote>

<blockquote><b>коэффициент: x{bet_config['multiplier']}</b></blockquote>
<blockquote><b>Предполагаемый выигрыш: {amount * bet_config['multiplier']:.2f}$</b></blockquote>

🍀 <b>Желаем удачи!</b>"""

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💸Сделать ставку", url=PAYMENT_LINK))
            print(f"📤 Отправка сообщения о ставке в канал {CHANNEL_ID}")
            bet_message = self.bot.send_message(
                CHANNEL_ID,
                bet_message_text,
                parse_mode='HTML',
                reply_markup=markup
            )
            print(f"✅ Сообщение о ставке отправлено")
            time.sleep(1)

            if game_type == 'dice':
                print(f"🎲 Бросаем кубик...")
                dice_message = self.bot.send_dice(
                    CHANNEL_ID,
                    emoji="🎲",
                    reply_to_message_id=bet_message.message_id
                )
                dice_value = dice_message.dice.value
                time.sleep(3)

                self._send_game_result_with_image(
                    dice_message.message_id,
                    dice_value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )

            elif game_type == 'basketball':
                print(f"🏀 Бросаем баскетбольный мяч...")
                dice_message = self.bot.send_dice(
                    CHANNEL_ID,
                    emoji="🏀",
                    reply_to_message_id=bet_message.message_id
                )
                dice_value = dice_message.dice.value
                time.sleep(3)

                self._send_game_result_with_image(
                    dice_message.message_id,
                    dice_value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )

            elif game_type == 'football':
                print(f"⚽ Бьем по воротам...")
                dice_message = self.bot.send_dice(
                    CHANNEL_ID,
                    emoji="⚽",
                    reply_to_message_id=bet_message.message_id
                )
                dice_value = dice_message.dice.value
                time.sleep(3)

                self._send_game_result_with_image(
                    dice_message.message_id,
                    dice_value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )

            elif game_type == 'darts':
                print(f"🎯 Бросаем дротик...")
                dice_message = self.bot.send_dice(
                    CHANNEL_ID,
                    emoji="🎯",
                    reply_to_message_id=bet_message.message_id
                )
                dice_value = dice_message.dice.value
                time.sleep(3)

                self._send_game_result_with_image(
                    dice_message.message_id,
                    dice_value,
                    user_id,
                    nickname,
                    amount,
                    bet_type,
                    bet_config,
                    from_bot
                )

            else:  # bowling
                print(f"🎳 Играем в боулинг...")

                if bet_type == 'боулинг_страйк':
                    # Для страйка кидаем только 1 эмоджи (игрок)
                    print(f"🎳 Бросок игрока (страйк)...")
                    player_roll = self.bot.send_dice(
                        CHANNEL_ID,
                        emoji="🎳",
                        reply_to_message_id=bet_message.message_id
                    )
                    time.sleep(3)

                    dice_value = player_roll.dice.value

                    print(f"🎳 Результат: {dice_value}")

                    self._send_game_result_with_image(
                        player_roll.message_id,
                        dice_value,
                        user_id,
                        nickname,
                        amount,
                        bet_type,
                        bet_config,
                        from_bot
                    )

                else:
                    # Для победы/поражения кидаем 2 эмоджи
                    print(f"🎳 Бросок игрока...")
                    player_roll = self.bot.send_dice(
                        CHANNEL_ID,
                        emoji="🎳",
                        reply_to_message_id=bet_message.message_id
                    )
                    time.sleep(2)

                    print(f"🎳 Бросок бота...")
                    bot_roll = self.bot.send_dice(
                        CHANNEL_ID,
                        emoji="🎳",
                        reply_to_message_id=player_roll.message_id
                    )
                    time.sleep(3)

                    player_value = player_roll.dice.value
                    bot_value = bot_roll.dice.value

                    print(f"🎳 Результат: Игрок = {player_value}, Бот = {bot_value}")

                    # Проверяем, нужно ли перебрасывать при ничьей
                    if player_value == bot_value:
                        print(f"🎳 Ничья! Перебрасываем...")
                        time.sleep(1)

                        # Перебрасываем еще раз
                        player_roll = self.bot.send_dice(
                            CHANNEL_ID,
                            emoji="🎳",
                            reply_to_message_id=bot_roll.message_id
                        )
                        time.sleep(2)

                        bot_roll = self.bot.send_dice(
                            CHANNEL_ID,
                            emoji="🎳",
                            reply_to_message_id=player_roll.message_id
                        )
                        time.sleep(3)

                        player_value = player_roll.dice.value
                        bot_value = bot_roll.dice.value
                        print(f"🎳 Результат после переброса: Игрок = {player_value}, Бot = {bot_value}")

                    # Определяем результат
                    is_win = False
                    if bet_type == 'боулинг_поражение':
                        if player_value < bot_value:
                            is_win = True
                    elif bet_type == 'боулинг_победа':
                        if player_value > bot_value:
                            is_win = True

                    # Создаем фиктивное значение для общей функции
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

    def _send_game_result_with_image(self, dice_message_id, dice_value, user_id, nickname, amount, bet_type, bet_config, from_bot):
        """Отправляет результат игры с изображением (общая функция для всех игр)"""
        try:
            # Определяем выигрыш
            is_win = False
            winnings = 0

            if bet_type.startswith('куб_'):
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
                    # Для победы/поражения результат уже определен в _create_channel_game
                    is_win = dice_value > 0

            if is_win:
                winnings = amount * bet_config['multiplier']
                if from_bot:
                    self.add_balance(user_id, winnings)
                    print(f"🎉 Победа! Начислено {winnings} USDT пользователю {user_id}")

                    # Начисляем реферальный бонус
                    if hasattr(self, 'referral_system') and self.referral_system:
                        referral_bonus = self.referral_system.process_referral_win(user_id, winnings)
                        if referral_bonus > 0:
                            print(f"📈 Начислено {referral_bonus:.2f} USDT рефереру за выигрыш реферала")
            else:
                print(f"😔 Проигрыш. Пользователь {user_id} потерял {amount} USDT")

            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💸 Сделать ставку", url=PAYMENT_LINK))

            if is_win:
                result_text = f"""
<b>🎉 Вы выиграли!</b>

<blockquote><b>🍀<i>Выигрыш <code>{winnings:.2f}$</code> был начислен на баланс в боте</i></b></blockquote>

🥳<b>Поздравляем!</b>

<a href="https://t.me/your_bot">Как играть</a> | <a href="https://t.me/your_bot">Канал новостей</a>
"""
                image_url = WIN_IMAGE_URL
            else:
                result_text = f"""
<b>❌вы проиграли!</b>

<blockquote><b><i>Это не повод сдаваться! Пробуй снова и снова до победного!</i></b></blockquote>

🍀<b>Повезет в следующий раз!</b>

<a href="https://t.me/your_bot">Как играть</a> | <a href="https://t.me/your_bot">Канал новостей</a>
"""
                image_url = LOSE_IMAGE_URL

            print(f"📸 Отправляю изображение: {image_url}")
            try:
                self.bot.send_photo(
                    CHANNEL_ID,
                    photo=image_url,
                    caption=result_text,
                    parse_mode='HTML',
                    reply_to_message_id=dice_message_id,
                    reply_markup=markup
                )
                print(f"✅ Результат игры с изображением отправлен в канал")
            except Exception as e:
                print(f"❌ Ошибка при отправке фото: {e}")
                self.bot.send_message(
                    CHANNEL_ID,
                    result_text,
                    parse_mode='HTML',
                    reply_to_message_id=dice_message_id,
                    reply_markup=markup
                )
                print(f"✅ Результат игры отправлен текстом в канал")

        except Exception as e:
            print(f"❌ Ошибка при отправке результата: {e}")

    def set_referral_system(self, referral_system):
        """Устанавливает ссылку на реферальную систему"""
        self.referral_system = referral_system
        print("✅ Реферальная система подключена к играм")

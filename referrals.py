"""
Короткая и красивая реферальная система
5% от выигрышей рефералов начисляется рефереру
"""

import json
import os
from telebot import types

# Константы реферальной системы
REFERRAL_PERCENT = 0.05  # 5% от выигрыша
MIN_WITHDRAW_REFERRAL = 1.0  # Минимум для вывода реферальных
REFERRALS_FILE = 'referrals.json'

# Ссылка на изображение для рефералки
REFERRAL_IMAGE_URL = "https://iimg.su/i/MICWEM"

class ReferralSystem:
    def __init__(self, bot, game_instance):
        self.bot = bot
        self.game = game_instance
        self.referral_data = self.load_referral_data()
        self.pending_withdraws = {}

    def load_referral_data(self):
        """Загружает данные реферальной системы"""
        if os.path.exists(REFERRALS_FILE):
            try:
                with open(REFERRALS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                print(f"✅ Загружены данные рефералов")

                # Проверяем и добавляем отсутствующие ключи для совместимости
                required_keys = ['referrals', 'referrers', 'earnings', 'withdrawn', 'user_info']
                for key in required_keys:
                    if key not in data:
                        data[key] = {}

                return data
            except Exception as e:
                print(f"❌ Ошибка загрузки реферальных данных: {e}")

        # Создаем новую структуру
        return {
            'referrals': {},  # referrer_id -> [referee_ids]
            'referrers': {},  # referee_id -> referrer_id
            'earnings': {},   # user_id -> {'available': X}
            'withdrawn': {},  # user_id -> total_withdrawn
            'user_info': {}   # user_id -> {'username': '', 'first_name': ''}
        }

    def save_referral_data(self):
        """Сохраняет данные реферальной системы"""
        try:
            with open(REFERRALS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.referral_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"❌ Ошибка сохранения реферальных данных: {e}")

    def save_user_info(self, user_id, username, first_name):
        """Сохраняет информацию о пользователе"""
        user_str = str(user_id)

        if 'user_info' not in self.referral_data:
            self.referral_data['user_info'] = {}

        if user_str not in self.referral_data['user_info']:
            self.referral_data['user_info'][user_str] = {}

        self.referral_data['user_info'][user_str]['username'] = username or ''
        self.referral_data['user_info'][user_str]['first_name'] = first_name or ''

    def get_user_display_name(self, user_id):
        """Возвращает отображаемое имя пользователя"""
        user_str = str(user_id)

        if ('user_info' in self.referral_data and
            user_str in self.referral_data['user_info']):
            user_info = self.referral_data['user_info'][user_str]

            if user_info.get('username'):
                return f"@{user_info['username']}"
            elif user_info.get('first_name'):
                return user_info['first_name']

        return f"ID: {user_id}"

    def register_referral(self, referee_id, referrer_id, referee_username=None, referee_first_name=None):
        """Регистрирует нового реферала с защитой от повторной регистрации"""
        try:
            referee_str = str(referee_id)
            referrer_str = str(referrer_id)

            # Нельзя пригласить себя
            if referee_id == referrer_id:
                return False

            # ЗАЩИТА: Проверяем, не приглашал ли уже кто-то этого пользователя
            if referee_str in self.referral_data['referrers']:
                print(f"⚠️ Пользователь {referee_id} уже является чьим-то рефералом")
                return False

            # Сохраняем информацию о реферале
            self.save_user_info(referee_id, referee_username, referee_first_name)

            # Регистрируем
            if referrer_str not in self.referral_data['referrals']:
                self.referral_data['referrals'][referrer_str] = []

            if referee_str not in self.referral_data['referrals'][referrer_str]:
                self.referral_data['referrals'][referrer_str].append(referee_str)

            self.referral_data['referrers'][referee_str] = referrer_str

            # Инициализируем заработок
            if referrer_str not in self.referral_data['earnings']:
                self.referral_data['earnings'][referrer_str] = {'available': 0.0}

            # Инициализируем withdrawn
            if 'withdrawn' not in self.referral_data:
                self.referral_data['withdrawn'] = {}
            if referrer_str not in self.referral_data['withdrawn']:
                self.referral_data['withdrawn'][referrer_str] = 0.0

            self.save_referral_data()

            # УВЕДОМЛЕНИЕ: Отправляем уведомление рефереру
            try:
                referee_name = self.get_user_display_name(referee_id)
                self.bot.send_message(
                    referrer_id,
                    f"<blockquote>🎉<b>Новый реферал!</b></blockquote>\n\n",
                    parse_mode='HTML'
                )
                print(f"✅ Уведомление отправлено рефереру {referrer_id}")
            except Exception as e:
                print(f"⚠️ Не удалось отправить уведомление рефереру: {e}")

            print(f"✅ Реферал {referee_id} зарегистрирован от {referrer_id}")
            return True

        except Exception as e:
            print(f"❌ Ошибка регистрации реферала: {e}")
            return False

    def process_referral_win(self, user_id, win_amount):
        """Начисляет 5% от выигрыша реферала его рефереру"""
        try:
            user_str = str(user_id)

            if user_str in self.referral_data['referrers']:
                referrer_str = self.referral_data['referrers'][user_str]
                referrer_id = int(referrer_str)

                # Вычисляем 5% от выигрыша
                referral_bonus = win_amount * REFERRAL_PERCENT

                # Начисляем рефереру
                if referrer_str not in self.referral_data['earnings']:
                    self.referral_data['earnings'][referrer_str] = {'available': 0.0}

                self.referral_data['earnings'][referrer_str]['available'] += referral_bonus

                self.save_referral_data()
                print(f"💰 +{referral_bonus:.2f} USDT рефереру {referrer_id}")

                # Отправляем уведомление рефереру
                try:
                    referee_name = self.get_user_display_name(user_id)
                    self.bot.send_message(
                        referrer_id,
                        f"<blockquote>🎉 <b>Начислен реферальный бонус!</b></blockquote>\n\n",
                        parse_mode='HTML'
                    )
                except:
                    pass

                return referral_bonus

            return 0

        except Exception as e:
            print(f"❌ Ошибка начисления бонуса: {e}")
            return 0

    def get_stats(self, user_id):
        """Возвращает статистику пользователя"""
        user_str = str(user_id)

        # Проверяем наличие ключей
        if 'withdrawn' not in self.referral_data:
            self.referral_data['withdrawn'] = {}

        # Количество рефералов
        total_refs = len(self.referral_data['referrals'].get(user_str, []))

        # Доступные средства
        earnings_data = self.referral_data['earnings'].get(user_str, {'available': 0.0})
        if isinstance(earnings_data, (int, float)):
            # Если данные в старом формате
            available = float(earnings_data)
            self.referral_data['earnings'][user_str] = {'available': available}
        else:
            available = earnings_data.get('available', 0.0)

        # Выведенные средства
        withdrawn = self.referral_data['withdrawn'].get(user_str, 0.0)

        return {
            'total_refs': total_refs,
            'available': available,
            'withdrawn': withdrawn,
            'can_withdraw': available >= MIN_WITHDRAW_REFERRAL
        }

    def get_referral_link(self, user_id):
        """Генерирует реферальную ссылку"""
        bot_username = self.bot.get_me().username
        return f"https://t.me/{bot_username}?start=ref{user_id}"

    def show_menu(self, message_or_call):
        """Показывает меню рефералки"""
        if hasattr(message_or_call, 'message'):
            # Это callback
            message = message_or_call.message
            user_id = message_or_call.from_user.id
        else:
            # Это обычное сообщение
            message = message_or_call
            user_id = message.from_user.id

        stats = self.get_stats(user_id)
        ref_link = self.get_referral_link(user_id)

        # Краткий и красивый текст
        text = f"""
<b>👥 Реферальная система</b>

<blockquote>📊 <b>Ваша статистика:</b>
├ 💹 Приглашено: <b><code>{stats['total_refs']}</code> чел.</b>
├ 💸 Доступно: <b><code>{stats['available']:.2f}$</code></b>
└ 📤 Выведено: <b><code>{stats['withdrawn']:.2f}$</code></b></blockquote>

<blockquote>🎉<b>Получайте 5% от выигрышей друзей!</b></blockquote>

<blockquote>🔗 <b>Ваша ссылка:</b>
<code>{ref_link}</code></blockquote>
"""

        # Компактная клавиатура (БЕЗ КНОПКИ ОБНОВИТЬ)
        markup = types.InlineKeyboardMarkup(row_width=2)

        if stats['can_withdraw']:
            markup.add(types.InlineKeyboardButton("📤 Вывести", callback_data="ref_withdraw"))

        markup.add(
            types.InlineKeyboardButton("📋 Мои рефералы", callback_data="ref_list"),
            types.InlineKeyboardButton("📢 Поделиться", callback_data="ref_share")
        )

        try:
            # Пытаемся обновить существующее сообщение
            if hasattr(message_or_call, 'message'):
                self.bot.edit_message_caption(
                    chat_id=message.chat.id,
                    message_id=message.message_id,
                    caption=text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
            else:
                # Или отправляем новое с изображением
                self.bot.send_photo(
                    message.chat.id,
                    photo=REFERRAL_IMAGE_URL,
                    caption=text,
                    parse_mode='HTML',
                    reply_markup=markup
                )
        except Exception as e:
            # Если не получается обновить, отправляем новое
            print(f"⚠️ Не удалось обновить сообщение: {e}")
            self.bot.send_photo(
                message.chat.id,
                photo=REFERRAL_IMAGE_URL,
                caption=text,
                parse_mode='HTML',
                reply_markup=markup
            )

    def show_ref_list(self, call):
        """Показывает список рефералов с именами пользователей"""
        user_id = call.from_user.id
        user_str = str(user_id)

        refs = self.referral_data['referrals'].get(user_str, [])

        if refs:
            text = f"<b>📋 Ваши рефералы ({len(refs)}):</b>\n\n"

            for i, ref_id_str in enumerate(refs[:20], 1):
                try:
                    ref_id = int(ref_id_str)
                    display_name = self.get_user_display_name(ref_id)
                    text += f"{i}. {display_name}\n"
                except:
                    text += f"{i}. ID: {ref_id_str}\n"

            if len(refs) > 20:
                text += f"\n... и еще {len(refs) - 20} рефералов"
        else:
            text = "<blockquote>📭 <b>У вас пока нет рефералов</b></blockquote>"

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="ref_menu"))

        try:
            self.bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except:
            self.bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='HTML',
                reply_markup=markup
            )

    def show_withdraw(self, call):
        """Показывает меню вывода"""
        user_id = call.from_user.id
        stats = self.get_stats(user_id)

        if stats['can_withdraw']:
            text = "<blockquote><b>📝 Введите сумму!</b></blockquote>"
            self.pending_withdraws[str(user_id)] = True
        else:
            text = f"""
<blockquote>❌ <b>Недостаточно средств!</b>

Мин: <b><code>{MIN_WITHDRAW_REFERRAL}$</code></b></blockquote>
"""

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="ref_menu"))

        try:
            self.bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except:
            self.bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='HTML',
                reply_markup=markup
            )

    def show_share(self, call):
        """Показывает меню для шаринга"""
        user_id = call.from_user.id
        ref_link = self.get_referral_link(user_id)

        text = f"""
<b>📢 Поделиться ссылкой</b>

<blockquote>🔗 <b>Ваша ссылка:</b>
<code>{ref_link}</code></blockquote>

<blockquote>📝 <b>Сообщение для отправки:</b>
<code>🎰 Играй и выигрывай USDT!
{ref_link}</code></blockquote>

<i>Скопируйте и отправьте друзьям</i>
"""

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="ref_menu"))

        try:
            self.bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=text,
                parse_mode='HTML',
                reply_markup=markup
            )
        except:
            self.bot.edit_message_text(
                text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode='HTML',
                reply_markup=markup
            )

    def process_withdraw(self, message):
        """Обрабатывает вывод средств"""
        user_id = message.from_user.id
        user_str = str(user_id)

        if user_str not in self.pending_withdraws:
            return False

        try:
            amount = float(message.text)
            stats = self.get_stats(user_id)

            # Проверки
            if amount < MIN_WITHDRAW_REFERRAL:
                self.bot.send_message(
                    message.chat.id,
                    f"<blockquote>❌ Минимум: {MIN_WITHDRAW_REFERRAL} USDT</blockquote>",
                    parse_mode='HTML'
                )
                return True

            if amount > stats['available']:
                self.bot.send_message(
                    message.chat.id,
                    f"<blockquote>❌ Максимум: {stats['available']:.2f} USDT</blockquote>",
                    parse_mode='HTML'
                )
                return True

            # Проверяем и инициализируем структуры
            if 'withdrawn' not in self.referral_data:
                self.referral_data['withdrawn'] = {}

            # Списываем и начисляем
            if user_str not in self.referral_data['earnings']:
                self.referral_data['earnings'][user_str] = {'available': 0.0}

            self.referral_data['earnings'][user_str]['available'] -= amount

            if user_str not in self.referral_data['withdrawn']:
                self.referral_data['withdrawn'][user_str] = 0.0

            self.referral_data['withdrawn'][user_str] += amount

            # Добавляем на основной баланс
            self.game.add_balance(user_id, amount)

            # Удаляем состояние вывода
            del self.pending_withdraws[user_str]
            self.save_referral_data()

            # Отправляем подтверждение
            self.bot.send_message(
                message.chat.id,
               f"<blockquote>✅ <b>Выведено {amount:.2f}$!</b></blockquote>\n",
                parse_mode='HTML'
            )

            return True

        except ValueError:
            self.bot.send_message(
                message.chat.id,
                "<blockquote>❌ Введите число (например: 1.5)</blockquote>",
                parse_mode='HTML'
            )
            return True
        except Exception as e:
            print(f"❌ Ошибка вывода: {e}")
            self.bot.send_message(
                message.chat.id,
                "<blockquote>❌ Ошибка при выводе</blockquote>",
                parse_mode='HTML'
            )
            return True

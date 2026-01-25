[file name]: channel.py
[file content begin]
import telebot
from telebot import types
from datetime import datetime

class WithdrawalChannel:
    def __init__(self, token):
        self.bot = telebot.TeleBot(token)
        self.channel_id = None
        
    def set_channel(self, channel_id):
        """Установка ID канала"""
        self.channel_id = channel_id
        
    def send_withdrawal_notification(self, withdrawal_data):
        """Отправка уведомления о новой заявке в канал"""
        try:
            if not self.channel_id:
                print("❌ ID канала не установлен")
                return None
                
            text = f"""═══════════════════════════
💰 <b>НОВАЯ ЗАЯВКА НА ВЫВОД</b> 💰
═══════════════════════════

<b>📋 ИНФОРМАЦИЯ О ЗАЯВКЕ:</b>
<blockquote>🆔 Номер: <b>#{withdrawal_data['withdrawal_id']}</b>
👤 Пользователь: <b>{withdrawal_data['username']}</b>
👤 ID: <b>{withdrawal_data['user_id']}</b>
💰 Сумма: <b>{withdrawal_data['amount']} USDT</b>
📅 Дата: <b>{withdrawal_data['created_at']}</b></blockquote>

<b>⏳ СТАТУС:</b> <b>ОЖИДАЕТ ПОДТВЕРЖДЕНИЯ</b> ⏳"""

            keyboard = types.InlineKeyboardMarkup(row_width=2)
            keyboard.add(
                types.InlineKeyboardButton(
                    "✅ Одобрить",
                    callback_data=f"channel_approve_{withdrawal_data['withdrawal_id']}"
                ),
                types.InlineKeyboardButton(
                    "❌ Отклонить",
                    callback_data=f"channel_reject_{withdrawal_data['withdrawal_id']}"
                )
            )
            
            message = self.bot.send_message(
                self.channel_id,
                text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            
            return message.message_id
            
        except Exception as e:
            print(f"❌ Ошибка при отправке уведомления в канал: {e}")
            return None
            
    def update_withdrawal_status(self, message_id, withdrawal_data, status, admin_message=None):
        """Обновление статуса заявки в канале"""
        try:
            if not self.channel_id:
                print("❌ ID канала не установлен")
                return
                
            status_text = "✅ ОДОБРЕНО" if status == 'approved' else "❌ ОТКЛОНЕНО"
            status_emoji = "✅" if status == 'approved' else "❌"
            
            text = f"""═══════════════════════════
{status_emoji} <b>ЗАЯВКА ОБРАБОТАНА</b> {status_emoji}
═══════════════════════════

<b>📋 ИНФОРМАЦИЯ О ЗАЯВКЕ:</b>
<blockquote>🆔 Номер: <b>#{withdrawal_data['withdrawal_id']}</b>
👤 Пользователь: <b>{withdrawal_data['username']}</b>
👤 ID: <b>{withdrawal_data['user_id']}</b>
💰 Сумма: <b>{withdrawal_data['amount']} USDT</b>
📅 Дата создания: <b>{withdrawal_data['created_at']}</b>
{status_emoji} Статус: <b>{status_text}</b>
📅 Дата обработки: <b>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</b></blockquote>
{f'<b>💬 СООБЩЕНИЕ:</b>\n<blockquote>{admin_message}</blockquote>' if admin_message else ''}"""
            
            self.bot.edit_message_text(
                text,
                self.channel_id,
                message_id,
                parse_mode='HTML'
            )
            
        except Exception as e:
            print(f"❌ Ошибка при обновлении статуса в канале: {e}")
[file content end]

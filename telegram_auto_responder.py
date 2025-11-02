#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Auto Responder с уведомлениями оператору
Улучшенная версия с исправлением всех проблем
"""

import asyncio
import logging
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import User

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='[%(levelname)s %(asctime)s] %(message)s',
    level=logging.INFO,
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class TelegramAutoResponder:
    """Автоответчик с пересылкой уведомлений оператору"""

    def __init__(self):
        # API credentials
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.phone = os.getenv('PHONE_NUMBER')

        # ID оператора для уведомлений
        self.notification_user_id = int(os.getenv('NOTIFICATION_USER_ID', '0'))

        # Рабочее время
        self.work_hours = {
            'mon_thu': {'start': 9, 'end': 17, 'end_minutes': 30},  # Пн-Чт: 9:00-17:30
            'fri': {'start': 9, 'end': 17, 'end_minutes': 0},        # Пт: 9:00-17:00
            'weekend': [5, 6]  # Сб-Вс
        }

        # Сообщение автоответа
        self.auto_reply_message = os.getenv(
            'AUTO_REPLY_MESSAGE',
            """🌙 Спасибо за ваше сообщение!

Сейчас нерабочее время или выходной день.
Рабочие часы:
• Пн-Чт: 9:00 - 17:30
• Пт: 9:00 - 17:00
• Сб-Вс: выходные

Я отвечу вам в ближайшее рабочее время."""
        )

        # Хранилища
        self.replied_users = {}  # {user_id: date} - кому уже ответили
        # Связь: ID уведомления оператору -> данные отправителя
        self.message_mapping = {}  # {notification_msg_id: {'sender_id': int, 'original_msg_id': int}}

        # Telegram клиент
        self.client = TelegramClient('telegram_session', self.api_id, self.api_hash)

    def is_working_hours(self) -> bool:
        """Проверка рабочего времени с учетом дней недели"""
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        current_weekday = now.weekday()  # 0=Пн, 6=Вс

        # Суббота и воскресенье - нерабочие
        if current_weekday in self.work_hours['weekend']:
            return False

        # Понедельник-четверг: 9:00 - 17:30
        if current_weekday <= 3:
            end_hour = self.work_hours['mon_thu']['end']
            end_minutes = self.work_hours['mon_thu']['end_minutes']
            return (
                current_hour >= self.work_hours['mon_thu']['start'] and
                (current_hour < end_hour or (current_hour == end_hour and current_minute < end_minutes))
            )

        # Пятница: 9:00 - 17:00
        if current_weekday == 4:
            return (
                current_hour >= self.work_hours['fri']['start'] and
                current_hour < self.work_hours['fri']['end']
            )

        return False

    async def handle_new_message(self, event):
        """Обработка новых входящих сообщений"""
        try:
            # Игнорируем не личные чаты
            if not event.is_private:
                return

            sender_id = event.sender_id
            me = await self.client.get_me()

            # Игнорируем сообщения от себя
            if sender_id == me.id:
                return

            # Обрабатываем ответы оператора
            if sender_id == self.notification_user_id and event.is_reply:
                await self.handle_operator_reply(event)
                return

            # Игнорируем остальные сообщения от оператора
            if sender_id == self.notification_user_id:
                return

            # Проверяем рабочее время
            if not self.is_working_hours():
                await self.handle_after_hours_message(event)

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")

    async def handle_after_hours_message(self, event):
        """Обработка сообщений вне рабочего времени"""
        try:
            sender_id = event.sender_id
            current_date = datetime.now().date()

            # Получаем информацию об отправителе
            sender = await event.get_sender()
            sender_name = sender.first_name or "Unknown"
            sender_username = f"@{sender.username}" if sender.username else "без username"

            # Отправляем автоответ (один раз в день)
            if sender_id not in self.replied_users or self.replied_users[sender_id] != current_date:
                await event.respond(self.auto_reply_message)
                self.replied_users[sender_id] = current_date
                logger.info(f"Автоответ отправлен: {sender_name}")

            # Отправляем уведомление оператору
            if self.notification_user_id:
                await self.send_notification_to_operator(event, sender_name, sender_username, sender_id)

        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения вне рабочего времени: {e}")

    async def send_notification_to_operator(self, event, sender_name, sender_username, sender_id):
        """Отправка уведомления оператору"""
        try:
            # Текст уведомления
            notification_text = f"""📩 НОВОЕ СООБЩЕНИЕ В НЕРАБОЧЕЕ ВРЕМЯ

👤 От: {sender_name} ({sender_username})
🆔 ID: {sender_id}
🕐 Время: {datetime.now().strftime('%H:%M:%S')}

💬 Ответьте на ПЕРЕСЛАННОЕ сообщение ниже, чтобы отправить ответ пользователю."""

            # Отправляем уведомление
            notification_msg = await self.client.send_message(
                self.notification_user_id,
                notification_text
            )

            # Пересылаем оригинальное сообщение (поддержка медиа)
            forwarded_msg = await self.client.forward_messages(
                self.notification_user_id,
                event.message
            )

            # Сохраняем связь: ID пересланного сообщения -> данные отправителя
            self.message_mapping[forwarded_msg.id] = {
                'sender_id': sender_id,
                'original_msg_id': event.message.id
            }

            logger.info(f"Уведомление отправлено оператору для {sender_id}")

        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления: {e}")

    async def handle_operator_reply(self, event):
        """Обработка ответов оператора"""
        try:
            reply_to_msg_id = event.message.reply_to_msg_id

            # Ищем данные оригинального отправителя
            mapping_data = self.message_mapping.get(reply_to_msg_id)

            if not mapping_data:
                await event.reply("❌ Не найден оригинальный отправитель для этого сообщения")
                return

            original_sender_id = mapping_data['sender_id']

            # Отправляем ответ пользователю
            # Проверяем тип сообщения (текст, медиа и т.д.)
            if event.message.text:
                # Текстовое сообщение
                await self.client.send_message(
                    original_sender_id,
                    event.message.text
                )
            elif event.message.media:
                # Медиафайл
                await self.client.send_file(
                    original_sender_id,
                    event.message.media,
                    caption=event.message.message
                )
            else:
                await event.reply("⚠️ Неподдерживаемый тип сообщения")
                return

            logger.info(f"Ответ отправлен пользователю {original_sender_id}")
            await event.reply("✅ Ответ успешно отправлен")

            # Удаляем из маппинга (необязательно, очистится в полночь)
            # del self.message_mapping[reply_to_msg_id]

        except Exception as e:
            logger.error(f"Ошибка при отправке ответа: {e}")
            await event.reply(f"❌ Ошибка: {e}")

    async def handle_outgoing_message(self, event):
        """Обработка исходящих сообщений (когда отвечаем вручную)"""
        try:
            # Если ответили вручную - сбрасываем флаг автоответа
            chat_id = event.chat_id

            if chat_id in self.replied_users:
                # Можно удалить, чтобы отправить еще один автоответ в тот же день
                # del self.replied_users[chat_id]
                pass

        except Exception as e:
            logger.error(f"Ошибка при обработке исходящего сообщения: {e}")

    async def clear_daily_data(self):
        """Очистка данных каждый день в полночь"""
        while True:
            try:
                now = datetime.now()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_midnight = (tomorrow - now).total_seconds()

                await asyncio.sleep(seconds_until_midnight)

                # Очищаем данные
                self.replied_users.clear()
                self.message_mapping.clear()
                logger.info("Ежедневная очистка данных выполнена")

            except Exception as e:
                logger.error(f"Ошибка при очистке данных: {e}")
                await asyncio.sleep(3600)  # Повтор через час при ошибке

    async def start(self):
        """Запуск автоответчика"""
        await self.client.start(phone=self.phone)

        me = await self.client.get_me()

        print("=" * 60)
        print("🤖 TELEGRAM AUTO RESPONDER - УЛУЧШЕННАЯ ВЕРСИЯ")
        print("=" * 60)
        print(f"👤 Аккаунт: {me.first_name} (@{me.username})")
        print(f"⏰ Рабочее время:")
        print(f"   • Пн-Чт: 9:00 - 17:30")
        print(f"   • Пт: 9:00 - 17:00")
        print(f"   • Сб-Вс: выходные")
        print(f"🕐 Текущее время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}")
        print(f"📊 Статус: {'✅ Рабочее время' if self.is_working_hours() else '🌙 Нерабочее время'}")
        if self.notification_user_id:
            print(f"📬 Уведомления оператору: ID {self.notification_user_id}")
        print("=" * 60)
        print("✅ Автоответчик запущен и работает...")
        print()

        # Регистрируем обработчики
        @self.client.on(events.NewMessage(incoming=True))
        async def incoming_handler(event):
            await self.handle_new_message(event)

        @self.client.on(events.NewMessage(outgoing=True))
        async def outgoing_handler(event):
            await self.handle_outgoing_message(event)

        # Запускаем задачу очистки
        asyncio.create_task(self.clear_daily_data())

        # Держим клиент активным
        await self.client.run_until_disconnected()

    async def stop(self):
        """Остановка автоответчика"""
        logger.info("Остановка...")
        await self.client.disconnect()


async def main():
    """Главная функция"""
    try:
        responder = TelegramAutoResponder()
        await responder.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа завершена")

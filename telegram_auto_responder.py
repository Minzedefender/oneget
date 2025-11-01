#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Auto Responder
Автоматический ответчик для личного Telegram аккаунта
"""

import asyncio
import logging
from datetime import datetime, time
from typing import Dict, Optional
import os
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.tl.types import User

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='[%(levelname) 5s/%(asctime)s] %(name)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class TelegramAutoResponder:
    """Класс для автоматических ответов в Telegram"""

    def __init__(self):
        # API credentials (получить на https://my.telegram.org)
        self.api_id = int(os.getenv('API_ID', '0'))
        self.api_hash = os.getenv('API_HASH', '')
        self.phone = os.getenv('PHONE_NUMBER', '')

        # Рабочее время (формат 24-часовой)
        self.work_start = time(int(os.getenv('WORK_START_HOUR', '9')), 0)  # 9:00
        self.work_end = time(int(os.getenv('WORK_END_HOUR', '18')), 0)    # 18:00

        # Выходные дни (0 = Понедельник, 6 = Воскресенье)
        self.weekend_days = [5, 6]  # Суббота и Воскресенье

        # Время ожидания перед автоответом (в секундах)
        self.response_delay = int(os.getenv('RESPONSE_DELAY_MINUTES', '10')) * 60

        # Сообщения
        self.busy_message = os.getenv(
            'BUSY_MESSAGE',
            'Извините, сейчас занят. Перезвоню при первой возможности.'
        )
        self.after_hours_message = os.getenv(
            'AFTER_HOURS_MESSAGE',
            'Сейчас не рабочее время. Отвечу в ближайшее рабочее время.'
        )

        # Словарь для отслеживания необработанных сообщений
        # {chat_id: {'last_message_time': datetime, 'task': asyncio.Task}}
        self.pending_messages: Dict[int, Dict] = {}

        # Множество чатов, которым уже отправили автоответ
        self.auto_responded_chats = set()

        # Telegram клиент
        self.client = TelegramClient('telegram_session', self.api_id, self.api_hash)

    def is_working_hours(self) -> bool:
        """Проверка, рабочее ли время сейчас"""
        now = datetime.now()

        # Проверка выходных дней
        if now.weekday() in self.weekend_days:
            return False

        # Проверка времени суток
        current_time = now.time()
        return self.work_start <= current_time <= self.work_end

    async def schedule_auto_response(self, chat_id: int, is_working_hours: bool):
        """Планирование автоответа через заданное время"""
        try:
            # Ждем указанное время
            await asyncio.sleep(self.response_delay)

            # Проверяем, не ответили ли мы уже вручную
            if chat_id in self.pending_messages:
                # Выбираем сообщение в зависимости от времени
                message = self.busy_message if is_working_hours else self.after_hours_message

                # Отправляем автоответ
                await self.client.send_message(chat_id, message)
                logger.info(f"Отправлен автоответ в чат {chat_id}")

                # Удаляем из списка ожидания
                del self.pending_messages[chat_id]
                self.auto_responded_chats.add(chat_id)

        except asyncio.CancelledError:
            logger.debug(f"Автоответ для чата {chat_id} отменен (ответили вручную)")
        except Exception as e:
            logger.error(f"Ошибка при отправке автоответа: {e}")

    async def handle_incoming_message(self, event):
        """Обработка входящих сообщений"""
        try:
            # Получаем информацию о чате
            chat = await event.get_chat()
            chat_id = event.chat_id

            # Игнорируем сообщения от ботов и групп
            if not isinstance(chat, User) or chat.bot:
                return

            # Игнорируем исходящие сообщения
            if event.out:
                return

            logger.info(f"Получено сообщение от {chat.first_name} ({chat_id})")

            # Проверяем рабочее время
            is_working = self.is_working_hours()

            # Если не рабочее время - отправляем ответ сразу
            if not is_working and chat_id not in self.auto_responded_chats:
                await self.client.send_message(chat_id, self.after_hours_message)
                logger.info(f"Отправлено сообщение о нерабочем времени в чат {chat_id}")
                self.auto_responded_chats.add(chat_id)
                return

            # Если есть активная задача для этого чата - отменяем её
            if chat_id in self.pending_messages:
                if 'task' in self.pending_messages[chat_id]:
                    self.pending_messages[chat_id]['task'].cancel()

            # Создаем новую задачу автоответа
            task = asyncio.create_task(
                self.schedule_auto_response(chat_id, is_working)
            )

            self.pending_messages[chat_id] = {
                'last_message_time': datetime.now(),
                'task': task
            }

        except Exception as e:
            logger.error(f"Ошибка при обработке входящего сообщения: {e}")

    async def handle_outgoing_message(self, event):
        """Обработка исходящих сообщений"""
        try:
            chat_id = event.chat_id

            # Если мы ответили - отменяем автоответ
            if chat_id in self.pending_messages:
                if 'task' in self.pending_messages[chat_id]:
                    self.pending_messages[chat_id]['task'].cancel()
                del self.pending_messages[chat_id]
                logger.info(f"Отменен автоответ для чата {chat_id} (ответили вручную)")

            # Сбрасываем флаг автоответа
            if chat_id in self.auto_responded_chats:
                self.auto_responded_chats.remove(chat_id)

        except Exception as e:
            logger.error(f"Ошибка при обработке исходящего сообщения: {e}")

    async def start(self):
        """Запуск бота"""
        logger.info("Запуск Telegram Auto Responder...")

        # Подключение к Telegram
        await self.client.start(phone=self.phone)
        logger.info("Успешно подключено к Telegram")

        # Получаем информацию о себе
        me = await self.client.get_me()
        logger.info(f"Работаем от имени: {me.first_name} (@{me.username})")
        logger.info(f"Рабочие часы: {self.work_start.strftime('%H:%M')} - {self.work_end.strftime('%H:%M')}")
        logger.info(f"Задержка автоответа: {self.response_delay // 60} минут")

        # Регистрируем обработчики событий
        @self.client.on(events.NewMessage(incoming=True))
        async def incoming_handler(event):
            await self.handle_incoming_message(event)

        @self.client.on(events.NewMessage(outgoing=True))
        async def outgoing_handler(event):
            await self.handle_outgoing_message(event)

        logger.info("Автоответчик запущен и работает...")

        # Держим соединение активным
        await self.client.run_until_disconnected()

    async def stop(self):
        """Остановка бота"""
        logger.info("Остановка автоответчика...")

        # Отменяем все активные задачи
        for chat_id, data in self.pending_messages.items():
            if 'task' in data:
                data['task'].cancel()

        await self.client.disconnect()
        logger.info("Автоответчик остановлен")


async def main():
    """Главная функция"""
    responder = TelegramAutoResponder()

    try:
        await responder.start()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки...")
        await responder.stop()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        await responder.stop()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа завершена")

# -*- coding: utf-8 -*-
"""
Конфигурационный файл для Telegram Auto Responder
"""

# Telegram API настройки
# Получить API credentials можно на https://my.telegram.org
API_ID = 'your_api_id'
API_HASH = 'your_api_hash'
PHONE_NUMBER = '+1234567890'  # Ваш номер телефона в международном формате

# Рабочее время (24-часовой формат)
WORK_START_HOUR = 9   # Начало рабочего дня (9:00)
WORK_END_HOUR = 18    # Конец рабочего дня (18:00)

# Задержка перед автоответом (в минутах)
RESPONSE_DELAY_MINUTES = 10  # Автоответ через 10 минут

# Сообщения для автоответа
BUSY_MESSAGE = """Извините, сейчас занят. Перезвоню при первой возможности."""

AFTER_HOURS_MESSAGE = """Сейчас не рабочее время. Отвечу в ближайшее рабочее время."""

# Выходные дни (0 = Понедельник, 6 = Воскресенье)
WEEKEND_DAYS = [5, 6]  # Суббота и Воскресенье

# Настройки логирования
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR

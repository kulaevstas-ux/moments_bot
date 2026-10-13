#!/bin/bash
# Скрипт для остановки всех экземпляров бота

echo "🔍 Ищем процессы бота..."

# Находим и завершаем все процессы Python, связанные с ботом
pkill -9 -f "python.*run.py" 2>/dev/null
pkill -9 -f "python.*bot.main" 2>/dev/null
pkill -9 -f "python.*bot" 2>/dev/null

# Также ищем по PID файлам и другим признакам
ps aux | grep -i python | grep -E "run\.py|bot|8182901376" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null

# Ждём немного
sleep 3

# Проверяем, остались ли процессы
REMAINING=$(ps aux | grep -E "python.*run\.py|python.*bot\.main|python.*bot|8182901376" | grep -v grep | wc -l | tr -d ' ')

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ Все процессы бота успешно остановлены"
else
    echo "⚠️ Найдено $REMAINING процессов. Принудительное завершение..."
    ps aux | grep -E "python.*run\.py|python.*bot\.main|python.*bot|8182901376" | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null
    sleep 2
    echo "✅ Процессы завершены"
fi

# Очищаем веб-хук через Telegram API (если он установлен)
echo ""
echo "🔧 Очищаем веб-хук (если установлен)..."
cd "$(dirname "$0")"

# Загружаем токен из .env
if [ -f .env ]; then
    BOT_TOKEN=$(grep BOT_TOKEN .env | cut -d '=' -f2 | tr -d '"' | tr -d "'" | xargs)
    if [ ! -z "$BOT_TOKEN" ]; then
        curl -s "https://api.telegram.org/bot${BOT_TOKEN}/deleteWebhook?drop_pending_updates=true" > /dev/null 2>&1
        echo "✅ Веб-хук очищен"
    else
        echo "⚠️ Не удалось получить токен из .env"
    fi
else
    echo "⚠️ Файл .env не найден"
fi

echo ""
echo "✅ Готово! Теперь можно запускать бота заново."


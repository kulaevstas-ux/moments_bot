#!/bin/bash
# Скрипт для перезапуска бота

echo "🛑 Останавливаем бота..."
./stop_bot.sh

echo ""
echo "⏳ Ждём 2 секунды..."
sleep 2

echo ""
echo "🚀 Запускаем бота..."
cd "$(dirname "$0")"
python3 run.py


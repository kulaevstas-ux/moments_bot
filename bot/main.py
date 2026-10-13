import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import BOT_TOKEN, YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID
from bot.handlers import start, upload, style, payment, generate

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    """Основная функция запуска бота"""
    # Проверяем токен
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Установите BOT_TOKEN в переменных окружения или в config.py")
        return
    
    # Инициализируем бота (aiogram 3.x использует стандартные таймауты)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрируем роутеры
    dp.include_router(start.router)
    dp.include_router(upload.router)
    dp.include_router(style.router)
    dp.include_router(payment.router)
    dp.include_router(generate.router)
    
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.warning(
            "YOOKASSA_SHOP_ID или YOOKASSA_SECRET_KEY не заданы — оплата ЮKassa недоступна"
        )

    logger.info("Запускаем бота...")
    # Не проверяем подключение заранее - start_polling сделает это сам
    
    # Запускаем polling с обработкой ошибок
    try:
        await dp.start_polling(
            bot,
            close_bot_session=True,
            allowed_updates=["message", "callback_query"]  # Обрабатываем только нужные типы обновлений
        )
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при работе бота: {e}", exc_info=True)
    finally:
        # Закрываем сессию бота
        try:
            if bot.session:
                await bot.session.close()
                logger.info("Сессия бота закрыта")
        except Exception as e:
            logger.warning(f"Ошибка при закрытии сессии: {e}")

if __name__ == "__main__":
    asyncio.run(main())


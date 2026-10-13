from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot.services.utils import (
    get_user_data,
    get_user_photo_file_ids,
    set_user_generated_images,
    complete_session,
    update_user_data,
)
from bot.services.proxy_api import generate_coloring_images
from bot.services.pdf_generator import create_coloring_pdf
from bot.config import STYLES, DATA_DIR
from pathlib import Path
import asyncio
import logging

logger = logging.getLogger(__name__)

router = Router()

async def generate_coloring(message: Message, user_id: int, state: FSMContext = None):
    """Генерирует раскраску для пользователя"""
    try:
        # Получаем данные пользователя
        user_data = get_user_data(user_id)
        photo_file_ids = get_user_photo_file_ids(user_id)
        style_key = user_data.get("style")
        
        if not photo_file_ids or not style_key:
            await _generation_problem(message, user_id, state)
            return
        
        # Получаем фото из Telegram по file_id
        bot = message.bot
        images_data = []
        for file_id in photo_file_ids:
            try:
                # Получаем файл из Telegram
                file = await bot.get_file(file_id)
                
                # Скачиваем фото в память (BytesIO)
                from io import BytesIO
                photo_bytes = BytesIO()
                await bot.download_file(file.file_path, destination=photo_bytes)
                photo_bytes.seek(0)
                images_data.append(photo_bytes.read())
            except Exception as e:
                logger.error(f"Ошибка при получении фото {file_id}: {e}")
                continue
        
        if not images_data:
            await _generation_problem(message, user_id, state)
            return
        
        # Генерируем раскраски (возвращает байты изображений)
        generated_images = await generate_coloring_images(images_data, style_key)
        
        if not generated_images:
            await _generation_problem(message, user_id, state)
            return
        
        # Сохраняем информацию о сгенерированных изображениях
        # (сохраняем количество, так как байты слишком большие для JSON)
        set_user_generated_images(user_id, [f"generated_{i}" for i in range(len(generated_images))])
        
        # Создаём PDF из байтов (временно сохраняем в data/)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = DATA_DIR / f"{user_id}_coloring.pdf"
        success = create_coloring_pdf(generated_images, str(pdf_path))
        
        if not success:
            await _generation_problem(message, user_id, state)
            return
        
        # Отправляем PDF
        from aiogram.types import FSInputFile
        
        text = (
            "✅ <b>Ваша раскраска готова!</b>\n\n"
            "Теперь ее можно скачать в формате PDF, чтобы распечатать. "
            "Надеемся, результат вам понравится!\n\n"
            "🔸 У нас действует акция: чем больше фото, тем меньше цена!\n"
            "- от 1 до 5 фото: 50 ₽ за страницу\n"
            "- от 6 до 10 фото: 30 ₽ за страницу\n\n"
            "Если возникнут какие-либо вопросы, обращайтесь в поддержку: @kulaev_stas"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Создать еще раскраску",
                callback_data="restart"
            )]
        ])
        
        # Используем FSInputFile для отправки PDF
        pdf_document = FSInputFile(pdf_path, filename=f"coloring_{user_id}.pdf")
        pdf_msg = await message.answer_document(
            document=pdf_document,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        
        # Сохраняем message_id сообщения с PDF для последующего удаления кнопки
        if state:
            await state.update_data(pdf_message_id=pdf_msg.message_id)
        
        # Отмечаем сессию как завершённую (пользователь получил PDF)
        complete_session(user_id)
        update_user_data(user_id, {"order_done": True})
        
        # Удаляем сообщение о начале генерации (если есть)
        if state:
            state_data = await state.get_data()
            generation_message_id = state_data.get("generation_message_id")
            if generation_message_id:
                try:
                    await message.bot.delete_message(
                        chat_id=message.chat.id,
                        message_id=generation_message_id
                    )
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение о генерации: {e}")
        
        # Удаляем временный PDF файл после отправки
        try:
            import os
            os.remove(pdf_path)
        except Exception as e:
            logger.warning(f"Не удалось удалить временный PDF: {e}")

    except Exception as e:
        logger.error(f"Ошибка при генерации раскраски: {e}", exc_info=True)
        await _generation_problem(message, user_id, state)


async def _generation_problem(message: Message, user_id: int, state: FSMContext = None):
    """Сообщение, если раскраску не удалось создать"""
    from html import escape
    if state:
        state_data = await state.get_data()
        generation_message_id = state_data.get("generation_message_id")
        if generation_message_id:
            try:
                await message.bot.delete_message(message.chat.id, generation_message_id)
            except Exception:
                pass
    payment_id = get_user_data(user_id).get("payment_id") or "—"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Обратиться в поддержку", url="https://t.me/kulaev_stas")]
    ])
    await message.answer(
        "🤨 Во время генерации раскраски произошла какая-то неполадка\n\n"
        "✅ Не переживайте, а напишите нашему специалисту поддержки, "
        "он оперативно решит вашу проблему: @kulaev_stas\n\n"
        "Идентификатор платежа:\n"
        f"<code>{escape(str(payment_id))}</code>",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(lambda c: c.data == "restart")
async def restart_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Создать ещё одну раскраску'"""
    from bot.handlers.start import cmd_start
    from bot.services.utils import reset_user_data
    
    # Отвечаем на callback сразу, чтобы убрать индикатор загрузки
    await callback.answer()
    
    # Убираем кнопку из сообщения с PDF (обновляем сообщение без кнопки)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning(f"Не удалось убрать кнопку из сообщения с PDF: {e}")
    
    # Сбрасываем данные пользователя перед вызовом /start
    user_id = callback.from_user.id
    reset_user_data(user_id)
    await state.clear()
    
    # Создаём Message объект из callback для вызова cmd_start
    # cmd_start ожидает Message, но у нас CallbackQuery
    # Используем callback.message как Message объект
    await cmd_start(callback.message, state)


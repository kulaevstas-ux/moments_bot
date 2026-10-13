from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.config import ASSETS_DIR, EXAMPLES_URL
from bot.services.utils import reset_user_data, create_session
from bot.handlers.states import UploadStates
import os
import logging

logger = logging.getLogger(__name__)
router = Router()

def upload_instruction_text() -> str:
    """Текст шага загрузки фото"""
    return (
        "<b>Супер! Теперь загрузи свои фото, которые хочешь превратить в раскраску.</b>\n\n"
        "📎 Присылай мне фото из галереи по одному или сразу несколько.\n\n"
        "⚠️ Максимум <b>10 фото</b>.\n\n"
        "Совет: лучше всего подходят фото с <b>чётким контуром</b> и <b>хорошим освещением</b>."
    )

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    try:
        # Сбрасываем состояние пользователя
        user_id = message.from_user.id
        reset_user_data(user_id)
        # Создаём новую сессию
        create_session(user_id)
        await state.clear()
        
        # Приветственное сообщение
        text = (
            "💫 <b>Привет! Я — волшебная палочка для твоих фотографий!</b>\n\n"
            "<b>Что я умею:</b>\n"
            "Помогу превратить твои моменты из фотографий в классные контурные раскраски.\n\n"
            "<b>Как меня можно использовать:</b>\n"
            "Создай уникальный подарок, развивашку для ребёнка или просто арт-терапию для себя!\n\n"
            "⬇️ Можешь посмотреть примеры созданных мной раскрасок, либо сразу приступить к созданию своей раскраски."
        )
        
        # Кнопки
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ Создать раскраску", callback_data="create_coloring")],
            [InlineKeyboardButton(text="Посмотреть примеры", url="https://moments_bot.tilda.ws/tdocs/primeri-udc22ssu0a08txs")]
        ])
        
        # Отправляем сообщение с фото-заглушкой
        placeholder_path = ASSETS_DIR / "start_placeholder.jpg"
        try:
            if placeholder_path.exists():
                from aiogram.types import FSInputFile
                photo = FSInputFile(placeholder_path)
                await message.answer_photo(
                    photo=photo,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            else:
                # Если фото нет, отправляем просто текст
                await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Ошибка при отправке фото: {e}")
            # Если ошибка с фото, отправляем просто текст
            await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Ошибка в обработчике /start: {e}", exc_info=True)
        try:
            await message.answer("Произошла ошибка. Попробуйте позже.")
        except:
            pass

@router.callback_query(F.data == "create_coloring")
async def create_coloring_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Создать раскраску'"""
    try:
        # Подтверждаем callback сразу
        await callback.answer()
        
        # Удаляем предыдущее сообщение
        try:
            await callback.message.delete()
        except:
            pass
        
        text = upload_instruction_text()
        
        # Используем parse_mode="HTML" для форматирования текста
        msg = await callback.message.answer(text, parse_mode="HTML")
        # Сохраняем ID сообщения с инструкциями для последующего удаления
        await state.update_data(upload_instruction_message_id=msg.message_id)
        await state.set_state(UploadStates.uploading_photos)
    except Exception as e:
        logger.error(f"Ошибка в обработчике create_coloring: {e}", exc_info=True)
        try:
            await callback.answer("Произошла ошибка. Попробуйте позже.", show_alert=True)
        except:
            pass


from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot.config import STYLES, ASSETS_DIR, MIN_PHOTOS, MAX_PHOTOS
from bot.services.utils import get_user_photo_count, set_user_style

router = Router()

@router.callback_query(F.data == "choose_style")
async def choose_style_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбора стиля"""
    user_id = callback.from_user.id
    
    # Проверяем количество фото
    photo_count = get_user_photo_count(user_id)
    if photo_count < MIN_PHOTOS:
        await callback.answer(f"Нужно минимум {MIN_PHOTOS} фото!", show_alert=True)
        return
    if photo_count > MAX_PHOTOS:
        await callback.answer("Можно загрузить максимум 10 фото", show_alert=True)
        return

    await callback.answer()
    await state.set_state(None)

    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except:
        pass
    
    text = (
        "✨ <b>Время магии!</b>\n"
        "Выбери стиль для своей раскраски.\n\n"
        "Перед выбором, можешь посмотреть примеры, нажав на кнопку «Посмотреть примеры»"
    )
    
    # Создаём кнопки со стилями (сетка 2x3)
    buttons = []
    
    # Первая строка: Дисней, Аниме
    buttons.append([
        InlineKeyboardButton(text="🏰 Дисней", callback_data=f"style_disney"),
        InlineKeyboardButton(text="🪭 Аниме", callback_data=f"style_anime")
    ])
    
    # Вторая строка: Симпсоны, Комикс
    buttons.append([
        InlineKeyboardButton(text="🟡 Симпсоны", callback_data=f"style_simpsons"),
        InlineKeyboardButton(text="💬 Комикс", callback_data=f"style_comics")
    ])
    
    # Кнопка с примерами
    buttons.append([
        InlineKeyboardButton(text="Посмотреть примеры", url="https://moments_bot.tilda.ws/tdocs/stili-u54gvl0tk5ye4rs")
    ])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    # Отправляем сообщение с фото-заглушкой
    placeholder_path = ASSETS_DIR / "styles_placeholder.jpg"
    try:
        if placeholder_path.exists():
            # Используем FSInputFile для более эффективной загрузки
            from aiogram.types import FSInputFile
            photo = FSInputFile(placeholder_path)
            await callback.message.answer_photo(
                photo=photo,
                caption=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        # Если ошибка с фото, отправляем просто текст
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Ошибка при отправке фото: {e}")
        await callback.message.answer(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data.startswith("style_"))
async def style_selected_callback(callback: CallbackQuery, state: FSMContext):
    """Обработчик выбранного стиля: сразу открывает форму оплаты"""
    user_id = callback.from_user.id

    style_key = callback.data.replace("style_", "")
    if style_key not in STYLES:
        await callback.answer("Неизвестный стиль!", show_alert=True)
        return

    photo_count = get_user_photo_count(user_id)
    if photo_count < MIN_PHOTOS or photo_count > MAX_PHOTOS:
        await callback.answer("Проверьте количество фото: от 1 до 10.", show_alert=True)
        return

    await callback.answer()

    set_user_style(user_id, style_key)

    try:
        await callback.message.delete()
    except Exception:
        pass

    from bot.handlers.payment import open_payment
    await open_payment(callback.message, user_id, state)


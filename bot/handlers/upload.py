import asyncio

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from bot.config import MAX_PHOTOS, MIN_PHOTOS
from bot.services.utils import (
    add_user_photo,
    clear_user_photos,
    get_user_photo_count,
    get_user_photo_file_ids,
)
from bot.handlers.states import UploadStates
from bot.handlers.start import upload_instruction_text

router = Router()
_upload_locks: dict[int, asyncio.Lock] = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    if user_id not in _upload_locks:
        _upload_locks[user_id] = asyncio.Lock()
    return _upload_locks[user_id]


@router.message(F.photo, StateFilter(UploadStates.uploading_photos))
async def handle_photo_upload(message: Message, state: FSMContext):
    """Обработчик загрузки фотографий"""
    await _remember_photo(message, state, message.photo[-1].file_id)


@router.message(F.document, StateFilter(UploadStates.uploading_photos))
async def handle_document_upload(message: Message, state: FSMContext):
    """Фото без сжатия Telegram присылает файлом"""
    document = message.document
    if document and _is_image_document(document):
        await _remember_photo(message, state, document.file_id)
        return
    await _ask_for_uncompressed_photo(message, state)


def _is_image_document(document) -> bool:
    mime = (document.mime_type or "").lower()
    if mime.startswith("image/"):
        return True
    name = (document.file_name or "").lower()
    return name.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".gif"))


async def _ask_for_uncompressed_photo(message: Message, state: FSMContext):
    state_data = await state.get_data()
    hint_id = state_data.get("uncompressed_hint_message_id")
    if hint_id:
        try:
            await message.bot.delete_message(message.chat.id, hint_id)
        except Exception:
            pass
    msg = await message.answer("Загрузите фото без сжатия")
    await state.update_data(uncompressed_hint_message_id=msg.message_id)


async def _remember_photo(message: Message, state: FSMContext, file_id: str):
    user_id = message.from_user.id
    existing_file_ids = get_user_photo_file_ids(user_id)
    if file_id in existing_file_ids:
        if not message.media_group_id:
            await _show_upload_status(message, state, duplicate=True)
        return

    is_first_in_group = False
    if message.media_group_id:
        state_data = await state.get_data()
        processed_groups = state_data.get("processed_media_groups", [])
        if message.media_group_id not in processed_groups:
            is_first_in_group = True
            processed_groups.append(message.media_group_id)
            await state.update_data(processed_media_groups=processed_groups)
            await asyncio.sleep(1.5)
        else:
            async with _lock_for(user_id):
                add_user_photo(user_id, file_id)
                if get_user_photo_count(user_id) > MAX_PHOTOS:
                    await _show_upload_status(message, state)
            return

    async with _lock_for(user_id):
        add_user_photo(user_id, file_id)
        if is_first_in_group or not message.media_group_id:
            await _show_upload_status(message, state)


async def _show_upload_status(message: Message, state: FSMContext, duplicate: bool = False):
    """Показывает счётчик фото или ошибку, если их больше 10"""
    user_id = message.from_user.id
    photo_count = get_user_photo_count(user_id)
    state_data = await state.get_data()

    hint_id = state_data.get("uncompressed_hint_message_id")
    if hint_id:
        try:
            await message.bot.delete_message(message.chat.id, hint_id)
        except Exception:
            pass
        await state.update_data(uncompressed_hint_message_id=None)

    if state_data.get("upload_instruction_message_id"):
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=state_data["upload_instruction_message_id"],
            )
        except Exception:
            pass
        await state.update_data(upload_instruction_message_id=None)

    if state_data.get("upload_message_id"):
        try:
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=state_data["upload_message_id"],
            )
        except Exception:
            pass

    if photo_count > MAX_PHOTOS:
        text = (
            "⚠️ <b>Можно загрузить максимум 10 фото</b>\n"
            f"Вы загрузили {photo_count}\n\n"
            "Перезапустите бота командой /start, и заново загрузите фотографии так, "
            "чтобы их общее количество не превышало 10"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Загрузить фото заново", callback_data="reupload_photos")]
        ])
        msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
        await state.update_data(upload_message_id=msg.message_id)
        return

    if photo_count < MIN_PHOTOS:
        return

    duplicate_note = "Это фото уже было загружено ранее.\n\n" if duplicate else ""
    style_line = (
        "🎨 Или можешь перейти к самому интересному — выбору стиля"
        if duplicate
        else "🎨 <b>Или можешь перейти к самому интересному — выбору стиля!</b>"
    )
    text = (
        f"{duplicate_note}"
        f"📥 <b>{photo_count} фото загружено.</b>\n\n"
        "Если хочешь добавить ещё фото — просто отправь их.\n\n"
        f"{style_line}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎨 Выбрать стиль для {photo_count} фото",
            callback_data="choose_style",
        )]
    ])
    msg = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(upload_message_id=msg.message_id)


@router.callback_query(F.data == "reupload_photos")
async def reupload_photos_callback(callback: CallbackQuery, state: FSMContext):
    """Начинает загрузку заново и не учитывает уже присланные фото"""
    await callback.answer()
    clear_user_photos(callback.from_user.id)
    await state.set_state(UploadStates.uploading_photos)
    await state.update_data(upload_message_id=None, processed_media_groups=[])
    msg = await callback.message.answer(upload_instruction_text(), parse_mode="HTML")
    await state.update_data(upload_instruction_message_id=msg.message_id)

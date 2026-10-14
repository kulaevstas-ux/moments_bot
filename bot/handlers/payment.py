import asyncio
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.config import MAX_PHOTOS, MIN_PHOTOS, STYLES
from bot.services.utils import (
    calculate_price,
    generation_wait_seconds,
    get_user_data,
    get_user_photo_count,
    price_per_photo,
    set_user_payment,
)
from bot.services.yookassa import (
    YooKassaError,
    create_payment,
    get_payment,
    yookassa_configured,
)

logger = logging.getLogger(__name__)
router = Router()

_lock = asyncio.Lock()
_active_payments: set[str] = set()
_watchers: dict[int, asyncio.Task] = {}


def _invoice_keyboard(price: int, confirmation_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {price} ₽", url=confirmation_url)],
        [InlineKeyboardButton(text="Проверить оплату", callback_data="check_payment")],
    ])


async def _send_invoice(message, user_id, payment_id, price, photo_count, style_name, confirmation_url, state):
    invoice = await message.answer(
        f"💳 <b>Счёт на {price} ₽</b>\n\n"
        f"📷 Фото: {photo_count}\n"
        f"🎨 Стиль: {style_name}\n\n"
        "Нажмите «Оплатить» — откроется форма ЮKassa. "
        "После оплаты вернитесь в этот чат: я проверю платёж, создам раскраску "
        "и пришлю ссылку на чек.",
        reply_markup=_invoice_keyboard(price, confirmation_url),
        parse_mode="HTML",
    )
    _start_watcher(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        payment_id=payment_id,
        state=state,
        invoice_message_id=invoice.message_id,
    )


async def _resend_pending_invoice(message, user_id: int, state: FSMContext) -> bool:
    """Повторно отправляет уже выставленный счёт, чтобы не создать второй платёж"""
    user = get_user_data(user_id)
    payment_id = user.get("payment_id")
    confirmation_url = user.get("confirmation_url")
    if not payment_id or not confirmation_url or user.get("paid") or user.get("order_done"):
        return False

    try:
        payment = await get_payment(payment_id)
    except YooKassaError:
        return False

    if payment.get("status") != "pending":
        return False

    style_key = user.get("style")
    photo_count = get_user_photo_count(user_id)
    style_name = STYLES.get(style_key, {}).get("name", "—")
    price = calculate_price(photo_count)
    await state.clear()
    await message.answer("Счёт уже выставлен. Можно оплатить его по кнопке ниже.")
    await _send_invoice(
        message, user_id, payment_id, price, photo_count, style_name, confirmation_url, state
    )
    return True


async def open_payment(message: Message, user_id: int, state: FSMContext):
    """Создаёт платёж ЮKassa и показывает кнопку со ссылкой на форму оплаты"""
    user_data = get_user_data(user_id)
    photo_count = get_user_photo_count(user_id)
    style_key = user_data.get("style")

    if user_data.get("order_done"):
        await message.answer("Этот заказ уже выполнен. Новый можно начать командой /start.")
        return

    if user_data.get("paid") and user_data.get("payment_id"):
        await message.answer(
            "Оплата уже прошла. Можно ещё раз запустить создание раскраски.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Повторить создание", callback_data="retry_generation")]
            ]),
        )
        return

    if (
        not style_key
        or style_key not in STYLES
        or photo_count < MIN_PHOTOS
        or photo_count > MAX_PHOTOS
    ):
        await message.answer(
            "Ошибка! Проверьте данные заказа или напишите в поддержку @kulaev_stas"
        )
        return

    if not yookassa_configured():
        await message.answer(
            "Оплата пока не настроена. Добавьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в файл .env."
        )
        return

    style_name = STYLES[style_key]["name"]
    unit_price = price_per_photo(photo_count)
    price = calculate_price(photo_count)
    description = f"Раскраска по {photo_count} фото, стиль {style_name}"

    try:
        payment = await create_payment(
            price=price,
            description=description,
            user_id=user_id,
            style_key=style_key,
        )
    except YooKassaError as exc:
        logger.error("Не удалось создать платёж для %s: %s", user_id, exc)
        await message.answer(str(exc))
        return

    payment_id = payment.get("id")
    confirmation_url = (payment.get("confirmation") or {}).get("confirmation_url")
    if not payment_id or not confirmation_url:
        logger.error("В ответе ЮKassa нет ссылки на оплату: %s", payment.get("id"))
        await message.answer("ЮKassa не вернула ссылку на оплату. Попробуйте ещё раз.")
        return

    set_user_payment(user_id, payment_id, confirmation_url)
    text = (
        "<b>Почти всё готово! Давай проверим:</b>\n\n"
        f"📷 Количество фото: {photo_count}\n"
        f"🎨 Стиль: {style_name}\n"
        f"💰 Стоимость: {price} ₽ (расчёт: {photo_count} * {unit_price} ₽)\n\n"
        "Проверь загруженные фото перед оплатой. Если хочешь загрузить другие фото "
        "или выбрать другой стиль, перезапусти бота командой /start\n\n"
        "<b>Безопасная оплата</b>\n"
        "Нажимай «Оплатить картой», выбирай любой удобный способ оплаты "
        "(СБП, SberPay или любой картой российского банка). "
        "У нас безопасная оплата через официальный сервис приема платежей.\n\n"
        "<b>Что после оплаты?</b>\n"
        "После оплаты я сразу начну делать твою раскраску. "
        "Примерное время создания одной раскраски 30 секунд.\n\n"
        "<b>Акция</b>\n"
        "Чем больше фото, тем меньше цена!\n"
        "- от 1 до 5 фото: 35 ₽ за страницу\n"
        "- от 6 до 10 фото: 30 ₽ за страницу"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {price} ₽", url=confirmation_url)]
    ])
    invoice = await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    _start_watcher(
        bot=message.bot,
        chat_id=message.chat.id,
        user_id=user_id,
        payment_id=payment_id,
        state=state,
        invoice_message_id=invoice.message_id,
    )


@router.callback_query(F.data.startswith("pay_"))
async def payment_callback(callback: CallbackQuery, state: FSMContext):
    """Старые кнопки оплаты тоже открывают форму ЮKassa без запроса почты"""
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await open_payment(callback.message, callback.from_user.id, state)


@router.callback_query(F.data == "check_payment")
async def check_payment_callback(callback: CallbackQuery, state: FSMContext):
    """Ручная проверка статуса платежа"""
    user_id = callback.from_user.id
    user_data = get_user_data(user_id)
    payment_id = user_data.get("payment_id")

    if not payment_id:
        await callback.answer("Счёт не найден. Нажмите «Оплатить картой» ещё раз.", show_alert=True)
        return

    if user_data.get("order_done"):
        await callback.answer("Этот заказ уже выполнен.", show_alert=True)
        return

    if payment_id in _active_payments:
        await callback.answer("Оплата уже получена, создаём раскраску.", show_alert=True)
        return

    try:
        payment = await get_payment(payment_id)
    except YooKassaError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    status = payment.get("status")
    if status == "succeeded":
        await callback.answer()
        await fulfill_payment(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            user_id=user_id,
            payment_id=payment_id,
            state=state,
            invoice_message_id=callback.message.message_id,
        )
        return

    if status == "canceled":
        await callback.answer()
        await notify_payment_failed(
            callback.bot,
            callback.message.chat.id,
            callback.message.message_id,
        )
        return

    await callback.answer(
        "Платёж ещё не поступил. Завершите оплату на форме ЮKassa.",
        show_alert=True,
    )


def _start_watcher(bot, chat_id: int, user_id: int, payment_id: str, state: FSMContext, invoice_message_id: int):
    previous = _watchers.get(user_id)
    if previous and not previous.done():
        previous.cancel()
    _watchers[user_id] = asyncio.create_task(
        _watch_payment(bot, chat_id, user_id, payment_id, state, invoice_message_id)
    )


async def _watch_payment(bot, chat_id, user_id, payment_id, state, invoice_message_id):
    """Ждёт успешную оплату и запускает заказ без повторного нажатия кнопки"""
    try:
        for _ in range(180):
            await asyncio.sleep(5)
            user = get_user_data(user_id)
            if user.get("payment_id") != payment_id or user.get("order_done"):
                return
            try:
                payment = await get_payment(payment_id)
            except YooKassaError as exc:
                logger.warning("Не удалось проверить платёж %s: %s", payment_id, exc)
                continue

            status = payment.get("status")
            if status == "succeeded":
                await fulfill_payment(
                    bot, chat_id, user_id, payment_id, state, invoice_message_id
                )
                return
            if status == "canceled":
                await notify_payment_failed(bot, chat_id, invoice_message_id)
                return
    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.error("Ошибка ожидания платежа %s: %s", payment_id, exc, exc_info=True)


async def fulfill_payment(bot, chat_id, user_id, payment_id, state, invoice_message_id=None):
    """Отмечает оплату и запускает генерацию. Чек уходит после готового PDF."""
    already_paid = False
    async with _lock:
        user = get_user_data(user_id)
        if user.get("payment_id") != payment_id:
            return "stale"
        if user.get("order_done"):
            return "done"
        if payment_id in _active_payments:
            return "busy"
        already_paid = bool(user.get("paid"))
        _active_payments.add(payment_id)
        from bot.services.utils import set_user_paid
        set_user_paid(user_id, True)

    try:
        if invoice_message_id:
            try:
                await bot.delete_message(chat_id, invoice_message_id)
            except Exception:
                pass

        user = get_user_data(user_id)
        photo_count = get_user_photo_count(user_id)
        if not already_paid:
            style_key = user.get("style")
            style_name = STYLES.get(style_key, {}).get("name", "—")
            price = calculate_price(photo_count)
            await bot.send_message(
                chat_id,
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                f"Ваш заказ: расскраска по {photo_count} фото в стиле «{style_name}» "
                f"стоимостью {price} ₽\n\n"
                "Идентификатор платежа:\n"
                f"<code>{payment_id}</code>",
                parse_mode="HTML",
            )

        await _run_generation(
            bot,
            chat_id,
            user_id,
            state,
            generation_wait_seconds(photo_count),
        )
        return "started"
    finally:
        _active_payments.discard(payment_id)


async def notify_payment_failed(bot, chat_id: int, message_id: int = None):
    """Стирает счёт и сообщает, что оплата не прошла"""
    if message_id:
        try:
            await bot.delete_message(chat_id, message_id)
        except Exception:
            pass
    await bot.send_message(
        chat_id,
        "🚫 <b>Оплата не прошла!</b>\n\n"
        "Попробуйте перезапустить бота командой /start и попробовать снова, "
        "выбрав другую карту или способ оплаты",
        parse_mode="HTML",
    )


async def _run_generation(bot, chat_id, user_id, state, wait_seconds: int):
    generation_msg = await bot.send_message(
        chat_id,
        "<b>Создаём вашу раскраску...</b>\n\n"
        f"⏱️ Примерное время ожидания: {wait_seconds} секунд.",
        parse_mode="HTML",
    )
    if state:
        await state.update_data(generation_message_id=generation_msg.message_id)

    from bot.handlers.generate import generate_coloring
    await generate_coloring(generation_msg, user_id, state)


@router.callback_query(F.data == "retry_generation")
async def retry_generation_callback(callback: CallbackQuery, state: FSMContext):
    """Повторная генерация, если оплата уже прошла, а PDF не отправился"""
    user_id = callback.from_user.id
    user = get_user_data(user_id)
    payment_id = user.get("payment_id")

    if user.get("order_done"):
        await callback.answer("Раскраска уже готова.", show_alert=True)
        return
    if not user.get("paid") or not payment_id:
        await callback.answer("Оплаченный заказ не найден.", show_alert=True)
        return
    if payment_id in _active_payments:
        await callback.answer("Уже создаём раскраску.", show_alert=True)
        return

    await callback.answer()
    await fulfill_payment(
        bot=callback.bot,
        chat_id=callback.message.chat.id,
        user_id=user_id,
        payment_id=payment_id,
        state=state,
    )

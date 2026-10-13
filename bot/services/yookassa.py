import asyncio
import logging
import uuid
from datetime import datetime
from html import escape
from typing import Optional
from urllib.parse import urlencode

import aiohttp

from bot.config import (
    YOOKASSA_API_URL,
    YOOKASSA_RETURN_URL,
    YOOKASSA_SECRET_KEY,
    YOOKASSA_SHOP_ID,
)

logger = logging.getLogger(__name__)


class YooKassaError(Exception):
    """Ошибка запроса к API ЮKassa"""


def yookassa_configured() -> bool:
    return bool(YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY)


def format_amount(price: int) -> str:
    return f"{price:.2f}"


async def create_payment(
    price: int,
    description: str,
    user_id: int,
    style_key: str,
) -> dict:
    """Создаёт платёж и возвращает объект ЮKassa с confirmation_url"""
    amount = format_amount(price)
    payload = {
        "amount": {"value": amount, "currency": "RUB"},
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": YOOKASSA_RETURN_URL,
        },
        "description": description[:128],
        "metadata": {
            "user_id": str(user_id),
            "style": style_key,
        },
    }
    return await _request(
        "POST",
        "/payments",
        json_body=payload,
        idempotence_key=str(uuid.uuid4()),
    )


async def get_payment(payment_id: str) -> dict:
    return await _request("GET", f"/payments/{payment_id}")


async def get_receipts(payment_id: str) -> list:
    data = await _request("GET", "/receipts", params={"payment_id": payment_id})
    return data.get("items") or []


def receipt_url(receipt: dict, amount: str) -> Optional[str]:
    """Ссылка на чек: поле API, если оно есть, иначе страница чека по фискальным реквизитам"""
    for key in ("receipt_url", "url", "link"):
        value = receipt.get(key)
        if isinstance(value, str) and value.startswith("https://"):
            return value

    fn = receipt.get("fiscal_storage_number")
    fd = receipt.get("fiscal_document_number")
    fp = receipt.get("fiscal_attribute")
    if not (fn and fd and fp):
        return None

    query = {
        "fn": fn,
        "i": fd,
        "fp": fp,
        "n": "1",
    }
    if amount:
        query["s"] = amount
    registered = _receipt_time(receipt.get("registered_at"))
    if registered:
        query["t"] = registered
    return f"https://consumer.1-ofd.ru/v1?{urlencode(query)}"


async def deliver_receipt(bot, chat_id: int, user_id: int):
    """После генерации отправляет сообщение со ссылкой на чек"""
    from bot.services.utils import get_user_data, update_user_data

    user = get_user_data(user_id)
    if user.get("receipt_sent"):
        return

    payment_id = user.get("payment_id")
    if not payment_id or not yookassa_configured():
        return

    email = user.get("customer_email") or ""
    amount = ""
    try:
        payment = await get_payment(payment_id)
        amount = (payment.get("amount") or {}).get("value") or ""
    except YooKassaError as exc:
        logger.error("Не удалось получить платёж %s для чека: %s", payment_id, exc)

    url = None
    status = None
    for attempt in range(8):
        try:
            receipts = await get_receipts(payment_id)
        except YooKassaError as exc:
            logger.error("Не удалось получить чек %s: %s", payment_id, exc)
            receipts = []

        receipt = _pick_receipt(receipts)
        if receipt:
            status = receipt.get("status")
            url = receipt_url(receipt, amount)
            if url and status == "succeeded":
                break
            if status == "canceled":
                break
        if attempt < 7:
            await asyncio.sleep(5)

    if url:
        safe_url = escape(url, quote=True)
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Открыть чек", url=url)]
        ])
        await bot.send_message(
            chat_id,
            "🧾 <b>Чек об оплате</b>\n\n"
            f"<a href=\"{safe_url}\">Открыть чек</a>",
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        update_user_data(user_id, {"receipt_sent": True, "receipt_url": url})
        return

    if email and status != "canceled":
        await bot.send_message(
            chat_id,
            "🧾 <b>Чек об оплате</b>\n\n"
            f"Ссылку на чек пока не удалось получить. Чек отправлен на {escape(email)}.",
            parse_mode="HTML",
        )
        update_user_data(user_id, {"receipt_sent": True})
        return

    await bot.send_message(
        chat_id,
        "🧾 Не удалось получить ссылку на чек. "
        f"Номер платежа: <code>{escape(str(payment_id))}</code>\n"
        "Напишите в поддержку @kulaev_stas",
        parse_mode="HTML",
    )
    update_user_data(user_id, {"receipt_sent": True})


def _pick_receipt(receipts: list) -> Optional[dict]:
    payments = [item for item in receipts if item.get("type") == "payment"]
    if not payments:
        payments = receipts
    for item in payments:
        if item.get("status") == "succeeded":
            return item
    return payments[0] if payments else None


def _receipt_time(value: Optional[str]) -> str:
    if not value:
        return ""
    raw = value.replace("Z", "+00:00")
    if "." in raw:
        head, tail = raw.split(".", 1)
        tz = ""
        if "+" in tail:
            tz = "+" + tail.split("+", 1)[1]
        elif "-" in tail:
            tz = "-" + tail.split("-", 1)[1]
        raw = head + tz
    try:
        return datetime.fromisoformat(raw).strftime("%Y%m%dT%H%M")
    except ValueError:
        return ""


async def _request(
    method: str,
    path: str,
    json_body: Optional[dict] = None,
    params: Optional[dict] = None,
    idempotence_key: Optional[str] = None,
) -> dict:
    if not yookassa_configured():
        raise YooKassaError("Не заданы YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")

    headers = {"Content-Type": "application/json"}
    if idempotence_key:
        headers["Idempotence-Key"] = idempotence_key

    timeout = aiohttp.ClientTimeout(total=30)
    auth = aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
    url = f"{YOOKASSA_API_URL}{path}"

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                json=json_body,
                params=params,
                headers=headers,
                auth=auth,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    logger.error(
                        "ЮKassa %s %s -> %s: %s",
                        method,
                        path,
                        response.status,
                        data,
                    )
                    raise YooKassaError(_user_message(response.status))
                return data
    except aiohttp.ClientError as exc:
        logger.error("Сеть ЮKassa %s %s: %s", method, path, exc)
        raise YooKassaError("Не удалось связаться с ЮKassa. Попробуйте ещё раз.") from exc


def _user_message(status: int) -> str:
    if status in (401, 403):
        return "ЮKassa отклонила ключ магазина. Проверьте shopId и секретный ключ."
    return "ЮKassa не приняла запрос. Попробуйте ещё раз или напишите @kulaev_stas."

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from bot.config import USERS_DB

def ensure_directories():
    """Создаёт необходимые директории, если их нет"""
    USERS_DB.parent.mkdir(parents=True, exist_ok=True)

def empty_user(session_id: Optional[str] = None) -> Dict:
    """Пустой профиль текущего заказа"""
    return {
        "current_session_id": session_id,
        "photo_count": 0,
        "photo_file_ids": [],
        "style": None,
        "order_id": None,
        "paid": False,
        "generated_images": [],
        "payment_id": None,
        "confirmation_url": None,
        "customer_email": None,
        "receipt_url": None,
        "receipt_sent": False,
        "order_done": False,
    }

def load_users() -> Dict:
    """Загружает данные пользователей из JSON"""
    ensure_directories()
    if USERS_DB.exists():
        try:
            with open(USERS_DB, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Обеспечиваем обратную совместимость со старой структурой
                if "sessions" not in data:
                    data["sessions"] = []
                if "users" not in data:
                    data["users"] = {}
                return data
        except (json.JSONDecodeError, IOError):
            return {"sessions": [], "users": {}}
    return {"sessions": [], "users": {}}

def save_users(users: Dict):
    """Сохраняет данные пользователей в JSON"""
    ensure_directories()
    with open(USERS_DB, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def get_user_data(user_id: int) -> Dict:
    """Получает данные пользователя"""
    data = load_users()
    users = data.get("users", {})
    if str(user_id) not in users:
        users[str(user_id)] = empty_user()
        data["users"] = users
        save_users(data)
    return users[str(user_id)]

def update_user_data(user_id: int, data: Dict):
    """Обновляет данные пользователя"""
    all_data = load_users()
    users = all_data.get("users", {})
    if str(user_id) not in users:
        users[str(user_id)] = {}
    users[str(user_id)].update(data)
    all_data["users"] = users
    save_users(all_data)

def reset_user_data(user_id: int):
    """Сбрасывает данные пользователя"""
    all_data = load_users()
    users = all_data.get("users", {})
    users[str(user_id)] = empty_user()
    all_data["users"] = users
    save_users(all_data)

def add_user_photo(user_id: int, file_id: str):
    """Добавляет фото пользователя (только file_id)"""
    user_data = get_user_data(user_id)
    if "photo_file_ids" not in user_data:
        user_data["photo_file_ids"] = []
    
    # Проверяем, нет ли уже этого file_id
    if file_id not in user_data["photo_file_ids"]:
        user_data["photo_file_ids"].append(file_id)
        photo_count = len(user_data["photo_file_ids"])
        user_data["photo_count"] = photo_count
        update_user_data(user_id, user_data)
        # Обновляем сессию
        update_session(user_id, photo_count=photo_count)

def get_user_photo_count(user_id: int) -> int:
    """Получает количество загруженных фото пользователя"""
    user_data = get_user_data(user_id)
    return user_data.get("photo_count", 0)

def get_user_photo_file_ids(user_id: int) -> List[str]:
    """Получает список file_id загруженных фото пользователя"""
    user_data = get_user_data(user_id)
    return user_data.get("photo_file_ids", [])

def set_user_style(user_id: int, style: str):
    """Устанавливает стиль для пользователя"""
    update_user_data(user_id, {"style": style})
    # Обновляем сессию
    update_session(user_id, style=style)

def set_user_paid(user_id: int, paid: bool = True):
    """Устанавливает статус оплаты"""
    update_user_data(user_id, {"paid": paid})
    # Обновляем сессию
    update_session(user_id, paid=paid)

def set_user_payment(user_id: int, payment_id: str, confirmation_url: str, email: str = ""):
    """Сохраняет платёж ЮKassa"""
    update_user_data(user_id, {
        "payment_id": payment_id,
        "confirmation_url": confirmation_url,
        "customer_email": email,
        "paid": False,
        "receipt_url": None,
        "receipt_sent": False,
        "order_done": False,
    })

def clear_user_photos(user_id: int):
    """Сбрасывает фото текущего заказа, чтобы новая загрузка началась с нуля"""
    update_user_data(user_id, {
        "photo_count": 0,
        "photo_file_ids": [],
        "style": None,
        "paid": False,
        "payment_id": None,
        "confirmation_url": None,
        "order_id": None,
        "generated_images": [],
        "receipt_url": None,
        "receipt_sent": False,
        "order_done": False,
    })
    update_session(user_id, photo_count=0, style=None, paid=False)

def set_user_generated_images(user_id: int, images: List[str]):
    """Сохраняет сгенерированные изображения"""
    update_user_data(user_id, {"generated_images": images})

def price_per_photo(photo_count: int) -> int:
    """Цена одной страницы: 50 ₽ до 5 фото, 30 ₽ с 6 фото"""
    from bot.config import PRICE_FROM_6, PRICE_UP_TO_5
    if photo_count <= 5:
        return PRICE_UP_TO_5
    return PRICE_FROM_6

def calculate_price(photo_count: int) -> int:
    """Рассчитывает стоимость заказа"""
    if photo_count <= 0:
        return 0
    return photo_count * price_per_photo(photo_count)

def generation_wait_seconds(photo_count: int) -> int:
    """Сколько секунд показывать в сообщении об ожидании"""
    if photo_count >= 6:
        return 120
    return 60

# ==================== Функции для работы с сессиями ====================

def create_session(user_id: int) -> str:
    """Создаёт новую сессию для пользователя и возвращает session_id"""
    all_data = load_users()
    sessions = all_data.get("sessions", [])
    users = all_data.get("users", {})
    
    # Генерируем уникальный ID сессии
    session_id = str(uuid.uuid4())
    
    # Создаём новую сессию
    new_session = {
        "session_id": session_id,
        "user_id": user_id,
        "photo_count": 0,
        "style": None,
        "paid": False,
        "completed": False,
        "created_at": datetime.now().isoformat(),
        "completed_at": None
    }
    
    sessions.append(new_session)
    
    # Обновляем текущую сессию пользователя
    if str(user_id) not in users:
        users[str(user_id)] = empty_user(session_id)
    else:
        users[str(user_id)]["current_session_id"] = session_id
    
    all_data["sessions"] = sessions
    all_data["users"] = users
    save_users(all_data)
    
    return session_id

def update_session(user_id: int, **kwargs):
    """Обновляет данные текущей сессии пользователя"""
    all_data = load_users()
    sessions = all_data.get("sessions", [])
    users = all_data.get("users", {})
    
    user_data = users.get(str(user_id), {})
    current_session_id = user_data.get("current_session_id")
    
    if not current_session_id:
        return
    
    # Находим сессию и обновляем её
    for session in sessions:
        if session["session_id"] == current_session_id and session["user_id"] == user_id:
            # Обновляем только переданные поля
            for key, value in kwargs.items():
                if key in ["photo_count", "style", "paid", "completed"]:
                    session[key] = value
            break
    
    all_data["sessions"] = sessions
    save_users(all_data)

def complete_session(user_id: int):
    """Отмечает текущую сессию как завершённую (пользователь получил PDF)"""
    all_data = load_users()
    sessions = all_data.get("sessions", [])
    users = all_data.get("users", {})
    
    user_data = users.get(str(user_id), {})
    current_session_id = user_data.get("current_session_id")
    
    if not current_session_id:
        return
    
    # Находим сессию и отмечаем как завершённую
    for session in sessions:
        if session["session_id"] == current_session_id and session["user_id"] == user_id:
            session["completed"] = True
            session["completed_at"] = datetime.now().isoformat()
            # Обновляем финальные данные сессии из данных пользователя
            session["photo_count"] = user_data.get("photo_count", 0)
            session["style"] = user_data.get("style")
            session["paid"] = user_data.get("paid", False)
            break
    
    all_data["sessions"] = sessions
    save_users(all_data)


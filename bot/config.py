import os
from pathlib import Path
from dotenv import load_dotenv

# Базовая директория проекта
BASE_DIR = Path(__file__).parent.parent

# Загружаем переменные окружения из .env файла
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN не найден! Создайте файл .env в корне проекта и добавьте туда BOT_TOKEN=ваш_токен"
    )

# ProxyAPI
PROXY_API_KEY = os.getenv("PROXY_API_KEY")
if not PROXY_API_KEY:
    raise ValueError(
        "PROXY_API_KEY не найден! Создайте файл .env в корне проекта и добавьте туда PROXY_API_KEY=ваш_ключ"
    )
PROXY_API_BASE_URL = "https://api.proxyapi.ru/openai/v1"

# Модель и параметры генерации
IMAGE_MODEL = "gpt-image-1-mini"
IMAGE_SIZE = "1024x1536"
IMAGE_QUALITY = "high"

# Минимальное и максимальное количество фото в одном заказе
MIN_PHOTOS = 1
MAX_PHOTOS = 10

# Цена за одно фото: 1–5 фото и 6–10 фото
PRICE_UP_TO_5 = 50
PRICE_FROM_6 = 30

# Стили раскрасок
STYLES = {
    "disney": {
        "name": "Дисней",
        "prompt": "Преврати это изображение в иллюстрацию в стиле мультфильмов, вдохновлённую анимационной студией Walt Disney."
    },
    "anime": {
        "name": "Аниме",
        "prompt": "Преврати это изображение в иллюстрацию в стиле японских аниме мультфильмов."
    },
    "simpsons": {
        "name": "Симпсоны",
        "prompt": "Преврати это изображение в иллюстрацию в стиле мультфильмов, вдохновлённую анимационным мультфильмом «Симпсоны»."
    },
    "comics": {
        "name": "Комикс",
        "prompt": "Преврати это изображение в иллюстрацию в стиле, вдохновлённым комиксами Marvel и DC."
    },
    "kids": {
        "name": "Детский",
        "prompt": "Преврати это изображение в иллюстрацию в стиле детских книжек, с мягкими линиями и доброй атмосферой."
    },
    "realism": {
        "name": "Реализм",
        "prompt": "Преврати это изображение в реалистичную иллюстрацию, максимально приближенную к оригинальному фото."
    }
}

# Общие требования для всех стилей
COMMON_REQUIREMENTS = (
    "Чёрно-белая контурная раскраска, чистые плавные линии, профессиональный векторный стиль, "
    "высокая чёткость, высокая детализация, правильная анатомия, корректные руки и пальцы, "
    "без искажений, совпадение ракурса, совпадение выражения лица и эмоций, аккуратные и чёткие контуры, "
    "ровная композиция, проработанный передний и задний план."
)

# Пути к файлам
ASSETS_DIR = BASE_DIR / "bot" / "assets"
DATA_DIR = BASE_DIR / "bot" / "data"
USERS_DB = DATA_DIR / "users.json"

# Примеры
EXAMPLES_URL = "https://teletype.in/@moments_tg_bot/4ogqhVhDcPF"
STYLES_EXAMPLES_URL = "https://teletype.in/@moments_tg_bot/kxNdXGh3XQs"

# Время генерации (секунды)
GENERATION_TIME = 60

# ЮKassa (форма оплаты по API)
# shopId и секретный ключ — в личном кабинете ЮKassa, раздел «Интеграция» → «Ключи API»
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "").strip()
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "").strip()
YOOKASSA_RETURN_URL = os.getenv("YOOKASSA_RETURN_URL", "https://t.me/moments_photo_bot").strip()
# 1 — без НДС (Чеки от ЮKassa)
YOOKASSA_VAT_CODE = int(os.getenv("YOOKASSA_VAT_CODE", "1").strip() or "1")
YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


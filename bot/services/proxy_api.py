import base64
import asyncio
import logging
from io import BytesIO
from typing import List
from openai import OpenAI
from bot.config import (
    PROXY_API_KEY,
    PROXY_API_BASE_URL,
    IMAGE_MODEL,
    IMAGE_SIZE,
    IMAGE_QUALITY,
    STYLES,
    COMMON_REQUIREMENTS
)

logger = logging.getLogger(__name__)


def _generate_coloring_image_sync(image_data: bytes, style_key: str) -> bytes:
    """
    Синхронная функция для генерации раскраски из изображения через ProxyAPI
    
    Args:
        image_data: Байты изображения
        style_key: Ключ стиля из STYLES
        
    Returns:
        Байты сгенерированного изображения
    """
    style = STYLES[style_key]
    
    # Формируем промпт
    prompt = f"{style['prompt']}\n\n{COMMON_REQUIREMENTS}"
    
    # Создаём клиент OpenAI с ProxyAPI
    client = OpenAI(
        api_key=PROXY_API_KEY,
        base_url=PROXY_API_BASE_URL,
    )
    
    # Определяем формат изображения по первым байтам
    image_format = "jpg"
    if len(image_data) >= 8 and image_data[:8] == b'\x89PNG\r\n\x1a\n':
        image_format = "png"
    elif len(image_data) >= 2 and image_data[:2] == b'\xff\xd8':
        image_format = "jpg"
    
    # Создаём файловый объект из байтов
    image_file = BytesIO(image_data)
    image_file.name = f"image.{image_format}"  # Имя файла для API
    
    try:
        # Используем images.edit с параметрами size и quality через extra_body
        # ProxyAPI поддерживает эти параметры, но SDK может не принимать их напрямую
        result = client.images.edit(
            model=IMAGE_MODEL,
            image=image_file,
            prompt=prompt,
            extra_body={
                "size": IMAGE_SIZE,
                "quality": IMAGE_QUALITY
            }
        )
        
        # Извлекаем изображение из ответа
        if result.data and len(result.data) > 0:
            # Проверяем наличие b64_json
            if hasattr(result.data[0], 'b64_json') and result.data[0].b64_json:
                image_b64 = result.data[0].b64_json
                return base64.b64decode(image_b64)
            # Если нет b64_json, проверяем URL
            elif hasattr(result.data[0], 'url') and result.data[0].url:
                import requests
                img_response = requests.get(result.data[0].url, timeout=30)
                if img_response.status_code == 200:
                    return img_response.content
        
        raise Exception("Не удалось получить изображение из ответа API")
    
    except Exception as e:
        logger.error(f"Ошибка при генерации изображения: {e}")
        raise


async def generate_coloring_image(image_data: bytes, style_key: str) -> bytes:
    """
    Асинхронная обёртка для генерации раскраски из изображения через ProxyAPI
    
    Args:
        image_data: Байты изображения
        style_key: Ключ стиля из STYLES
        
    Returns:
        Байты сгенерированного изображения
    """
    # Запускаем синхронную функцию в отдельном потоке
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _generate_coloring_image_sync,
        image_data,
        style_key
    )


async def generate_coloring_images(
    image_data_list: List[bytes],
    style_key: str
) -> List[bytes]:
    """
    Генерирует раскраски для всех загруженных фото одновременно
    
    Args:
        image_data_list: Список байтов изображений
        style_key: Ключ стиля (disney, anime, etc.)
    
    Returns:
        Список байтов сгенерированных изображений
    """
    if not image_data_list:
        return []
    
    if style_key not in STYLES:
        raise ValueError(f"Неизвестный стиль: {style_key}")
    
    # Генерируем все изображения параллельно
    tasks = [generate_coloring_image(img_data, style_key) for img_data in image_data_list]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Фильтруем исключения
    generated_images = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Ошибка генерации изображения {i}: {result}")
        else:
            generated_images.append(result)
    
    return generated_images

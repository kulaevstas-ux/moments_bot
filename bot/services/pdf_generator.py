from io import BytesIO
from typing import List
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from PIL import Image

def create_coloring_pdf(images_data: List[bytes], output_path: str) -> bool:
    """
    Создаёт PDF-файл с раскрасками
    
    Args:
        images_data: Список байтов сгенерированных изображений
        output_path: Путь для сохранения PDF
    
    Returns:
        True если успешно, False иначе
    """
    if not images_data:
        return False
    
    try:
        # Создаём PDF
        c = canvas.Canvas(output_path, pagesize=A4)
        width, height = A4
        
        for img_bytes in images_data:
            # Открываем изображение из байтов
            img_data = BytesIO(img_bytes)
            pil_image = Image.open(img_data)
            
            # Рассчитываем размеры для вписывания в страницу
            img_width, img_height = pil_image.size
            aspect_ratio = img_width / img_height
            
            # Оставляем отступы
            margin = 50
            available_width = width - 2 * margin
            available_height = height - 2 * margin
            
            if aspect_ratio > (available_width / available_height):
                # Ширина ограничивает
                draw_width = available_width
                draw_height = available_width / aspect_ratio
            else:
                # Высота ограничивает
                draw_height = available_height
                draw_width = available_height * aspect_ratio
            
            # Центрируем изображение
            x = (width - draw_width) / 2
            y = (height - draw_height) / 2
            
            # Добавляем изображение на страницу
            img_data.seek(0)
            c.drawImage(ImageReader(pil_image), x, y, width=draw_width, height=draw_height)
            c.showPage()
        
        c.save()
        return True
    
    except Exception as e:
        print(f"Ошибка при создании PDF: {e}")
        return False

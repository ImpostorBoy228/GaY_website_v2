from django.db.models.signals import post_save
from django.dispatch import receiver
from core.models import Video, Tag
from django.utils.text import slugify
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Video)
def generate_tags_on_video_save(sender, instance, created, **kwargs):
    """Generate tags from video title when a new video is created"""
    if created and instance.title:
        try:
            # Генерация тегов из названия видео
            title = instance.title.lower()
            words = title.split()
            
            # Удаляем стоп-слова
            stop_words = {'на', 'в', 'и', 'с', 'по', 'для', 'как', 'что', 'это', 'или', 'если', 'но', 'а', 'же', 'ли', 'бы', 'то'}
            keywords = [word for word in words if word not in stop_words and len(word) > 2]
            
            # Ограничиваем количество тегов
            keywords = keywords[:5]
            
            # Создаем теги
            for keyword in keywords:
                # Удаляем знаки препинания
                keyword = ''.join(c for c in keyword if c.isalnum())
                if len(keyword) > 2:  # Минимальная длина тега
                    tag, created = Tag.objects.get_or_create(
                        name=keyword,
                        defaults={'slug': slugify(keyword)}
                    )
                    instance.tags.add(tag)
            
            logger.info(f"Generated tags for video {instance.id}: {keywords}")
            
            # Рассчитываем рейтинг
            instance.calculate_absolute_rating()
            
        except Exception as e:
            logger.error(f"Error in generate_tags_on_video_save for video {instance.id}: {str(e)}")

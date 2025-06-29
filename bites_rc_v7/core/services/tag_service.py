import json
import logging
import subprocess
from django.conf import settings
from django.utils.text import slugify
from core.models import Tag, Video

logger = logging.getLogger(__name__)

def generate_tags_for_video(video):
    """
    Генерирует теги для видео на основе заголовка и описания, используя Ollama
    
    Args:
        video: Объект Video для которого нужно сгенерировать теги
        
    Returns:
        list: Список созданных тегов
    """
    logger.info(f"Starting tag generation for video ID {video.id}: {video.title}")
    try:
        # Подготовка контекста для модели
        context = f"""
        Analyze the title and description of the video and create 5-7 relevant tags. 
        Tags should be short (1-2 words), accurately reflect the topic of the video, and be useful for searching.
        Video title: "{video.title}"
        Description: "{video.description[:300] if video.description else ''}..."
        
        Rules:
        1. Each tag must be a noun or a phrase without verbs.
        2. Use only lowercase letters.
        3. Do not use numbering, list markers, or other formatting.
        4. Don't mention the word "tag" in the reply.
        5. Tags for social platforms should NOT contain # or @
        6. Put only the tags themselves separated by commas.
        7. Tags should be on english language
        
        Examples of good tags: cyberpunk, artificial intelligence, game review, tutorial, memes
        Examples of bad tags: #cool_video, how to make, @blogger, top 10
        
        Your response is comma-separated tags only.
        """

        # Отправка запроса в Ollama напрямую
        try:
            logger.info("Attempting to generate tags using Ollama (Mistral model)")
            # Примечание: Ollama должен быть запущен с помощью 'ollama serve &'
            result = subprocess.run(
                ["ollama", "run", "mistral:7b-instruct", context],
                capture_output=True,
                text=True,
                timeout=60,
                check=True
            )
            tags_text = result.stdout.strip()
            logger.info(f"Successfully generated tags using Ollama: {tags_text}")
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Ollama failed, using fallback method: {str(e)}")
            # Fallback: простой алгоритм извлечения ключевых слов без Ollama
            tags_text = fallback_tag_generation(video.title, video.description)
            logger.info(f"Generated tags using fallback method: {tags_text}")

        # Очистка и стандартизация результата
        tags_text = tags_text.replace('\n', ' ')
        
        # Удаляем нумерацию и лишние символы
        import re
        # Удаляем нумерацию вида "1. ", "2. " и т.д.
        tags_text = re.sub(r'\d+\.\s*', '', tags_text)
        # Удаляем нумерацию в скобках вида "(1)", "(2)" и т.д.
        tags_text = re.sub(r'\(\d+\)\s*', '', tags_text)
        
        # Разделение текста на отдельные теги
        tags_list = [tag.strip().lower() for tag in tags_text.split(',') if tag.strip()]
        
        # Убираем пустые теги
        tags_list = [tag for tag in tags_list if tag]
        
        # Ограничиваем количество тегов до 7
        tags_list = tags_list[:7]
        
        # Создаем или получаем существующие объекты Tag
        created_tags = []
        for tag_name in tags_list:
            if tag_name:
                tag, created = Tag.objects.get_or_create(name=tag_name)
                created_tags.append(tag)
                action = "Created" if created else "Using existing"
                logger.info(f"{action} tag: {tag_name}")
        
        # Связываем теги с видео
        video.tags.add(*created_tags)
        logger.info(f"Added {len(created_tags)} tags to video {video.id}")
        
        return created_tags
    
    except Exception as e:
        logger.error(f"Error generating tags for video {video.id}: {str(e)}")
        return []

def fallback_tag_generation(title, description):
    """
    Резервный метод генерации тегов на основе частотного анализа
    без использования внешних моделей.
    """
    import re
    from collections import Counter
    
    logger.info("Using fallback tag generation method")
    
    # Объединяем заголовок и описание
    text = f"{title} {description}".lower()
    
    # Убираем пунктуацию и делим на слова
    words = re.findall(r'\b\w+\b', text)
    
    # Фильтруем стоп-слова (здесь можно расширить список)
    stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'из', 'а', 'что', 'как', 'это', 'этот', 'к', 'у', 
                 'the', 'a', 'an', 'and', 'in', 'on', 'of', 'to', 'for', 'with', 'by'}
    filtered_words = [w for w in words if len(w) > 2 and w not in stop_words]
    
    # Подсчитываем частоту слов
    word_counts = Counter(filtered_words)
    
    # Берем 5-7 самых частых слов как теги
    top_words = [word for word, _ in word_counts.most_common(7)]
    
    result = ", ".join(top_words)
    logger.info(f"Fallback generated tags: {result}")
    return result

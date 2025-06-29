import logging
import subprocess
import json
import re
from django.conf import settings
from core.services.tag_service import generate_tags_for_video

logger = logging.getLogger(__name__)

def analyze_video(video):
    """
    Анализирует видео, используя его название и описание, и сохраняет результаты
    в поле analysis.
    
    Args:
        video: Объект Video для анализа
        
    Returns:
        dict: Словарь с результатами анализа
    """
    try:
        # Логируем начало анализа
        logger.info(f"Starting video analysis for ID {video.id}: {video.title}")
        
        # Получаем текст для анализа
        title = video.title
        description = video.description or ""
        
        # Логируем информацию о видео
        logger.info(f"Video metadata - Title: {title[:50]}..., Description length: {len(description)} chars")
        
        # Используем Ollama для анализа видео
        analysis_results = {}
        
        # 1. Анализируем эмоциональный тон видео
        analysis_results.update(analyze_sentiment(title, description))
        logger.info(f"Sentiment analysis completed: {analysis_results.get('sentiment_score', 'N/A')}")
        
        # 2. Определяем категорию видео
        analysis_results.update(determine_category(title, description))
        logger.info(f"Category determined: {analysis_results.get('category', 'N/A')}")
        
        # 3. Генерируем краткое описание видео
        analysis_results.update(generate_summary(title, description))
        logger.info(f"Summary generated, length: {len(analysis_results.get('summary', ''))}")
        
        # 4. Оцениваем потенциальную популярность
        analysis_results.update(estimate_popularity(title, description, video))
        logger.info(f"Popularity score estimated: {analysis_results.get('popularity_score', 'N/A')}")
        
        # Сохраняем результаты анализа в видео
        video.analysis = analysis_results
        video.save(update_fields=['analysis'])
        
        # Генерируем теги для видео
        tags = generate_tags_for_video(video)
        logger.info(f"Generated {len(tags)} tags for video {video.id}")
        
        # Пересчитываем рейтинг
        rating = video.recalculate_ratings()
        logger.info(f"Recalculated rating for video {video.id}: {rating}")
        
        return analysis_results
        
    except Exception as e:
        logger.error(f"Error analyzing video {video.id}: {str(e)}")
        # В случае ошибки создаём минимальный анализ
        basic_analysis = {
            'error': str(e),
            'sentiment_score': 0.5,  # нейтральное значение
            'category': 'uncategorized',
            'popularity_score': 0.0
        }
        video.analysis = basic_analysis
        video.save(update_fields=['analysis'])
        return basic_analysis

def analyze_sentiment(title, description):
    """Анализирует эмоциональный тон контента"""
    logger.info("Starting sentiment analysis")
    
    try:
        prompt = f"Оцени эмоциональный тон этого контента по шкале от 0 (крайне негативный) до 1 (крайне позитивный). Дай только число с 2 знаками после запятой, без дополнительного текста: \nНазвание: {title} \nОписание: {description[:500]}"
        
        result = run_ollama_model(prompt)
        # Извлекаем число из ответа
        sentiment_match = re.search(r'0\.\d{1,2}|1\.0', result)
        if sentiment_match:
            sentiment_score = float(sentiment_match.group(0))
        else:
            # Если не удалось извлечь точное число, используем эвристику
            if "0." in result:
                parts = result.split("0.")
                if len(parts) > 1 and parts[1][:2].isdigit():
                    sentiment_score = float("0." + parts[1][:2])
                else:
                    sentiment_score = 0.5
            else:
                sentiment_score = 0.5
        
        return {
            'sentiment_score': sentiment_score,
            'sentiment_raw': result[:100]  # сохраняем часть исходного ответа для отладки
        }
    except Exception as e:
        logger.error(f"Error in sentiment analysis: {str(e)}")
        return {'sentiment_score': 0.5}

def determine_category(title, description):
    """Определяет категорию видео"""
    logger.info("Determining video category")
    
    try:
        prompt = f"Выбери ОДНУ наиболее подходящую категорию для этого видео из списка: развлечение, образование, игры, музыка, спорт, технологии, наука, новости, путешествия, мода, красота, еда, животные, политика, бизнес, искусство. \nНазвание: {title} \nОписание: {description[:500]} \nОтвет (только категория):"
        
        result = run_ollama_model(prompt)
        # Удаляем лишний текст и приводим к нижнему регистру
        category = result.strip().lower()
        
        # Проверяем, что категория входит в список допустимых
        valid_categories = ['развлечение', 'образование', 'игры', 'музыка', 'спорт', 'технологии', 
                         'наука', 'новости', 'путешествия', 'мода', 'красота', 'еда', 'животные', 
                         'политика', 'бизнес', 'искусство']
        
        # Ищем совпадения в ответе
        for valid_cat in valid_categories:
            if valid_cat in category:
                return {'category': valid_cat}
        
        # Если не нашли точного совпадения
        return {'category': 'другое'}
    except Exception as e:
        logger.error(f"Error in category determination: {str(e)}")
        return {'category': 'неопределено'}

def generate_summary(title, description, max_length=150):
    """Генерирует краткое описание для видео"""
    logger.info("Generating video summary")
    
    try:
        # Если описание короткое, используем его как есть
        if description and len(description) <= max_length:
            return {'summary': description}
        
        prompt = f"Создай краткое описание видео в 1-2 предложения (не более 150 символов) на основе: \nНазвание: {title} \nОписание: {description[:1000]}"
        
        summary = run_ollama_model(prompt)
        # Обрезаем до нужной длины
        summary = summary[:max_length]
        
        return {'summary': summary}
    except Exception as e:
        logger.error(f"Error in summary generation: {str(e)}")
        return {'summary': title[:max_length]}

def estimate_popularity(title, description, video):
    """Оценивает потенциальную популярность видео по шкале от 0 до 1"""
    logger.info("Estimating video popularity potential")
    
    try:
        # Комбинируем несколько факторов для оценки:
        # 1. Длина видео (для YouTube) - средняя длина более предпочтительна
        if video.duration:
            duration_minutes = video.duration / 60
            if 5 <= duration_minutes <= 15:
                duration_score = 0.9
            elif 3 <= duration_minutes < 5 or 15 < duration_minutes <= 25:
                duration_score = 0.7
            elif duration_minutes < 3:
                duration_score = 0.5
            else:
                duration_score = 0.3
        else:
            duration_score = 0.5
        
        # 2. Для YouTube видео - используем соотношение лайков к просмотрам
        if video.is_youtube and video.youtube_views > 0:
            likes_ratio = min(video.youtube_likes / video.youtube_views, 0.3) / 0.3  # нормализуем до 1
        else:
            likes_ratio = 0.5
        
        # 3. Используем AI для оценки привлекательности названия
        prompt = f"Оцени насколько это название видео привлекательно для зрителей по шкале от 0 до 1 (где 1 - максимально привлекательное). Дай только число с 1 знаком после запятой, без объяснений: {title}"
        
        title_score_raw = run_ollama_model(prompt)
        title_score_match = re.search(r'0\.\d|1\.0|1', title_score_raw)
        
        if title_score_match:
            title_score = float(title_score_match.group(0))
        else:
            # Если не удалось извлечь число
            title_score = 0.5
        
        # Итоговая оценка - средневзвешенное значение всех факторов
        popularity_score = (duration_score * 0.3) + (likes_ratio * 0.4) + (title_score * 0.3)
        
        return {
            'popularity_score': round(popularity_score, 2),
            'duration_score': round(duration_score, 2),
            'title_score': round(title_score, 2)
        }
    except Exception as e:
        logger.error(f"Error in popularity estimation: {str(e)}")
        return {'popularity_score': 0.5}

def run_ollama_model(prompt, model="mistral", timeout=30):
    """
    Запускает модель Ollama и получает результат
    
    В случае ошибки возвращает запасной ответ
    """
    try:
        logger.info(f"Running Ollama model '{model}'")
        
        # Запускаем Ollama с указанным запросом
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True
        )
        
        # Извлекаем и возвращаем результат
        output = result.stdout.strip()
        logger.info(f"Ollama response received ({len(output)} chars)")
        return output
        
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Error running Ollama: {str(e)}")
        if "No such file or directory" in str(e):
            logger.error("Ollama not installed or not in PATH")
            return "Ошибка: Ollama не установлена"
        return f"Ошибка Ollama: {str(e)[:100]}"
        
    except Exception as e:
        logger.error(f"Unexpected error with Ollama: {str(e)}")
        return "Ошибка анализа"

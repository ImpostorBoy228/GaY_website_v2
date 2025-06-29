from core.models import VideoDownloadQueue, Video
from django.core.cache import cache
import logging
import time
from django.db import transaction
from django.db.models import Max, F
# Удаляем импорт tasks, чтобы избежать циклической зависимости

logger = logging.getLogger(__name__)

class DownloadQueueService:
    """
    Сервис для управления очередью скачивания видео.
    Обеспечивает последовательное скачивание видео.
    """
    
    # Кэш-ключи для оптимизации
    ACTIVE_DOWNLOADS_KEY = 'active_downloads_count'
    MAX_CONCURRENT_DOWNLOADS = 3  # Максимальное количество одновременных загрузок
    
    @classmethod
    def add_to_queue(cls, video, user=None):
        start_time = time.time()
        logger.info(f"[QUEUE_ADD_START] Adding video {video.id} ({video.youtube_id}) - '{video.title}' to download queue")
        
        existing = VideoDownloadQueue.objects.filter(video=video, status__in=['queued', 'downloading']).first()
        if existing:
            logger.info(f"[QUEUE_EXISTS] Video {video.id} already in queue with status {existing.status}")
            return existing

        with transaction.atomic():
            # Оптимизированный запрос с SELECT FOR UPDATE
            last_position = VideoDownloadQueue.objects.aggregate(Max=Max('position')).get('Max') or 0
            queue_item = VideoDownloadQueue.objects.create(
                video=video,
                user=user,
                position=last_position + 1,
                status='queued'
            )
            
            elapsed_time = time.time() - start_time
            logger.info(f"[QUEUE_ADD_COMPLETE] Added video {video.id} to download queue at position {queue_item.position} in {elapsed_time:.2f} seconds")
            
            # Проверяем, есть ли активные загрузки, если нет - запускаем процесс
            active_count = cache.get(cls.ACTIVE_DOWNLOADS_KEY) or 0
            if active_count < cls.MAX_CONCURRENT_DOWNLOADS:
                cls.process_next_in_queue()
                
            return queue_item
    
    @classmethod
    def get_queue_stats(cls):
        """Возвращает статистику по очереди загрузок"""
        from django.db.models import Count, Q
        
        stats = {
            'total': VideoDownloadQueue.objects.count(),
            'queued': VideoDownloadQueue.objects.filter(status='queued').count(),
            'downloading': VideoDownloadQueue.objects.filter(status='downloading').count(),
            'completed': VideoDownloadQueue.objects.filter(status='completed').count(),
            'failed': VideoDownloadQueue.objects.filter(status='failed').count(),
        }
        
        # Получаем текущие загружаемые видео
        current_downloads = VideoDownloadQueue.objects.filter(
            status='downloading'
        ).select_related('video').order_by('position')[:cls.MAX_CONCURRENT_DOWNLOADS]
        
        stats['current_downloads'] = [
            {
                'video_id': item.video.id,
                'youtube_id': item.video.youtube_id,
                'title': item.video.title[:50] + '...' if item.video.title else 'No title',
                'progress': item.progress,
                'status': item.status
            } for item in current_downloads
        ]
        
        # Добавляем информацию о следующих в очереди
        next_in_queue = VideoDownloadQueue.objects.filter(
            status='queued'
        ).select_related('video').order_by('position')[:5]  # Следующие 5 в очереди
        
        stats['next_in_queue'] = [
            {
                'video_id': item.video.id,
                'youtube_id': item.video.youtube_id,
                'title': item.video.title[:50] + '...' if item.video.title else 'No title',
                'position': item.position
            } for item in next_in_queue
        ]
        
        return stats

    @classmethod
    def process_next_in_queue(cls):
        start_time = time.time()
        logger.info(f"[QUEUE_PROCESS_START] Looking for next video in queue")
        
        # Логируем текущую статистику очереди
        stats = cls.get_queue_stats()
        logger.info(
            f"[QUEUE_STATS] Total: {stats['total']}, "
            f"Queued: {stats['queued']}, "
            f"Downloading: {stats['downloading']}, "
            f"Completed: {stats['completed']}, "
            f"Failed: {stats['failed']}"
        )
        
        # Проверяем количество активных загрузок
        active_count = cache.get(cls.ACTIVE_DOWNLOADS_KEY) or 0
        
        # Если уже максимум активных загрузок, не запускаем новые
        if active_count >= cls.MAX_CONCURRENT_DOWNLOADS:
            logger.info(f"[QUEUE_PROCESS_MAX] Already at max concurrent downloads ({active_count}/{cls.MAX_CONCURRENT_DOWNLOADS})")
            return
            
        # Находим следующий элемент в очереди с блокировкой
        with transaction.atomic():
            next_item = VideoDownloadQueue.objects.select_for_update().filter(status='queued').order_by('position').first()
            
            if next_item:
                # Увеличиваем счетчик активных загрузок
                cache.set(cls.ACTIVE_DOWNLOADS_KEY, active_count + 1)
                
                elapsed_time = time.time() - start_time
                logger.info(f"[QUEUE_PROCESS_FOUND] Starting download for video {next_item.video.id} ({next_item.video.youtube_id}) at position {next_item.position} (took {elapsed_time:.2f}s to find)")
                
                # Используем countdown=0 для немедленного запуска и task_id для отслеживания
                task_id = f"download_video_{next_item.video.id}_{int(time.time())}"
                # Отложенный импорт для избежания циклической зависимости
                try:
                    logger.info(f"[QUEUE_DEBUG] Importing download_youtube_video task for video {next_item.video.id}")
                    from youtube_api.tasks import download_youtube_video
                    logger.info(f"[QUEUE_DEBUG] Successfully imported download_youtube_video task")
                    
                    # Передаем через apply_async с полными параметрами
                    logger.info(f"[QUEUE_DEBUG] Calling apply_async for video {next_item.video.id} with task_id {task_id}")
                    async_result = download_youtube_video.apply_async(
                        kwargs={
                            'video_id': next_item.video.youtube_id,
                            'queue_item_id': next_item.id
                        },
                        countdown=0,  # Запускаем немедленно
                        task_id=task_id  # Уникальный ID для отслеживания
                    )
                    logger.info(f"[QUEUE_TASK_CREATED] Created Celery task {task_id} with async_result: {async_result}")
                except Exception as e:
                    logger.error(f"[QUEUE_TASK_ERROR] Error creating Celery task: {str(e)}")
                    import traceback
                    logger.error(f"[QUEUE_TASK_TRACEBACK] {traceback.format_exc()}")
                    raise
                
                # Запускаем следующую загрузку, если есть место для параллельной работы
                if active_count + 1 < cls.MAX_CONCURRENT_DOWNLOADS:
                    logger.info(f"[QUEUE_CAN_PROCESS_MORE] Can process more videos ({active_count + 1}/{cls.MAX_CONCURRENT_DOWNLOADS})")
                    cls.process_next_in_queue()
            else:
                logger.info("[QUEUE_EMPTY] No items in queue to process")
                return None
            
            # Меняем статус на 'downloading'
            next_item.status = 'downloading'
            next_item.save()
            
            # Обновляем статус в кеше
            cache_key = f'video_download_status_{next_item.video.youtube_id}'
            cache.set(cache_key, {
                'status': 'downloading',
                'progress': 0,
                'queue_position': next_item.position
            }, timeout=3600)
            
            return next_item
    
    @classmethod
    def get_queue_item(cls, queue_item_id, video_id=None, youtube_id=None):
        """
        Получает элемент очереди по его ID.
        Если элемент не найден по ID, пытается найти по video_id или youtube_id.
        """
        try:
            # Сначала пытаемся найти по ID
            return VideoDownloadQueue.objects.get(id=queue_item_id)
        except VideoDownloadQueue.DoesNotExist:
            logger.warning(f"Queue item {queue_item_id} not found by direct ID, trying alternative methods")
            
            # Пытаемся найти по video_id, если он предоставлен
            if video_id:
                try:
                    queue_item = VideoDownloadQueue.objects.filter(
                        video_id=video_id, 
                        status__in=['queued', 'downloading']
                    ).order_by('-added_at').first()
                    if queue_item:
                        logger.info(f"Using existing queue item {queue_item.id} for video {video_id}")
                        return queue_item
                except Exception as e:
                    logger.error(f"Error finding queue item by video_id {video_id}: {str(e)}")
            
            # Пытаемся найти по youtube_id, если он предоставлен
            if youtube_id:
                try:
                    video = Video.objects.filter(youtube_id=youtube_id).first()
                    if video:
                        queue_item = VideoDownloadQueue.objects.filter(
                            video=video, 
                            status__in=['queued', 'downloading']
                        ).order_by('-added_at').first()
                        if queue_item:
                            logger.info(f"Using existing queue item {queue_item.id} for youtube_id {youtube_id}")
                            return queue_item
                except Exception as e:
                    logger.error(f"Error finding queue item by youtube_id {youtube_id}: {str(e)}")
            
            logger.error(f"Queue item {queue_item_id} not found after all attempts")
            return None
        except Exception as e:
            logger.error(f"Error getting queue item: {str(e)}")
            return None
    
    @classmethod
    def set_status(cls, queue_item_id, status, error_message=None, video_path=None, video_id=None, youtube_id=None):
        """
        Устанавливает статус элемента очереди.
        Если элемент не найден по ID, пытается найти по video_id или youtube_id.
        """
        # Используем улучшенный метод get_queue_item для поиска элемента очереди
        queue_item = cls.get_queue_item(queue_item_id, video_id, youtube_id)
        
        if not queue_item:
            if youtube_id:
                logger.warning(f"Queue item {queue_item_id} not found for setting status to '{status}' for youtube_id {youtube_id}")
            elif video_id:
                logger.warning(f"Queue item {queue_item_id} not found for setting status to '{status}' for video_id {video_id}")
            else:
                logger.warning(f"Queue item {queue_item_id} not found for setting status to '{status}'")
            return False
            
        try:
            queue_item.status = status
            
            if error_message:
                queue_item.error_message = error_message
                
            queue_item.save()
            
            # Обновляем кэш
            cache_key = f'video_download_status_{queue_item.video.youtube_id}'
            cache_data = {
                'status': status,
                'progress': queue_item.progress,
                'queue_position': queue_item.position
            }
            
            if error_message:
                cache_data['error'] = error_message
                
            if video_path:
                cache_data['video_path'] = video_path
                
            cache.set(cache_key, cache_data, timeout=3600)
            
            # Если скачивание завершено или произошла ошибка,
            # уменьшаем счетчик активных загрузок
            if status in ['completed', 'failed']:
                active_count = cache.get(cls.ACTIVE_DOWNLOADS_KEY) or 0
                if active_count > 0:
                    cache.set(cls.ACTIVE_DOWNLOADS_KEY, active_count - 1)
                    logger.info(f"Decreased active downloads count to {active_count - 1} after queue item {queue_item.id} status changed to {status}")
            
            logger.info(f"Successfully set status '{status}' for queue item {queue_item.id}")
            return True
        except Exception as e:
            logger.error(f"Error updating queue status for item {queue_item_id}: {str(e)}")
            import traceback
            logger.error(f"[QUEUE_SET_STATUS_ERROR] {traceback.format_exc()}")
            return False
    
    @classmethod
    def update_status(cls, queue_item_id, status, error_message=None, video_path=None):
        """
        Алиас для set_status для обратной совместимости
        """
        return cls.set_status(queue_item_id, status, error_message, video_path)
            
    @classmethod
    def update_progress(cls, queue_item_id, progress, status='downloading', error=None, video_id=None, youtube_id=None):
        """
        Обновляет прогресс скачивания видео.
        Если элемент не найден по ID, пытается найти по video_id или youtube_id.
        """
        # Используем улучшенный метод get_queue_item для поиска элемента очереди
        queue_item = cls.get_queue_item(queue_item_id, video_id, youtube_id)
        
        if not queue_item:
            if youtube_id:
                logger.warning(f"Queue item {queue_item_id} not found for updating progress to {progress}% for youtube_id {youtube_id}")
            elif video_id:
                logger.warning(f"Queue item {queue_item_id} not found for updating progress to {progress}% for video_id {video_id}")
            else:
                logger.warning(f"Queue item {queue_item_id} not found for updating progress to {progress}%")
            return False
        
        try:
            queue_item.progress = progress
            queue_item.status = status
            
            if error:
                queue_item.error_message = error
            
            queue_item.save()
            
            # Обновляем кеш
            cache_key = f'video_download_status_{queue_item.video.youtube_id}'
            cache_data = {
                'status': status,
                'progress': progress,
                'queue_position': queue_item.position
            }
            
            if error:
                cache_data['error'] = error
                
            cache.set(cache_key, cache_data, timeout=3600)
            
            # Если скачивание завершено или произошла ошибка,
            # начинаем обработку следующего элемента в очереди
            if status in ['completed', 'failed']:
                cls.process_next_in_queue()
                
            return True
        except Exception as e:
            logger.error(f"Error updating progress for queue item {queue_item_id}: {str(e)}")
            import traceback
            logger.error(f"[QUEUE_UPDATE_PROGRESS_ERROR] {traceback.format_exc()}")
            return False
    
    @classmethod
    def mark_as_completed(cls, queue_item_id, video_id=None, youtube_id=None):
        """
        Отмечает элемент очереди как завершенный и обновляет статус видео
        Если элемент не найден по ID, пытается найти по video_id или youtube_id.
        """
        # Используем улучшенный метод get_queue_item для поиска элемента очереди
        queue_item = cls.get_queue_item(queue_item_id, video_id, youtube_id)
        
        if not queue_item:
            if youtube_id:
                logger.warning(f"Queue item {queue_item_id} not found for marking as completed for youtube_id {youtube_id}")
            elif video_id:
                logger.warning(f"Queue item {queue_item_id} not found for marking as completed for video_id {video_id}")
            else:
                logger.warning(f"Queue item {queue_item_id} not found for marking as completed")
            return False
        
        try:
            video = queue_item.video
            
            # Обновляем статус видео в модели Video
            video.is_downloaded = True
            video.save(update_fields=['is_downloaded'])
            
            # Обновляем элемент очереди
            queue_item.status = 'completed'
            queue_item.progress = 100
            queue_item.save(update_fields=['status', 'progress'])
            
            # Обновляем кеш статуса загрузки
            cache_key = f'video_download_status_{video.youtube_id}'
            cache_data = {
                'status': 'completed',
                'progress': 100,
                'queue_position': queue_item.position
            }
            cache.set(cache_key, cache_data, timeout=3600)
            
            # Уменьшаем счетчик активных загрузок
            active_count = cache.get(cls.ACTIVE_DOWNLOADS_KEY) or 0
            if active_count > 0:
                cache.set(cls.ACTIVE_DOWNLOADS_KEY, active_count - 1)
                
            logger.info(f"[TASK_MARK_COMPLETED] Successfully marked queue item {queue_item.id} as completed")
            
            # Обрабатываем следующий элемент в очереди
            cls.process_next_in_queue()
            return True
        except Exception as e:
            if queue_item:
                logger.error(f"Error marking queue item {queue_item.id} as completed: {e}")
            else:
                logger.error(f"Error marking queue item {queue_item_id} as completed: {e}")
            import traceback
            logger.error(f"[QUEUE_COMPLETED_ERROR] {traceback.format_exc()}")
            return False
    
    @classmethod
    def get_queue_status(cls, video_id=None, youtube_id=None):
        """
        Получает статус очереди для видео.
        """
        try:
            if youtube_id:
                video = Video.objects.filter(youtube_id=youtube_id).first()
                if not video:
                    return None
                video_id = video.id
                
            queue_item = VideoDownloadQueue.objects.filter(
                video_id=video_id
            ).order_by('-added_at').first()
            
            if not queue_item:
                return None
                
            return {
                'status': queue_item.status,
                'progress': queue_item.progress,
                'position': queue_item.position,
                'error': queue_item.error_message
            }
        except Exception as e:
            logger.error(f"Error getting queue status: {str(e)}")
            return None

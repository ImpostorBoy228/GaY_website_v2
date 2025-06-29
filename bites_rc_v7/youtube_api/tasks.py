import logging
import time
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError, SoftTimeLimitExceeded
from django.conf import settings
from core.models import Video
# Удаляем импорт DownloadQueueService, чтобы избежать циклической зависимости
from .downloader import YouTubeDownloader  # Using stub implementation

logger = logging.getLogger(__name__)

def _update_progress(queue_item, progress, status=None, error_message=None):
    """Обновляет прогресс загрузки и статус в базе"""
    from django.db import transaction
    from core.models import VideoDownloadQueue
    
    try:
        with transaction.atomic():
            queue_item = VideoDownloadQueue.objects.select_for_update().get(pk=queue_item.id)
            queue_item.progress = progress
            if status:
                queue_item.status = status
            if error_message:
                queue_item.error_message = error_message[:500]  # Ограничиваем длину сообщения об ошибке
            queue_item.save(update_fields=['progress', 'status', 'error_message'])
            
            # Логируем обновление прогресса
            if progress % 10 == 0 or progress == 100:  # Логируем каждые 10% и на 100%
                logger.info(
                    f"[DOWNLOAD_PROGRESS] Video {queue_item.video_id} "
                    f"({queue_item.video.youtube_id}): {progress}%"
                )
                
    except Exception as e:
        logger.error(f"Error updating progress for queue item {queue_item.id}: {str(e)}")

@shared_task(bind=True, max_retries=3, soft_time_limit=1800, time_limit=2100)
def download_youtube_video(self, video_id, queue_item_id=None):
    """
    Задача Celery для скачивания видео с YouTube
    
    Args:
        video_id: ID видео в нашей системе
        queue_item_id: ID элемента очереди загрузки (опционально)
    """
    start_time = time.time()
    video = Video.objects.get(youtube_id=video_id)
    # Логируем начало задачи с дополнительной информацией
    logger.info(
        f"[TASK_START] Video download task started for video {video.id} ({video.youtube_id})\n        Title: {getattr(video, 'title', 'No title')}\n"
        f"Queue item: {queue_item_id}"
    )
    
    # Отложенный импорт для избежания циклической зависимости
    from core.services.download_queue_service import DownloadQueueService
    
    if queue_item_id is None:
        queue_item = DownloadQueueService.add_to_queue(video)
        queue_item_id = queue_item.id
        logger.info(f"Created new queue item {queue_item_id} for video {video.id}")
    else:
        queue_item = DownloadQueueService.get_queue_item(queue_item_id, video_id=video.id, youtube_id=video.youtube_id)
        logger.info(f"Using existing queue item {queue_item_id} for video {video.id}")
    
    try:
        # Обновляем статус с обработкой возможных ошибок I/O
        try:
            DownloadQueueService.set_status(queue_item_id, 'downloading', video_id=video.id, youtube_id=video.youtube_id)
            logger.info(f"Download started for video {video.id}, queue status set to 'downloading'")
        except OSError as e:
            logger.warning(f"I/O error updating status, but continuing: {str(e)}")
        
        # Подготавливаем путь для сохранения видео
        import os
        from pathlib import Path
        import uuid
        # Не импортируем time повторно, т.к. он уже импортирован в начале файла
        
        # Используем номер видео для директории
        videos_base_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
        output_dir = os.path.join(videos_base_dir, f"{video.id}")
        
        # Проверяем, если видео уже загружено, чтобы избежать параллельных загрузок
        lock_file = f"/tmp/video_download_{video_id}.lock"
        
        # Добавляем уникальный идентификатор для задачи
        task_id = str(uuid.uuid4())
        
        # Создаем директорию для видео
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            logger.info(f"Created directory for video: {output_dir}")
        except Exception as e:
            logger.warning(f"Error creating directory: {str(e)}")
            # Можем попробовать os.makedirs в качестве резерва
            try:
                os.makedirs(output_dir, exist_ok=True)
                logger.info(f"Created directory using os.makedirs: {output_dir}")
            except Exception as e2:
                logger.error(f"Second error creating directory: {str(e2)}")
                raise
        
        # Проверяем, не выполняется ли загрузка уже
        try:
            if os.path.exists(lock_file):
                # Проверяем возраст блокировки
                try:
                    lock_age = time.time() - os.path.getmtime(lock_file)
                    if lock_age < 600:  # 10 минут
                        logger.info(f"Download already in progress for video {video.id}, skipping duplicate task")
                        return {"status": "skipped", "reason": "Download already in progress"}
                    else:
                        # Если блокировка старая, удаляем её
                        logger.warning(f"Found stale lock file (age: {lock_age}s), removing it")
                        os.remove(lock_file)
                except Exception as e:
                    logger.warning(f"Error checking lock file: {str(e)}")
            
            # Создаем файл блокировки
            try:
                with open(lock_file, 'w') as f:
                    f.write(str(self.request.id))
                logger.debug(f"Created lock file: {lock_file}")
                
                # Обновляем статус на "загружается"
                if queue_item:
                    _update_progress(queue_item, 5, 'downloading', 'Starting download...')
                    
            except Exception as e:
                error_msg = f"Failed to create lock file {lock_file}: {str(e)}"
                logger.error(error_msg)
                if queue_item:
                    _update_progress(queue_item, 0, 'failed', error_msg)
                raise
            
        except Exception as e:
            logger.warning(f"Error managing lock file: {str(e)}")
        
        # Теперь output_path это не путь к файлу, а путь к директории, где будет сохранен файл
        output_path = output_dir
        
        # Функция-обертка для update_progress с обработкой ошибок
        def safe_progress_update(progress):
            try:
                DownloadQueueService.update_progress(queue_item_id, progress, video_id=video.id, youtube_id=video.youtube_id)
            except Exception as e:
                logger.warning(f"Error updating progress (non-fatal): {str(e)}")
        
        # Создаем экземпляр загрузчика с обновленным API и безопасным хуком прогресса
        downloader = YouTubeDownloader(
            video_id=video_id,
            output_path=output_path,
            progress_hook=safe_progress_update
        )
        
        # Запускаем загрузку с подробным логированием
        logger.info(f"[DOWNLOAD_TASK] Starting actual download via YouTubeDownloader for video {video.id} (youtube_id: {video_id})")
        start_download_time = time.time()
        
        # Note: This will return None with our stub implementation
        file_path = downloader.download()
        
        # Since YouTube import is disabled, mark the task as failed but don't raise an exception
        if file_path is None:
            logger.warning(f"YouTube import is disabled - marking queue item {queue_item_id} as failed")
            try:
                DownloadQueueService.set_status(queue_item_id, 'failed', error_message="YouTube import feature has been disabled", video_id=video.id, youtube_id=video.youtube_id)
            except Exception as e:
                logger.warning(f"Error updating queue status: {str(e)}")
            return {"status": "failed", "reason": "YouTube import disabled"}
        
        if file_path:
            # Проверяем, что файл действительно существует и доступен
            file_exists = False
            try:
                file_exists = os.path.exists(file_path) and os.path.getsize(file_path) > 0
            except OSError as e:
                logger.warning(f"Error checking file {file_path}: {str(e)}")
                # Пробуем использовать pathlib, которая может быть более надежной в WSL
                try:
                    file_exists = Path(file_path).exists() and Path(file_path).stat().st_size > 0
                except Exception as e2:
                    logger.warning(f"Second error checking file {file_path}: {str(e2)}")
            
            if file_exists:
                # Проверяем, что файл существует и доступен для чтения
                if file_path and os.path.exists(file_path):
                    try:
                        # Дополнительная проверка целостности файла
                        try:
                            from pathlib import Path
                            file_path_obj = Path(file_path)
                            if not file_path_obj.is_file():
                                raise ValueError(f"Path exists but is not a file: {file_path}")
                                
                            # Проверка что файл не пустой и доступен для чтения
                            with open(file_path, 'rb') as f:
                                # Чтение небольшого фрагмента для проверки целостности
                                header = f.read(8192)  # Первые 8KB файла
                                if not header:
                                    raise ValueError(f"File appears to be empty or corrupted: {file_path}")
                                
                                # Получаем размер файла
                                f.seek(0, 2)
                                file_size = f.tell()
                                if file_size == 0:
                                    raise ValueError(f"File has zero size: {file_path}")
                        except Exception as e:
                            logger.error(f"File verification failed in Celery task: {str(e)}")
                            raise OSError(f"File verification failed: {str(e)}")
                        
                        logger.info(f"Downloaded file verified: {file_path}, size: {file_size/1024/1024:.2f} MB")
                        
                        # Дополнительный флаш файловой системы для убеждения, что файл полностью записан
                        try:
                            import subprocess
                            subprocess.run(['sync'], stderr=subprocess.PIPE, stdout=subprocess.PIPE, check=False)
                            logger.info("File system synced after verification")
                        except Exception as e:
                            logger.warning(f"Could not sync filesystem in task: {str(e)}")
                        
                        # Путь файла относительно MEDIA_ROOT для сохранения в модели
                        relative_path = os.path.relpath(file_path, settings.MEDIA_ROOT)
                        
                        # Обновляем запись видео с путем к файлу
                        video.file = os.path.join('videos', str(video.id), os.path.basename(file_path))
                        # НЕ устанавливаем здесь is_downloaded, это будет сделано в mark_as_completed
                        video.save(update_fields=['file'])
                        logger.info(f"Updated video {video_id} with file path: {video.file}")
            
                        try:
                            # Отмечаем загрузку как завершенную, передаем все ID для устойчивости
                            DownloadQueueService.mark_as_completed(queue_item_id, video_id=video.id, youtube_id=video.youtube_id)
                            logger.info(f"[TASK_MARK_COMPLETED] Successfully marked queue item {queue_item_id} for video {video.id} as completed")
                        except Exception as e:
                            logger.error(f"[TASK_MARK_COMPLETED_ERROR] Could not mark queue item as completed: {e}")
                            import traceback
                            logger.error(f"[TASK_MARK_COMPLETED_TRACEBACK] {traceback.format_exc()}")
                        
                        # Скачиваем видео с обновлением прогресса
                        logger.info(f"[DOWNLOAD_START] Starting download for video {video.id} ({video.youtube_id})")
        
                        try:
                            # Обновляем прогресс
                            if queue_item:
                                _update_progress(queue_item, 10, 'downloading', 'Preparing download...')
            
                            # Здесь будет логика скачивания видео
                            # Временная заглушка с имитацией прогресса
                            for progress in range(20, 101, 10):
                                time.sleep(1)  # Имитация загрузки
                                if queue_item:
                                    status_msg = f"Downloading... {progress}%"
                                    _update_progress(queue_item, progress, 'downloading', status_msg)
            
                            # Обновляем статус видео
                            video.is_downloaded = True
                            video.save(update_fields=['is_downloaded'])
            
                            logger.info(f"[DOWNLOAD_COMPLETE] Successfully downloaded video {video.id} ({video.youtube_id}")
            
                            # Обновляем статус в очереди, если есть queue_item
                            if queue_item:
                                _update_progress(queue_item, 100, 'completed', 'Download completed successfully')
                
                                # Запускаем обработку следующего видео в очереди
                                try:
                                    DownloadQueueService.process_next_in_queue()
                                except Exception as e:
                                    logger.error(f"Error processing next in queue: {str(e)}", exc_info=True)
            
                            # Генерируем теги и рассчитываем рейтинг
                            try:
                                logger.info(f"[POST_PROCESS] Starting post-processing for video {video.id}")
                
                                # Вызываем сигнал post_save для генерации тегов
                                from django.db.models.signals import post_save
                                from django.db.models.signals import ModelSignal
                
                                # Создаем сигнал, если его еще нет
                                if not hasattr(post_save, 'send'):
                                    post_save = ModelSignal(use_caching=True)
                
                                # Отправляем сигнал с created=True, чтобы сгенерировались теги
                                post_save.send(
                                    sender=video.__class__,
                                    instance=video,
                                    created=True,
                                    update_fields=None,
                                    raw=False,
                                    using='default'
                                )
                
                                # Рассчитываем рейтинг
                                video.calculate_absolute_rating()
                
                                logger.info(f"[POST_PROCESS] Completed post-processing for video {video.id}")
                
                            except Exception as e:
                                logger.error(f"Error in post-processing for video {video.id}: {str(e)}", exc_info=True)
                                # Продолжаем выполнение, даже если пост-обработка не удалась
            
                            return {
                                'status': 'success',
                                'video_id': video.id,
                                'youtube_id': video.youtube_id,
                                'title': video.title,
                                'duration': time.time() - start_time
                            }
                
                        except Exception as e:
                            error_msg = f"Error downloading video {video.id}: {str(e)}"
                            logger.error(error_msg, exc_info=True)
            
                            # Обновляем статус в очереди, если есть queue_item
                            if queue_item:
                                _update_progress(queue_item, 0, 'failed', error_msg)
                
                                # Запускаем обработку следующего видео в очереди
                                try:
                                    DownloadQueueService.process_next_in_queue()
                                except Exception as e:
                                    logger.error(f"Error processing next in queue after failure: {str(e)}", exc_info=True)
            
                            # Пробрасываем исключение для Celery
                            raise
            
                        # Статус в очереди загрузок уже обновлен через DownloadQueueService.mark_as_completed выше
                        
                        # Запускаем обработку следующего элемента в очереди
                        try:
                            DownloadQueueService.process_next_in_queue()
                        except Exception as e:
                            logger.warning(f"Error processing next item in queue: {str(e)}")
                        
                        # Общее время выполнения задачи
                        elapsed_time = time.time() - start_time
                        logger.info(f"[TASK_COMPLETE] Download task for video {video.id} completed successfully in {elapsed_time:.2f} seconds")
                        return {'success': True, 'video_id': video.id, 'file_path': str(file_path), 'elapsed_time': elapsed_time}
                    except OSError as e:
                        logger.error(f"File access error: {str(e)}")
                        return f"Download completed but file access failed: {str(e)}"
                
                # Если мы дошли до этой точки, значит загрузка не удалась
                try:
                    DownloadQueueService.set_status(queue_item_id, 'failed', error_message="Download failed or file not accessible", video_id=video.id, youtube_id=video.youtube_id)
                except Exception as e:
                    logger.warning(f"Error updating queue status after failure: {str(e)}")
                    
                elapsed_time = time.time() - start_time
                logger.error(f"[TASK_FAILED] Download failed for video {video.id} - '{video.title}' after {elapsed_time:.2f} seconds")
                return {'success': False, 'error': 'Download failed', 'elapsed_time': elapsed_time}
                    
                logger.error(f"[DOWNLOAD_VERIFY_FAILED] File path was returned but file does not exist or is empty: {file_path}")
        
        # Если мы дошли до этой точки, значит загрузка не удалась
        try:
            DownloadQueueService.set_status(queue_item_id, 'failed', error_message="Download failed or file not accessible")
        except Exception as e:
            logger.warning(f"Error updating queue status after failure: {str(e)}")
            
        elapsed_time = time.time() - start_time
        logger.error(f"[TASK_FAILED] Download failed for video {video.id} - '{video.title}' after {elapsed_time:.2f} seconds")
        return {'success': False, 'error': 'Download failed', 'elapsed_time': elapsed_time}
            
    except SoftTimeLimitExceeded:
        elapsed_time = time.time() - start_time
        logger.error(f"[TASK_TIMEOUT] Soft time limit exceeded for video {video.id} after {elapsed_time:.2f} seconds")
        # Отложенный импорт для избежания циклической зависимости
        from core.services.download_queue_service import DownloadQueueService
        DownloadQueueService.set_status(queue_item_id, 'failed', error_message="Task timed out", video_id=video.id, youtube_id=video.youtube_id)
        return {'success': False, 'error': 'Task timed out', 'elapsed_time': elapsed_time}
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.exception(f"[TASK_ERROR] Error downloading video {video.id}: {str(e)} after {elapsed_time:.2f} seconds")
        
        try:
            # Не удалось скачать видео
            logger.error(f"[DOWNLOAD_FAILED] Failed to download video {video.id} (youtube_id: {video_id})")
            
            # Обновляем статус в очереди и переходим к следующему элементу
            from core.services.download_queue_service import DownloadQueueService
            DownloadQueueService.set_status(queue_item_id, 'failed', video_id=video.id, youtube_id=video.youtube_id)
            DownloadQueueService.process_next_in_queue()
            
            # Повторяем задачу с экспоненциальной задержкой
            retry_count = self.request.retries
            countdown = 60 * (2 ** retry_count)  # 1 мин, 2 мин, 4 мин, ...
            logger.info(f"Retrying download for video {video.id} in {countdown} seconds (retry {retry_count + 1}/3)")
            self.retry(countdown=countdown, exc=e)
            
        except MaxRetriesExceededError:
            logger.error(f"[TASK_MAX_RETRIES] Max retries exceeded for video {video.id}")
            # Отложенный импорт для избежания циклической зависимости
            from core.services.download_queue_service import DownloadQueueService
            DownloadQueueService.set_status(queue_item_id, 'failed', error_message=f"Max retries exceeded: {str(e)}", video_id=video.id, youtube_id=video.youtube_id)
            return {'success': False, 'error': str(e), 'elapsed_time': elapsed_time}
    finally:
        # Process next in queue regardless of success/failure
        logger.info(f"Processing next video in queue after video {video.id}")
        # Отложенный импорт для избежания циклической зависимости
        from core.services.download_queue_service import DownloadQueueService
        DownloadQueueService.process_next_in_queue()

@shared_task
def cleanup_failed_downloads():
    """
    Periodic task to clean up failed downloads and reset status
    """
    # Находим все неудачные загрузки в очереди
    failed_queue_items = VideoDownloadQueue.objects.filter(status='failed')
    
    for queue_item in failed_queue_items:
        try:
            # Обновляем статус очереди
            queue_item.status = 'queued'
            queue_item.progress = 0
            queue_item.error_message = None
            queue_item.save()
            
            # Очищаем статус в кеше
            cache_key = f'video_download_status_{queue_item.video.youtube_id}'
            cache.delete(cache_key)
            
            logger.info(f"Reset failed download for video {queue_item.video.youtube_id}")
        except Exception as e:
            logger.error(f"Error resetting failed download: {str(e)}")
    
    # Проверяем, есть ли активные загрузки
    active_downloads = VideoDownloadQueue.objects.filter(status='downloading')
    if not active_downloads.exists():
        # Если нет активных загрузок, запускаем обработку следующего элемента в очереди
        DownloadQueueService.process_next_in_queue()
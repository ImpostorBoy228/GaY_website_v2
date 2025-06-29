from __future__ import absolute_import, unicode_literals
import os
import multiprocessing
multiprocessing.set_start_method('spawn', force=True)
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bites_videos.settings')

# Create the Celery app
app = Celery('bites_videos')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django apps configs.
app.autodiscover_tasks()

# Конфигурация для повышения производительности
app.conf.update(
    # Увеличиваем число параллельных процессов
    worker_concurrency=4,
    
    # Оптимизируем обработку очереди
    worker_prefetch_multiplier=4,
    
    # Устанавливаем таймаут задач
    task_time_limit=1800,  # 30 минут максимум на задачу
    task_soft_time_limit=1500,  # 25 минут мягкий лимит
    
    # Настраиваем повторные попытки
    task_acks_late=True,  # Подтверждение после выполнения
    task_reject_on_worker_lost=True,  # Вернуть задачу в очередь если воркер умирает
    
    # Улучшаем обработку ошибок
    task_track_started=True,  # Отслеживать начало выполнения задачи
    
    # Улучшаем производительность брокера
    broker_pool_limit=10,  # Больше соединений к брокеру
    broker_connection_timeout=30,  # Увеличиваем таймаут соединения
    
    # Логирование
    worker_log_level='INFO',
)

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}') 
import logging
import os
import queue
import threading
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import yt_dlp
from dotenv import load_dotenv
from models import Video, VideoCounter
from extensions import db
from datetime import datetime
from global_state import tasks

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    def __init__(self, app, socketio):
        logger.info("Инициализация YouTubeDownloader")
        self.app = app
        self.socketio = socketio
        load_dotenv()
        self.api_key = os.getenv('YOUTUBE_API_KEY')
        if not self.api_key:
            logger.error("YOUTUBE_API_KEY не найден в .env")
            raise ValueError("YOUTUBE_API_KEY не найден в .env")
        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        self.download_queue = queue.Queue()
        self.download_thread = threading.Thread(target=self._download_worker, daemon=True)
        self.download_thread.start()
        logger.info("YouTubeDownloader успешно инициализирован")

    def search_videos(self, query, max_results=10, min_views=0, min_duration=0, max_duration=3600):
        logger.info(f"Поиск видео по запросу: {query}, max_results={max_results}")
        try:
            request = self.youtube.search().list(
                part='id,snippet',
                q=query,
                type='video',
                maxResults=max_results
            )
            response = request.execute()
            video_ids = [item['id']['videoId'] for item in response.get('items', [])]
            logger.info(f"Получение деталей для {len(video_ids)} видео")
            videos = self._get_video_details(video_ids)
            logger.info(f"Получены детали для {len(videos)} видео")
            filtered_videos = [
                video for video in videos
                if (video.get('views', 0) >= min_views and
                    min_duration <= video.get('duration', 0) <= max_duration)
            ]
            logger.info(f"Найдено {len(filtered_videos)} видео по запросу '{query}'")
            return filtered_videos
        except HttpError as e:
            logger.error(f"Ошибка YouTube API: {e}")
            return []
        except Exception as e:
            logger.error(f"Неожиданная ошибка при поиске видео: {e}")
            return []

    def _get_video_details(self, video_ids):
        if not video_ids:
            return []
        request = self.youtube.videos().list(
            part='snippet,contentDetails,statistics',
            id=','.join(video_ids)
        )
        response = request.execute()
        videos = []
        for item in response.get('items', []):
            duration = self._parse_duration(item['contentDetails']['duration'])
            views = int(item['statistics'].get('viewCount', 0))
            videos.append({
                'video_id': item['id'],
                'title': item['snippet']['title'],
                'description': item['snippet'].get('description', ''),
                'duration': duration,
                'views': views,
                'tags': item['snippet'].get('tags', []),
                'channel': item['snippet']['channelTitle']
            })
        return videos

    def _parse_duration(self, duration):
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def search_by_tags(self, tags, max_results=10, min_views=0, min_duration=0, max_duration=3600):
        query = ' '.join(tags)
        return self.search_videos(query, max_results, min_views, min_duration, max_duration)

    def search_by_channel(self, channel, max_results=10, min_views=0, min_duration=0, max_duration=3600):
        logger.info(f"Поиск видео для канала: {channel}, max_results={max_results}")
        try:
            request = self.youtube.search().list(
                part='id,snippet',
                channelId=channel,
                type='video',
                maxResults=max_results
            )
            response = request.execute()
            video_ids = [item['id']['videoId'] for item in response.get('items', [])]
            logger.info(f"Получение деталей для {len(video_ids)} видео")
            videos = self._get_video_details(video_ids)
            logger.info(f"Получены детали для {len(videos)} видео")
            filtered_videos = [
                video for video in videos
                if (video.get('views', 0) >= min_views and
                    min_duration <= video.get('duration', 0) <= max_duration)
            ]
            logger.info(f"Найдено {len(filtered_videos)} видео для канала '{channel}'")
            return filtered_videos
        except HttpError as e:
            logger.error(f"Ошибка YouTube API: {e}")
            return []
        except Exception as e:
            logger.error(f"Неожиданная ошибка при поиске по каналу: {e}")
            return []

    def add_download_task(self, video_urls, task_id, uploader):
        logger.info(f"Добавление задачи загрузки для {len(video_urls)} видео с task_id {task_id}")
        for url in video_urls:
            self.download_queue.put((url, task_id, uploader))
        logger.info(f"Добавлено {len(video_urls)} видео в очередь загрузки для task_id {task_id}")

    def _download_worker(self):
        logger.info("Запуск рабочего потока загрузки")
        while True:
            try:
                if self.download_queue.empty():
                    logger.debug("Очередь загрузок пуста, ожидание...")
                    time.sleep(1)
                    continue
                url, task_id, uploader = self.download_queue.get()
                logger.info(f"Обработка загрузки для URL: {url}, task_id: {task_id}")
                self._download_video(url, task_id, uploader)
                self.download_queue.task_done()
            except Exception as e:
                logger.error(f"Ошибка в рабочем потоке загрузки: {e}")
                self.download_queue.task_done()

    def _download_video(self, url, task_id, uploader):
        logger.info(f"Загрузка видео с {url} для task_id {task_id}")
        video_id = url.split('v=')[-1][:11] if 'v=' in url else url.split('/')[-1]
        output_path = os.path.join('static', 'videos', f"{task_id}_{video_id}.mp4")
        thumbnail_path = os.path.join('static', 'thumbnails', f"{task_id}_{video_id}.jpg")
        
        # Обновление статуса задачи
        with self.app.app_context():
            if task_id in tasks:
                for task in tasks[task_id]['tasks']:
                    if task['video_id'] == video_id:
                        task['status'] = 'downloading'
                        task['progress'] = 10
                        self.socketio.emit('progress', tasks[task_id], namespace='/download')
                        logger.info(f"Обновлён статус для video_id {video_id}: downloading, прогресс 10%")

        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': True,
            'noplaylist': True,
            'progress_hooks': [lambda d: self._progress_hook(d, task_id, video_id)],
        }

        # Получение метаданных видео
        try:
            video_info = self._get_video_details([video_id])[0]
            title = video_info['title']
            description = video_info['description']
            duration = video_info['duration']
        except Exception as e:
            logger.error(f"Не удалось получить метаданные для видео {video_id}: {e}")
            title = f"Video {video_id}"
            description = ""
            duration = 0

        # Загрузка видео
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info(f"Успешно загружено видео в {output_path}")

            # Создание миниатюры
            try:
                import subprocess
                os.makedirs(os.path.dirname(thumbnail_path), exist_ok=True)
                cmd = [
                    'ffmpeg', '-i', output_path, '-ss', '10', '-vframes', '1',
                    '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',
                    '-q:v', '2', thumbnail_path
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                logger.info(f"Создан эскиз в {thumbnail_path}")
            except Exception as e:
                logger.error(f"Не удалось создать эскиз для видео {video_id}: {e}")
                thumbnail_path = None

            # Создание записи в таблице Video
            with self.app.app_context():
                try:
                    unique_video_id = f"{task_id}_{video_id}"
                    new_video = Video(
                        id=unique_video_id,
                        title=title,
                        description=description,
                        upload_date=datetime.utcnow(),
                        views=0,
                        uploader=uploader,
                        duration=duration,
                        file_extension='mp4',
                        thumbnail_extension='jpg' if thumbnail_path else None
                    )
                    db.session.add(new_video)

                    # Создание записи в VideoCounter
                    video_counter = VideoCounter(video_id=unique_video_id, views=0)
                    db.session.add(video_counter)

                    db.session.commit()
                    logger.info(f"Видео {unique_video_id} проиндексировано в базе данных")

                    # Обновление статуса задачи
                    if task_id in tasks:
                        tasks[task_id]['downloaded'] += 1
                        for task in tasks[task_id]['tasks']:
                            if task['video_id'] == video_id:
                                task['status'] = 'completed'
                                task['progress'] = 100
                        self.socketio.emit('progress', tasks[task_id], namespace='/download')
                        logger.info(f"Обновлён статус для video_id {video_id}: completed, прогресс 100%")
                except Exception as e:
                    db.session.rollback()
                    logger.error(f"Не удалось проиндексировать видео {video_id} в базе данных: {e}")
                    raise
        except Exception as e:
            logger.error(f"Не удалось загрузить видео с {url}: {e}")
            with self.app.app_context():
                if task_id in tasks:
                    for task in tasks[task_id]['tasks']:
                        if task['video_id'] == video_id:
                            task['status'] = 'failed'
                            task['progress'] = 0
                    self.socketio.emit('progress', tasks[task_id], namespace='/download')
                    logger.info(f"Обновлён статус для video_id {video_id}: failed")
            raise

    def _progress_hook(self, d, task_id, video_id):
        if d['status'] == 'downloading':
            with self.app.app_context():
                if task_id in tasks:
                    progress = min(90, int(d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 80) + 10)
                    for task in tasks[task_id]['tasks']:
                        if task['video_id'] == video_id:
                            task['progress'] = progress
                    self.socketio.emit('progress', tasks[task_id], namespace='/download')
                    logger.debug(f"Обновлён прогресс для video_id {video_id}: {progress}%")
        elif d['status'] == 'finished':
            logger.info(f"Завершена загрузка для video_id {video_id}")
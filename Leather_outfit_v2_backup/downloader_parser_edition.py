import os
import json
import requests
import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from datetime import datetime
import yt_dlp as youtube_dl
from dotenv import load_dotenv
import logging
from logging.handlers import RotatingFileHandler
import uuid
import time
from collections import defaultdict

load_dotenv()

# 🔧 Конфигурация красивого логирования
def setup_logging():
    logger = logging.getLogger('YouTubeBackup')
    logger.setLevel(logging.INFO)
    
    # Форматтер с цветами
    class ColorFormatter(logging.Formatter):
        grey = "\x1b[38;20m"
        yellow = "\x1b[33;20m"
        red = "\x1b[31;20m"
        bold_red = "\x1b[31;1m"
        reset = "\x1b[0m"
        blue = "\x1b[34;20m"
        green = "\x1b[32;20m"
        
        FORMATS = {
            logging.DEBUG: grey + "%(asctime)s [%(levelname)s] %(message)s" + reset,
            logging.INFO: blue + "%(asctime)s [%(levelname)s] " + green + "%(message)s" + reset,
            logging.WARNING: yellow + "%(asctime)s [%(levelname)s] %(message)s" + reset,
            logging.ERROR: red + "%(asctime)s [%(levelname)s] %(message)s" + reset,
            logging.CRITICAL: bold_red + "%(asctime)s [%(levelname)s] %(message)s" + reset
        }
        
        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
            return formatter.format(record)
    
    # Консольный вывод с цветами
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColorFormatter())
    
    # Файловый вывод с ротацией
    file_handler = RotatingFileHandler(
        'youtube_backup.log',
        maxBytes=5*1024*1024,  # 5 MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

logger = setup_logging()

# 🔐 Конфигурация
CONFIG = {
    "storage_path": os.getenv('STORAGE_PATH', '/mnt/d/videos'),
    "db_uri": os.getenv('SUPABASE_DB_URI'),
    "service_account_file": os.getenv('SERVICE_ACCOUNT_FILE', '/home/impostorboy/downlader/service_account.json'),
    "max_retries": 3,
    "retry_delay": 5,
    "avg_video_size_mb": 100,  # Для оценки времени загрузки
    "avg_download_speed_mbps": 10  # Для оценки времени загрузки
}

# 🔗 Подключение к базе данных
engine = create_engine(CONFIG['db_uri'], pool_pre_ping=True, pool_recycle=3600)
db = scoped_session(sessionmaker(bind=engine))

class YouTubeBackup:
    def __init__(self):
        """Инициализация с увеличенными timeout параметрами"""
        self.youtube_service = self.get_youtube_service()
        self.stats = defaultdict(int)
        self.download_timeout = 300  # 5 минут вместо 30 секунд
        self.max_download_attempts = 5  # Максимальное количество попыток загрузки

    def get_youtube_service(self):
        """Создание клиента YouTube API с использованием учетных данных службы."""
        try:
            credentials = service_account.Credentials.from_service_account_file(
                CONFIG['service_account_file'],
                scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
            )
            logger.info("🎬 YouTube service initialized successfully")
            return build('youtube', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"🔥 Failed to initialize YouTube service: {e}")
            return None

    def parse_duration(self, duration):
        """Парсинг длительности видео из формата ISO 8601 в секунды."""
        try:
            seconds = int(isodate.parse_duration(duration).total_seconds())
            logger.debug(f"⏱️ Duration parsed: {duration} → {seconds} seconds")
            return seconds
        except Exception as e:
            logger.warning(f"⚠️ Failed to parse duration '{duration}': {e}")
            return 0

    def save_video_to_db(self, video_id, title, description, uploader, views, duration, upload_date, file_extension='mp4', thumbnail_extension='jpg'):
        """Сохранение информации о видео в базу данных."""
        try:
            file_extension = file_extension.lstrip('.')
            thumbnail_extension = thumbnail_extension.lstrip('.')
            title = title[:200] if title else "Untitled"
            description = description[:5000] if description else ""
            uploader = uploader[:255] if uploader else "Unknown"
            
            db.execute(text(""" 
                INSERT INTO videos (id, title, description, uploader, views, duration, upload_date, file_extension, thumbnail_extension) 
                VALUES (:id, :title, :description, :uploader, :views, :duration, :upload_date, :file_extension, :thumbnail_extension) 
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    views = EXCLUDED.views,
                    duration = EXCLUDED.duration,
                    file_extension = EXCLUDED.file_extension,
                    thumbnail_extension = EXCLUDED.thumbnail_extension;
            """), {
                "id": video_id,
                "title": title,
                "description": description,
                "uploader": uploader,
                "views": views,
                "duration": duration,
                "upload_date": datetime.strptime(upload_date, '%Y-%m-%dT%H:%M:%SZ'),
                "file_extension": file_extension,
                "thumbnail_extension": thumbnail_extension
            })
            db.commit()
            logger.info(f"💾 Saved video {video_id} to database: '{title}'")
            self.stats['saved'] += 1
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Error saving video {video_id} to database: {e}")
            self.stats['db_errors'] += 1
            raise

    def download_thumbnail(self, video_id, format="jpg"):
        """Загрузка миниатюры видео в указанном формате."""
        try:
            thumbnail_path = os.path.join(CONFIG['storage_path'], f"{video_id}.{format}")
            url_variants = [
                f"https://img.youtube.com/vi/{video_id}/maxresdefault.{format}",
                f"https://img.youtube.com/vi/{video_id}/hqdefault.{format}",
                f"https://img.youtube.com/vi/{video_id}/mqdefault.{format}",
                f"https://img.youtube.com/vi/{video_id}/default.{format}",
            ]
            
            for url in url_variants:
                response = requests.get(url)
                if response.status_code == 200:
                    with open(thumbnail_path, 'wb') as f:
                        f.write(response.content)
                    logger.info(f"🖼️ Downloaded thumbnail for {video_id}: {thumbnail_path}")
                    self.stats['thumbnails'] += 1
                    return format
            
            logger.warning(f"⚠️ No thumbnail found for {video_id}")
            self.stats['thumbnail_fails'] += 1
            return None
        except Exception as e:
            logger.error(f"❌ Error downloading thumbnail for {video_id}: {e}")
            self.stats['thumbnail_errors'] += 1
            return None

    def get_video_info(self, video_id):
        """Получение информации о видео через YouTube API."""
        for attempt in range(CONFIG['max_retries']):
            try:
                response = self.youtube_service.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=video_id
                ).execute()

                if not response['items']:
                    logger.warning(f"⚠️ No info found for video {video_id}")
                    self.stats['no_info'] += 1
                    return None

                data = response['items'][0]
                duration = self.parse_duration(data.get('contentDetails', {}).get('duration', 'PT0S'))
                info = {
                    'title': data['snippet']['title'],
                    'channel': data['snippet']['channelTitle'],
                    'description': data['snippet']['description'],
                    'uploader': data['snippet']['channelTitle'],
                    'views': int(data['statistics'].get('viewCount', 0)),
                    'duration': duration,
                    'upload_date': data['snippet']['publishedAt'],
                    'tags': data['snippet'].get('tags', []),
                    'thumbnail': data['snippet']['thumbnails'].get('default', {}).get('url', '')
                }
                logger.debug(f"ℹ️ Retrieved info for {video_id}: {info['title']} ({info['views']} views, {info['duration']} sec)")
                return info
            except HttpError as e:
                if attempt < CONFIG['max_retries'] - 1:
                    logger.warning(f"⚠️ YouTube API error for {video_id}, attempt {attempt + 1}/{CONFIG['max_retries']}: {e}")
                    time.sleep(CONFIG['retry_delay'])
                    continue
                logger.error(f"❌ YouTube API error for {video_id}: {e}")
                self.stats['api_errors'] += 1
                return None
            except Exception as e:
                logger.error(f"❌ Error getting info for {video_id}: {e}")
                self.stats['info_errors'] += 1
                return None

    def check_video_exists(self, video_id):
        """Проверка, существует ли видео в базе данных."""
        try:
            result = db.execute(text("SELECT 1 FROM videos WHERE id = :id"), {"id": video_id})
            exists = result.fetchone() is not None
            logger.debug(f"🔍 Video {video_id} exists in database: {exists}")
            return exists
        except Exception as e:
            logger.error(f"❌ Error checking video {video_id} existence: {e}")
            self.stats['check_errors'] += 1
            return False

    def download_video(self, video_id, video_format="best"):
        """Загрузка видео с увеличенным timeout и повторными попытками"""
        output_template = f"{CONFIG['storage_path']}/%(id)s.%(ext)s"
        
        ydl_opts = {
            'format': video_format,
            'outtmpl': output_template,
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'cookiefile': os.path.join(os.path.expanduser('~'), 'cookies.txt'),
            'socket_timeout': self.download_timeout,
            'retries': self.max_download_attempts,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']  # Пропускаем сложные форматы для ускорения
                }
            }
        }

        for attempt in range(self.max_download_attempts):
            try:
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(
                        f'https://youtube.com/watch?v={video_id}',
                        download=True
                    )
                    actual_ext = info.get('ext', 'mp4')
                    logger.info(f"⬇️ Downloaded video {video_id} as {video_id}.{actual_ext}")
                    self.stats['downloaded'] += 1
                    return actual_ext
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_download_attempts} failed for {video_id}: {e}")
                if attempt < self.max_download_attempts - 1:
                    time.sleep(5 * (attempt + 1))  # Увеличиваем задержку между попытками
        
        logger.error(f"❌ Failed to download video {video_id} after {self.max_download_attempts} attempts")
        self.stats['download_errors'] += 1
        return None

    def process_video(self, video_id, thumbnail_format="jpg", video_format="best"):
        """Обработка одного видео: проверка, загрузка и сохранение."""
        if self.check_video_exists(video_id):
            logger.info(f"⏩ Video {video_id} already exists in database, skipping")
            self.stats['skipped'] += 1
            return False

        info = self.get_video_info(video_id)
        if not info:
            logger.warning(f"⚠️ Skipping video {video_id}: no info available")
            self.stats['no_info'] += 1
            return False

        thumb_ext = self.download_thumbnail(video_id, thumbnail_format) or thumbnail_format
        video_ext = self.download_video(video_id, video_format) or 'mp4'
        
        if video_ext:
            try:
                self.save_video_to_db(
                    video_id,
                    info['title'],
                    info['description'],
                    info['uploader'],
                    info['views'],
                    info['duration'],
                    info['upload_date'],
                    video_ext,
                    thumb_ext
                )
                return True
            except Exception as e:
                logger.error(f"❌ Failed to save video {video_id} to database: {e}")
                return False
        else:
            logger.warning(f"⚠️ Skipping video {video_id}: failed to download")
            return False

    def get_channel_id(self, channel_name):
        """Поиск channelId по названию канала."""
        try:
            response = self.youtube_service.search().list(
                q=channel_name,
                part='snippet',
                type='channel',
                maxResults=1
            ).execute()

            if response['items']:
                channel_id = response['items'][0]['id']['channelId']
                logger.info(f"Найден channelId для '{channel_name}': {channel_id}")
                return channel_id
            else:
                logger.error(f"Канал '{channel_name}' не найден")
                return None
        except HttpError as e:
            logger.error(f"Ошибка при поиске канала '{channel_name}': {e}")
            return None
        except Exception as e:
            logger.error(f"Неожиданная ошибка при поиске канала '{channel_name}': {e}")
            return None

    def search_videos(self, query, max_results=10):
        """Поиск видео по запросу через YouTube API."""
        try:
            videos = []
            page_token = None
            remaining_results = max_results
            videos_per_request = min(50, max_results)

            while remaining_results > 0:
                response = self.youtube_service.search().list(
                    q=query,
                    part='id,snippet',
                    maxResults=videos_per_request,
                    type='video',
                    pageToken=page_token
                ).execute()

                video_ids = [item['id']['videoId'] for item in response['items']]
                if not video_ids:
                    break

                videos_info = self.youtube_service.videos().list(
                    part='snippet,statistics',
                    id=','.join(video_ids)
                ).execute()

                for item in videos_info['items']:
                    videos.append({
                        'id': item['id'],
                        'title': item['snippet']['title'],
                        'channel': item['snippet']['channelTitle'],
                        'thumbnail': item['snippet']['thumbnails'].get('default', {}).get('url', ''),
                        'views': int(item['statistics'].get('viewCount', 0))
                    })

                remaining_results -= len(videos_info['items'])
                videos_per_request = min(50, remaining_results)
                page_token = response.get('nextPageToken')
                if not page_token or len(videos) >= max_results:
                    break

            logger.info(f"🔎 Found {len(videos)} videos for query '{query}'")
            return videos[:max_results]
        except HttpError as e:
            logger.error(f"❌ YouTube API error during video search: {e}")
            self.stats['api_errors'] += 1
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error during video search: {e}")
            self.stats['search_errors'] += 1
            return []

    def search_tags(self, query, max_results=10):
        """Поиск тегов, соответствующих запросу, с количеством видео."""
        try:
            tags = defaultdict(int)
            page_token = None
            videos_per_request = 50

            response = self.youtube_service.search().list(
                q=query,
                part='id',
                maxResults=videos_per_request,
                type='video',
                pageToken=page_token
            ).execute()

            video_ids = [item['id']['videoId'] for item in response['items']]
            if not video_ids:
                return []

            videos_info = self.youtube_service.videos().list(
                part='snippet',
                id=','.join(video_ids)
            ).execute()

            for item in videos_info['items']:
                video_tags = item['snippet'].get('tags', [])
                for tag in video_tags:
                    if query.lower() in tag.lower():
                        tags[tag] += 1

            sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)
            result = [{'name': tag, 'count': count} for tag, count in sorted_tags][:max_results]
            logger.info(f"🏷️ Found {len(result)} tags for query '{query}'")
            return result
        except HttpError as e:
            logger.error(f"❌ YouTube API error during tag search: {e}")
            self.stats['api_errors'] += 1
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error during tag search: {e}")
            self.stats['search_errors'] += 1
            return []

    def search_channels(self, query, max_results=10):
        """Поиск каналов по запросу через YouTube API."""
        try:
            channels = []
            page_token = None
            channels_per_request = min(50, max_results)

            while len(channels) < max_results:
                response = self.youtube_service.search().list(
                    q=query,
                    part='snippet',
                    maxResults=channels_per_request,
                    type='channel',
                    pageToken=page_token
                ).execute()

                for item in response['items']:
                    channels.append({
                        'title': item['snippet']['title'],
                        'thumbnail': item['snippet']['thumbnails'].get('default', {}).get('url', '')
                    })

                channels_per_request = min(50, max_results - len(channels))
                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            logger.info(f"📺 Found {len(channels)} channels for query '{query}'")
            return channels[:max_results]
        except HttpError as e:
            logger.error(f"❌ YouTube API error during channel search: {e}")
            self.stats['api_errors'] += 1
            return []
        except Exception as e:
            logger.error(f"❌ Unexpected error during channel search: {e}")
            self.stats['search_errors'] += 1
            return []

    def search_and_download(self, query, max_results=300, min_views=0, min_duration=0, max_duration=float('inf')):
        """Поиск и загрузка с гарантией количества результатов"""
        try:
            logger.info(f"🔎 Starting search for: '{query}' (max: {max_results}, views: >{min_views}, duration: {min_duration}-{max_duration}s)")
            
            downloaded_count = 0
            page_token = None
            processed_videos = 0
            max_attempts = max_results * 5  # Лимит для предотвращения бесконечного цикла
            videos_per_request = min(50, max(10, max_results - downloaded_count))  # Динамический размер страницы
            
            while downloaded_count < max_results and processed_videos < max_attempts:
                logger.info(f"📖 Fetching page (downloaded: {downloaded_count}/{max_results}, processed: {processed_videos})")
                
                # Поиск видео
                response = self.youtube_service.search().list(
                    q=query,
                    part='id,snippet',
                    maxResults=videos_per_request,
                    type='video',
                    pageToken=page_token
                ).execute()

                video_ids = [item['id']['videoId'] for item in response['items']]
                
                # Получаем информацию о видео
                videos_info = self.youtube_service.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=','.join(video_ids)
                ).execute()

                for video_info in videos_info['items']:
                    if downloaded_count >= max_results:
                        break

                    video_id = video_info['id']
                    processed_videos += 1
                    
                    try:
                        title = video_info['snippet']['title']
                        views = int(video_info['statistics'].get('viewCount', 0))
                        duration = self.parse_duration(video_info['contentDetails']['duration'])
                        
                        # Фильтры
                        if views < min_views:
                            logger.debug(f"⚡ Skipped '{title}' - views: {views} < {min_views}")
                            continue
                            
                        if not (min_duration <= duration <= max_duration):
                            logger.debug(f"⚡ Skipped '{title}' - duration: {duration}s not in {min_duration}-{max_duration}")
                            continue

                        logger.info(f"🎥 Processing #{downloaded_count+1}: '{title}' ({views} views, {duration}s)")
                        
                        if self.process_video(video_id):
                            downloaded_count += 1
                            logger.info(f"✅ Progress: {downloaded_count}/{max_results}")
                        else:
                            logger.warning(f"⚠️ Failed to process video {video_id}")

                    except Exception as e:
                        logger.error(f"❌ Error processing video {video_id}: {str(e)}")
                        continue

                # Адаптивный выбор следующей страницы
                page_token = response.get('nextPageToken')
                if not page_token:
                    logger.info("🔚 No more pages available")
                    break
                
                # Динамически обновляем размер страницы для следующего запроса
                videos_per_request = min(50, max(10, max_results - downloaded_count))

            if downloaded_count < max_results:
                logger.warning(f"Found only {downloaded_count}/{max_results} matching videos after processing {processed_videos} videos")
            else:
                logger.info(f"🏁 Successfully downloaded {downloaded_count} videos")

            return downloaded_count

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return downloaded_count
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return downloaded_count
            
    def download_by_tags(self, tags, max_results=300, min_views=0, min_duration=0, max_duration=float('inf')):
        """Загрузка видео по тегам с учетом фильтров."""
        if not tags:
            logger.warning("⚠️ No tags provided")
            return 0

        query = "|".join(tags)
        logger.info(f"🏷️ Searching by tags: {tags}")
        return self.search_and_download(query, max_results, min_views, min_duration, max_duration)

    def download_by_channel(self, channel_id=None, channel_name=None, max_results=300, min_views=0, min_duration=0, max_duration=float('inf')):
        """Загрузка видео с канала с учетом фильтров. Принимает channel_id или channel_name."""
        try:
            if not channel_id and channel_name:
                channel_id = self.get_channel_id(channel_name)
                if not channel_id:
                    logger.error(f"Не удалось найти channelId для '{channel_name}'. Прерывание.")
                    return 0

            if not channel_id:
                logger.error("Channel ID или название канала обязательно!")
                return 0

            logger.info(f"📺 Starting channel download: {channel_id}")
            
            downloaded_count = 0
            page_token = None
            videos_per_request = min(50, max(10, max_results))
            processed_videos = 0
            max_attempts = max_results * 3

            while downloaded_count < max_results and processed_videos < max_attempts:
                logger.info(f"📖 Fetching channel videos (downloaded: {downloaded_count}/{max_results})")
                
                response = self.youtube_service.search().list(
                    part='id',
                    channelId=channel_id,
                    maxResults=videos_per_request,
                    type='video',
                    order='date',
                    pageToken=page_token
                ).execute()

                video_ids = [item['id']['videoId'] for item in response['items']]
                
                videos_info = self.youtube_service.videos().list(
                    part='snippet,contentDetails,statistics',
                    id=','.join(video_ids)
                ).execute()

                for video_info in videos_info['items']:
                    if downloaded_count >= max_results:
                        break

                    video_id = video_info['id']
                    processed_videos += 1
                    
                    try:
                        title = video_info['snippet']['title']
                        views = int(video_info['statistics'].get('viewCount', 0))
                        duration = self.parse_duration(video_info['contentDetails']['duration'])
                        
                        # Фильтры
                        if views < min_views:
                            logger.debug(f"⚡ Skipped '{title}' - views: {views} < {min_views}")
                            continue
                            
                        if not (min_duration <= duration <= max_duration):
                            logger.debug(f"⚡ Skipped '{title}' - duration: {duration}s not in {min_duration}-{max_duration}")
                            continue

                        logger.info(f"🎥 Processing #{downloaded_count+1}: '{title}' ({views} views, {duration}s)")
                        
                        if self.process_video(video_id):
                            downloaded_count += 1
                            logger.info(f"✅ Progress: {downloaded_count}/{max_results}")
                        else:
                            logger.warning(f"⚠️ Failed to process video {video_id}")

                    except Exception as e:
                        logger.error(f"❌ Error processing video {video_id}: {str(e)}")
                        continue

                page_token = response.get('nextPageToken')
                if not page_token:
                    logger.info("🔚 No more videos in channel")
                    break

            logger.info(f"🏁 Finished channel download. Downloaded: {downloaded_count}/{max_results}")
            return downloaded_count

        except HttpError as e:
            logger.error(f"❌ YouTube API error: {e}")
            return 0
        except Exception as e:
            logger.error(f"❌ Unexpected error: {e}")
            return 0

    def mass_download(self, file_path):
        """Массовая загрузка видео из файла со списком URL."""
        try:
            logger.info(f"📂 Starting mass download from file: {file_path}")
            
            with open(file_path, 'r') as file:
                urls = [line.strip() for line in file if line.strip()]
                total = len(urls)
                success = 0
                
                for i, url in enumerate(urls, 1):
                    if 'v=' in url:
                        video_id = url.split('v=')[1].split('&')[0]
                        logger.info(f"🔗 Processing {i}/{total}: {video_id}")
                        if self.process_video(video_id):
                            success += 1
                
            logger.info(f"🏁 Mass download finished. Success: {success}/{total}")
            return success
        except Exception as e:
            logger.error(f"❌ Error in mass download: {e}")
            return 0

    def print_stats(self):
        """Вывод статистики работы."""
        logger.info("📊 Statistics:")
        for key, value in self.stats.items():
            logger.info(f"  {key.replace('_', ' ').title()}: {value}")

def main():
    """Основная функция для интерактивного выбора режима работы."""
    backup = YouTubeBackup()
    
    print("🎬 YouTube Backup Tool")
    print("1. Download single video")
    print("2. Mass download from file")
    print("3. Search and download by query")
    print("4. Download by tags")
    print("5. Download by channel")
    print("6. Exit")
    
    while True:
        choice = input("\nYour choice (1-6): ")
        
        try:
            if choice == '1':
                url = input("Video URL: ")
                if 'v=' in url:
                    video_id = url.split('v=')[1].split('&')[0]
                    thumbnail_format = input("Thumbnail format (jpg/png): ").strip() or "jpg"
                    video_format = input("Video format (best/mp4/...): ").strip() or "best"
                    backup.process_video(video_id, thumbnail_format, video_format)
            
            elif choice == '2':
                file_path = input("File path with URLs: ").strip()
                if os.path.exists(file_path):
                    backup.mass_download(file_path)
                else:
                    logger.error("❌ File not found!")
            
            elif choice == '3':
                query = input("Search query: ").strip()
                count = int(input("Number of videos: ").strip() or "10")
                min_views = int(input("Min views: ").strip() or "0")
                min_dur = int(input("Min duration (sec): ").strip() or "0")
                max_dur = int(input("Max duration (sec): ").strip() or "3600")
                backup.search_and_download(query, count, min_views, min_dur, max_dur)
            
            elif choice == '4':
                tags = input("Tags (comma separated): ").split(',')
                tags = [tag.strip() for tag in tags if tag.strip()]
                if tags:
                    count = int(input("Number of videos: ").strip() or "10")
                    min_views = int(input("Min views: ").strip() or "0")
                    min_dur = int(input("Min duration (sec): ").strip() or "0")
                    max_dur = int(input("Max duration (sec): ").strip() or "3600")
                    backup.download_by_tags(tags, count, min_views, min_dur, max_dur)
                else:
                    logger.error("❌ No tags provided!")
            
            elif choice == '5':
                channel_input = input("Channel ID or Channel Name: ").strip()
                if channel_input:
                    count = int(input("Number of videos: ").strip() or "10")
                    min_views = int(input("Min views: ").strip() or "0")
                    min_dur = int(input("Min duration (sec): ").strip() or "0")
                    max_dur = int(input("Max duration (sec): ").strip() or "3600")
                    # Если введён channelId (начинается с UC), передаём как channel_id
                    if channel_input.startswith('UC'):
                        backup.download_by_channel(channel_id=channel_input, max_results=count, min_views=min_views, min_dur=min_dur, max_dur=max_dur)
                    else:
                        backup.download_by_channel(channel_name=channel_input, max_results=count, min_views=min_views, min_dur=min_dur, max_dur=max_dur)
                else:
                    logger.error("❌ Channel ID or name is required!")
            
            elif choice == '6':
                print("👋 Exiting...")
                break
            
            else:
                print("❌ Invalid choice, please try again.")
            
            backup.print_stats()
        except ValueError as e:
            logger.error(f"❌ Invalid input: {e}")
        except Exception as e:
            logger.error(f"❌ Error: {e}")
        finally:
            db.remove()

if __name__ == '__main__':
    main()
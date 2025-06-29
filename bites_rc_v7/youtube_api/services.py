import requests
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlparse, parse_qs
from .api_key import YOUTUBE_API_KEY
from core.models import Video, Channel
from core.services.download_queue_service import DownloadQueueService
from functools import lru_cache
import os
from django.conf import settings
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile
from django.utils import timezone
from django.core.files import File
from tempfile import NamedTemporaryFile
import yt_dlp
import tempfile
from django.contrib.auth.models import User
import logging
import time

logger = logging.getLogger(__name__)

class YouTubeService:
    BASE_URL = 'https://www.googleapis.com/youtube/v3'
    
    def __init__(self, current_user=None):
        # Configure requests to not use any proxy
        self.session = requests.Session()
        self.session.trust_env = False  # Don't use environment variables for proxy
        self.current_user = current_user
        self.base_url = 'https://www.googleapis.com/youtube/v3'
        self.api_key = settings.YOUTUBE_API_KEY
        
        # Фильтры по умолчанию (без фильтрации)
        self.filters = {
            'min_views': 0,
            'max_views': 0,  # 0 означает без ограничений
            'min_duration': 0,
            'max_duration': 0  # 0 означает без ограничений
        }
    
    def set_filters(self, min_views=0, max_views=0, min_duration=0, max_duration=0):
        """Установить фильтры для импорта видео"""
        
        def _to_int_or_zero(value):
            if value is None or str(value).strip() == '':
                return 0
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0

        self.filters = {
            'min_views': _to_int_or_zero(min_views),
            'max_views': _to_int_or_zero(max_views),
            'min_duration': _to_int_or_zero(min_duration),
            'max_duration': _to_int_or_zero(max_duration)
        }
    
    def apply_filters(self, video_data):
        """Применяет фильтры к видео и возвращает True, если видео проходит фильтры"""
        logger.debug(f"[APPLYING_FILTERS] Filters being applied: {self.filters}")
        if not video_data:
            return False
            
        # Проверяем количество просмотров
        views = video_data.get('views')
        if views is None:
            views = 0
        try:
            views = int(views)
        except (ValueError, TypeError):
            views = 0 # Fallback if conversion fails

        if self.filters['min_views'] > 0 and views < self.filters['min_views']:
            return False
        if self.filters['max_views'] > 0 and views > self.filters['max_views']:
            return False
        
        # Проверяем длительность
        duration_seconds = video_data.get('duration_seconds') # Get duration in seconds directly
        if duration_seconds is None:
            duration_seconds = 0
        try:
            duration_seconds = int(duration_seconds)
        except (ValueError, TypeError):
            duration_seconds = 0 # Fallback if conversion fails
                
        if self.filters['min_duration'] > 0 and duration_seconds < self.filters['min_duration']:
            return False
        if self.filters['max_duration'] > 0 and duration_seconds > self.filters['max_duration']:
            return False
        
        return True

    @staticmethod
    def extract_video_id(url):
        """Extract video ID from YouTube URL."""
        parsed = urlparse(url)
        if parsed.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed.path == '/watch':
                return parse_qs(parsed.query)['v'][0]
            elif '/live/' in parsed.path:
                # Handle live stream URLs
                return parsed.path.split('/live/')[1]
        elif parsed.hostname == 'youtu.be':
            return parsed.path[1:]
        return None

    def extract_channel_id(self, url):
        """Extract channel ID from YouTube URL. Supports /channel/ID, /user/NAME, /@username."""
        parsed = urlparse(url)
        if parsed.hostname in ('www.youtube.com', 'youtube.com'):
            path_parts = [p for p in parsed.path.split('/') if p]
            # /channel/UCxxxx
            if len(path_parts) >= 2 and path_parts[0] == 'channel':
                return path_parts[1]
            # /user/username
            if len(path_parts) >= 2 and path_parts[0] == 'user':
                username = path_parts[1]
                # resolve username to channelId
                return self._resolve_channel_id_by_username(username)
            # /@username
            if len(path_parts) == 1 and path_parts[0].startswith('@'):
                handle = path_parts[0][1:]
                return self._resolve_channel_id_by_handle(handle)
        return None

    def _resolve_channel_id_by_username(self, username):
        # Use API to resolve /user/username to channelId
        params = {
            'key': self.api_key,
            'forUsername': username,
            'part': 'id'
        }
        resp = self.session.get(f'{self.base_url}/channels', params=params)
        data = resp.json()
        if data.get('items'):
            return data['items'][0]['id']
        return None

    def _resolve_channel_id_by_handle(self, handle):
        # Use API to resolve @handle to channelId
        # YouTube Data API v3 не поддерживает поиск по handle напрямую
        # поэтому используем поиск по названию канала
        logger.info(f"Resolving channel ID for @{handle}")
        
        # Ищем канал по handle через поиск
        search_params = {
            'key': self.api_key,
            'q': f'@{handle}',
            'type': 'channel',
            'part': 'snippet',
            'maxResults': 5  # Увеличиваем до 5 для большей вероятности нахождения
        }
        
        resp = self.session.get(f'{self.base_url}/search', params=search_params)
        data = resp.json()
        
        if data.get('items'):
            # Проверяем каждый результат, чтобы найти точное совпадение по handle
            for item in data['items']:
                channel_id = item['snippet']['channelId']
                channel_title = item['snippet']['title']
                logger.info(f"Found channel: {channel_title} (ID: {channel_id})")
                
                # Для большей точности можно проверить, есть ли в названии или описании канала упоминание handle
                if f'@{handle}' in channel_title.lower() or handle.lower() in channel_title.lower():
                    logger.info(f"Found exact match for @{handle}: {channel_id}")
                    return channel_id
            
            # Если точное совпадение не найдено, возвращаем первый результат
            logger.info(f"No exact match, using first result: {data['items'][0]['snippet']['channelId']}")
            return data['items'][0]['snippet']['channelId']
        
        logger.warning(f"Could not resolve channel ID for @{handle}")
        return None

    @staticmethod
    def parse_duration(duration_str):
        """Convert YouTube duration format (PT1H2M10S) to timedelta."""
        if not duration_str or not isinstance(duration_str, str) or not duration_str.startswith('PT'):
            logger.warning(f"Invalid or missing duration_str for parse_duration: {duration_str}")
            return timedelta(0)
        hours = minutes = seconds = 0
        duration = duration_str[2:]  # Remove PT
        time_dict = {'H': 0, 'M': 0, 'S': 0}
        current_num = ''
        
        for char in duration:
            if char.isdigit():
                current_num += char
            elif char in time_dict:
                time_dict[char] = int(current_num) if current_num else 0
                current_num = ''
        
        return timedelta(
            hours=time_dict['H'],
            minutes=time_dict['M'],
            seconds=time_dict['S']
        )

    def _process_video_data(self, video_data_item):
        """Обрабатывает данные видео из API в удобный формат"""
        if not video_data_item:
            logger.warning("Empty video_data_item received in _process_video_data")
            return {}

        video_id = video_data_item.get('id', '')
        snippet = video_data_item.get('snippet', {})
        statistics = video_data_item.get('statistics', {})
        content_details = video_data_item.get('contentDetails', {})
        
        duration_str = content_details.get('duration')
        duration_obj = self.parse_duration(duration_str)
        duration_seconds = int(duration_obj.total_seconds())
        
        published_at_str = snippet.get('publishedAt')
        upload_date_obj = None
        if published_at_str:
            try:
                # Parse and make timezone-aware (UTC)
                upload_date_obj = datetime.strptime(published_at_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt_timezone.utc)
            except ValueError:
                logger.warning(f"Could not parse publishedAt date: '{published_at_str}' for video ID: {video_id}")
                # upload_date_obj remains None, model default will apply
        
        thumbnails_data = snippet.get('thumbnails', {})
        thumbnail_url = thumbnails_data.get('high', {}).get('url')
        if not thumbnail_url:
            thumbnail_url = thumbnails_data.get('medium', {}).get('url')
        if not thumbnail_url:
            thumbnail_url = thumbnails_data.get('default', {}).get('url', '')

        return {
            'youtube_id': video_id,
            'title': snippet.get('title', ''),
            'description': snippet.get('description', ''),
            'upload_date': upload_date_obj,
            'views': int(statistics.get('viewCount', 0)),
            'likes': int(statistics.get('likeCount', 0)),
            'duration': duration_obj,  # Timedelta object
            'duration_seconds': duration_seconds,  # Integer seconds, for filtering
            'thumbnail_url': thumbnail_url,
            'channel_id': snippet.get('channelId', ''),
            'channel_title': snippet.get('channelTitle', '')
        }
    
    @lru_cache(maxsize=100)
    def get_video_data(self, video_id):
        """Fetch video data from YouTube API."""
        start_time = time.time()
        logger.info(f"[API_REQUEST_START] Fetching data for video {video_id}")
        
        url = f'{self.base_url}/videos?id={video_id}&key={self.api_key}&part=snippet,contentDetails,statistics'
        response = self.session.get(url)
        data = response.json()
        
        if 'items' not in data or not data['items']:
            logger.warning(f"[API_REQUEST_FAILED] No data found for video {video_id}")
            return None
        
        result = self._process_video_data(data['items'][0])
        # Добавляем youtube_id в результат
        result['youtube_id'] = video_id
        elapsed_time = time.time() - start_time
        logger.info(f"[API_REQUEST_COMPLETE] Fetched data for video {video_id} in {elapsed_time:.2f} seconds")
        return result
        
    async def get_video_data_async(self, video_id):
        """Асинхронный вариант получения данных видео из YouTube API."""
        start_time = time.time()
        logger.info(f"[ASYNC_API_REQUEST_START] Fetching data for video {video_id}")
        
        url = f'{self.base_url}/videos?id={video_id}&key={self.api_key}&part=snippet,contentDetails,statistics'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                if 'items' not in data or not data['items']:
                    logger.warning(f"[ASYNC_API_REQUEST_FAILED] No data found for video {video_id}")
        """Асинхронный вариант получения данных видео"""
        url = f'{self.base_url}/videos?id={video_id}&key={self.api_key}&part=snippet,contentDetails,statistics'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                if 'items' not in data or not data['items']:
                    return None
                    
                return self._process_video_data(data['items'][0])
                
    async def get_channel_data_async(self, channel_id):
        """Асинхронный вариант получения данных канала из YouTube API."""
        start_time = time.time()
        logger.info(f"[ASYNC_API_REQUEST_START] Fetching data for channel {channel_id}")
        
        url = f'{self.base_url}/channels?id={channel_id}&key={self.api_key}&part=snippet,statistics,brandingSettings'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                
                result = data['items'][0] if data.get('items') else None
                
                if result:
                    elapsed_time = time.time() - start_time
                    logger.info(f"[ASYNC_API_REQUEST_COMPLETE] Fetched data for channel {channel_id} in {elapsed_time:.2f} seconds")
                else:
                    logger.warning(f"[ASYNC_API_REQUEST_FAILED] No data found for channel {channel_id}")
                    
                return result
                
    def get_channel_data(self, channel_id):
        """Fetch channel data from YouTube API."""
        start_time = time.time()
        logger.info(f"[API_REQUEST_START] Fetching data for channel {channel_id}")
        
        params = {
            'key': self.api_key,
            'part': 'snippet,statistics,brandingSettings',
            'id': channel_id
        }
        response = self.session.get(f'{self.base_url}/channels', params=params)
        data = response.json()
        
        result = data['items'][0] if data.get('items') else None
        
        if result:
            elapsed_time = time.time() - start_time
            logger.info(f"[API_REQUEST_COMPLETE] Fetched data for channel {channel_id} in {elapsed_time:.2f} seconds")
        else:
            logger.warning(f"[API_REQUEST_FAILED] No data found for channel {channel_id}")
            
        return result
        
    def import_video(self, url, user=None, download_file=False):
        """Import a video from YouTube URL and optionally download it."""
        start_time = time.time()
        logger.info(f"[IMPORT_START] Importing video from URL: {url}")
        
        # Извлекаем ID видео из URL
        video_id = self.extract_video_id(url)
        if not video_id:
            logger.error(f"Failed to extract video ID from URL: {url}")
            return None, "Invalid YouTube URL"
        
        # Получаем данные о видео
        video_data = self.get_video_data(video_id)
        if not video_data:
            logger.error(f"Failed to fetch data for video {video_id}")
            return None, "Could not fetch video data"
        
        # Применяем фильтры, если они установлены
        if not self.apply_filters(video_data):
            logger.info(f"Video {video_id} did not pass filters")
            return None, "Video does not meet filter criteria"
        
        # Получаем канал (создаем, если не существует)
        channel_id_from_video_data = video_data.get('channel_id')
        channel_obj = None
        
        if channel_id_from_video_data:
            full_channel_data = self.get_channel_data(channel_id_from_video_data)
            
            if full_channel_data:
                snippet = full_channel_data.get('snippet', {})
                statistics = full_channel_data.get('statistics', {})
                branding_settings_image = full_channel_data.get('brandingSettings', {}).get('image', {})

                api_avatar_url = None
                thumbnails = snippet.get('thumbnails', {})
                if thumbnails:
                    for quality in ['high', 'medium', 'default']:
                        if quality in thumbnails and thumbnails[quality].get('url'):
                            api_avatar_url = thumbnails[quality]['url']
                            break
                
                api_banner_url = branding_settings_image.get('bannerExternalUrl')

                channel_obj, created = Channel.objects.get_or_create(
                    youtube_id=channel_id_from_video_data,
                    defaults={
                        'name': snippet.get('title', video_data.get('channel_title', 'Unknown Channel')),
                        'description': snippet.get('description', ''),
                        'is_youtube_channel': True,
                        'youtube_url': f'https://www.youtube.com/channel/{channel_id_from_video_data}',
                        'youtube_subscribers': int(statistics.get('subscriberCount', 0)),
                        'youtube_avatar_url': api_avatar_url,
                        'youtube_banner_url': api_banner_url,
                        'imported_by': user
                    }
                )
                
                if not created:
                    needs_save = False
                    if channel_obj.name != snippet.get('title', channel_obj.name):
                        channel_obj.name = snippet.get('title', channel_obj.name)
                        needs_save = True
                    if channel_obj.description != snippet.get('description', channel_obj.description):
                        channel_obj.description = snippet.get('description', channel_obj.description)
                        needs_save = True
                    if channel_obj.youtube_subscribers != int(statistics.get('subscriberCount', 0)):
                        channel_obj.youtube_subscribers = int(statistics.get('subscriberCount', 0))
                        needs_save = True
                    if channel_obj.youtube_avatar_url != api_avatar_url:
                        channel_obj.youtube_avatar_url = api_avatar_url
                        needs_save = True
                    if channel_obj.youtube_banner_url != api_banner_url:
                        channel_obj.youtube_banner_url = api_banner_url
                        needs_save = True
                        
                    if needs_save:
                        channel_obj.save()

                if api_avatar_url and (created or not channel_obj.avatar):
                    try:
                        logger.info(f"Attempting to download avatar from {api_avatar_url} for channel {channel_obj.youtube_id} during video import.")
                        response = requests.get(api_avatar_url, stream=True, timeout=10)
                        response.raise_for_status()
                        
                        img_temp = NamedTemporaryFile(delete=True)
                        for chunk in response.iter_content(chunk_size=8192):
                            img_temp.write(chunk)
                        img_temp.flush()

                        file_name = os.path.basename(urlparse(api_avatar_url).path)
                        _, ext = os.path.splitext(file_name)
                        if not ext:
                            content_type = response.headers.get('content-type')
                            if content_type == 'image/jpeg': ext = '.jpg'
                            elif content_type == 'image/png': ext = '.png'
                            elif content_type == 'image/webp': ext = '.webp'
                            else: ext = '.jpg'

                        avatar_filename = f'{channel_obj.youtube_id}_avatar{ext}'
                        channel_obj.avatar.save(avatar_filename, File(img_temp), save=True)
                        logger.info(f"Successfully downloaded and saved avatar to {channel_obj.avatar.url} for channel {channel_obj.youtube_id}")
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Error downloading avatar for channel {channel_obj.youtube_id} from {api_avatar_url}: {e}")
                    except Exception as e:
                        logger.error(f"Unexpected error processing avatar for channel {channel_obj.youtube_id}: {e}")
            else:
                logger.warning(f"Could not fetch full channel data for {channel_id_from_video_data} during video import.")
        
        # Создаем или обновляем видео
        try:
            video, created = Video.objects.update_or_create(
                youtube_id=video_id,
                defaults={
                    'title': video_data.get('title', ''),
                    'description': video_data.get('description', ''),
                    'upload_date': video_data.get('upload_date', timezone.now()),
                    'duration': video_data.get('duration', timedelta()).total_seconds(),
                    'views': video_data.get('views', 0),
                    'likes': video_data.get('likes', 0),
                    'youtube_url': f"https://www.youtube.com/watch?v={video_id}",
                    'channel': channel_obj,
                    'uploader': user,
                    'thumbnail_url': video_data.get('thumbnail_url', ''),
                    'source_type': 'youtube',
                    'is_youtube': True,
                    'youtube_views': video_data.get('views', 0),
                    'youtube_likes': video_data.get('likes', 0),
                    'youtube_thumbnail_url': video_data.get('thumbnail_url', ''),
                    'imported_by': user 
                }
            )
            
            # Если видео создано и нужно скачать файл
            if download_file and created:
                # Добавляем видео в очередь загрузки
                queue_service = DownloadQueueService()
                queue_service.add_to_queue(video, priority=1)
                
                logger.info(f"Added video {video_id} to download queue")
            
            elapsed_time = time.time() - start_time
            logger.info(f"[IMPORT_COMPLETE] Imported video {video_id} in {elapsed_time:.2f} seconds")
            return video, None
        except Exception as e:
            logger.exception(f"Error importing video {video_id}: {str(e)}")
            return None, str(e)
    
    def search_videos(self, query, limit=10):
        """Search for videos on YouTube by query."""
        start_time = time.time()
        logger.info(f"[API_REQUEST_START] Searching videos with query: {query}, limit={limit}")
        logger.info(f"[API_REQUEST_DETAIL] Using API key: {self.api_key[:5]}...")
        
        videos = []
        next_page_token = None
        params = {
            'key': self.api_key,
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'maxResults': min(50, limit),
            'safeSearch': 'none'
        }
        
        logger.info(f"[API_REQUEST_PARAMS] Search params: {params}")
        
        while len(videos) < limit:
            if next_page_token:
                params['pageToken'] = next_page_token
            
            try:
                logger.info(f"[API_REQUEST_CALL] Calling YouTube search API with params: {params}")
                response = self.session.get(f'{self.base_url}/search', params=params)
                logger.info(f"[API_RESPONSE_STATUS] Got response with status code: {response.status_code}")
                
                data = response.json()
                logger.info(f"[API_RESPONSE_DATA] Got {len(data.get('items', []))} items in search response")
                logger.debug(f"[API_RAW_ITEMS] Raw items from search: {data.get('items', [])}")
                
                if 'error' in data:
                    logger.error(f"[API_ERROR] YouTube API error: {data['error'].get('message', 'Unknown error')}")
                    break
                
                if 'items' not in data or not data['items']:
                    logger.warning(f"[API_NO_RESULTS] No items found for query: {query}")
                    break
                
                # Получаем ID видео из результатов поиска
                video_ids = [item['id']['videoId'] for item in data['items']]
                logger.info(f"[API_EXTRACTED_IDS] Found {len(video_ids)} video IDs from search results")
                
                # Получаем подробную информацию о каждом видео
                detailed_params = {
                    'key': self.api_key,
                    'part': 'snippet,contentDetails,statistics',
                    'id': ','.join(video_ids)
                }
                
                logger.info(f"[API_DETAIL_REQUEST] Fetching video details for {len(video_ids)} videos")
                details_response = self.session.get(f'{self.base_url}/videos', params=detailed_params)
                details_data = details_response.json()
                
                if 'items' in details_data and details_data['items']:
                    logger.info(f"[API_DETAIL_RESPONSE] Got details for {len(details_data['items'])} videos")
                    
                    for video_data in details_data['items']:
                        # Обрабатываем данные видео
                        processed_data = self._process_video_data(video_data)
                        
                        # Добавляем youtube_id в результат - это важно для правильной обработки
                        processed_data['youtube_id'] = video_data['id']
                        
                        # Применяем фильтры, если они установлены
                        logger.debug(f"[PRE_FILTER_DATA] Data for video {processed_data.get('youtube_id')}: Views={processed_data.get('views')}, DurationSec={processed_data.get('duration_seconds')}")
                        passed_filter = self.apply_filters(processed_data)
                        if passed_filter:
                            logger.info(f"[VIDEO_PASSED_FILTER] Video {video_data['id']} passed filters")
                            videos.append(processed_data)
                        else:
                            logger.info(f"[VIDEO_FILTERED_OUT] Video {video_data['id']} did not pass filters")
                        
                        if len(videos) >= limit:
                            logger.info(f"[LIMIT_REACHED] Reached limit of {limit} videos")
                            break
                else:
                    logger.warning(f"[API_NO_DETAILS] Could not get details for videos: {video_ids}")
            except Exception as e:
                logger.exception(f"[API_EXCEPTION] Error during API call: {str(e)}")
                break
            
            # Проверяем, есть ли следующая страница
            next_page_token = data.get('nextPageToken')
            if not next_page_token or len(videos) >= limit:
                break
        
        elapsed_time = time.time() - start_time
        logger.info(f"[API_REQUEST_COMPLETE] Found {len(videos)} videos for query '{query}' in {elapsed_time:.2f} seconds")
        return videos
    
    def get_channel_videos(self, channel_id, limit=10):
        """Get videos from a YouTube channel using the uploads playlist for full coverage."""
        videos = []
        # First, get the uploads playlist ID
        channel_data = self.get_channel_data(channel_id)
        uploads_playlist_id = None
        try:
            uploads_playlist_id = channel_data['contentDetails']['relatedPlaylists']['uploads']
        except (KeyError, TypeError):
            # Определяем params для запроса данных канала
            channel_params = {
                'key': self.api_key,
                'part': 'contentDetails',
                'id': channel_id
            }
            resp = self.session.get(f'{self.base_url}/channels', params=channel_params)
            data = resp.json()
            if data.get('items'):
                uploads_playlist_id = data['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        if not uploads_playlist_id:
            return []

        # Now, fetch videos from the uploads playlist
        next_page_token = None
        fetched = 0
        while fetched < limit:
            params = {
                'key': self.api_key,
                'part': 'snippet',
                'playlistId': uploads_playlist_id,
                'maxResults': min(50, limit - fetched)
            }
            if next_page_token:
                params['pageToken'] = next_page_token
            resp = self.session.get(f'{self.base_url}/playlistItems', params=params)
            data = resp.json()
            for item in data.get('items', []):
                # Safely get videoId to avoid KeyError
                video_id = item.get('snippet', {}).get('resourceId', {}).get('videoId')
                if not video_id:
                    logger.warning("Skipping playlist item without videoId: %s", item)
                    continue
                video_data = self.get_video_data(video_id)
                if video_data:
                    # Проверяем, что youtube_id добавлен в данные видео
                    if 'youtube_id' not in video_data:
                        video_data['youtube_id'] = video_id
                    videos.append(video_data)
                    fetched += 1
                    if fetched >= limit:
                        break
            next_page_token = data.get('nextPageToken')
            if not next_page_token:
                break
        return videos

    # Этот метод был удален, так как он дублирует функциональность расширенного метода search_videos с поддержкой лимита

    def download_video(self, video_id, output_path):
        """
        Download a YouTube video using yt-dlp.
        
        Args:
            video_id (str): The YouTube video ID
            output_path (str): The path where the video should be saved
            
        Returns:
            bool: True if download successful, False otherwise
        """
        try:
            from yt_dlp import YoutubeDL
            
            ydl_opts = {
                'format': 'best[ext=mp4]',  # Get best quality MP4
                'outtmpl': output_path,
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                url = f'https://www.youtube.com/watch?v={video_id}'
                ydl.download([url])
                
            return True
        except Exception as e:
            print(f"Error downloading video {video_id}: {str(e)}")
            return False
            
    def import_channel(self, channel_id, user, download_videos=False, download_limit=10):
        """Import a YouTube channel with all its details and optionally download its videos."""
        start_time = time.time()
        logger.info(f"[IMPORT_CHANNEL_START] Importing channel {channel_id}, download_videos={download_videos}, limit={download_limit}")
        
        # Получаем данные о канале
        channel_data = self.get_channel_data(channel_id)
        if not channel_data:
            logger.error(f"Failed to fetch data for channel {channel_id}")
            return None, "Could not fetch channel information"

        # Get avatar and banner URLs
        avatar_url_from_snippet = None
        thumbnails = channel_data['snippet'].get('thumbnails', {})
        if thumbnails:
            for quality in ['high', 'medium', 'default']: # Prefer higher quality
                if quality in thumbnails and thumbnails[quality].get('url'):
                    avatar_url_from_snippet = thumbnails[quality]['url']
                    break
        
        logger.debug(f"Extracted avatar_url_from_snippet={avatar_url_from_snippet} for channel {channel_id}")
        
        final_avatar_url = avatar_url_from_snippet

        banner_url = channel_data.get('brandingSettings', {}).get('image', {}).get('bannerExternalUrl')
        logger.debug(f"Extracted banner_url={banner_url} for channel {channel_id}")
        
        # Create or update channel
        channel, created = Channel.objects.get_or_create(
            youtube_id=channel_id,
            defaults={
                'name': channel_data['snippet']['title'],
                'description': channel_data['snippet'].get('description', ''),
                'owner': None, 
                'is_youtube_channel': True,
                'youtube_url': f'https://www.youtube.com/channel/{channel_id}',
                'youtube_subscribers': int(channel_data['statistics'].get('subscriberCount', 0)),
                'youtube_avatar_url': final_avatar_url, 
                'youtube_banner_url': banner_url,
                'imported_by': user
            }
        )
        logger.debug(f"Channel get_or_create: pk={channel.pk}, created={created}, current avatar on model: {channel.avatar}, youtube_avatar_url: {channel.youtube_avatar_url}")

        if not created:
            # Update existing channel
            channel.name = channel_data['snippet']['title']
            channel.description = channel_data['snippet'].get('description', '')
            channel.youtube_subscribers = int(channel_data['statistics'].get('subscriberCount', 0))
            channel.youtube_avatar_url = final_avatar_url 
            channel.youtube_banner_url = banner_url
            channel.save(update_fields=['name', 'description', 'youtube_subscribers', 'youtube_avatar_url', 'youtube_banner_url'])
            logger.debug(f"Updated existing channel: pk={channel.pk}, avatar on model: {channel.avatar}, youtube_avatar_url: {channel.youtube_avatar_url}")

        # Download and save avatar if a URL was found and (it's a new channel or existing channel has no avatar)
        if final_avatar_url and (created or not channel.avatar):
            try:
                logger.info(f"Attempting to download avatar from {final_avatar_url} for channel {channel_id}")
                response = requests.get(final_avatar_url, stream=True, timeout=10) 
                response.raise_for_status()

                img_temp = NamedTemporaryFile(delete=True)
                for chunk in response.iter_content(chunk_size=8192):
                    img_temp.write(chunk)
                img_temp.flush()

                file_name = os.path.basename(urlparse(final_avatar_url).path)
                _, ext = os.path.splitext(file_name)
                if not ext: 
                    content_type = response.headers.get('content-type')
                    if content_type == 'image/jpeg': ext = '.jpg'
                    elif content_type == 'image/png': ext = '.png'
                    elif content_type == 'image/webp': ext = '.webp'
                    else: ext = '.jpg' 

                avatar_filename = f'{channel_id}_avatar{ext}'
                channel.avatar.save(avatar_filename, File(img_temp), save=True)
                logger.info(f"Successfully downloaded and saved avatar to {channel.avatar.url} for channel {channel_id}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error downloading avatar for channel {channel_id} from {final_avatar_url}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing avatar for channel {channel_id}: {e}")

        # Download and save banner
        if banner_url:
            try:
                logging.info(f"Starting download of banner from {banner_url}")
                response = requests.get(banner_url)
                if response.status_code == 200:
                    img_temp = NamedTemporaryFile(delete=True)
                    img_temp.write(response.content)
                    img_temp.flush()
                    channel.banner.save(f'{channel_id}_banner.jpg', File(img_temp), save=True)
                    logging.info(f"Successfully downloaded and saved banner for channel {channel_id}")
            except Exception as e:
                logging.error(f"Error downloading banner for channel {channel_id}: {e}")

        # Import channel videos if requested
        if download_videos:
            try:
                # Get channel videos
                videos = self.get_channel_videos(channel_id, limit=download_limit)
                for video_data in videos:
                    try:
                        # Import each video
                        self.import_video(
                            f"https://www.youtube.com/watch?v={video_data['youtube_id']}",
                            user=user,
                            download_file=True,
                            channel=channel
                        )
                    except Exception as e:
                        print(f"Error importing video {video_data['youtube_id']}: {e}")
            except Exception as e:
                print(f"Error fetching channel videos: {e}")

        return channel, None

    def import_video(self, url, user, download_file=True, channel=None):
        """Import a YouTube video with all its details."""
        start_time = time.time()
        logger.info(f"[VIDEO_IMPORT_START] Importing video from URL: {url}")
        
        video_id = self.extract_video_id(url)
        if not video_id:
            logger.warning(f"[VIDEO_IMPORT_FAILED] Invalid YouTube URL: {url}")
            return None, "Invalid YouTube URL"

        # Check if video already exists
        existing_video = Video.objects.filter(youtube_id=video_id).first()
        if existing_video:
            logger.info(f"[VIDEO_IMPORT_SKIP] Video {video_id} already exists in database")
            return existing_video, None

        # Get video data
        logger.info(f"[VIDEO_IMPORT_STEP] Fetching video data for {video_id}")
        video_data = self.get_video_data(video_id)
        if not video_data:
            logger.error(f"[VIDEO_IMPORT_FAILED] Could not fetch information for video {video_id}")
            return None, "Could not fetch video information"

        # Get or import channel if not provided
        if not channel:
            channel_id = video_data['channel_id']
            logger.info(f"[VIDEO_IMPORT_STEP] Importing channel {channel_id} for video {video_id}")
            channel, error = self.import_channel(channel_id, user)
            if error:
                logger.error(f"[VIDEO_IMPORT_FAILED] Channel import failed for {channel_id}: {error}")
                return None, error

        # Create video instance
        logger.info(f"[VIDEO_IMPORT_STEP] Creating database entry for video {video_id}")
        video = Video.objects.create(
            title=video_data['title'],
            description=video_data['description'],
            channel=channel,
            uploaded_by=channel.owner if channel.owner else user,
            imported_by=user,
            youtube_id=video_id,
            is_youtube=True,
            youtube_views=video_data['views'],
            youtube_likes=video_data['likes'],
            duration=int(video_data['duration'].total_seconds()),
            youtube_thumbnail_url=video_data['thumbnail_url']
        )

        # Download thumbnail
        if video_data['thumbnail_url']:
            try:
                logger.info(f"[VIDEO_IMPORT_STEP] Downloading thumbnail for video {video_id}")
                response = requests.get(video_data['thumbnail_url'])
                if response.status_code == 200:
                    img_temp = NamedTemporaryFile(delete=True)
                    img_temp.write(response.content)
                    img_temp.flush()
                    video.thumbnail.save(f'{video_id}_thumb.jpg', File(img_temp), save=True)
                    logger.info(f"[VIDEO_IMPORT_STEP] Thumbnail downloaded for video {video_id}")
            except Exception as e:
                logger.error(f"[VIDEO_IMPORT_WARNING] Error downloading thumbnail for {video_id}: {e}")
        
        # Add to download queue if requested
        if download_file:
            logger.info(f"[VIDEO_IMPORT_STEP] Adding video {video_id} to download queue")
            DownloadQueueService.add_to_queue(video, user)
        
        elapsed_time = time.time() - start_time
        logger.info(f"[VIDEO_IMPORT_COMPLETE] Successfully imported video {video_id} in {elapsed_time:.2f} seconds")
        return video, None
        
    async def import_video_async(self, url, user, download_file=True, channel=None):
        """Асинхронный вариант импорта видео с YouTube."""
        start_time = time.time()
        logger.info(f"[ASYNC_VIDEO_IMPORT_START] Importing video from URL: {url}")
        
        video_id = self.extract_video_id(url)
        if not video_id:
            logger.warning(f"[ASYNC_VIDEO_IMPORT_FAILED] Invalid YouTube URL: {url}")
            return None, "Invalid YouTube URL"

        # Check if video already exists
        existing_video = Video.objects.filter(youtube_id=video_id).first()
        if existing_video:
            logger.info(f"[ASYNC_VIDEO_IMPORT_SKIP] Video {video_id} already exists in database")
            return existing_video, None

        # Get video data asynchronously
        logger.info(f"[ASYNC_VIDEO_IMPORT_STEP] Fetching video data for {video_id}")
        video_data = await self.get_video_data_async(video_id)
        if not video_data:
            logger.error(f"[ASYNC_VIDEO_IMPORT_FAILED] Could not fetch information for video {video_id}")
            return None, "Could not fetch video information"

        # Get or import channel if not provided (using synchronous method for now)
        # В будущих версиях можно сделать и этот метод асинхронным
        if not channel:
            channel_id = video_data['channel_id']
            logger.info(f"[ASYNC_VIDEO_IMPORT_STEP] Importing channel {channel_id} for video {video_id}")
            channel, error = self.import_channel(channel_id, user)
            if error:
                logger.error(f"[ASYNC_VIDEO_IMPORT_FAILED] Channel import failed for {channel_id}: {error}")
                return None, error

        # Create video instance
        logger.info(f"[ASYNC_VIDEO_IMPORT_STEP] Creating database entry for video {video_id}")
        video = Video.objects.create(
            title=video_data['title'],
            description=video_data['description'],
            channel=channel,
            uploaded_by=channel.owner if channel.owner else user,
            imported_by=user,
            youtube_id=video_id,
            is_youtube=True,
            youtube_views=video_data['views'],
            youtube_likes=video_data['likes'],
            duration=int(video_data['duration'].total_seconds()),
            youtube_thumbnail_url=video_data['thumbnail_url']
        )

        # Download thumbnail asynchronously
        if video_data['thumbnail_url']:
            try:
                logger.info(f"[ASYNC_VIDEO_IMPORT_STEP] Downloading thumbnail for video {video_id}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(video_data['thumbnail_url']) as response:
                        if response.status == 200:
                            content = await response.read()
                            img_temp = NamedTemporaryFile(delete=True)
                            img_temp.write(content)
                            img_temp.flush()
                            video.thumbnail.save(f'{video_id}_thumb.jpg', File(img_temp), save=True)
                            logger.info(f"[ASYNC_VIDEO_IMPORT_STEP] Thumbnail downloaded for video {video_id}")
            except Exception as e:
                logger.error(f"[ASYNC_VIDEO_IMPORT_WARNING] Error downloading thumbnail for {video_id}: {e}")
        
        # Add to download queue if requested
        if download_file:
            logger.info(f"[ASYNC_VIDEO_IMPORT_STEP] Adding video {video_id} to download queue")
            DownloadQueueService.add_to_queue(video, user)
        
        elapsed_time = time.time() - start_time
        logger.info(f"[ASYNC_VIDEO_IMPORT_COMPLETE] Successfully imported video {video_id} in {elapsed_time:.2f} seconds")
        return video, None
        
    async def import_video_async(self, url, user, download_file=True, channel=None):
        """Асинхронная версия импорта видео с YouTube"""
        video_id = self.extract_video_id(url)
        if not video_id:
            return None, "Invalid YouTube URL"

        # Check if video already exists
        existing_video = Video.objects.filter(youtube_id=video_id).first()
        if existing_video:
            return existing_video, None

        # Get video data асинхронно
        video_data = await self.get_video_data_async(video_id)
        if not video_data:
            return None, "Could not fetch video information"

        # Get or import channel if not provided
        if not channel:
            channel_id = video_data['channel_id']
            # Для асинхронности, выполняем синхронный импорт канала в этой версии
            # В будущем можно реализовать async версию import_channel
            channel, error = self.import_channel(channel_id, user)
            if error:
                return None, error

        # Create video instance
        video = Video.objects.create(
            title=video_data['title'],
            description=video_data['description'],
            channel=channel,
            uploaded_by=channel.owner if channel.owner else user,
            imported_by=user,
            youtube_id=video_id,
            is_youtube=True,
            youtube_views=video_data['views'],
            youtube_likes=video_data['likes'],
            duration=int(video_data['duration'].total_seconds()),
            youtube_thumbnail_url=video_data['thumbnail_url']
        )

        # Download thumbnail асинхронно
        if video_data['thumbnail_url']:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(video_data['thumbnail_url']) as response:
                        if response.status == 200:
                            img_content = await response.read()
                            img_temp = NamedTemporaryFile(delete=True)
                            img_temp.write(img_content)
                            img_temp.flush()
                            video.thumbnail.save(f'{video_id}_thumb.jpg', File(img_temp), save=True)
            except Exception as e:
                logger.error(f"Error downloading thumbnail: {e}")

        # Download video file if requested
        if download_file:
            try:
                logger.info(f"Adding video {video_id} to download queue asynchronously")
                DownloadQueueService.add_to_queue(video, user)
                logger.info(f"Video {video_id} successfully added to download queue")
            except Exception as e:
                logger.error(f"Error adding video to download queue: {e}")

        return video, None 
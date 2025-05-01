import os
import logging
from sqlalchemy import text
from config import SUPABASE_CONFIG
from models import db
from flask import url_for, current_app
from cachetools import TTLCache

# Логирование
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Глобальные переменные для WebRTC
peers = {}  # {videoId: [{id: peerId}]}
signals = {}  # {videoId: {peerId: [signals]}}
peer_chunks = {}  # {videoId: {peerId: [chunkIds]}}
CHUNK_SIZE = 1024 * 1024  # 1 MB

# Кэш для thumbnail-путей (хранит данные 10 минут)
thumbnail_cache = TTLCache(maxsize=1000, ttl=600)

# Вторичный путь для хранения видео и thumbnails
SECONDARY_STORAGE_PATH = '/run/media/impostorboy/server/videos'

def get_thumbnail_paths(video_ids):
    """
    Получает пути к thumbnail для списка video_ids или одного video_id одним SQL-запросом.
    Возвращает словарь {video_id: thumbnail_url} для списка или строку thumbnail_url для одного ID.
    """
    if isinstance(video_ids, str):
        result = get_thumbnail_paths([video_ids])
        return result.get(video_ids, url_for('static', filename='default-thumbnail.webp', _external=True))

    try:
        cached_results = {vid: thumbnail_cache.get(vid) for vid in video_ids if vid in thumbnail_cache}
        uncached_ids = [vid for vid in video_ids if vid not in thumbnail_cache]

        if not uncached_ids:
            logger.debug(f"All thumbnail paths for {len(video_ids)} videos found in cache")
            return cached_results

        result = db.session.execute(
            text("SELECT id, thumbnail_extension FROM videos WHERE id IN :ids"),
            {"ids": tuple(uncached_ids)}
        ).fetchall()

        thumbnail_extensions = {row[0]: row[1] for row in result}

        for video_id in uncached_ids:
            ext = thumbnail_extensions.get(video_id, 'jpg')
            ext = ext.lstrip('.') if ext else 'jpg'
            thumbnail_name = f"{video_id}.{ext}"

            primary_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', thumbnail_name)
            if os.path.exists(primary_path) and os.access(primary_path, os.R_OK):
                with current_app.app_context():
                    thumbnail_url = url_for('stream_thumbnail', filename=thumbnail_name, _external=True)
                logger.debug(f"Thumbnail found for video {video_id} at primary path: {primary_path}")
                thumbnail_cache[video_id] = thumbnail_url
                cached_results[video_id] = thumbnail_url
                continue

            secondary_path = os.path.join(SECONDARY_STORAGE_PATH, thumbnail_name)
            if os.path.exists(secondary_path) and os.access(secondary_path, os.R_OK):
                with current_app.app_context():
                    thumbnail_url = url_for('stream_thumbnail', filename=thumbnail_name, _external=True)
                logger.debug(f"Thumbnail found for video {video_id} at secondary path: {secondary_path}")
                thumbnail_cache[video_id] = thumbnail_url
                cached_results[video_id] = thumbnail_url
                continue

            logger.warning(f"Thumbnail file not found for video {video_id} at {primary_path} or {secondary_path}")
            with current_app.app_context():
                default_url = url_for('static', filename='default-thumbnail.webp', _external=True)
            thumbnail_cache[video_id] = default_url
            cached_results[video_id] = default_url

        return cached_results

    except Exception as e:
        logger.error(f"Error getting thumbnail paths for videos {video_ids}: {str(e)}")
        with current_app.app_context():
            default_url = url_for('static', filename='default-thumbnail.webp', _external=True)
        return {vid: default_url for vid in video_ids}
        
def invalidate_thumbnail_cache(video_id):
    """
    Инвалидирует кэш для указанного video_id.
    Используется при обновлении или создании нового thumbnail.
    """
    if video_id in thumbnail_cache:
        del thumbnail_cache[video_id]
        logger.debug(f"Invalidated thumbnail cache for video {video_id}")

def format_views(views):
    """
    Форматирует количество просмотров для отображения.
    """
    try:
        if views is None:
            return "0"
        views_int = int(views) if isinstance(views, str) else views
        if views_int >= 1_000_000:
            return f"{views_int / 1_000_000:.1f} млн"
        elif views_int >= 1_000:
            return f"{views_int / 1_000:.1f} тыс"
        return str(views_int)
    except (ValueError, TypeError) as e:
        logger.error(f"Error formatting views: {e}")
        return str(views) if views is not None else "0"

def fetch_chunks_for_peer(video_id, peer_id):
    """
    Назначает чанки видео для пира в WebRTC.
    """
    try:
        video_path = None
        for ext in ['.mp4', '.webm', '.mkv']:
            path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
            if os.path.exists(path):
                video_path = path
                break
        if not video_path:
            # Проверяем вторичный путь
            for ext in ['.mp4', '.webm', '.mkv']:
                path = os.path.join(SECONDARY_STORAGE_PATH, f"{video_id}{ext}")
                if os.path.exists(path):
                    video_path = path
                    break
        if not video_path:
            logger.error(f"Video {video_id} not found for peer {peer_id}")
            return

        size = os.path.getsize(video_path)
        total_chunks = (size + CHUNK_SIZE - 1) // CHUNK_SIZE
        if video_id not in peer_chunks:
            peer_chunks[video_id] = {}
        if peer_id not in peer_chunks[video_id]:
            peer_chunks[video_id][peer_id] = []

        for i in range(total_chunks):
            chunk_id = f"chunk_{i}"
            if chunk_id not in peer_chunks[video_id][peer_id]:
                peer_chunks[video_id][peer_id].append(chunk_id)
                logger.info(f"Assigned {chunk_id} to peer {peer_id} for video {video_id}")

    except Exception as e:
        logger.error(f"Error fetching chunks for peer {peer_id} in video {video_id}: {e}")
import os
from dotenv import load_dotenv

load_dotenv()

# Конфигурация Supabase
SUPABASE_CONFIG = {
    "storage_path": os.getenv('STORAGE_PATH', '/run/media/impostorboy/server/videos'),
    "db_uri": os.getenv('SUPABASE_DB_URI'),
    "api_url": os.getenv('SUPABASE_URL'),
    "api_key": os.getenv('SUPABASE_KEY')
}

# Конфигурация для YouTubeBackup
CONFIG = {
    "storage_path": os.getenv('STORAGE_PATH', '/run/media/impostorboy/server/videos'),
    "db_uri": os.getenv('SUPABASE_DB_URI'),
    "service_account_file": os.getenv('SERVICE_ACCOUNT_FILE'),
    "avg_video_size_mb": 10,  # Средний размер видео в МБ
    "avg_download_speed_mbps": 1  # Средняя скорость скачивания в МБ/с
}
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_cors import CORS
from dotenv import load_dotenv
from config import SUPABASE_CONFIG
from models import db, User
from routes import init_routes
import threading
from downloader_parser_edition import YouTubeBackup
import logging
import time

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = SUPABASE_CONFIG['db_uri']
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SUPABASE_JWT_SECRET')

# CORS
CORS(app, resources={r"/api/*": {"origins": "http://192.168.1.63:5000", "methods": ["GET", "POST", "OPTIONS"], "allow_headers": ["Content-Type", "Accept"], "expose_headers": ["Content-Range", "Content-Length"]}})

# Инициализация базы данных
db.init_app(app)
migrate = Migrate(app, db)

# Инициализация LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define user_loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Подключение маршрутов
init_routes(app)

# Глобальная очередь (для обработки в одном потоке)
processing_lock = threading.Lock()

def process_queue():
    """Обработка очереди в фоновом потоке."""
    backup = YouTubeBackup()
    while True:
        with processing_lock:
            with app.app_context():  # Добавляем контекст приложения
                from models import DownloadRequest
                request = DownloadRequest.query.filter_by(status='pending').order_by(DownloadRequest.created_at).first()
                if not request:
                    time.sleep(5)
                    continue
                
                try:
                    request.status = 'processing'
                    request.started_at = time.time()
                    db.session.commit()
                    
                    downloaded_count = 0
                    if request.request_type == 'search_and_download':
                        downloaded_count = backup.search_and_download(
                            query=request.request_value,
                            max_results=request.count,
                            min_views=request.min_views,
                            min_duration=request.min_duration,
                            max_duration=request.max_duration
                        )
                    elif request.request_type == 'single_video':
                        video_id = request.request_value.split('v=')[1].split('&')[0] if 'v=' in request.request_value else request.request_value
                        success = backup.process_video(video_id)
                        downloaded_count = 1 if success else 0
                    elif request.request_type == 'mass_download':
                        temp_file = os.path.join(SUPABASE_CONFIG['storage_path'], f'temp_{int(time.time())}.txt')
                        with open(temp_file, 'w') as f:
                            f.write(request.request_value)
                        try:
                            downloaded_count = backup.mass_download(temp_file)
                        finally:
                            os.remove(temp_file)
                    elif request.request_type == 'download_by_tags':
                        tags_list = [tag.strip() for tag in request.request_value.split(',') if tag.strip()]
                        downloaded_count = backup.download_by_tags(
                            tags=tags_list,
                            max_results=request.count,
                            min_views=request.min_views,
                            min_duration=request.min_duration,
                            max_duration=request.max_duration
                        )
                    elif request.request_type == 'download_by_channel':
                        downloaded_count = backup.download_by_channel(
                            channel_id=request.request_value,
                            max_results=request.count,
                            min_views=request.min_views,
                            min_duration=request.min_duration,
                            max_duration=request.max_duration
                        )
                    
                    request.status = 'completed'
                    request.completed_at = time.time()
                    request.downloaded_count = downloaded_count
                    db.session.commit()
                    logger.info(f"Completed request {request.id}: {request.request_type} - {request.request_value}")
                except Exception as e:
                    request.status = 'failed'
                    db.session.commit()
                    logger.error(f"Failed request {request.id}: {str(e)}")
        
        time.sleep(1)

# Запуск обработчика очереди в отдельном потоке
threading.Thread(target=process_queue, daemon=True).start()

def init_app():
    pass

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    init_app()
    app.run(debug=True, host='0.0.0.0', port=1488)
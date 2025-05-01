import os
import io
import time
import subprocess
import json
import re
import tempfile
import ssl
import requests
from flask import Flask, request, jsonify, render_template, send_file, send_from_directory, abort, flash, redirect, url_for, Response
from flask_login import login_user, logout_user, login_required, current_user
from flask_jwt_extended import jwt_required, create_access_token
from sqlalchemy import text
from threading import Thread
from extensions import db
from models import User, Video, Comment, Subscription, DownloadRequest, VideoCounter, VideoVote
from utils import get_thumbnail_paths, format_views, fetch_chunks_for_peer, peers, signals, peer_chunks, CHUNK_SIZE
from config import SUPABASE_CONFIG, CONFIG
import humanize
import uuid
from datetime import datetime
from sentiment_analyzer import SentimentAnalyzer
from googleapiclient.discovery import build
from dotenv import load_dotenv
import mimetypes
import logging

# Логирование
logger = logging.getLogger(__name__)

# Загрузка конфигурации из .env
load_dotenv()
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
if not YOUTUBE_API_KEY:
    logger.error("YOUTUBE_API_KEY не найден в .env")
    raise ValueError("YOUTUBE_API_KEY не найден в .env")

# Инициализация анализатора настроений
sentiment_analyzer = SentimentAnalyzer()

# Глобальное хранилище задач
try:
    from global_state import tasks
except ImportError:
    tasks = {}

def init_routes(app, logger):
    logger.info("Инициализация маршрутов")

    # Роут для видео
    app.add_url_rule('/videos/<path:filename>', endpoint='videos', view_func=lambda filename: send_from_directory(SUPABASE_CONFIG['storage_path'], filename))

    @app.route('/', methods=['GET'])
    def index():
        logger.info("Доступ к главной странице")
        videos = Video.query.order_by(Video.upload_date.desc()).limit(10).all()
        return render_template('index.html', videos=videos, page=1, total_pages=1, query='')

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            try:
                username = request.form['username']
                email = request.form['email']
                password = request.form['password']
                avatar = request.files.get('avatar')

                if User.query.filter_by(username=username).first():
                    flash('Имя пользователя уже существует')
                    return redirect(url_for('register'))
                
                if User.query.filter_by(email=email).first():
                    flash('Email уже зарегистрирован')
                    return redirect(url_for('register'))
                
                avatar_path = None
                if avatar and avatar.filename:
                    avatar_dir = os.path.join('static', 'avatars')
                    os.makedirs(avatar_dir, exist_ok=True)
                    avatar_filename = f'{username}_{int(time.time())}.webp'
                    avatar_path = os.path.join(avatar_dir, avatar_filename)
                    avatar.save(avatar_path)

                new_user = User(username=username, email=email, avatar=avatar_path)
                new_user.set_password(password)
                db.session.add(new_user)
                db.session.commit()

                flash('Регистрация успешна! Теперь вы можете войти.')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Ошибка регистрации: {e}")
                flash('Произошла ошибка при регистрации')
                return redirect(url_for('register'))
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            try:
                if request.content_type == 'application/json':
                    data = request.get_json()
                    if not data:
                        logger.error("Invalid JSON data provided")
                        return jsonify({'error': 'Invalid JSON data'}), 400
                    username = data.get('username')
                    password = data.get('password')
                else:
                    username = request.form.get('username')
                    password = request.form.get('password')

                if not username or not password:
                    logger.error("Missing username or password")
                    return jsonify({'error': 'Missing username or password'}), 400

                logger.info(f"Attempting login for username: {username}")
                user = User.query.filter_by(username=username).first()

                if user and user.check_password(password):
                    login_user(user)
                    logger.info(f"User ID for {username}: {user.id}")
                    if not isinstance(user.id, int):
                        logger.error(f"Invalid user.id type: {type(user.id)}, value: {user.id}")
                        return jsonify({'error': 'Internal server error: Invalid user ID'}), 500
                    access_token = create_access_token(identity=user.id)
                    logger.info(f"Login successful for username: {username}, token generated")
                    return jsonify({'access_token': access_token}), 200
                else:
                    logger.warning(f"Invalid credentials for username: {username}")
                    flash('Неверное имя пользователя или пароль.')
                    return jsonify({'error': 'Invalid username or password'}), 401
            except Exception as e:
                logger.error(f"Login error: {str(e)}")
                return jsonify({'error': f'Login failed: {str(e)}'}), 500
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.route('/dashboard')
    @login_required
    def dashboard():
        videos = Video.query.filter_by(uploader=current_user.username).order_by(Video.upload_date.desc()).all()
        subscriptions = User.query.join(Subscription, Subscription.channel_id == User.id).filter(Subscription.subscriber_id == current_user.id).all()
        return render_template('dashboard.html', user=current_user, videos=videos, subscriptions=subscriptions)

    @app.route('/channel/<username>')
    def channel(username):
        channel = User.query.filter_by(username=username).first_or_404()
        videos = Video.query.filter_by(uploader=channel.username).order_by(Video.upload_date.desc()).all()
        subscriber_count = Subscription.query.filter_by(channel_id=channel.id).count()
        is_subscribed = False
        if current_user.is_authenticated:
            is_subscribed = Subscription.query.filter_by(subscriber_id=current_user.id, channel_id=channel.id).first() is not None
        return render_template('channel.html', channel=channel, videos=videos, subscriber_count=subscriber_count, is_subscribed=is_subscribed)

    @app.route('/subscribe/<username>', methods=['POST'])
    @jwt_required()
    def subscribe(username):
        channel = User.query.filter_by(username=username).first_or_404()
        subscription = Subscription.query.filter_by(subscriber_id=current_user.id, channel_id=channel.id).first()
        if subscription:
            db.session.delete(subscription)
            db.session.commit()
            return jsonify({'message': 'Unsubscribed'})
        else:
            new_subscription = Subscription(subscriber_id=current_user.id, channel_id=channel.id)
            db.session.add(new_subscription)
            db.session.commit()
            return jsonify({'message': 'Subscribed'})

    @app.route('/video/<video_id>')
    def video_detail(video_id):
        video = Video.query.get_or_404(video_id)
        page = request.args.get('page', 1, type=int)
        per_page = 10

        pagination = Comment.query.filter_by(video_id=video_id).order_by(Comment.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        comments = pagination.items

        upvotes = VideoVote.query.filter_by(video_id=video_id, action='like').count()
        downvotes = VideoVote.query.filter_by(video_id=video_id, action='dislike').count()
        vote_value = upvotes - downvotes
        total_votes = upvotes + downvotes
        rating = (upvotes - downvotes) / total_votes if total_votes > 0 else 0

        return render_template('video.html', video=video, comments=comments, pagination=pagination, upvotes=upvotes, downvotes=downvotes, vote_value=vote_value, rating=rating)

    @app.route('/video/<video_id>/upvote', methods=['POST'])
    @jwt_required()
    def upvote_video(video_id):
        video = Video.query.get_or_404(video_id)
        existing_vote = VideoVote.query.filter_by(user_id=current_user.id, video_id=video_id).first()
        
        try:
            if existing_vote:
                if existing_vote.action == 'like':
                    db.session.delete(existing_vote)
                else:
                    existing_vote.action = 'like'
            else:
                vote = VideoVote(user_id=current_user.id, video_id=video_id, action='like')
                db.session.add(vote)
            
            db.session.commit()

            upvotes = VideoVote.query.filter_by(video_id=video_id, action='like').count()
            downvotes = VideoVote.query.filter_by(video_id=video_id, action='dislike').count()
            vote_value = upvotes - downvotes
            
            return jsonify({
                'upvotes': upvotes,
                'downvotes': downvotes,
                'vote_value': vote_value
            })
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при голосовании за видео {video_id}: {e}")
            return jsonify({'error': 'Failed to upvote'}), 500

    @app.route('/video/<video_id>/downvote', methods=['POST'])
    @jwt_required()
    def downvote_video(video_id):
        video = Video.query.get_or_404(video_id)
        existing_vote = VideoVote.query.filter_by(user_id=current_user.id, video_id=video_id).first()
        
        try:
            if existing_vote:
                if existing_vote.action == 'dislike':
                    db.session.delete(existing_vote)
                else:
                    existing_vote.action = 'dislike'
            else:
                vote = VideoVote(user_id=current_user.id, video_id=video_id, action='dislike')
                db.session.add(vote)
            
            db.session.commit()

            upvotes = VideoVote.query.filter_by(video_id=video_id, action='like').count()
            downvotes = VideoVote.query.filter_by(video_id=video_id, action='dislike').count()
            vote_value = upvotes - downvotes
            
            return jsonify({
                'upvotes': upvotes,
                'downvotes': downvotes,
                'vote_value': vote_value
            })
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при голосовании против видео {video_id}: {e}")
            return jsonify({'error': 'Failed to downvote'}), 500

    @app.route('/add_comment/<video_id>', methods=['POST'])
    @jwt_required()
    def add_comment(video_id):
        text = request.form.get('comment_text')
        if not text:
            flash('Комментарий не может быть пустым')
            return redirect(url_for('video_detail', video_id=video_id))
        sentiment = sentiment_analyzer.analyze(text)
        comment = Comment(
            video_id=video_id,
            user_id=current_user.id,
            text=text,
            created_at=datetime.utcnow(),
            sentiment=sentiment
        )
        db.session.add(comment)
        db.session.commit()
        flash('Комментарий добавлен')
        return redirect(url_for('video_detail', video_id=video_id))

    @app.route('/stream/<path:filename>')
    def stream_video(filename):
        full_path = os.path.join(SUPABASE_CONFIG['storage_path'], filename)
        
        if not os.path.exists(full_path):
            logger.error(f"Видеофайл {filename} не найден")
            abort(404)

        range_header = request.headers.get('Range', None)
        if not range_header:
            return send_file(full_path)

        size = os.path.getsize(full_path)
        byte1, byte2 = 0, None
        m = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if m:
            g = m.groups()
            byte1 = int(g[0])
            if g[1]:
                byte2 = int(g[1])

        length = size - byte1
        if byte2 is not None:
            length = byte2 - byte1 + 1

        with open(full_path, 'rb') as f:
            f.seek(byte1)
            data = f.read(length)

        resp = Response(
            data,
            206,
            mimetype=mimetypes.guess_type(full_path)[0],
            content_type=mimetypes.guess_type(full_path)[0],
            direct_passthrough=True
        )
        resp.headers.add('Content-Range', f'bytes {byte1}-{byte1 + length - 1}/{size}')
        resp.headers.add('Accept-Ranges', 'bytes')
        resp.headers.add('Content-Length', str(length))
        return resp

    @app.route('/stream_video/<filename>')
    def stream_video_file(filename):
        file_path = os.path.join(SUPABASE_CONFIG['storage_path'], filename)
        if not os.path.exists(file_path):
            logger.error(f"Видеофайл {filename} не найден")
            abort(404)
        return send_file(file_path, mimetype='video/mp4')

    @app.route('/edit_video/<video_id>', methods=['POST'])
    @jwt_required()
    def edit_video(video_id):
        try:
            video = Video.query.filter_by(id=video_id, uploader=current_user.username).first()
            if not video:
                flash('Видео не найдено или вы не являетесь его владельцем.', 'error')
                return redirect(url_for('dashboard'))

            title = request.form.get('title')
            description = request.form.get('description')
            thumbnail = request.files.get('thumbnail')

            if not title:
                flash('Название видео обязательно.', 'error')
                return redirect(url_for('dashboard'))

            video.title = title
            video.description = description

            if thumbnail and thumbnail.filename:
                thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails')
                os.makedirs(thumbnail_dir, exist_ok=True)
                thumbnail_filename = f"{video_id}.jpg"
                thumbnail_path = os.path.join(thumbnail_dir, thumbnail_filename)
                thumbnail.save(thumbnail_path)
                video.thumbnail_extension = 'jpg'

            db.session.commit()
            flash('Видео успешно обновлено!', 'success')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка редактирования видео {video_id}: {str(e)}")
            flash(f'Ошибка при редактировании видео: {str(e)}', 'error')

        return redirect(url_for('dashboard'))

    @app.route('/upload', methods=['GET', 'POST'])
    @login_required
    def upload():
        if request.method == 'GET':
            logger.info("Рендеринг upload.html")
            return render_template('upload.html', stage='upload')

        logger.info(f"Accessing /upload, method: POST, headers: {dict(request.headers)}")
        stage = request.form.get('stage')

        if stage == 'upload':
            try:
                video_file = request.files.get('video_file')
                video_title = request.form.get('video_title')
                video_description = request.form.get('video_description', '')

                if not video_file or not video_title:
                    flash('Видеофайл и название обязательны.')
                    return render_template('upload.html', stage='upload')

                allowed_types = ['video/mp4', 'video/webm', 'video/x-matroska']
                if video_file.mimetype not in allowed_types:
                    flash('Неподдерживаемый формат файла. Поддерживаются MP4, WebM, MKV.')
                    return render_template('upload.html', stage='upload')

                video_id = f"id_{uuid.uuid4().hex[:8]}"

                file_extension = os.path.splitext(video_file.filename)[1].lower().lstrip('.')
                if file_extension not in ['mp4', 'webm', 'mkv']:
                    file_extension = 'mp4'

                temp_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                temp_video_path = os.path.join(temp_dir, f"{video_id}.{file_extension}")
                video_file.save(temp_video_path)

                cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', temp_video_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                duration = 0
                try:
                    duration_data = json.loads(result.stdout)
                    duration = float(duration_data['format']['duration'])
                except Exception as e:
                    logger.error(f"Ошибка получения длительности для {video_id}: {e}")
                    os.remove(temp_video_path)
                    flash('Ошибка при определении длительности видео.')
                    return render_template('upload.html', stage='upload')

                thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', video_id)
                os.makedirs(thumbnail_dir, exist_ok=True)
                thumbnail_percentages = [0.1, 0.3, 0.5, 0.7]
                thumbnail_times = [duration * p for p in thumbnail_percentages]
                thumbnail_paths = []
                for i, t in enumerate(thumbnail_times):
                    if t >= duration:
                        continue
                    thumbnail_path = os.path.join(thumbnail_dir, f"thumb_{i}.jpg")
                    cmd = [
                        'ffmpeg', '-ss', str(t), '-i', temp_video_path, '-vframes', '1',
                        '-vf', 'scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2',
                        '-q:v', '2', '-y', thumbnail_path
                    ]
                    try:
                        subprocess.run(cmd, check=True, capture_output=True)
                        thumbnail_paths.append(f"{video_id}/thumb_{i}.jpg")
                        logger.info(f"Создан эскиз на {thumbnail_path} для времени {t:.2f}s")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"Ошибка FFmpeg для эскиза на {t:.2f}s для {video_id}: {e.stderr.decode()}")
                        continue

                if not thumbnail_paths:
                    os.remove(temp_video_path)
                    flash('Ошибка при создании эскизов видео.')
                    return render_template('upload.html', stage='upload')

                temp_metadata = {
                    'video_id': video_id,
                    'title': video_title,
                    'description': video_description,
                    'file_extension': file_extension,
                    'duration': duration,
                    'temp_video_path': temp_video_path,
                    'thumbnail_paths': thumbnail_paths
                }
                metadata_path = os.path.join(temp_dir, f"{video_id}.json")
                with open(metadata_path, 'w') as f:
                    json.dump(temp_metadata, f)

                return render_template('upload.html', stage='thumbnails', videomead=True, video_id=video_id, thumbnails=thumbnail_paths)
            except Exception as e:
                logger.error(f"Ошибка загрузки видео: {e}")
                flash(f'Ошибка при загрузке видео: {str(e)}')
                return render_template('upload.html', stage='upload')

        elif stage == 'thumbnails':
            video_id = request.form.get('video_id')
            temp_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'temp')
            metadata_path = os.path.join(temp_dir, f"{video_id}.json")
            if not os.path.exists(metadata_path):
                flash('Ошибка: Метаданные видео не найдены.')
                return render_template('upload.html', stage='upload')

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            selected_thumbnail = request.form.get('thumbnail')
            if not selected_thumbnail:
                flash('Пожалуйста, выберите эскиз.')
                return render_template('upload.html', stage='thumbnails', video_id=video_id, thumbnails=metadata['thumbnail_paths'])

            try:
                final_video_path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}.{metadata['file_extension']}")
                os.makedirs(os.path.dirname(final_video_path), exist_ok=True)
                os.rename(metadata['temp_video_path'], final_video_path)

                thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails')
                os.makedirs(thumbnail_dir, exist_ok=True)
                final_thumbnail_path = os.path.join(thumbnail_dir, f"{video_id}.jpg")
                selected_thumbnail_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', selected_thumbnail)
                os.rename(selected_thumbnail_path, final_thumbnail_path)

                temp_thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', video_id)
                for thumb in metadata['thumbnail_paths']:
                    thumb_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', thumb)
                    if os.path.exists(thumb_path) and thumb_path != selected_thumbnail_path:
                        os.remove(thumb_path)
                if os.path.exists(temp_thumbnail_dir):
                    os.rmdir(temp_thumbnail_dir)
                os.remove(metadata_path)

                new_video = Video(
                    id=video_id,
                    title=metadata['title'],
                    description=metadata['description'],
                    upload_date=datetime.utcnow(),
                    views=0,
                    uploader=current_user.username,
                    duration=metadata['duration'],
                    file_extension=metadata['file_extension'],
                    thumbnail_extension='jpg'
                )
                db.session.add(new_video)

                video_counter = VideoCounter(video_id=video_id, views=0)
                db.session.add(video_counter)

                db.session.commit()

                flash('Видео успешно загружено!')
                return redirect(url_for('video_detail', video_id=video_id))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Ошибка выбора эскиза: {e}")
                flash(f'Ошибка при выборе эскиза: {str(e)}')
                return render_template('upload.html', stage='thumbnails', video_id=video_id, thumbnails=metadata['thumbnail_paths'])

    @app.route('/zapros_na_postavku', methods=['GET', 'POST'])
    @login_required
    def zapros_na_postavku():
        if request.method == 'GET':
            logger.info("Рендеринг zapros_na_postavku.html")
            return render_template('zapros_na_postavku.html')

        logger.info(f"Accessing /zapros_na_postavku, method: POST, headers: {dict(request.headers)}")
        try:
            data = request.get_json(silent=True)
            logger.info(f"Получен запрос на загрузку: {data}")
            if not data:
                logger.error("Данные не предоставлены или неверный JSON")
                return jsonify({'error': 'No data provided or invalid JSON'}), 400

            action = data.get('type')
            if action not in ['search', 'tags', 'channel', 'single', 'mass']:
                logger.error(f"Неверный тип действия: {action}")
                return jsonify({'error': f'Invalid action type: {action}'}), 400

            task_id = str(uuid.uuid4())
            video_urls = []
            video_count = 0
            estimated_time = 0
            request_value = ""

            try:
                if action == 'search':
                    query = data.get('query')
                    if not query:
                        logger.error("Для действия search требуется запрос")
                        return jsonify({'error': 'Query is required'}), 400
                    min_views = data.get('minViews', 0)
                    min_duration = data.get('minDuration', 0)
                    max_duration = data.get('maxDuration', 3600)
                    max_results = data.get('maxResults', 10)
                    videos = app.downloader.search_videos(query, max_results, min_views, min_duration, max_duration)
                    video_urls = [f"https://www.youtube.com/watch?v={v['video_id']}" for v in videos]
                    video_count = len(video_urls)
                    request_value = query
                    logger.info(f"Найдено {video_count} видео для запроса: {query}")
                elif action == 'tags':
                    tags = data.get('tags', [])
                    if not tags:
                        logger.error("Для действия tags требуются теги")
                        return jsonify({'error': 'Tags are required'}), 400
                    min_views = data.get('minViews', 0)
                    min_duration = data.get('minDuration', 0)
                    max_duration = data.get('maxDuration', 3600)
                    max_results = data.get('maxResults', 10)
                    videos = app.downloader.search_by_tags(tags, max_results, min_views, min_duration, max_duration)
                    video_urls = [f"https://www.youtube.com/watch?v={v['video_id']}" for v in videos]
                    video_count = len(video_urls)
                    request_value = ','.join(tags)
                    logger.info(f"Найдено {video_count} видео для тегов: {request_value}")
                elif action == 'channel':
                    channel = data.get('channel')
                    if not channel:
                        logger.error("Для действия channel требуется канал")
                        return jsonify({'error': 'Channel is required'}), 400
                    min_views = data.get('minViews', 0)
                    min_duration = data.get('minDuration', 0)
                    max_duration = data.get('maxDuration', 3600)
                    max_results = data.get('maxResults', 10)
                    videos = app.downloader.search_by_channel(channel, max_results, min_views, min_duration, max_duration)
                    video_urls = [f"https://www.youtube.com/watch?v={v['video_id']}" for v in videos]
                    video_count = len(video_urls)
                    request_value = channel
                    logger.info(f"Найдено {video_count} видео для канала: {channel}")
                elif action == 'single':
                    video_url = data.get('videoUrl')
                    if not video_url or not re.match(r'^https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}', video_url):
                        logger.error("Неверный или отсутствующий URL видео для действия single")
                        return jsonify({'error': 'Invalid video URL'}), 400
                    video_urls = [video_url]
                    video_count = 1
                    request_value = video_url
                    logger.info(f"Обработка одного URL видео: {video_url}")
                elif action == 'mass':
                    urls = data.get('urls', [])
                    if not urls:
                        logger.error("Для действия mass требуются URL")
                        return jsonify({'error': 'URLs are required'}), 400
                    valid_urls = [url for url in urls if re.match(r'^https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]{11}', url)]
                    if not valid_urls:
                        logger.error("Не предоставлены действительные URL для действия mass")
                        return jsonify({'error': 'No valid URLs provided'}), 400
                    video_urls = valid_urls
                    video_count = len(video_urls)
                    request_value = '\n'.join(video_urls)
                    logger.info(f"Обработка {video_count} действительных URL для действия mass")
            except ssl.SSLError as ssl_err:
                logger.error(f"Ошибка SSL при поиске видео: {ssl_err}")
                return jsonify({'error': 'SSL connection failure. Please try again later.'}), 500
            except requests.exceptions.SSLError as req_ssl_err:
                logger.error(f"Ошибка SSL в requests при поиске видео: {req_ssl_err}")
                return jsonify({'error': 'SSL connection failure. Please try again later.'}), 500
            except Exception as e:
                logger.error(f"Неожиданная ошибка при поиске видео: {e}")
                return jsonify({'error': f'Failed to process video search: {str(e)}'}), 500

            # Используем прямой доступ к атрибутам CONFIG с fallback значениями
            avg_video_size_mb = getattr(CONFIG, 'avg_video_size_mb', 100)
            avg_download_speed_mbps = getattr(CONFIG, 'avg_download_speed_mbps', 10)
            estimated_time = video_count * avg_video_size_mb / avg_download_speed_mbps

            new_request = DownloadRequest(
                user_id=current_user.id,
                request_type=action,
                request_value=request_value,
                count=len(video_urls),
                min_views=data.get('minViews', 0),
                min_duration=data.get('minDuration', 0),
                max_duration=data.get('maxDuration', 3600),
                video_count=video_count,
                estimated_time=estimated_time,
                status='pending'
            )
            db.session.add(new_request)
            db.session.commit()
            logger.info(f"Создан DownloadRequest с ID {new_request.id} для task_id {task_id}")

            tasks[task_id] = {
                'videos': video_urls,
                'downloaded': 0,
                'status': 'pending',
                'tasks': [{'video_id': url.split('v=')[1][:11] if 'v=' in url else url.split('/')[-1], 'status': 'pending', 'progress': 0} for url in video_urls]
            }
            logger.info(f"Инициализирована задача {task_id} с {len(video_urls)} видео")

            try:
                app.downloader.add_download_task(video_urls, task_id, current_user.username)
                logger.info(f"Успешно добавлены задачи загрузки для task_id {task_id}")
            except ssl.SSLError as ssl_err:
                logger.error(f"Ошибка SSL в add_download_task для task_id {task_id}: {ssl_err}")
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['tasks'] = [{'video_id': task['video_id'], 'status': 'failed', 'progress': 0} for task in tasks[task_id]['tasks']]
                new_request.status = 'failed'
                db.session.commit()
                return jsonify({'error': 'SSL connection failure'}), 500
            except Exception as e:
                logger.error(f"Ошибка в add_download_task для task_id {task_id}: {e}")
                tasks[task_id]['status'] = 'failed'
                tasks[task_id]['tasks'] = [{'video_id': task['video_id'], 'status': 'failed', 'progress': 0} for task in tasks[task_id]['tasks']]
                new_request.status = 'failed'
                db.session.commit()
                return jsonify({'error': str(e)}), 500

            def update_status():
                with app.app_context():
                    try:
                        logger.info(f"Запуск update_status для task_id {task_id}")
                        while app.downloader.download_queue.qsize() > 0:
                            time.sleep(1)
                        logger.info(f"Очередь загрузок завершена для task_id {task_id}")
                        tasks[task_id]['status'] = 'completed'
                        tasks[task_id]['downloaded'] = len(tasks[task_id]['videos'])
                        tasks[task_id]['tasks'] = [{'video_id': task['video_id'], 'status': 'completed', 'progress': 100} for task in tasks[task_id]['tasks']]
                        new_request.status = 'completed'
                        new_request.completed_at = datetime.utcnow()
                        new_request.downloaded_count = tasks[task_id]['downloaded']
                        db.session.commit()
                        logger.info(f"Задача {task_id} успешно завершена")
                    except Exception as e:
                        logger.error(f"Ошибка обновления статуса задачи для task_id {task_id}: {e}")
                        tasks[task_id]['status'] = 'failed'
                        tasks[task_id]['tasks'] = [{'video_id': task['video_id'], 'status': 'failed', 'progress': 0} for task in tasks[task_id]['tasks']]
                        new_request.status = 'failed'
                        db.session.commit()
                        logger.info(f"Задача {task_id} помечена как неудавшаяся")

            Thread(target=update_status, daemon=True).start()
            logger.info(f"Запущен поток update_status для task_id: {task_id}")
            return jsonify({'task_id': task_id})
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка обработки запроса на загрузку: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/static/thumbnails/<path:filename>')
    def stream_thumbnail(filename):
        if filename.startswith('thumbnails/'):
            clean_filename = filename[len('thumbnails/'):]
        else:
            clean_filename = filename

        primary_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', clean_filename)
        if os.path.isfile(primary_path):
            return send_from_directory(os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails'), clean_filename)

        secondary_path = os.path.join(SUPABASE_CONFIG['storage_path'], clean_filename)
        if os.path.isfile(secondary_path):
            return send_from_directory(SUPABASE_CONFIG['storage_path'], clean_filename)

        logger.warning(f"Эскиз {clean_filename} не найден в основном или вторичном пути")
        return send_from_directory('static', 'default-thumbnail.webp')

    @app.route('/api/register_peer', methods=['POST'])
    def register_peer():
        data = request.get_json()
        video_id = data.get('videoId')
        peer_id = data.get('peerId')
        if not video_id or not peer_id:
            logger.error(f"Отсутствует videoId или peerId в запросе register_peer")
            return jsonify({'error': 'Missing videoId or peerId'}), 400
        if video_id not in peers:
            peers[video_id] = []
            peer_chunks[video_id] = {}
        if not any(p['id'] == peer_id for p in peers[video_id]):
            peers[video_id].append({'id': peer_id})
            peer_chunks[video_id][peer_id] = []
            logger.info(f"Пир {peer_id} зарегистрирован для видео {video_id}")
        return jsonify({'status': 'ok'})

    @app.route('/api/peers/<video_id>')
    def get_peers(video_id):
        peers_list = peers.get(video_id, [])
        logger.info(f"Возвращено {len(peers_list)} пиров для видео {video_id}")
        return jsonify(peers_list)

    @app.route('/api/signal', methods=['POST'])
    def send_signal():
        data = request.get_json()
        video_id = data.get('videoId')
        from_id = data.get('from')
        to_id = data.get('to')
        signal = data.get('signal')
        if not all([video_id, from_id, to_id, signal]):
            logger.error(f"Отсутствуют параметры в запросе signal")
            return jsonify({'error': 'Missing parameters'}), 400
        if video_id not in signals:
            signals[video_id] = {}
        if to_id not in signals[video_id]:
            signals[video_id][to_id] = []
        signals[video_id][to_id].append({'from': from_id, 'to': to_id, 'signal': signal})
        logger.info(f"Сигнал отправлен от {from_id} к {to_id} для видео {video_id}")
        return jsonify({'status': 'ok'})

    @app.route('/api/poll_signals/<video_id>/<peer_id>')
    def poll_signals(video_id, peer_id):
        if video_id in signals and peer_id in signals[video_id]:
            sigs = signals[video_id][peer_id]
            signals[video_id][peer_id] = []
            if sigs:
                logger.info(f"Возвращено {len(sigs)} сигналов для пира {peer_id} в видео {video_id}")
            if video_id in peer_chunks and peer_id in peer_chunks[video_id]:
                if not peer_chunks[video_id][peer_id]:
                    logger.info(f"Нет чанков для пира {peer_id} в видео {video_id}, запуск выборки с сервера")
                    fetch_chunks_for_peer(video_id, peer_id)
            return jsonify(sigs)
        logger.debug(f"Нет сигналов для пира {peer_id} в видео {video_id}")
        if video_id in peer_chunks and peer_id in peer_chunks[video_id]:
            if not peer_chunks[video_id][peer_id]:
                logger.info(f"Нет чанков для пира {peer_id} в видео {video_id}, запуск выборки с сервера")
                fetch_chunks_for_peer(video_id, peer_id)
        return jsonify([])

    @app.route('/api/video_metadata/<video_id>')
    def video_metadata(video_id):
        video_path = None
        for ext in ['.mp4', '.webm', '.mkv']:
            path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
            if os.path.exists(path):
                video_path = path
                break
        if not video_path:
            logger.error(f"Видео {video_id} не найдено")
            return jsonify({'error': 'Video not found'}), 404
        size = os.path.getsize(video_path)
        logger.info(f"Метаданные для видео {video_id}: размер={size}")
        return jsonify({'size': size})

    @app.route('/api/chunk/<video_id>/<chunk_id>')
    def get_chunk(video_id, chunk_id):
        video_path = None
        for ext in ['.mp4', '.webm', '.mkv']:
            path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
            if os.path.exists(path):
                video_path = path
                break
        if not video_path:
            logger.error(f"Видео {video_id} не найдено для чанка {chunk_id}")
            return jsonify({'error': 'Video not found'}), 404
        chunk_num = int(chunk_id.split('_')[1])
        offset = chunk_num * CHUNK_SIZE
        try:
            with tempfile.NamedTemporaryFile(suffix='.webm') as temp_file:
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-ss', str(offset / 1000000),
                    '-t', str(CHUNK_SIZE / 1000000),
                    '-c:v', 'libvpx-vp9', '-c:a', 'opus',
                    '-threads', '2', '-cpu-used', '4', '-speed', '4',
                    '-f', 'webm', temp_file.name
                ]
                subprocess.run(cmd, check=True, capture_output=True)
                with open(temp_file.name, 'rb') as f:
                    chunk = f.read()
            logger.info(f"Обслужен чанк {chunk_id} для видео {video_id}, размер={len(chunk)}")
            return send_file(io.BytesIO(chunk), mimetype='video/webm')
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка FFmpeg для чанка {chunk_id} видео {video_id}: {e.stderr.decode()}")
            return jsonify({'error': 'Failed to generate chunk'}), 500

    @app.route('/api/request_chunks/<video_id>/<peer_id>', methods=['OPTIONS'])
    def request_chunks_options(video_id, peer_id):
        resp = Response('', 204)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        resp.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    @app.route('/api/request_chunks/<video_id>/<peer_id>', methods=['POST'])
    def request_chunks(video_id, peer_id):
        data = request.get_json()
        chunk_ids = data.get('chunkIds', [])
        if not chunk_ids:
            logger.error(f"Не предоставлены ID чанков для пира {peer_id} в видео {video_id}")
            return jsonify({'error': 'No chunk IDs provided'}), 400

        video_path = None
        for ext in ['.mp4', '.webm', '.mkv']:
            path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
            if os.path.exists(path):
                video_path = path
                break
        if not video_path:
            logger.error(f"Видео {video_id} не найдено в {SUPABASE_CONFIG['storage_path']} для пира {peer_id}")
            return jsonify({'error': 'Video not found'}), 404

        results = {}
        for chunk_id in chunk_ids:
            chunk_num = int(chunk_id.split('_')[1])
            offset = chunk_num * CHUNK_SIZE
            try:
                with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
                    temp_file_path = temp_file.name
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-ss', str(offset / 1000000),
                    '-t', str(CHUNK_SIZE / 1000000),
                    '-c:v', 'libvpx-vp9', '-c:a', 'opus',
                    '-threads', '2', '-cpu-used', '4', '-speed', '4',
                    '-f', 'webm', temp_file_path
                ]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                with open(temp_file_path, 'rb') as f:
                    chunk = f.read()
                os.unlink(temp_file_path)
                results[chunk_id] = chunk.hex()
                if video_id not in peer_chunks:
                    peer_chunks[video_id] = {}
                if peer_id not in peer_chunks[video_id]:
                    peer_chunks[video_id][peer_id] = []
                if chunk_id not in peer_chunks[video_id][peer_id]:
                    peer_chunks[video_id][peer_id].append(chunk_id)
                logger.info(f"Доставлен {chunk_id} пиру {peer_id} для видео {video_id}, размер={len(chunk)}")
            except subprocess.CalledProcessError as e:
                logger.error(f"Ошибка FFmpeg для {chunk_id}: {e.stderr.decode()}")
                results[chunk_id] = None
            except Exception as e:
                logger.error(f"Ошибка доставки {chunk_id} пиру {peer_id}: {str(e)}")
                results[chunk_id] = None

        return jsonify(results)

    @app.route('/hls/<video_id>.m3u8')
    def serve_hls(video_id):
        video_path = None
        for ext in ['.mp4', '.webm', '.mkv']:
            path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
            if os.path.exists(path):
                video_path = path
                break
        if not video_path:
            logger.error(f"Видео {video_id} не найдено для HLS")
            return jsonify({'error': 'Video not found'}), 404
        hls_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'hls', video_id)
        hls_playlist = os.path.join(hls_dir, f"{video_id}.m3u8")
        if os.path.exists(hls_playlist):
            logger.info(f"Обслуживается кэшированный плейлист HLS: {hls_playlist}")
            return send_file(hls_playlist, mimetype='application/vnd.apple.mpegurl')
        os.makedirs(hls_dir, exist_ok=True)
        cmd = [
            'ffmpeg', '-i', video_path, '-c:v', 'copy', '-c:a', 'copy',
            '-hls_time', '10', '-hls_list_size', '0', '-f', 'hls', hls_playlist
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Сгенерирован плейлист HLS: {hls_playlist}")
            return send_file(hls_playlist, mimetype='application/vnd.apple.mpegurl')
        except subprocess.CalledProcessError as e:
            logger.error(f"Ошибка FFmpeg для HLS {video_id}: {e.stderr.decode()}")
            return jsonify({'error': 'Failed to generate HLS playlist'}), 500

    @app.route('/api/task_progress/<task_id>', methods=['GET'])
    def task_progress(task_id):
        if task_id in tasks:
            return jsonify(tasks[task_id])
        return jsonify({'error': 'Task not found'}), 404

    @app.route('/api/download', methods=['POST'])
    @jwt_required()
    @login_required
    def api_download():
        return zapros_na_postavku()

    @app.route('/api/search_tags')
    def search_tags():
        query = request.args.get('query', '')
        if not query:
            return jsonify([])
        try:
            videos = app.downloader.search_videos(query, max_results=10)
            tag_list = []
            for video in videos:
                tag_list.extend(video.get('tags', []))
            return jsonify(list(set(tag_list))[:10])
        except ssl.SSLError as ssl_err:
            logger.error(f"Ошибка SSL в search_tags: {ssl_err}")
            return jsonify({'error': 'SSL connection failure'}), 500
        except Exception as e:
            logger.error(f"Ошибка поиска тегов: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/api/search_channels')
    def search_channels():
        query = request.args.get('query', '')
        if not query:
            return jsonify([])
        try:
            youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
            yt_request = youtube.search().list(
                part='snippet',
                q=query,
                type='channel',
                maxResults=10
            )
            response = yt_request.execute()
            channels = [{
                'title': item['snippet']['title'],
                'thumbnail': item['snippet']['thumbnails']['default']['url']
            } for item in response.get('items', [])]
            return jsonify(channels)
        except ssl.SSLError as ssl_err:
            logger.error(f"Ошибка SSL в search_channels: {ssl_err}")
            return jsonify({'error': 'SSL connection failure'}), 500
        except Exception as e:
            logger.error(f"Ошибка поиска каналов: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/ws/download_status', methods=['GET'])
    def download_status():
        task_id = request.args.get('task_id')
        if task_id in tasks:
            return jsonify({
                'task_id': task_id,
                'status': tasks[task_id]['status'],
                'downloaded': tasks[task_id]['downloaded'],
                'total': len(tasks[task_id]['videos'])
            })
        return jsonify({'error': 'Task not found'}), 404

    @app.route('/queue', methods=['GET'])
    @jwt_required()
    @login_required
    def get_queue():
        requests = DownloadRequest.query.order_by(DownloadRequest.created_at).all()
        queue_data = []
        
        total_wait_time = 0
        for req in requests:
            if req.status == 'pending':
                total_wait_time += req.estimated_time
            queue_data.append({
                'id': req.id,
                'request_type': req.request_type,
                'request_value': req.request_value,
                'status': req.status,
                'video_count': req.video_count,
                'estimated_time': req.estimated_time,
                'wait_time': total_wait_time if req.status == 'pending' else 0,
                'downloaded_count': req.downloaded_count
            })
        
        return jsonify(queue_data)

    @app.route('/avatars/<path:filename>')
    def stream_avatar(filename):
        avatar_dir = os.path.join('static', 'avatars')
        default_avatar = 'default-avatar.webp'
        
        clean_filename = filename
        if filename.startswith('static/avatars/'):
            clean_filename = filename[len('static/avatars/'):]
        
        avatar_path = os.path.join(avatar_dir, clean_filename)
        if os.path.isfile(avatar_path):
            return send_from_directory(avatar_dir, clean_filename)
        
        default_path = os.path.join('static', default_avatar)
        if os.path.isfile(default_path):
            return send_from_directory('static', default_avatar)
        
        logger.warning(f"Аватар {clean_filename} не найден, дефолтный аватар также отсутствует")
        abort(404)

    logger.info("Маршруты успешно зарегистрированы")
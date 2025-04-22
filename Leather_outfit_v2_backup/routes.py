import os
import io
import time
import subprocess
import json
import re
import tempfile
from flask import Response, request, send_file, send_from_directory, render_template, redirect, url_for, flash, jsonify, abort
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import text
import mimetypes
from models import db, User, Video, DownloadRequest, VideoCounter
from utils import get_thumbnail_paths, format_views, fetch_chunks_for_peer, logger, peers, signals, peer_chunks, CHUNK_SIZE
from downloader_parser_edition import YouTubeBackup
from config import SUPABASE_CONFIG, CONFIG
import humanize
import requests
import uuid
from datetime import datetime

def init_routes(app):
    # Serve video files
    app.add_url_rule('/videos/<path:filename>', endpoint='videos', view_func=lambda filename: send_from_directory(SUPABASE_CONFIG['storage_path'], filename))

    @app.route('/')
    def index():
        query = request.args.get('query', '')
        page = int(request.args.get('page', 1))
        per_page = 20

        # Подсчёт общего количества видео
        if query:
            total_videos = db.session.execute(
                text("SELECT COUNT(*) FROM videos WHERE title LIKE :query"),
                {"query": f"%{query}%"}
            ).scalar()
        else:
            total_videos = db.session.execute(
                text("SELECT COUNT(*) FROM videos")
            ).scalar()

        offset = (page - 1) * per_page
        total_pages = (total_videos + per_page - 1) // per_page

        # Получение видео
        if query:
            result = db.session.execute(
                text("SELECT id, title, description, upload_date, views, uploader, thumbnail_extension FROM videos WHERE title LIKE :query ORDER BY upload_date DESC LIMIT :limit OFFSET :offset"),
                {"query": f"%{query}%", "limit": per_page, "offset": offset}
            ).fetchall()
        else:
            result = db.session.execute(
                text("SELECT id, title, description, upload_date, views, uploader, thumbnail_extension FROM videos ORDER BY upload_date DESC LIMIT :limit OFFSET :offset"),
                {"limit": per_page, "offset": offset}
            ).fetchall()

        # Проверка на пустой результат
        if not result:
            logger.info("Нет видео для отображения")
            return render_template('index.html', videos=[], page=page, total_pages=total_pages, query=query)

        # Собираем все video_id для пакетного получения миниатюр
        video_ids = [row[0] for row in result]
        thumbnail_paths = get_thumbnail_paths(video_ids)  # Пакетный запрос миниатюр

        videos = []
        for row in result:
            video_id = row[0]
            title = row[1]
            views = row[4]
            videos.append({
                'id': video_id,
                'title': title or "Без названия",
                'thumbnail_path': thumbnail_paths.get(video_id, url_for('static', filename='default-thumbnail.webp', _external=True)),
                'views': format_views(views)
            })

        return render_template('index.html', videos=videos, page=page, total_pages=total_pages, query=query)

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
                logger.error(f"Registration error: {e}")
                flash('Произошла ошибка при регистрации')
                return redirect(url_for('register'))

        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            try:
                username = request.form['username']
                password = request.form['password']
                user = User.query.filter_by(username=username).first()

                if user and user.check_password(password):
                    login_user(user)
                    return redirect(url_for('dashboard'))
                flash('Неверное имя пользователя или пароль.')
            except Exception as e:
                logger.error(f"Login error: {e}")
                flash('Произошла ошибка при входе')
        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('login'))

    @app.template_filter('format_number')
    def format_number(value):
        try:
            return humanize.intcomma(value)
        except:
            return value

    @app.route('/stream/<path:filename>')
    def stream_video(filename):
        full_path = os.path.join(SUPABASE_CONFIG['storage_path'], filename)
        
        if not os.path.exists(full_path):
            logger.error(f"Video file {filename} not found")
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

    @app.route('/dashboard')
    @login_required
    def dashboard():
        # Fetch videos where uploader matches the current user's username
        videos = db.session.execute(
            text("SELECT id, title, description, upload_date, views, uploader, thumbnail_extension FROM videos WHERE uploader = :uploader ORDER BY upload_date DESC"),
            {"uploader": current_user.username}
        ).fetchall()

        # Prepare video data for the template
        video_list = []
        if videos:
            # Get thumbnail paths for all video IDs
            video_ids = [row[0] for row in videos]
            thumbnail_paths = get_thumbnail_paths(video_ids)  # Batch fetch thumbnails

            for row in videos:
                video_id = row[0]
                video_list.append({
                    'id': video_id,
                    'title': row[1] or "Без названия",
                    'description': row[2],
                    'thumbnail_path': thumbnail_paths.get(video_id, url_for('static', filename='default-thumbnail.webp', _external=True)),
                    'views': format_views(row[4])
                })

        return render_template('dashboard.html', user=current_user, videos=video_list)

    @app.route('/edit_video/<video_id>', methods=['POST'])
    @login_required
    def edit_video(video_id):
        try:
            # Fetch the video
            video = Video.query.filter_by(id=video_id, uploader=current_user.username).first()
            if not video:
                flash('Видео не найдено или вы не являетесь его владельцем.', 'error')
                return redirect(url_for('dashboard'))

            # Get form data
            title = request.form.get('title')
            description = request.form.get('description')
            thumbnail = request.files.get('thumbnail')

            if not title:
                flash('Название видео обязательно.', 'error')
                return redirect(url_for('dashboard'))

            # Update video details
            video.title = title
            video.description = description

            # Handle thumbnail update
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
            logger.error(f"Error editing video {video_id}: {str(e)}")
            flash(f'Ошибка при редактировании видео: {str(e)}', 'error')

        return redirect(url_for('dashboard'))

    @app.route('/video/<video_id>')
    def video_detail(video_id):
        try:
            video = db.session.execute(
                text("SELECT id, title, description, upload_date, views, uploader, duration, file_extension, thumbnail_extension FROM videos WHERE id = :id"),
                {"id": video_id}
            ).mappings().first()

            if not video:
                logger.error(f"Video {video_id} not found in database")
                flash(f"Видео с ID {video_id} не найдено", "error")
                return redirect(url_for('index'))

            video_dict = dict(video)
            file_extension = video_dict.get('file_extension', 'mp4').lstrip('.')
            valid_extensions = [f'.{file_extension}', '.mp4', '.webm', '.mkv']

            found = False
            for ext in valid_extensions:
                video_path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
                if os.path.exists(video_path):
                    video_dict['file_path'] = f"{video_id}{ext}"
                    found = True
                    break
            
            if not found:
                logger.error(f"No video file found for {video_id} with extensions {valid_extensions}")
                flash(f"Видео с ID {video_id} не найдено на сервере.", "error")
                return redirect(url_for('index'))

            video_dict['thumbnail_path'] = get_thumbnail_paths(video_id)
            return render_template('video.html', video=video_dict)
        except Exception as e:
            logger.error(f"Video detail error for {video_id}: {str(e)}")
            flash(f"Ошибка при загрузке видео: {str(e)}", "error")
            return redirect(url_for('index'))

    @app.route('/watch_by_id', methods=['GET', 'POST'])
    def watch_by_id():
        if request.method == 'POST':
            video_id = request.form.get('video_id')
            if not video_id:
                flash('Введите ID видео')
                return redirect(url_for('watch_by_id'))
            
            try:
                video = db.session.execute(
                    text("SELECT id, title, description, upload_date, views, uploader, duration, file_extension, thumbnail_extension FROM videos WHERE id = :id"),
                    {"id": video_id}
                ).mappings().first()

                if not video:
                    flash(f'Видео с ID {video_id} не найдено')
                    return redirect(url_for('watch_by_id'))

                video_dict = dict(video)
                valid_extensions = ['.mp4', '.webm', '.mkv']
                found = False
                
                for ext in valid_extensions:
                    video_path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
                    if os.path.exists(video_path):
                        video_dict['file_path'] = f"{video_id}{ext}"
                        found = True
                        break
                
                if not found:
                    flash(f'Файл видео для ID {video_id} не найден')
                    return redirect(url_for('watch_by_id'))

                video_dict['thumbnail_path'] = get_thumbnail_paths(video_id)
                logger.info(f"Rendering video {video_id}")
                return render_template('watch_by_id.html', video=video_dict)
            except Exception as e:
                logger.error(f"Error loading video {video_id}: {str(e)}")
                flash('Произошла ошибка при загрузке видео')
                return redirect(url_for('watch_by_id'))
        return render_template('watch_by_id.html')

    @app.route('/api/video/<video_id>')
    def api_video(video_id):
        try:
            video = db.session.execute(
                text("SELECT id, title, file_extension, thumbnail_extension FROM videos WHERE id = :id"),
                {"id": video_id}
            ).mappings().first()

            if not video:
                logger.error(f"Video {video_id} not found for API request")
                return jsonify({'error': 'Video not found'}), 404

            video_dict = dict(video)
            video_dict['stream_url'] = url_for('stream_video', filename=f"{video_id}.{video_dict['file_extension']}", _external=True)
            video_dict['thumbnail_path'] = get_thumbnail_paths(video_id)
            return jsonify(video_dict)
        except Exception as e:
            logger.error(f"API и API error for video {video_id}: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/upload', methods=['GET', 'POST'])
    @login_required
    def upload():
        if request.method == 'GET':
            return render_template('upload_video.html')

        stage = request.form.get('stage')

        if stage == 'upload':
            try:
                video_file = request.files.get('video_file')
                video_title = request.form.get('video_title')
                video_description = request.form.get('video_description', '')

                if not video_file or not video_title:
                    flash('Видеофайл и название обязательны.')
                    return render_template('upload_video.html', stage='upload')

                allowed_types = ['video/mp4', 'video/webm', 'video/x-matroska']
                if video_file.mimetype not in allowed_types:
                    flash('Неподдерживаемый формат файла. Поддерживаются MP4, WebM, MKV.')
                    return render_template('upload_video.html', stage='upload')

                # Получение нового ID из VideoCounter
                counter = VideoCounter.query.first()
                if not counter:
                    counter = VideoCounter(last_id=-1)
                    db.session.add(counter)
                counter.last_id += 1
                video_id = f"id_{counter.last_id}"
                db.session.commit()

                file_extension = os.path.splitext(video_file.filename)[1].lower().lstrip('.')
                if file_extension not in ['mp4', 'webm', 'mkv']:
                    file_extension = 'mp4'

                temp_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'temp')
                os.makedirs(temp_dir, exist_ok=True)
                temp_video_path = os.path.join(temp_dir, f"{video_id}.{file_extension}")
                video_file.save(temp_video_path)

                # Получение длительности видео
                cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', temp_video_path]
                result = subprocess.run(cmd, capture_output=True, text=True)
                duration = 0
                try:
                    duration_data = json.loads(result.stdout)
                    duration = float(duration_data['format']['duration'])
                except Exception as e:
                    logger.error(f"Error getting duration for {video_id}: {e}")
                    os.remove(temp_video_path)
                    flash('Ошибка при определении длительности видео.')
                    return render_template('upload_video.html', stage='upload')

                # Создание миниатюр
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
                        thumbnail_paths.append(f"{video_id}/thumb_{i}.jpg")  # Убрали префикс thumbnails/
                        logger.info(f"Created thumbnail at {thumbnail_path} for time {t:.2f}s")
                    except subprocess.CalledProcessError as e:
                        logger.error(f"FFmpeg thumbnail error at {t:.2f}s for {video_id}: {e.stderr.decode()}")
                        continue

                if not thumbnail_paths:
                    os.remove(temp_video_path)
                    flash('Ошибка при создании эскизов видео.')
                    return render_template('upload_video.html', stage='upload')

                logger.info(f"Thumbnail paths for video {video_id}: {thumbnail_paths}")

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

                return render_template('upload_video.html', stage='thumbnails', video_id=video_id, thumbnails=thumbnail_paths)
            except Exception as e:
                logger.error(f"Video upload error: {e}")
                flash(f'Ошибка при загрузке видео: {str(e)}')
                return render_template('upload_video.html', stage='upload')

        elif stage == 'thumbnails':
            video_id = request.form.get('video_id')
            temp_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'temp')
            metadata_path = os.path.join(temp_dir, f"{video_id}.json")
            if not os.path.exists(metadata_path):
                flash('Ошибка: Метаданные видео не найдены.')
                return render_template('upload_video.html', stage='upload')

            with open(metadata_path, 'r') as f:
                metadata = json.load(f)

            selected_thumbnail = request.form.get('thumbnail')
            if not selected_thumbnail:
                flash('Пожалуйста, выберите эскиз.')
                return render_template('upload_video.html', stage='thumbnails', video_id=video_id, thumbnails=metadata['thumbnail_paths'])

            try:
                final_video_path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}.{metadata['file_extension']}")
                os.makedirs(os.path.dirname(final_video_path), exist_ok=True)
                os.rename(metadata['temp_video_path'], final_video_path)

                thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails')
                os.makedirs(thumbnail_dir, exist_ok=True)
                final_thumbnail_path = os.path.join(thumbnail_dir, f"{video_id}.jpg")
                selected_thumbnail_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', selected_thumbnail)  # Исправлено
                os.rename(selected_thumbnail_path, final_thumbnail_path)

                temp_thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', video_id)
                for thumb in metadata['thumbnail_paths']:
                    thumb_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', thumb)  # Исправлено
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
                db.session.commit()

                flash('Видео успешно загружено!')
                return redirect(url_for('video_detail', video_id=video_id))
            except Exception as e:
                db.session.rollback()
                logger.error(f"Thumbnail selection error: {e}")
                flash(f'Ошибка при выборе эскиза: {str(e)}')
                return render_template('upload_video.html', stage='thumbnails', video_id=video_id, thumbnails=metadata['thumbnail_paths'])

    @app.route('/static/thumbnails/<path:filename>')
    def stream_thumbnail(filename):
        logger.info(f"Requested thumbnail: {filename}")
        # Проверяем, начинается ли путь с 'thumbnails/'
        if filename.startswith('thumbnails/'):
            clean_filename = filename[len('thumbnails/'):]
        else:
            clean_filename = filename
        logger.debug(f"Cleaned filename: {clean_filename}")

        # Формируем основной путь
        primary_path = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails', clean_filename)
        logger.debug(f"Checking primary path: {primary_path}")
        logger.debug(f"Primary path exists: {os.path.exists(primary_path)}")
        logger.debug(f"Primary path is file: {os.path.isfile(primary_path)}")

        if os.path.isfile(primary_path):
            logger.info(f"Serving thumbnail from: {primary_path}")
            return send_from_directory(os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails'), clean_filename)

        # Проверяем альтернативный путь
        secondary_path = os.path.join(SUPABASE_CONFIG['storage_path'], clean_filename)
        logger.debug(f"Checking secondary path: {secondary_path}")
        logger.debug(f"Secondary path exists: {os.path.exists(secondary_path)}")
        logger.debug(f"Secondary path is file: {os.path.isfile(secondary_path)}")

        if os.path.isfile(secondary_path):
            logger.info(f"Serving thumbnail from: {secondary_path}")
            return send_from_directory(SUPABASE_CONFIG['storage_path'], clean_filename)

        logger.warning(f"Thumbnail {clean_filename} not found in primary or secondary path")
        return send_from_directory('static', 'default-thumbnail.webp')

    @app.route('/api/register_peer', methods=['POST'])
    def register_peer():
        data = request.get_json()
        video_id = data.get('videoId')
        peer_id = data.get('peerId')
        if not video_id or not peer_id:
            logger.error(f"Missing videoId or peerId in register_peer request")
            return jsonify({'error': 'Missing videoId or peerId'}), 400
        if video_id not in peers:
            peers[video_id] = []
            peer_chunks[video_id] = {}
        if not any(p['id'] == peer_id for p in peers[video_id]):
            peers[video_id].append({'id': peer_id})
            peer_chunks[video_id][peer_id] = []
            logger.info(f"Peer {peer_id} registered for video {video_id}")
        return jsonify({'status': 'ok'})

    @app.route('/api/peers/<video_id>')
    def get_peers(video_id):
        peers_list = peers.get(video_id, [])
        logger.info(f"Returning {len(peers_list)} peers for video {video_id}")
        return jsonify(peers_list)

    @app.route('/api/signal', methods=['POST'])
    def send_signal():
        data = request.get_json()
        video_id = data.get('videoId')
        from_id = data.get('from')
        to_id = data.get('to')
        signal = data.get('signal')
        if not all([video_id, from_id, to_id, signal]):
            logger.error(f"Missing parameters in signal request")
            return jsonify({'error': 'Missing parameters'}), 400
        if video_id not in signals:
            signals[video_id] = {}
        if to_id not in signals[video_id]:
            signals[video_id][to_id] = []
        signals[video_id][to_id].append({'from': from_id, 'to': to_id, 'signal': signal})
        logger.info(f"Signal sent from {from_id} to {to_id} for video {video_id}")
        return jsonify({'status': 'ok'})

    @app.route('/api/poll_signals/<video_id>/<peer_id>')
    def poll_signals(video_id, peer_id):
        if video_id in signals and peer_id in signals[video_id]:
            sigs = signals[video_id][peer_id]
            signals[video_id][peer_id] = []
            if sigs:
                logger.info(f"Returning {len(sigs)} signals for peer {peer_id} in video {video_id}")
            if video_id in peer_chunks and peer_id in peer_chunks[video_id]:
                if not peer_chunks[video_id][peer_id]:
                    logger.info(f"No chunks for peer {peer_id} in video {video_id}, triggering server fetch")
                    fetch_chunks_for_peer(video_id, peer_id)
            return jsonify(sigs)
        logger.debug(f"No signals for peer {peer_id} in video {video_id}")
        if video_id in peer_chunks and peer_id in peer_chunks[video_id]:
            if not peer_chunks[video_id][peer_id]:
                logger.info(f"No chunks for peer {peer_id} in video {video_id}, triggering server fetch")
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
            logger.error(f"Video {video_id} not found")
            return jsonify({'error': 'Video not found'}), 404
        size = os.path.getsize(video_path)
        logger.info(f"Metadata for video {video_id}: size={size}")
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
            logger.error(f"Video {video_id} not found for chunk {chunk_id}")
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
            logger.info(f"Served chunk {chunk_id} for video {video_id}, size={len(chunk)}")
            return send_file(io.BytesIO(chunk), mimetype='video/webm')
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error for chunk {chunk_id} of video {video_id}: {e.stderr.decode()}")
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
        logger.debug(f"Received chunk request for video {video_id}, peer {peer_id}")
        data = request.get_json()
        chunk_ids = data.get('chunkIds', [])
        logger.info(f"Processing chunk request for video {video_id}, peer {peer_id}, chunks: {chunk_ids}")
        if not chunk_ids:
            logger.error(f"No chunk IDs provided for peer {peer_id} in video {video_id}")
            return jsonify({'error': 'No chunk IDs provided'}), 400

        video_path = None
        for ext in ['.mp4', '.webm', '.mkv']:
            path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}{ext}")
            if os.path.exists(path):
                video_path = path
                break
        if not video_path:
            logger.error(f"Video {video_id} not found in {SUPABASE_CONFIG['storage_path']} for peer {peer_id}")
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
                logger.info(f"Delivered {chunk_id} to peer {peer_id} for video {video_id}, size={len(chunk)}")
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg error for {chunk_id}: {e.stderr.decode()}")
                results[chunk_id] = None
            except Exception as e:
                logger.error(f"Error delivering {chunk_id} to peer {peer_id}: {str(e)}")
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
            logger.error(f"Video {video_id} not found for HLS")
            return jsonify({'error': 'Video not found'}), 404
        hls_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'hls', video_id)
        hls_playlist = os.path.join(hls_dir, f"{video_id}.m3u8")
        if os.path.exists(hls_playlist):
            logger.info(f"Serving cached HLS playlist: {hls_playlist}")
            return send_file(hls_playlist, mimetype='application/vnd.apple.mpegurl')
        os.makedirs(hls_dir, exist_ok=True)
        cmd = [
            'ffmpeg', '-i', video_path, '-c:v', 'copy', '-c:a', 'copy',
            '-hls_time', '10', '-hls_list_size', '0', '-f', 'hls', hls_playlist
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Generated HLS playlist: {hls_playlist}")
            return send_file(hls_playlist, mimetype='application/vnd.apple.mpegurl')
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error for HLS {video_id}: {e.stderr.decode()}")
            return jsonify({'error': 'Failed to generate HLS playlist'}), 500

    @app.route('/api/search_videos')
    def search_videos():
        query = request.args.get('query', '')
        if not query:
            return jsonify([])
        try:
            backup = YouTubeBackup()
            videos = backup.search_videos(query, max_results=10)
            return jsonify([{
                'id': video['id'],
                'title': video['title'],
                'channel': video['channel'],
                'thumbnail': video['thumbnail'],
                'views': format_views(video['views'])
            } for video in videos])
        except Exception as e:
            logger.error(f"Error searching videos: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/api/search_tags')
    def search_tags():
        query = request.args.get('query', '')
        if not query:
            return jsonify([])
        try:
            backup = YouTubeBackup()
            tags = backup.search_tags(query, max_results=10)
            return jsonify(tags)
        except Exception as e:
            logger.error(f"Error searching tags: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/api/search_channels')
    def search_channels():
        query = request.args.get('query', '')
        if not query:
            return jsonify([])
        try:
            backup = YouTubeBackup()
            channels = backup.search_channels(query, max_results=10)
            return jsonify([{
                'title': channel['title'],
                'thumbnail': channel['thumbnail']
            } for channel in channels])
        except Exception as e:
            logger.error(f"Error searching channels: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    @app.route('/api/video_info')
    def video_info():
        video_id = request.args.get('video_id', '')
        if not video_id:
            return jsonify({'error': 'Video ID required'}), 400
        try:
            backup = YouTubeBackup()
            video = backup.get_video_info(video_id)
            if not video:
                return jsonify({'error': 'Video not found'}), 404
            return jsonify({
                'title': video['title'],
                'channel': video['channel'],
                'thumbnail': video['thumbnail'],
                'views': format_views(video['views'])
            })
        except Exception as e:
            logger.error(f"Error fetching video info: {str(e)}")
            return jsonify({'error': 'Server error'}), 500

    def estimate_download_time(video_count, avg_size_mb=CONFIG['avg_video_size_mb'], avg_speed_mbps=CONFIG['avg_download_speed_mbps']):
        total_size_mb = video_count * avg_size_mb
        time_seconds = total_size_mb / avg_speed_mbps
        return int(time_seconds)

    def get_video_count(request_type, request_value, count):
        if request_type == 'single_video':
            return 1
        elif request_type == 'mass_download':
            return len([line for line in request_value.split('\n') if line.strip()])
        elif request_type in ['search_and_download', 'download_by_tags', 'download_by_channel']:
            return min(count, 50)
        return count

    def generate_thumbnail(video_path, video_id):
        """Generate a thumbnail for a downloaded video."""
        thumbnail_dir = os.path.join(SUPABASE_CONFIG['storage_path'], 'thumbnails')
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = os.path.join(thumbnail_dir, f"{video_id}.jpg")
        
        cmd = [
            'ffmpeg', '-i', video_path, '-ss', '1', '-vframes', '1',
            '-vf', 'scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2',
            '-y', thumbnail_path
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            logger.info(f"Generated thumbnail for video {video_id} at {thumbnail_path}")
            return thumbnail_path
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg thumbnail error for video {video_id}: {e.stderr.decode()}")
            return None

    @app.route('/zapros_na_postavku', methods=['GET', 'POST'])
    @login_required
    def zapros_na_postavku():
        if request.method == 'POST':
            try:
                action = request.form.get('action')
                query = request.form.get('query')
                video_url = request.form.get('video_url')
                mass_links = request.form.get('mass_links')
                tags = request.form.get('tags')
                channel_id = request.form.get('channel_id')
                channel_name = request.form.get('channel_name')
                channel_mode = request.form.get('channel_mode')
                count = int(request.form.get('count', 10))
                min_views = int(request.form.get('min_views', 0))
                min_duration = int(request.form.get('min_duration', 0))
                max_duration = int(request.form.get('max_duration', 3600))

                # Валидация
                if action == 'search_and_download' and not query:
                    raise ValueError("Поисковой запрос обязателен")
                elif action == 'single_video' and (not video_url or 'v=' not in video_url):
                    raise ValueError("Некорректный URL видео")
                elif action == 'mass_download' and not mass_links:
                    raise ValueError("Ссылки для массовой загрузки обязательны")
                elif action == 'download_by_tags' and not tags:
                    raise ValueError("Теги обязательны")
                elif action == 'download_by_channel' and channel_mode == 'by_id' and not channel_id:
                    raise ValueError("ID канала обязателен")
                elif action == 'download_by_channel' and channel_mode == 'by_name' and not channel_name:
                    raise ValueError("Название канала обязательно")

                # Определяем request_type и request_value
                if action == 'search_and_download':
                    request_type = action
                    request_value = query
                elif action == 'single_video':
                    request_type = action
                    request_value = video_url
                elif action == 'mass_download':
                    request_type = action
                    request_value = mass_links
                elif action == 'download_by_tags':
                    request_type = action
                    request_value = tags
                elif action == 'download_by_channel':
                    request_type = action
                    request_value = channel_id if channel_mode == 'by_id' else channel_name

                # Оценка количества видео и времени
                video_count = get_video_count(request_type, request_value, count)
                estimated_time = estimate_download_time(video_count)

                # Добавление в очередь
                new_request = DownloadRequest(
                    user_id=current_user.id,
                    request_type=request_type,
                    request_value=request_value,
                    count=count,
                    min_views=min_views,
                    min_duration=min_duration,
                    max_duration=max_duration,
                    video_count=video_count,
                    estimated_time=estimated_time
                )
                db.session.add(new_request)
                db.session.commit()

                # Обработка загрузки
                backup = YouTubeBackup()
                videos = []
                if request_type == 'single_video':
                    video_id = re.search(r'v=([^&]+)', request_value)
                    if not video_id:
                        raise ValueError("Невозможно извлечь ID видео из URL")
                    video_id = video_id.group(1)
                    video_info = backup.get_video_info(video_id)
                    if video_info:
                        videos.append(video_info)
                elif request_type == 'mass_download':
                    for link in request_value.split('\n'):
                        if link.strip():
                            video_id = re.search(r'v=([^&]+)', link)
                            if not video_id:
                                logger.warning(f"Invalid URL in mass download: {link}")
                                continue
                            video_id = video_id.group(1)
                            video_info = backup.get_video_info(video_id)
                            if video_info:
                                videos.append(video_info)
                elif request_type == 'search_and_download':
                    search_results = backup.search_videos(request_value, max_results=count)
                    videos.extend(search_results)
                elif request_type == 'download_by_tags':
                    tag_results = backup.search_videos(tags, max_results=count)
                    videos.extend(tag_results)
                elif request_type == 'download_by_channel':
                    channel_videos = backup.get_channel_videos(request_value, max_results=count)
                    videos.extend(channel_videos)

                for video in videos:
                    video_id = video['id']
                    # Проверка на существование видео в базе
                    if Video.query.filter_by(id=video_id).first():
                        logger.info(f"Video {video_id} already exists in database")
                        continue

                    # Скачивание видео
                    video_path = os.path.join(SUPABASE_CONFIG['storage_path'], f"{video_id}.mp4")
                    try:
                        backup.download_video(video_id, video_path)
                    except Exception as e:
                        logger.error(f"Failed to download video {video_id}: {str(e)}")
                        continue

                    if not os.path.exists(video_path):
                        logger.error(f"Video file {video_path} not found after download")
                        continue

                    # Получение длительности
                    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', video_path]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    duration = 0
                    try:
                        duration_data = json.loads(result.stdout)
                        duration = int(float(duration_data['format']['duration']))
                    except Exception as e:
                        logger.error(f"Error getting duration for {video_id}: {e}")

                    # Генерация миниатюры
                    thumbnail_path = generate_thumbnail(video_path, video_id)
                    if not thumbnail_path:
                        logger.warning(f"Using default thumbnail for {video_id}")
                        thumbnail_path = None

                    # Сохранение в базу данных
                    new_video = Video(
                        id=video_id,
                        title=video.get('title', 'Без названия'),
                        description=video.get('description', ''),
                        upload_date=datetime.utcnow(),
                        views=video.get('views', 0),
                        uploader=video.get('channel', current_user.username),
                        duration=duration,
                        file_extension='mp4',
                        thumbnail_extension='jpg'
                    )
                    db.session.add(new_video)
                    db.session.commit()

                    logger.info(f"Successfully added video {video_id} to database")
                    new_request.downloaded_count += 1

                new_request.status = 'completed'
                new_request.completed_at = datetime.utcnow()
                db.session.commit()

                flash(f"Запрос (ID: {new_request.id}) успешно обработан. Загружено {new_request.downloaded_count} видео.")
            except ValueError as e:
                flash(f"Ошибка: {str(e)}")
                logger.error(f"Invalid input: {str(e)}")
            except Exception as e:
                db.session.rollback()
                flash(f"Ошибка при обработке запроса: {str(e)}")
                logger.error(f"Error processing request: {str(e)}")

        return render_template('zapros_na_postavku.html')

    @app.route('/queue', methods=['GET'])
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
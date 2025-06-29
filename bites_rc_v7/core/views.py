from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import StreamingHttpResponse, HttpResponse, HttpResponseServerError, FileResponse, JsonResponse
from django.conf import settings
from django.core.cache import cache
from django.views.decorators.http import condition, require_POST, require_GET
from django.utils import timezone
from django.views.decorators.gzip import gzip_page
from django.db.models import Count, Avg, F, Q, Subquery, OuterRef
from django.contrib import messages
from wsgiref.util import FileWrapper
import os
import re
import mimetypes
import time
import json
import random
import math
import logging
from datetime import datetime, timedelta
from supabase import create_client, Client
from .models import Video, Like, Dislike, Comment, Channel, UserProfile, Subscription, Ad, VideoTransition
from .forms import VideoUploadForm, CommentForm, UserProfileForm, ChannelForm, AdForm, YouTubeImportSettingsForm
from django.urls import reverse
from django.core.exceptions import ValidationError, FieldError
from .services.tag_service import generate_tags_for_video
from decimal import Decimal
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.views.static import serve
from youtube_api.services import YouTubeService

# Инициализация логгера
logger = logging.getLogger(__name__)


def analytics_test(request):
    """
    Тестовая страница для отладки API аналитики
    """
    return render(request, 'core/analytics_test.html')


@require_POST
def register_video_transition(request):
    from_id = request.POST.get('from_id')
    to_id = request.POST.get('to_id')
    if not (from_id and to_id):
        return JsonResponse({'success': False, 'status': 400})
    try:
        from_video = Video.objects.get(pk=from_id)
        to_video = Video.objects.get(pk=to_id)
        transition, created = VideoTransition.objects.get_or_create(from_video=from_video, to_video=to_video)
        transition.count += 1
        transition.save()
        logger.info(f"Transition from video {from_video.pk} to {to_video.pk} {'created' if created else 'updated'}. New count: {transition.count}")
        return JsonResponse({'success': True, 'count': transition.count})
    except Video.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'Video with id {from_id} or {to_id} not found.'}, status=404)


@login_required
def direct_seek_log(request):
    """
    Прямая запись перемоток видео в базу данных (поддерживает пакетную отправку)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Только POST-запросы'}, status=405)
    
    try:
        data = json.loads(request.body)
        video_id = data.get('video_id')
        
        if not video_id:
            return JsonResponse({'error': 'Необходим параметр video_id'}, status=400)
        
        # Получаем видео
        video = get_object_or_404(Video, pk=video_id)
        
        # Импортируем модель VideoSeek
        from analytics.models import VideoSeek
        
        # Проверяем, есть ли массив перемоток или одиночная перемотка
        seeks = data.get('seeks')
        
        if seeks and isinstance(seeks, list):
            # Пакетная обработка нескольких перемоток
            created_seeks = []
            
            for seek_data in seeks:
                from_position = seek_data.get('from')
                to_position = seek_data.get('to')
                
                if not all([from_position, to_position]):
                    continue  # Пропускаем неполные данные
                
                # Создаем новую запись о перемотке
                seek = VideoSeek(
                    user=request.user,
                    video=video,
                    from_position=from_position,
                    to_position=to_position
                )
                seek.save()
                created_seeks.append({
                    'id': seek.id,
                    'from': from_position,
                    'to': to_position
                })
            
            logger.info(f"Created {len(created_seeks)} seek records for user {request.user.username} and video {video_id}")
            return JsonResponse({
                'status': 'batch_created', 
                'message': f'Создано {len(created_seeks)} записей о перемотках',
                'seeks': created_seeks
            })
        else:
            # Обработка одиночной перемотки (для обратной совместимости)
            from_position = data.get('from_position')
            to_position = data.get('to_position')
            
            if not all([from_position, to_position]):
                return JsonResponse({
                    'error': 'Необходимы параметры from_position и to_position'
                }, status=400)
            
            # Создаем новую запись о перемотке
            seek = VideoSeek(
                user=request.user,
                video=video,
                from_position=from_position,
                to_position=to_position
            )
            seek.save()
            
            logger.info(f"Created single seek record for user {request.user.username} and video {video_id}")
            return JsonResponse({'status': 'created', 'seek_id': seek.id})
        
    except Video.DoesNotExist:
        return JsonResponse({'error': 'Видео не найдено'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Неверный JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error tracking seek: {e}")
        return JsonResponse({'error': str(e)}, status=500)

# Initialize Supabase client
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)

def home(request):
    search_query = request.GET.get('q', '')
    view_mode = request.GET.get('mode', 'standard')
    page = request.GET.get('page', 1)
    
    if search_query:
        video_list = Video.objects.filter(title__icontains=search_query).order_by('-absolute_rating', '-upload_date')
    else:
        video_list = Video.objects.all().order_by('-absolute_rating', '-upload_date')
    
    paginator = Paginator(video_list, 12)
    try:
        videos = paginator.page(page)
    except PageNotAnInteger:
        videos = paginator.page(1)
    except EmptyPage:
        videos = paginator.page(paginator.num_pages)
    
    # Преобразуем в список для вставки рекламы
    video_items = list(videos.object_list)
    
    # Вставляем рекламу ровно раз в N видео (N = frequency)
    ads = Ad.objects.filter(active=True).order_by('frequency')
    if ads:
        ad = ads.first()  # Берём рекламу с минимальной частотой
        n = max(ad.frequency, 1)
        # Вставляем рекламу после каждого n-го видео
        i = n
        while i <= len(video_items):
            ad_instance = ad
            ad_instance.is_ad = True
            video_items.insert(i, ad_instance)
            i += n + 1  # чтобы не вставлять подряд

    # Calculate time elapsed for videos (skip ads)
    for video in video_items:
        if not getattr(video, 'is_ad', False):
            video.time_elapsed = calculate_time_elapsed(video.upload_date)
    
    return render(request, 'core/home.html', {
        'videos': videos,
        'video_items': video_items,
        'search_query': search_query,
        'view_mode': view_mode,
        'paginator': paginator
    })





def calculate_time_elapsed(date):
    """Calculate human-readable time elapsed since video upload"""
    now = timezone.now()
    diff = now - date
    
    if diff.days > 365:
        years = diff.days // 365
        return f"{years} {'год' if years == 1 else 'года' if 2 <= years <= 4 else 'лет'} назад"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months} {'месяц' if months == 1 else 'месяца' if 2 <= months <= 4 else 'месяцев'} назад"
    elif diff.days > 0:
        return f"{diff.days} {'день' if diff.days == 1 else 'дня' if 2 <= diff.days <= 4 else 'дней'} назад"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} {'час' if hours == 1 else 'часа' if 2 <= hours <= 4 else 'часов'} назад"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} {'минуту' if minutes == 1 else 'минуты' if 2 <= minutes <= 4 else 'минут'} назад"
    else:
        return "только что"

def register(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        username = request.POST.get('username')
        
        if not all([email, password, username]):
            return render(request, 'core/register.html', {'error': 'All fields are required'})
        
        try:
            # Check if user already exists
            if User.objects.filter(email=email).exists():
                return render(request, 'core/register.html', {'error': 'Email already registered'})
            
            if User.objects.filter(username=username).exists():
                return render(request, 'core/register.html', {'error': 'Username already taken'})
            
            # Register user with Supabase
            response = supabase.auth.sign_up({
                'email': email,
                'password': password,
                'options': {
                    'data': {
                        'username': username
                    }
                }
            })
            
            # Create Django user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password
            )
            # Create user profile
            UserProfile.objects.create(user=user)
            messages.success(request, 'Registration successful! Please log in.')
            return redirect('core:login')
            
        except Exception as e:
            return render(request, 'core/register.html', {'error': str(e)})
    
    return render(request, 'core/register.html')

def login_view(request):
    if request.method == 'POST':
        login_field = request.POST.get('email')  # This can be either email or username
        password = request.POST.get('password')
        
        if not all([login_field, password]):
            return render(request, 'core/login.html', {'error': 'Все поля обязательны для заполнения'})
        
        try:
            # First, try to find user by email
            user = User.objects.filter(email=login_field).first()
            
            # If not found by email, try username
            if user is None:
                user = User.objects.filter(username=login_field).first()
            
            if user is None:
                return render(request, 'core/login.html', {'error': 'Пользователь не найден'})
            
            # Try to authenticate with Supabase using user's email
            try:
                response = supabase.auth.sign_in_with_password({
                    'email': user.email,
                    'password': password
                })
            except Exception as e:
                print(f"Supabase authentication error: {e}")
                # Continue with Django authentication even if Supabase fails
            
            # Authenticate user in Django
            user = authenticate(request, username=user.username, password=password)
            if user is not None:
                login(request, user)
                return redirect('core:home')
            else:
                return render(request, 'core/login.html', {'error': 'Неверный пароль'})
            
        except Exception as e:
            return render(request, 'core/login.html', {'error': str(e)})
    
    return render(request, 'core/login.html')

def logout_view(request):
    # First sign out from Supabase
    try:
        supabase.auth.sign_out()
    except Exception as e:
        # Log the error but continue with Django logout
        print(f"Error signing out from Supabase: {e}")
    
    # Then sign out from Django
    logout(request)
    messages.success(request, 'Successfully logged out')
    return redirect('core:home')

@login_required
def upload_video(request):
    youtube_error = None
    import_settings_form = YouTubeImportSettingsForm()
    user_channel = request.user.channels.first()
    # Инициализируем форму загрузки видео в начале функции, чтобы она всегда была доступна
    form = VideoUploadForm()
    
    if request.method == 'POST':
        # Проверяем, это YouTube импорт или обычная загрузка
        if 'youtube_import' in request.POST:
            # Обработка YouTube импорта
            import_settings_form = YouTubeImportSettingsForm(request.POST)
            if import_settings_form.is_valid():
                # Получаем данные формы
                import_mode = import_settings_form.cleaned_data['import_mode']
                
                try:
                    from youtube_api.services import YouTubeService
                    from core.services.download_queue_service import DownloadQueueService

                    # Инициализируем сервис и устанавливаем фильтры
                    youtube_service = YouTubeService(current_user=request.user)
                    
                    # Добавляем логирование для отладки
                    import logging
                    logger = logging.getLogger(__name__)
                    
                    # Установка фильтров, если они используются
                    if import_settings_form.cleaned_data['use_filters']:
                        youtube_service.set_filters(
                            min_views=import_settings_form.cleaned_data.get('min_views', 0),
                            max_views=import_settings_form.cleaned_data.get('max_views', 0),
                            min_duration=import_settings_form.cleaned_data.get('min_duration', 0),
                            max_duration=import_settings_form.cleaned_data.get('max_duration', 0)
                        )
                    
                    imported_videos = []
                    
                    # Режим импорта одного видео
                    if import_mode == 'single':
                        url = import_settings_form.cleaned_data['single_url']
                        if url:
                            # Проверка и обработка YouTube Shorts URL
                            if 'youtube.com/shorts/' in url:
                                # Преобразуем URL shorts в обычный youtube URL
                                video_id = url.split('shorts/')[1].split('?')[0]
                                url = f'https://www.youtube.com/watch?v={video_id}'
                                logger.info(f"Converted YouTube Shorts URL to regular URL: {url}")
                            
                            video, error = youtube_service.import_video(url, request.user, download_file=True)
                            if video:
                                imported_videos.append(video)
                            elif error:
                                youtube_error = error
                    
                    # Режим импорта нескольких видео
                    elif import_mode == 'multiple':
                        urls = import_settings_form.cleaned_data['multiple_urls'].splitlines()
                        for url in urls:
                            url = url.strip()
                            if url:
                                # Проверка и обработка YouTube Shorts URL
                                if 'youtube.com/shorts/' in url:
                                    # Преобразуем URL shorts в обычный youtube URL
                                    video_id = url.split('shorts/')[1].split('?')[0]
                                    url = f'https://www.youtube.com/watch?v={video_id}'
                                    logger.info(f"Converted YouTube Shorts URL to regular URL: {url}")
                                
                                video, error = youtube_service.import_video(url, request.user, download_file=True)
                                if video:
                                    imported_videos.append(video)
                    
                    # Режим поиска видео
                    elif import_mode == 'search':
                        query = import_settings_form.cleaned_data['search_query']
                        max_count = import_settings_form.cleaned_data['max_count'] or 10
                        videos_data = youtube_service.search_videos(query, limit=max_count)
                        
                        for video_data in videos_data:
                            if 'youtube_id' in video_data:
                                video_url = f"https://www.youtube.com/watch?v={video_data['youtube_id']}"
                                video, error = youtube_service.import_video(video_url, request.user, download_file=True)
                                if video:
                                    imported_videos.append(video)
                    
                    # Режим импорта с канала
                    elif import_mode == 'channel':
                        channel_url = import_settings_form.cleaned_data['channel_url']
                        max_count = import_settings_form.cleaned_data['max_count'] or 10
                        
                        channel_id = youtube_service.extract_channel_id(channel_url)
                        if not channel_id:
                            youtube_error = 'Не удалось извлечь ID канала из URL'
                        else:
                            # Импортируем канал и его видео
                            channel, error = youtube_service.import_channel(
                                channel_id, 
                                request.user, 
                                download_videos=True, 
                                download_limit=max_count
                            )
                            
                            if error:
                                youtube_error = error
                            elif channel:
                                # Получаем импортированные видео канала
                                imported_videos = channel.videos.all()
                    
                    # Выводим сообщение об успехе
                    if imported_videos:
                        messages.success(
                            request, 
                            f'Начата загрузка {len(imported_videos)} видео. Вы можете отслеживать статус на странице вашего канала.'
                        )
                        if user_channel:
                            return redirect('core:channel_videos', channel_id=user_channel.pk)
                        return redirect('core:home')
                    else:
                        if not youtube_error:
                            youtube_error = 'Не найдено подходящих видео для импорта'
                
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())  # Для отладки в консоли
                    youtube_error = f'Ошибка при импорте с YouTube: {str(e)}'
        else:
            # Обычная загрузка видео с компьютера
            form = VideoUploadForm(request.POST, request.FILES)
            if form.is_valid():
                video = form.save(commit=False)
                video.uploaded_by = request.user
                
                # Если у пользователя есть канал, связываем видео с ним
                if user_channel:
                    video.channel = user_channel
                
                video.save()
                
                # Обработка тегов
                if form.cleaned_data.get('tags'):
                    tags_list = [tag.strip() for tag in form.cleaned_data['tags'].split(',') if tag.strip()]
                    for tag_name in tags_list:
                        video.add_tag(tag_name)
                
                # Автоматическая генерация тегов, если отмечено
                if form.cleaned_data.get('auto_generate_tags'):
                    generate_tags_for_video(video)
                
                messages.success(request, 'Видео успешно загружено')
                return redirect('core:video_detail', pk=video.pk)
    else:
        # Форма уже инициализирована в начале функции
        # Если пользователь имеет канал, предварительно заполняем поле канала
        if user_channel:
            form.fields['channel'].initial = user_channel.id

    return render(request, 'core/upload.html', {
        'form': form,
        'import_settings_form': import_settings_form,
        'youtube_error': youtube_error
    })

def close_file(self):
    """Helper function to close file handle after streaming"""
    if hasattr(self, '_file'):
        self._file.close()

def stream_video(request, pk):
    video = get_object_or_404(Video, pk=pk)
    logger = logging.getLogger(__name__)
    
    # Проверяем, есть ли файл в базе данных и доступен ли он физически
    physical_file_exists = False
    if video.file:
        file_path = os.path.join(settings.MEDIA_ROOT, str(video.file))
        physical_file_exists = os.path.isfile(file_path) and os.path.getsize(file_path) > 0
        logger.info(f"[STREAM_VIDEO] Video {pk} physical file exists: {physical_file_exists}, path: {file_path}")
    
    # Если файл существует и доступен, устанавливаем is_downloaded = True если ещё не установлено
    if physical_file_exists and not video.is_downloaded:
        video.is_downloaded = True
        video.save(update_fields=['is_downloaded'])
        logger.info(f"[STREAM_VIDEO] Updated video {pk} is_downloaded status to True")
    
    # Если файла нет в модели или он недоступен физически
    if not physical_file_exists:
        # If it's a YouTube video, check download status
        if video.is_youtube and video.youtube_id:
            cache_key = f'video_download_status_{video.youtube_id}'
            download_status = cache.get(cache_key)
            
            logger.info(f"[STREAM_VIDEO] Video {pk} download status from cache: {download_status}")
            
            if download_status and download_status.get('status') == 'downloading':
                # Video is currently downloading
                return JsonResponse({
                    'status': 'downloading',
                    'progress': download_status.get('progress', 0),
                    'youtube_id': video.youtube_id,
                    'youtube_url': f'https://www.youtube.com/watch?v={video.youtube_id}'
                })
            elif download_status and download_status.get('status') == 'completed':
                # Загрузка завершена, но файл не найден по пути
                logger.warning(f"[STREAM_VIDEO] Video {pk} marked as completed in cache but file not found")
                # Сбрасываем статус загрузки и пробуем скачать заново
                cache.delete(cache_key)
                try:
                    from youtube_api.tasks import download_youtube_video
                    # Запускаем загрузку заново
                    download_youtube_video.delay(video.youtube_id)
                    return JsonResponse({
                        'status': 'download_queued',
                        'message': 'Файл не найден, запускаем загрузку заново',
                        'youtube_id': video.youtube_id
                    })
                except Exception as e:
                    logger.error(f"[STREAM_VIDEO] Error requeuing download for video {video.youtube_id}: {e}")
            elif not download_status or download_status.get('status') in ['failed', None]:
                try:
                    from youtube_api.tasks import download_youtube_video
                    download_youtube_video.delay(video.youtube_id)
                    return JsonResponse({
                        'status': 'download_queued',
                        'youtube_id': video.youtube_id,
                        'youtube_url': f'https://www.youtube.com/watch?v={video.youtube_id}'
                    })
                except Exception as e:
                    logger.error(f"[STREAM_VIDEO] Error queuing download for video {video.youtube_id}: {e}")
            
            # Return YouTube embed info as fallback
            return JsonResponse({
                'status': 'youtube_fallback',
                'youtube_id': video.youtube_id,
                'youtube_url': f'https://www.youtube.com/watch?v={video.youtube_id}'
            })
            
    # Если файл существует физически, отдаем его
    try:
        file_path = video.file.path
        logger.info(f"[STREAM_VIDEO] Serving video file: {file_path}")
        
        # Проверяем запрос Range для поддержки перемотки
        content_type = mimetypes.guess_type(file_path)[0] or 'video/mp4'
        response = FileResponse(open(file_path, 'rb'), content_type=content_type)
        
        # Добавляем заголовки для поддержки перемотки
        response['Accept-Ranges'] = 'bytes'
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
        return response
    except Exception as e:
        logger.error(f"[STREAM_VIDEO] Error serving video file for video {pk}: {e}")
        return JsonResponse({'status': 'error', 'message': 'Ошибка при отдаче видеофайла'}, status=500)

def video_detail(request, pk):
    video = get_object_or_404(Video, pk=pk)
    video.views += 1
    video.save()
    
    # Track analytics for authenticated users
    if request.user.is_authenticated:
        try:
            # Импортируем модель аналитики
            from analytics.models import UserVideoView
            
            # Проверяем, есть ли уже активный просмотр этого видео
            active_views = UserVideoView.objects.filter(
                user=request.user,
                video_id=pk,
                is_active=True
            )
            
            if not active_views.exists():
                # Создаем новую запись о просмотре
                UserVideoView.objects.create(
                    user=request.user,
                    video_id=pk,
                    is_active=True
                )
                logger.info(f"Created video view record for user {request.user.username} and video {pk}")
        except Exception as e:
            logger.error(f"Error tracking video view in analytics: {e}")
    
    # Get download status for YouTube videos
    download_status = None
    if video.is_youtube and not video.is_downloaded:
        cache_key = f'video_download_status_{video.youtube_id}'
        download_status = cache.get(cache_key)
    
    # Get comments and update time elapsed with pagination (6 comments per page)
    comments_list = video.comments.all().order_by('-created_at')
    comments_page = request.GET.get('comments_page', 1)
    comments_paginator = Paginator(comments_list, 6)  # 6 комментариев на странице
    
    try:
        comments = comments_paginator.page(comments_page)
    except PageNotAnInteger:
        comments = comments_paginator.page(1)
    except EmptyPage:
        comments = comments_paginator.page(comments_paginator.num_pages)
    
    # Добавляем время создания для каждого комментария
    for comment in comments:
        comment.time_elapsed = calculate_time_elapsed(comment.created_at)
    
    # Check if user liked/disliked this video
    user_liked = False
    user_disliked = False
    is_subscribed = False
    
    if request.user.is_authenticated:
        user_liked = Like.objects.filter(video=video, user=request.user).exists()
        user_disliked = Dislike.objects.filter(video=video, user=request.user).exists()
        
        # Check if user is subscribed to the video's channel
        if video.channel:
            is_subscribed = video.channel.subscribers.filter(id=request.user.id).exists()
    
    # Add time elapsed for the video
    if not getattr(video, 'is_ad', False):
        video.time_elapsed = calculate_time_elapsed(video.upload_date)
    
    # Get recommended videos (by tags) - видео похожие по тегам, максимум 8 видео
    RECOMMENDED_VIDEOS_LIMIT = 8
    
    if video.tags.exists():
        video_tags = video.tags.all()
        
        # Аннотируем количество переходов
        transitions = VideoTransition.objects.filter(
            from_video=video,
            to_video=OuterRef('pk')
        ).values('count')
        
        recommended_videos_queryset = Video.objects.filter(
            tags__in=video_tags
        ).exclude(pk=video.pk).distinct().annotate(
            transition_count=Subquery(transitions)
        )
        
        # Получаем все подходящие видео
        all_recommended_videos = list(recommended_videos_queryset)

        video_info_before_sort = [(v.pk, v.transition_count) for v in all_recommended_videos]
        logger.info(f"Recommended videos for video {pk} before sorting (pk, transition_count): {video_info_before_sort}")

        # Сортируем по количеству совпадающих тегов (наиболее релевантные сначала)
        recommended_videos = sorted(
            all_recommended_videos,
            key=lambda v: (v.transition_count or 0, sum(1 for tag in video_tags if tag in v.tags.all()), v.absolute_rating),
            reverse=True
        )[:RECOMMENDED_VIDEOS_LIMIT]  # Ограничиваем количество видео

        video_info_after_sort = [(v.pk, v.transition_count) for v in recommended_videos]
        logger.info(f"Recommended videos for video {pk} after sorting (pk, transition_count): {video_info_after_sort}")

        # Добавляем time_elapsed для каждого видео
        for rec_video in recommended_videos:
            rec_video.time_elapsed = calculate_time_elapsed(rec_video.upload_date)
    else:
        # Если у видео нет тегов, показываем популярные видео
        recommended_videos = Video.objects.exclude(pk=video.pk).order_by('-absolute_rating', '-upload_date')[:RECOMMENDED_VIDEOS_LIMIT]
        for rec_video in recommended_videos:
            rec_video.time_elapsed = calculate_time_elapsed(rec_video.upload_date)
    
    # Get similar videos by tags with pagination
    similar_videos = []
    similar_videos_page = request.GET.get('similar_page', 1)
    items_per_page = 12  # Количество видео на страницу
    
    if video.tags.exists():
        video_tags = video.tags.all()
        similar_videos_queryset = Video.objects.filter(tags__in=video_tags).exclude(pk=video.pk).distinct()
        
        # Получаем все подходящие видео (до 666)
        all_similar_videos = list(similar_videos_queryset)
        
        # Сортируем по количеству совпадающих тегов (наиболее релевантные сначала)
        all_similar_videos = sorted(
            all_similar_videos,
            key=lambda v: sum(1 for tag in video_tags if tag in v.tags.all()),
            reverse=True
        )[:666]
        
        # Добавляем time_elapsed для каждого видео
        for sim_video in all_similar_videos:
            sim_video.time_elapsed = calculate_time_elapsed(sim_video.upload_date)
        
        # Создаем пагинатор
        paginator = Paginator(all_similar_videos, items_per_page)
        
        try:
            similar_videos = paginator.page(similar_videos_page)
        except PageNotAnInteger:
            similar_videos = paginator.page(1)
        except EmptyPage:
            similar_videos = paginator.page(paginator.num_pages)
    
    comment_form = CommentForm()
    return render(request, 'core/video_detail.html', {
        'video': video, 
        'comments': comments, 
        'comments_paginator': comments_paginator,
        'comment_form': comment_form,
        'user_liked': user_liked,
        'user_disliked': user_disliked,
        'is_subscribed': is_subscribed,
        'download_status': download_status,
        'recommended_videos': recommended_videos,
        'similar_videos': similar_videos
    })

def get_video_download_status(request, video_id):
    """AJAX endpoint to check video download status with queue support"""
    from core.services.download_queue_service import DownloadQueueService
    
    # Сначала проверяем кеш для быстрого ответа
    cache_key = f'video_download_status_{video_id}'
    cache_status = cache.get(cache_key)
    
    # Получаем информацию о видео
    video = Video.objects.filter(youtube_id=video_id).first()
    
    if video and video.is_downloaded:
        # Если видео уже скачано, возвращаем completed
        status = {
            'status': 'completed',
            'progress': 100
        }
    else:
        # Проверяем статус в очереди
        queue_status = DownloadQueueService.get_queue_status(youtube_id=video_id)
        
        if queue_status:
            # Если видео в очереди, возвращаем статус из очереди
            status = {
                'status': queue_status['status'],
                'progress': queue_status['progress'],
                'queue_position': queue_status['position']
            }
            
            if queue_status['error']:
                status['error'] = queue_status['error']
        elif cache_status:
            # Если нет в очереди, но есть в кеше (для обратной совместимости)
            status = cache_status
        else:
            # Если нигде не найдено, статус 'pending'
            status = {
                'status': 'pending',
                'progress': 0
            }
    
    return JsonResponse(status)


def add_to_download_queue(request, video_id):
    """AJAX endpoint to add a video to the download queue"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Метод не поддерживается'}, status=405)
    
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Требуется авторизация'}, status=403)
    
    from core.services.download_queue_service import DownloadQueueService
    
    try:
        # Проверяем существует ли видео
        video = Video.objects.filter(youtube_id=video_id).first()
        
        if not video:
            return JsonResponse({'success': False, 'error': 'Видео не найдено'}, status=404)
        
        if video.is_downloaded:
            return JsonResponse({'success': True, 'status': 'completed', 'message': 'Видео уже скачано'})
        
        # Проверяем, есть ли видео уже в очереди
        queue_status = DownloadQueueService.get_queue_status(youtube_id=video_id)
        
        if queue_status:
            return JsonResponse({
                'success': True, 
                'status': queue_status['status'],
                'message': 'Видео уже в очереди',
                'queue_position': queue_status['position']
            })
        
        # Добавляем в очередь
        queue_item = DownloadQueueService.add_to_queue(video, request.user)
        
        # Начинаем обработку очереди, если еще не запущена
        DownloadQueueService.process_next_in_queue()
        
        return JsonResponse({
            'success': True,
            'message': 'Видео добавлено в очередь',
            'queue_position': queue_item.position,
            'status': queue_item.status
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def profile(request, username):
    user = get_object_or_404(User, username=username)
    
    # Ensure user has a profile
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Get user's videos
    videos = Video.objects.filter(uploaded_by=user).order_by('-upload_date')
    
    # Get stats
    total_views = sum(video.views for video in videos)
    total_likes = sum(video.likes.count() for video in videos)
    total_dislikes = sum(video.dislikes.count() for video in videos)
    
    # Check if user has a channel
    try:
        channel = user.channel
        has_channel = True
    except:
        channel = None
        has_channel = False
    
    return render(request, 'core/profile.html', {
        'profile_user': user, 
        'profile': profile,
        'videos': videos,
        'stats': {
            'video_count': videos.count(),
            'total_views': total_views,
            'total_likes': total_likes,
            'total_dislikes': total_dislikes,
        },
        'has_channel': has_channel,
        'channel': channel
    })

@login_required
def edit_profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect('core:profile', username=request.user.username)
    else:
        form = UserProfileForm(instance=profile)
    
    return render(request, 'core/edit_profile.html', {'form': form})

@login_required
def create_channel(request):
    if request.method == 'POST':
        form = ChannelForm(request.POST, request.FILES)
        if form.is_valid():
            channel = form.save(commit=False)
            channel.owner = request.user
            channel.save()
            return redirect('core:channel_detail', channel_id=channel.pk)
    else:
        form = ChannelForm()
    
    return render(request, 'core/create_channel.html', {'form': form})

@login_required
def edit_channel(request, channel_id):
    channel = get_object_or_404(Channel, id=channel_id, owner=request.user)
    
    if request.method == 'POST':
        form = ChannelForm(request.POST, request.FILES, instance=channel)
        if form.is_valid():
            form.save()
            return redirect('core:channel_detail', channel_id=channel.pk)
    else:
        form = ChannelForm(instance=channel)
    
    return render(request, 'core/edit_channel.html', {'form': form, 'channel': channel})

def channel_detail(request, channel_id):
    channel = get_object_or_404(Channel, id=channel_id)
    
    # Track analytics for authenticated users
    if request.user.is_authenticated:
        try:
            # Импортируем модель аналитики
            from analytics.models import UserChannelView
            
            # Проверяем, есть ли уже активный просмотр этого канала
            active_views = UserChannelView.objects.filter(
                user=request.user,
                channel_id=channel_id,
                is_active=True
            )
            
            if not active_views.exists():
                # Создаем новую запись о просмотре канала
                UserChannelView.objects.create(
                    user=request.user,
                    channel_id=channel_id,
                    is_active=True
                )
                logger.info(f"Created channel view record for user {request.user.username} and channel {channel_id}")
        except Exception as e:
            logger.error(f"Error tracking channel view in analytics: {e}")
    
    # Get channel videos
    videos = Video.objects.filter(channel=channel).order_by('-upload_date')
    
    # Get stats
    total_views = sum(video.views for video in videos)
    subscriber_count = channel.subscribers.count()
    
    # Check if user is subscribed and if they own the channel
    is_subscribed = False
    is_owner = False
    
    if request.user.is_authenticated:
        is_subscribed = channel.subscribers.filter(id=request.user.id).exists()
        is_owner = (channel.owner == request.user)
    
    return render(request, 'core/channel_detail.html', {
        'channel': channel,
        'videos': videos,
        'stats': {
            'video_count': videos.count(),
            'total_views': total_views,
            'subscriber_count': subscriber_count,
        },
        'is_subscribed': is_subscribed,
        'is_owner': is_owner
    })

@login_required
def channel_videos(request, channel_id):
    """View for channel owner to manage videos"""
    channel = get_object_or_404(Channel, id=channel_id, owner=request.user)
    videos = Video.objects.filter(channel=channel).order_by('-upload_date')
    
    return render(request, 'core/channel_videos.html', {
        'channel': channel,
        'videos': videos
    })

@login_required
def delete_video(request, pk):
    video = get_object_or_404(Video, pk=pk)
    
    # Check if user is the video owner
    if video.uploaded_by != request.user:
        messages.error(request, "Вы не можете удалить это видео")
        return redirect('core:video_detail', pk=pk)
    
    # Store channel info before deletion
    channel_id = video.channel.id if video.channel else None
    
    if request.method == 'POST':
        # Delete the video file
        if video.file and os.path.exists(video.file.path):
            os.remove(video.file.path)
        
        # Delete thumbnail if exists
        if video.thumbnail and os.path.exists(video.thumbnail.path):
            os.remove(video.thumbnail.path)
        
        video.delete()
        messages.success(request, "Видео успешно удалено")
        
        # Redirect based on whether video had a channel
        if channel_id:
            return redirect('core:channel_videos', channel_id=channel_id)
        return redirect('core:home')
    
    return render(request, 'core/delete_video.html', {'video': video})

@login_required
def edit_video(request, pk):
    video = get_object_or_404(Video, pk=pk)
    
    # Check if user is the video owner
    if video.uploaded_by != request.user:
        messages.error(request, "Вы не можете редактировать это видео")
        return redirect('core:video_detail', pk=pk)
    
    if request.method == 'POST':
        form = VideoUploadForm(request.POST, request.FILES, instance=video)
        if form.is_valid():
            form.save()
            messages.success(request, "Видео успешно обновлено")
            return redirect('core:video_detail', pk=video.pk)
    else:
        form = VideoUploadForm(instance=video)
    
    return render(request, 'core/edit_video.html', {'form': form, 'video': video})

@login_required
def subscribe(request, channel_id):
    channel = get_object_or_404(Channel, id=channel_id)
    
    # Can't subscribe to your own channel
    if channel.owner == request.user:
        messages.warning(request, "Вы не можете подписаться на свой канал")
        return redirect('core:channel_detail', channel_id=channel_id)
    
    # Add user to subscribers
    channel.subscribers.add(request.user)
    
    # Log subscription
    Subscription.objects.get_or_create(user=request.user, channel=channel)
    
    # Recalculate channel owner's karma
    try:
        profile = UserProfile.objects.get(user=channel.owner)
        profile.calculate_karma()
    except:
        pass
    
    return redirect('core:channel_detail', channel_id=channel_id)

@login_required
def unsubscribe(request, channel_id):
    channel = get_object_or_404(Channel, id=channel_id)
    
    # Remove user from subscribers
    channel.subscribers.remove(request.user)
    
    # Remove subscription record
    Subscription.objects.filter(user=request.user, channel=channel).delete()
    
    # Recalculate channel owner's karma
    try:
        profile = UserProfile.objects.get(user=channel.owner)
        profile.calculate_karma()
    except:
        pass
    
    return redirect('core:channel_detail', channel_id=channel_id)

@login_required
def like_video(request, pk):
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return redirect('core:video_detail', pk=pk)
        
    video = get_object_or_404(Video, pk=pk)
    print(f"Processing like for video {pk} by user {request.user.username}")
    
    # Remove dislike if exists
    dislike_deleted = Dislike.objects.filter(video=video, user=request.user).delete()
    print(f"Removed dislike: {dislike_deleted}")
    
    # Toggle like
    like, created = Like.objects.get_or_create(video=video, user=request.user)
    print(f"Like created: {created}")
    if not created:
        like.delete()
        print("Existing like removed")
    
    # Update video rating
    video.calculate_absolute_rating()
    
    # Calculate karma for video uploader
    try:
        profile = UserProfile.objects.get(user=video.uploaded_by)
        profile.calculate_karma()
    except Exception as e:
        print(f"Error calculating karma: {e}")
    
    # Get updated counts
    likes_count = video.likes_count
    dislikes_count = video.get_dislikes_count()
    print(f"Updated counts - likes: {likes_count}, dislikes: {dislikes_count}")
    
    response_data = {
        'success': True,
        'likes': likes_count,
        'dislikes': dislikes_count,
        'absolute_rating': video.absolute_rating,
        'liked': created
    }
    print(f"Sending response: {response_data}")
    return JsonResponse(response_data)

@login_required
def dislike_video(request, pk):
    if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return redirect('core:video_detail', pk=pk)
        
    video = get_object_or_404(Video, pk=pk)
    print(f"Processing dislike for video {pk} by user {request.user.username}")
    
    # Remove like if exists
    like_deleted = Like.objects.filter(video=video, user=request.user).delete()
    print(f"Removed like: {like_deleted}")
    
    # Toggle dislike
    dislike, created = Dislike.objects.get_or_create(video=video, user=request.user)
    print(f"Dislike created: {created}")
    if not created:
        dislike.delete()
        print("Existing dislike removed")
    
    # Update video rating
    video.calculate_absolute_rating()
    
    # Calculate karma for video uploader
    try:
        profile = UserProfile.objects.get(user=video.uploaded_by)
        profile.calculate_karma()
    except Exception as e:
        print(f"Error calculating karma: {e}")
    
    # Get updated counts
    likes_count = video.likes_count
    dislikes_count = video.get_dislikes_count()
    print(f"Updated counts - likes: {likes_count}, dislikes: {dislikes_count}")
    
    response_data = {
        'success': True,
        'likes': likes_count,
        'dislikes': dislikes_count,
        'absolute_rating': video.absolute_rating,
        'disliked': created
    }
    print(f"Sending response: {response_data}")
    return JsonResponse(response_data)

@login_required
def add_comment(request, pk):
    video = get_object_or_404(Video, pk=pk)
    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.video = video
            comment.user = request.user
            
            # Автоматическое определение тональности с помощью transformers
            try:
                # Простая проверка на негативные слова - для английского и русского
                eng_negative_words = ['fuck', 'shit', 'hate', 'awful', 'terrible', 'bad', 'worst', 'sucks', 'garbage', 'trash']
                rus_negative_words = ['хуй', 'пизд', 'блядь', 'ебал', 'хуев', 'пидор', 'говн', 'дерьм', 'ненавижу', 'отстой', 'хрень']
                
                # Позитивные слова для проверки
                eng_positive_words = ['good', 'great', 'awesome', 'excellent', 'love', 'best', 'amazing', 'wonderful']
                rus_positive_words = ['отлично', 'прекрасно', 'круто', 'супер', 'класс', 'обожаю', 'нравится', 'лучший', 'хорош']
                
                content_lower = comment.content.lower()
                
                # Определяем язык на основе наличия кириллицы
                has_cyrillic = bool(re.search('[а-яА-Я]', content_lower))
                
                # Проверка наличия негативных слов
                has_negative_words = any(word in content_lower for word in eng_negative_words)
                if has_cyrillic:
                    has_negative_words = has_negative_words or any(word in content_lower for word in rus_negative_words)
                
                # Проверка наличия позитивных слов
                has_positive_words = any(word in content_lower for word in eng_positive_words)
                if has_cyrillic:
                    has_positive_words = has_positive_words or any(word in content_lower for word in rus_positive_words)
                
                if has_negative_words:
                    comment.sentiment = 0.0  # Явно негативный комментарий
                elif has_positive_words:
                    comment.sentiment = 1.0  # Явно позитивный комментарий
                else:
                    try:
                        # Для русского текста используем rubert-sentiment
                        if has_cyrillic:
                            try:
                                tokenizer = AutoTokenizer.from_pretrained("cointegrated/rubert-sentiment")
                                model = AutoModelForSequenceClassification.from_pretrained("cointegrated/rubert-sentiment")
                                inputs = tokenizer(content, return_tensors="pt", truncation=True, padding=True)
                                outputs = model(**inputs)
                                scores = outputs.logits.softmax(dim=1)
                                result = scores.tolist()[0]
                                
                                # Преобразование результата в значение от 0 до 1
                                if result[0] > result[1]:  # Негативный сентимент
                                    sentiment_score = 0.33
                                else:  # Позитивный сентимент
                                    sentiment_score = 0.66
                            except Exception as e:
                                print(f"Ошибка при анализе сентимента (rubert-sentiment): {str(e)}")
                                sentiment_score = 0.5
                    except Exception as inner_e:
                        print(f"Общая ошибка модели сентимент-анализа: {inner_e}")
                        # В случае ошибки используем простой анализ текста
                        if any(word in content_lower for word in (eng_negative_words + rus_negative_words if has_cyrillic else eng_negative_words)):
                            comment.sentiment = 0.0  # Негативный
                        elif any(word in content_lower for word in (eng_positive_words + rus_positive_words if has_cyrillic else eng_positive_words)):
                            comment.sentiment = 1.0  # Позитивный
                        else:
                            comment.sentiment = 0.5  # Нейтральный
            except Exception as e:
                # В случае любой ошибки, обеспечиваем значение по умолчанию
                print(f"Ошибка сентимент-анализа: {e}")
                comment.sentiment = 0.5
            
            comment.save()
            
            # Recalculate video rating
            video.calculate_absolute_rating()
            
            # Calculate karma for comment author
            try:
                profile = UserProfile.objects.get(user=request.user)
                profile.calculate_karma()
            except:
                pass
            
            return redirect('core:video_detail', pk=pk)
    return redirect('core:video_detail', pk=pk)

@login_required
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    
    # Check if user is the comment author
    if comment.user != request.user and comment.video.uploaded_by != request.user:
        messages.error(request, "Вы не можете удалить этот комментарий")
        return redirect('core:video_detail', pk=comment.video.pk)
    
    video_pk = comment.video.pk
    comment.delete()
    
    # Recalculate video rating
    video = Video.objects.get(pk=video_pk)
    video.calculate_absolute_rating()
    
    return redirect('core:video_detail', pk=video_pk)

@login_required
def user_karma(request):
    """View user's karma and statistics"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    # Gather karma statistics
    # Получаем только непосредственно загруженные пользователем видео (не импортированные с YouTube)
    videos = Video.objects.filter(uploaded_by=request.user).exclude(imported_by=request.user)
    
    # Получаем импортированные видео отдельно
    imported_videos = Video.objects.filter(imported_by=request.user)
    
    # Статистика загруженных видео
    video_count = videos.count()
    total_views = sum(video.views for video in videos)
    total_likes = sum(video.likes.count() for video in videos)
    total_dislikes = sum(video.dislikes.count() for video in videos)
    
    # Статистика импортированных видео
    imported_count = imported_videos.count()
    
    # Общая статистика комментариев
    comments_made = Comment.objects.filter(user=request.user).count()
    comments_received = Comment.objects.filter(video__in=videos).count()
    
    # Get karma breakdown
    try:
        likes_given = Like.objects.filter(user=request.user).count()
        dislikes_given = Dislike.objects.filter(user=request.user).count()
        comments = Comment.objects.filter(user=request.user)
        comment_sentiment_avg = 0.5
        if comments.exists():
            comment_sentiment_avg = sum(c.sentiment for c in comments) / comments.count()
        
        video_comments = Comment.objects.filter(video__in=videos)
        video_sentiment_avg = 0.5
        if video_comments.exists():
            video_sentiment_avg = sum(c.sentiment for c in video_comments) / video_comments.count()
        
        # Get subscriber count
        try:
            subscribers = request.user.channel.subscribers.count()
        except:
            subscribers = 0
        
        account_age = (timezone.now() - profile.created_at).days
        if account_age < 1:
            account_age = 1  # Prevent division by zero
        
        # Average like/dislike ratio on videos
        avg_like_ratio = 0.85  # Default value
        if total_likes + total_dislikes > 0:
            avg_like_ratio = total_likes / (total_likes + total_dislikes)
        
        karma_stats = {
            'likes_given': likes_given,
            'dislikes_given': dislikes_given,
            'comments_made': comments_made,
            'comments_sentiment': f"{comment_sentiment_avg:.2f}",
            'video_count': video_count,
            'imported_count': imported_count,
            'total_likes': total_likes,
            'total_dislikes': total_dislikes,
            'videos_sentiment': f"{video_sentiment_avg:.2f}",
            'subscribers': subscribers,
            'account_age': account_age,
            'avg_like_ratio': f"{avg_like_ratio:.2f}",
            'karma_stability': f"{profile.karma_stability:.2f}",
        }
    except Exception as e:
        karma_stats = {"error": str(e)}
    
    return render(request, 'core/user_karma.html', {
        'profile': profile,
        'stats': {
            'video_count': video_count,
            'imported_count': imported_count,
            'total_views': total_views,
            'total_likes': total_likes,
            'total_dislikes': total_dislikes,
            'comments_made': comments_made,
            'comments_received': comments_received,
        },
        'karma_stats': karma_stats
    })



@login_required
def recalculate_karma(request):
    """Recalculate user's karma"""
    try:
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        profile.calculate_karma()
        messages.success(request, f"Карма пересчитана: {profile.karma:.2f}")
    except Exception as e:
        messages.error(request, f"Ошибка при пересчете кармы: {str(e)}")
    
    return redirect('core:user_karma')

@login_required
def recalculate_all_ratings(request):
    """Recalculate ratings for all videos"""
    from django.db import transaction
    import logging
    import time
    logger = logging.getLogger(__name__)
    
    start_time = time.time()
    try:
        with transaction.atomic():
            videos = Video.objects.select_related().prefetch_related('comments', 'likes').all()
            count = 0
            
            for video in videos:
                try:
                    video.calculate_absolute_rating()
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to calculate rating for video {video.id}: {str(e)}")
                    raise
            
            execution_time = time.time() - start_time
            messages.success(request, f"Рейтинги пересчитаны для {count} видео за {execution_time:.2f} секунд")
    except Exception as e:
        logger.error(f"Error during rating recalculation: {str(e)}")
        messages.error(request, f"Ошибка при пересчете рейтингов: {str(e)}")
    
    return redirect('core:home')

@login_required
def regenerate_all_tags(request):
    """Regenerate tags for all videos"""
    from django.db import transaction
    import logging
    import time
    from .services.tag_service import generate_tags_for_video
    logger = logging.getLogger(__name__)
    
    start_time = time.time()
    try:
        with transaction.atomic():
            videos = Video.objects.all()
            count = 0
            failed = 0
            
            for video in videos:
                try:
                    # Удаляем текущие теги перед генерацией новых
                    video.tags.clear()
                    # Генерируем новые теги
                    tags = generate_tags_for_video(video)
                    if tags:
                        count += 1
                    else:
                        failed += 1
                except Exception as e:
                    logger.error(f"Failed to generate tags for video {video.id}: {str(e)}")
                    failed += 1
            
            execution_time = time.time() - start_time
            messages.success(request, 
                f"Теги сгенерированы для {count} видео (не удалось: {failed}) за {execution_time:.2f} секунд")
    except Exception as e:
        logger.error(f"Error during tag regeneration: {str(e)}")
        messages.error(request, f"Ошибка при генерации тегов: {str(e)}")
    
    return redirect('core:home')

def random_video(request):
    """Redirect to a random video"""
    random_video = Video.objects.order_by('?').first()
    if random_video:
        return redirect('core:video_detail', pk=random_video.pk)
    return redirect('core:home')

def get_etag(request, pk):
    """Generate ETag for video caching"""
    video = get_object_or_404(Video, pk=pk)
    return f'video-{pk}-{os.path.getmtime(video.file.path)}'

def get_last_modified(request, pk):
    """Get last modified time for video"""
    video = get_object_or_404(Video, pk=pk)
    timestamp = os.path.getmtime(video.file.path)
    return timezone.make_aware(datetime.fromtimestamp(timestamp))

@login_required
def ratings(request):
    # Get page numbers for each block
    top_page = request.GET.get('top_page', 1)
    bottom_page = request.GET.get('bottom_page', 1)
    users_page = request.GET.get('users_page', 1)
    channels_page = request.GET.get('channels_page', 1)
    views_page = request.GET.get('views_page', 1)
    active_page = request.GET.get('active_page', 1)

    # Querysets
    top_videos_qs = Video.objects.order_by('-absolute_rating')
    bottom_videos_qs = Video.objects.order_by('absolute_rating')
    top_users_qs = UserProfile.objects.order_by('-karma')
    top_channels_qs = list(Channel.objects.filter(is_youtube_channel=True).order_by('-youtube_subscribers'))
    top_channels_qs.extend(list(Channel.objects.filter(is_youtube_channel=False).annotate(
        subscriber_count=Count('subscribers')
    ).order_by('-subscriber_count')))
    top_channels_qs.sort(key=lambda x: x.youtube_subscribers if x.is_youtube_channel else x.subscribers.count(), reverse=True)
    top_views_qs = Video.objects.annotate(
        total_views=F('views') + F('youtube_views')
    ).order_by('-total_views')
    most_active_users_qs = User.objects.annotate(
        comment_count=Count('comments')
    ).filter(comment_count__gt=0).order_by('-comment_count')

    # Paginators
    top_videos_p = Paginator(top_videos_qs, 10)
    bottom_videos_p = Paginator(bottom_videos_qs, 10)
    top_users_p = Paginator(top_users_qs, 10)
    top_channels_p = Paginator(top_channels_qs, 10)
    top_views_p = Paginator(top_views_qs, 10)
    most_active_users_p = Paginator(most_active_users_qs, 10)

    try:
        top_videos = top_videos_p.page(top_page)
    except (PageNotAnInteger, EmptyPage):
        top_videos = top_videos_p.page(1)
    try:
        bottom_videos = bottom_videos_p.page(bottom_page)
    except (PageNotAnInteger, EmptyPage):
        bottom_videos = bottom_videos_p.page(1)
    try:
        top_users = top_users_p.page(users_page)
    except (PageNotAnInteger, EmptyPage):
        top_users = top_users_p.page(1)
    try:
        top_channels = top_channels_p.page(channels_page)
    except (PageNotAnInteger, EmptyPage):
        top_channels = top_channels_p.page(1)
    try:
        top_views = top_views_p.page(views_page)
    except (PageNotAnInteger, EmptyPage):
        top_views = top_views_p.page(1)
    try:
        most_active_users = most_active_users_p.page(active_page)
    except (PageNotAnInteger, EmptyPage):
        most_active_users = most_active_users_p.page(1)

    return render(request, 'core/ratings.html', {
        'top_videos': top_videos,
        'bottom_videos': bottom_videos,
        'top_users': top_users,
        'top_channels': top_channels,
        'top_views': top_views,
        'most_active_users': most_active_users,
        'top_videos_p': top_videos_p,
        'bottom_videos_p': bottom_videos_p,
        'top_users_p': top_users_p,
        'top_channels_p': top_channels_p,
        'top_views_p': top_views_p,
        'most_active_users_p': most_active_users_p,
    })

def search(request):
    """Search videos by title, description, or channel name"""
    query = request.GET.get('q', '')
    results = Video.objects.none()  # Default to an empty queryset
    # channels_results = Channel.objects.none() # If we want to add channel search back

    if query:
        try:
            # Search for videos by title or description
            results = Video.objects.filter(
                Q(title__icontains=query) | 
                Q(description__icontains=query)
            ).distinct()
            
            # Example: Search for channels by name (optional, can be added to context if template handles it)
            # channels_results = Channel.objects.filter(name__icontains=query).distinct()

        except FieldError as e:
            logger.error(f"Search query for videos failed: {e} for query: '{query}'")
            messages.error(request, f"Произошла ошибка при поиске видео. Пожалуйста, попробуйте другой запрос.")
            # results will remain Video.objects.none()
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"Unexpected error during video search: {e} for query: '{query}'")
            messages.error(request, "Произошла непредвиденная ошибка при поиске.")
            # results will remain Video.objects.none()
            
    context = {
        'query': query,
        'results': results,
        # 'channels': channels_results, # If you want to pass channels to the template
    }
    return render(request, 'core/search_results.html', context)

@login_required
def all_channels(request):
    """View all channels including YouTube channels"""
    # Get all channels, both user-created and YouTube-imported
    channels = Channel.objects.all().order_by('-youtube_subscribers', '-subscribers')
    
    # Mark which channels belong to the current user
    for channel in channels:
        channel.is_owner = (channel.owner == request.user)
        channel.is_subscribed = channel.subscribers.filter(id=request.user.id).exists()
    
    return render(request, 'core/all_channels.html', {
        'channels': channels
    })

# Added advertisement management views
@login_required
def ad_manager(request):
    if request.method == 'POST':
        form = AdForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, 'Реклама успешно добавлена.')
            return redirect('core:ad_manager')
    else:
        form = AdForm()
    ads = Ad.objects.all()
    return render(request, 'core/ad_manager.html', {'form': form, 'ads': ads})

@login_required
def ad_edit(request, ad_id):
    ad = get_object_or_404(Ad, pk=ad_id)
    if request.method == 'POST':
        form = AdForm(request.POST, request.FILES, instance=ad)
        if form.is_valid():
            form.save()
            messages.success(request, 'Реклама обновлена.')
            return redirect('core:ad_manager')
    else:
        form = AdForm(instance=ad)
    return render(request, 'core/ad_edit.html', {'form': form, 'ad': ad})

@login_required
def ad_delete(request, ad_id):
    ad = get_object_or_404(Ad, pk=ad_id)
    ad.delete()
    messages.success(request, 'Реклама удалена.')
    return redirect('core:ad_manager')

@login_required
def ad_detail(request, ad_id):
    ad = get_object_or_404(Ad, pk=ad_id)
    return render(request, 'core/ad_detail.html', {'ad': ad})

@require_GET
def api_random_ad(request):
    from .models import Ad
    import random
    ads = list(Ad.objects.filter(active=True))
    if not ads:
        return JsonResponse({'url': None})
    ad = random.choice(ads)
    return JsonResponse({'url': ad.video_file.url})

def generate_tags(request, video_id):
    """Generate tags for video based on title and description"""
    video = get_object_or_404(Video, pk=video_id)
    
    try:
        # Генерируем теги
        generated_tags = generate_tags_for_video(video)
        if generated_tags:
            tag_names = ', '.join([tag.name for tag in generated_tags])
            messages.success(request, f'Теги успешно сгенерированы: {tag_names}')
        else:
            messages.warning(request, 'Не удалось сгенерировать теги')
    except Exception as e:
        logging.error(f"Error generating tags: {str(e)}")
        messages.error(request, 'Произошла ошибка при генерации тегов')
    
    return redirect('core:video_detail', pk=video_id)



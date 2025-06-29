from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.generic import ListView
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .forms import VideoSearchForm, VideoImportForm, ChannelImportForm
from core.models import Video, Channel
from .services import YouTubeService
from core.services.video_analysis import analyze_video
from core.services.tag_service import generate_tags_for_video
import logging

logger = logging.getLogger(__name__)


def import_video(request):
    if request.method == 'POST':
        form = VideoImportForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['video_url']
            service = YouTubeService()
            video_id = service.extract_video_id(url)
            
            if video_id:
                logger.info(f"Importing YouTube video ID: {video_id}")
                video_data = service.get_video_data(video_id)
                
                if video_data:
                    # Сохраняем видео в базе данных
                    video, created = Video.objects.update_or_create(
                        youtube_id=video_id,
                        defaults=video_data
                    )
                    action_word = "imported" if created else "updated"
                    
                    # 1. Анализируем видео
                    logger.info(f"Running analysis for video ID: {video.id}")
                    try:
                        analysis_results = analyze_video(video)
                        analysis_status = "successfully"
                    except Exception as e:
                        logger.error(f"Error analyzing video: {str(e)}")
                        analysis_status = "with errors"
                    
                    # 2. Генерируем теги для видео (вызов уже включен в analyze_video)
                    # Но дополнительно логируем результат
                    tags_count = video.tags.count()
                    
                    # 3. Рейтинг уже пересчитан в analyze_video, получаем значение
                    rating = video.absolute_rating
                    
                    # Формируем сообщение об успехе с дополнительной информацией
                    messages.success(
                        request,
                        f'Video {action_word} {analysis_status}! ' 
                        f'Rating: {rating:.1f}, Tags: {tags_count}'
                    )
                    return redirect('video_list')
                else:
                    messages.error(request, 'Could not fetch video data.')
            else:
                messages.error(request, 'Invalid YouTube URL.')
    else:
        form = VideoImportForm()
    
    return render(request, 'youtube_api/import_video.html', {'form': form})


def import_channel(request):
    if request.method == 'POST':
        form = ChannelImportForm(request.POST)
        if form.is_valid():
            url = form.cleaned_data['channel_url']
            service = YouTubeService()
            channel_id = service.extract_channel_id(url)
            
            if not request.user.is_authenticated:
                messages.error(request, 'You must be logged in to import channels.')
                return redirect('login')
            
            if channel_id:
                logger.info(f"Extracting channel data for ID: {channel_id}")
                channel_data = service.get_channel_data(channel_id)
                if channel_data:
                    # Import channel with authenticated user
                    channel, error = service.import_channel(channel_id, request.user)
                    
                    if error:
                        messages.error(request, error)
                        return redirect('video_list')
                    
                    # Анализируем все импортированные видео канала
                    imported_videos = Video.objects.filter(channel=channel)
                    videos_count = imported_videos.count()
                    
                    logger.info(f"Starting analysis of {videos_count} videos from channel {channel.name}")
                    analyzed_count = 0
                    avg_rating = 0
                    
                    # Используем async-задачу или прямой вызов в зависимости от количества видео
                    if videos_count > 10:
                        # Для большого количества видео показываем уведомление о фоновой задаче
                        messages.success(
                            request,
                            f'Successfully imported channel {channel.name} with {videos_count} videos! '
                            f'Videos will be analyzed in the background.'
                        )
                        # TODO: Здесь можно добавить вызов Celery задачи для анализа множества видео
                        # analyze_channel_videos.delay(channel.id)
                        
                        # Пока запускаем синхронный анализ для первых 5 видео
                        for video in imported_videos[:5]:
                            try:
                                analyze_video(video)
                                analyzed_count += 1
                                avg_rating += video.absolute_rating
                            except Exception as e:
                                logger.error(f"Error analyzing video {video.id}: {str(e)}")
                    else:
                        # Для небольшого количества видео выполняем анализ синхронно
                        for video in imported_videos:
                            try:
                                analyze_video(video)
                                analyzed_count += 1
                                avg_rating += video.absolute_rating
                            except Exception as e:
                                logger.error(f"Error analyzing video {video.id}: {str(e)}")
                        
                        # Вычисляем средний рейтинг
                        if analyzed_count > 0:
                            avg_rating /= analyzed_count
                        
                        messages.success(
                            request,
                            f'Successfully imported channel {channel.name} with {videos_count} videos! '
                            f'Analyzed {analyzed_count} videos, avg rating: {avg_rating:.1f}'
                        )
                    
                    return redirect('video_list')
                else:
                    messages.error(request, 'Could not fetch channel data.')
            else:
                messages.error(request, 'Invalid channel URL.')
    else:
        form = ChannelImportForm()
    
    return render(request, 'youtube_api/import_channel.html', {'form': form})



@login_required
def recalculate_all_ratings(request):
    """Recalculate ratings for all videos"""
    if not request.user.is_staff:
        print("\n[RECALC] Отказано в доступе: пользователь не является staff")
        messages.error(request, 'Only staff members can recalculate ratings.')
        return redirect('video_list')
    
    print("\n[RECALC] Пользователь авторизован, начинаем пересчет...")    
    try:
        videos = Video.objects.all()
        total = videos.count()
        print(f"[RECALC] Найдено {total} видео для пересчета")
        
        for i, video in enumerate(videos, 1):
            print(f"\n[RECALC] [{i}/{total}] Обработка видео {video.id}: {video.title}")
            rating = video.recalculate_ratings()
            print(f"[RECALC] Результат: Рейтинг = {rating:.3f}")
        
        print("\n[RECALC] Пересчет рейтингов успешно завершен\n")
        messages.success(request, f'Successfully recalculated ratings for {total} videos.')
    except Exception as e:
        print(f"\n[RECALC] ОШИБКА при пересчете рейтингов: {str(e)}\n")
        messages.error(request, f'Error recalculating ratings: {str(e)}')
    
    return redirect('video_list')


class VideoListView(ListView):
    model = Video
    template_name = 'youtube_api/video_list.html'
    context_object_name = 'videos'
    paginate_by = 12

    def get_queryset(self):
        queryset = Video.objects.all()
        form = VideoSearchForm(self.request.GET)
        
        if form.is_valid():
            if form.cleaned_data.get('query'):
                query = form.cleaned_data['query']
                queryset = queryset.filter(
                    Q(title__icontains=query) |
                    Q(description__icontains=query)
                )
            
            if form.cleaned_data.get('min_views'):
                queryset = queryset.filter(views__gte=form.cleaned_data['min_views'])
            
            if form.cleaned_data.get('min_likes'):
                queryset = queryset.filter(likes__gte=form.cleaned_data['min_likes'])
            
            if form.cleaned_data.get('upload_date_from'):
                queryset = queryset.filter(upload_date__gte=form.cleaned_data['upload_date_from'])
            
            if form.cleaned_data.get('upload_date_to'):
                queryset = queryset.filter(upload_date__lte=form.cleaned_data['upload_date_to'])
            
            # Add sorting options
            sort_by = form.cleaned_data.get('sort_by', '-upload_date')
            if sort_by == 'antitop':
                queryset = queryset.order_by('-antitop_rating')
            else:
                queryset = queryset.order_by(sort_by)
        
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search_form'] = VideoSearchForm(self.request.GET)
        context['show_antitop'] = True  # Flag to show antitop rating in template
        return context

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Video, Comment, VideoVote
from django.conf import settings
from .sentiment import analyze_sentiment
import json

def video_detail(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    video.views += 1
    video.save()
    
    # Get user's vote if authenticated
    user_vote = None
    if request.user.is_authenticated:
        try:
            vote = VideoVote.objects.get(user=request.user, video=video)
            user_vote = vote.vote_type
        except VideoVote.DoesNotExist:
            pass
    
    # Get comments with pagination
    comments = Comment.objects.filter(video=video).order_by('-created_at')
    paginator = Paginator(comments, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get recommended videos (videos from the same channel and similar tags)
    recommended_videos = Video.objects.filter(
        Q(channel=video.channel) | Q(tags__in=video.tags.all())
    ).exclude(id=video.id).distinct()[:10]
    
    context = {
        'video': video,
        'user_vote': user_vote,
        'comments': page_obj,
        'recommended_videos': recommended_videos,
    }
    return render(request, 'video_detail.html', context)

@login_required
@require_POST
def add_comment(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    text = request.POST.get('text', '').strip()
    
    if not text:
        return JsonResponse({'success': False, 'error': 'Комментарий не может быть пустым'})
    
    # Analyze sentiment
    sentiment = analyze_sentiment(text)
    
    comment = Comment.objects.create(
        video=video,
        user=request.user,
        text=text,
        sentiment=sentiment
    )
    
    return JsonResponse({
        'success': True,
        'comment': {
            'text': comment.text,
            'username': comment.user.username,
            'user_id': comment.user.id,
            'avatar_url': comment.user.profile.avatar.url if hasattr(comment.user, 'profile') else '/static/images/default-avatar.png',
            'sentiment': sentiment
        }
    })

@login_required
@require_POST
def vote_video(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    action = request.POST.get('action')
    
    if action not in ['like', 'dislike']:
        return JsonResponse({'success': False, 'error': 'Неверное действие'})
    
    try:
        vote = VideoVote.objects.get(user=request.user, video=video)
        if vote.vote_type == action:
            vote.delete()
        else:
            vote.vote_type = action
            vote.save()
    except VideoVote.DoesNotExist:
        VideoVote.objects.create(user=request.user, video=video, vote_type=action)
    
    upvotes = VideoVote.objects.filter(video=video, vote_type='like').count()
    downvotes = VideoVote.objects.filter(video=video, vote_type='dislike').count()
    
    try:
        user_vote = VideoVote.objects.get(user=request.user, video=video).vote_type
    except VideoVote.DoesNotExist:
        user_vote = None
    
    return JsonResponse({
        'success': True,
        'upvotes': upvotes,
        'downvotes': downvotes,
        'user_vote': user_vote
    }) 
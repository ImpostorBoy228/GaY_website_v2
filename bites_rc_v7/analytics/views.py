from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from .models import UserVideoView, VideoSeek, UserChannelView
from core.models import Like, Dislike
from .serializers import (
    UserVideoViewSerializer, VideoSeekSerializer, UserChannelViewSerializer
)
from core.models import Video, Channel

import json
import logging
logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_video_view(request):
    """
    Track when a user starts viewing a video
    """
    try:
        video_id = request.data.get('video_id')
        if not video_id:
            return Response({'error': 'video_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        video = get_object_or_404(Video, pk=video_id)
        
        # Check if there's an active view and end it
        active_views = UserVideoView.objects.filter(
            user=request.user, 
            video=video,
            is_active=True
        )
        
        if active_views.exists():
            # Already tracking this video view
            return Response({'success': True, 'message': 'Already tracking this view'}, 
                            status=status.HTTP_200_OK)
        
        # Create a new view record
        view = UserVideoView(
            user=request.user,
            video=video,
            is_active=True
        )
        view.save()
        
        serializer = UserVideoViewSerializer(view)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error tracking video view: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_video_view(request):
    """
    Track when a user stops viewing a video and update duration
    """
    try:
        video_id = request.data.get('video_id')
        duration = request.data.get('duration')
        
        if not video_id:
            return Response({'error': 'video_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        if not duration:
            return Response({'error': 'duration is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        video = get_object_or_404(Video, pk=video_id)
        
        # Find the active view and end it
        active_view = UserVideoView.objects.filter(
            user=request.user, 
            video=video,
            is_active=True
        ).first()
        
        if not active_view:
            return Response({'error': 'No active view found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Update the view duration and set to inactive
        active_view.duration = int(duration)
        active_view.is_active = False
        active_view.save()
        
        serializer = UserVideoViewSerializer(active_view)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error ending video view: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Функция track_like удалена, так как лайки/дизлайки записываются напрямую через модели core.Like и core.Dislike


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_seek(request):
    """
    Track when a user seeks in a video
    """
    try:
        video_id = request.data.get('video_id')
        from_position = request.data.get('from_position')
        to_position = request.data.get('to_position')
        
        if not all([video_id, from_position, to_position]):
            return Response(
                {'error': 'video_id, from_position, and to_position are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        video = get_object_or_404(Video, pk=video_id)
        
        # Check if there's a recent seek within the last 3 seconds that should be merged
        recent_seek = VideoSeek.objects.filter(
            user=request.user,
            video=video,
            timestamp__gte=timezone.now() - timezone.timedelta(seconds=3)
        ).order_by('-timestamp').first()
        
        # Объединяем перемотки, если они происходят в течение 3 секунд
        # Это предотвращает создание множества записей при перетаскивании ползунка
        if recent_seek and (timezone.now() - recent_seek.timestamp).total_seconds() < 3:
            recent_seek.to_position = to_position
            recent_seek.save()
            serializer = VideoSeekSerializer(recent_seek)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
        # Create a new seek record
        seek = VideoSeek(
            user=request.user,
            video=video,
            from_position=from_position,
            to_position=to_position
        )
        seek.save()
        
        serializer = VideoSeekSerializer(seek)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error tracking seek: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def track_channel_view(request):
    """
    Track when a user views a channel
    """
    try:
        channel_id = request.data.get('channel_id')
        if not channel_id:
            return Response({'error': 'channel_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        channel = get_object_or_404(Channel, pk=channel_id)
        
        # Check if there's an active view and end it
        active_views = UserChannelView.objects.filter(
            user=request.user, 
            channel=channel,
            is_active=True
        )
        
        if active_views.exists():
            # Already tracking this channel view
            return Response({'success': True, 'message': 'Already tracking this channel view'}, 
                            status=status.HTTP_200_OK)
        
        # Create a new view record
        view = UserChannelView(
            user=request.user,
            channel=channel,
            is_active=True
        )
        view.save()
        
        serializer = UserChannelViewSerializer(view)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error tracking channel view: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def end_channel_view(request):
    """
    Track when a user stops viewing a channel and update duration
    """
    try:
        channel_id = request.data.get('channel_id')
        duration = request.data.get('duration')
        
        if not channel_id:
            return Response({'error': 'channel_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        if not duration:
            return Response({'error': 'duration is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        channel = get_object_or_404(Channel, pk=channel_id)
        
        # Find the active view and end it
        active_view = UserChannelView.objects.filter(
            user=request.user, 
            channel=channel,
            is_active=True
        ).first()
        
        if not active_view:
            return Response({'error': 'No active channel view found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Update the view duration and set to inactive
        active_view.duration = int(duration)
        active_view.is_active = False
        active_view.save()
        
        serializer = UserChannelViewSerializer(active_view)
        return Response(serializer.data, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error ending channel view: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

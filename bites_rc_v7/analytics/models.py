from django.db import models
from django.contrib.auth.models import User
from core.models import Video, Channel
import logging

logger = logging.getLogger(__name__)

class UserVideoView(models.Model):
    """Records when a user views a video"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='video_views')
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='user_views')
    timestamp = models.DateTimeField(auto_now_add=True)
    duration = models.PositiveIntegerField(default=0, help_text='Time spent watching in seconds')
    is_active = models.BooleanField(default=True, help_text='Whether the view is currently active')

    class Meta:
        verbose_name = 'Video View'
        verbose_name_plural = 'Video Views'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user.username} viewed {self.video.title} for {self.duration}s'

# Модель UserLike удалена, так как она дублирует существующие модели Like и Dislike в core

class VideoSeek(models.Model):
    """Records when a user seeks in a video"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='video_seeks')
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='user_seeks')
    timestamp = models.DateTimeField(auto_now_add=True)
    from_position = models.PositiveIntegerField(help_text='Seek from position in seconds')
    to_position = models.PositiveIntegerField(help_text='Seek to position in seconds')

    class Meta:
        verbose_name = 'Video Seek'
        verbose_name_plural = 'Video Seeks'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user.username} seeked {self.video.title} from {self.from_position}s to {self.to_position}s'

class UserChannelView(models.Model):
    """Records when a user views a channel"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channel_views')
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='user_views')
    timestamp = models.DateTimeField(auto_now_add=True)
    duration = models.PositiveIntegerField(default=0, help_text='Time spent on channel in seconds')
    is_active = models.BooleanField(default=True, help_text='Whether the view is currently active')

    class Meta:
        verbose_name = 'Channel View'
        verbose_name_plural = 'Channel Views'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user.username} viewed {self.channel.name} for {self.duration}s'

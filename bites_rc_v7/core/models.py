from django.db import models
from django.contrib.auth.models import User
from django.core.files.storage import FileSystemStorage
import math
from django.utils import timezone
from django.db.models import Avg
import os
import re
from urllib.parse import unquote
from django.utils.text import slugify
import logging

# Configure logger
logger = logging.getLogger(__name__)

class NoLimitFilenameFileSystemStorage(FileSystemStorage):
    """Custom storage class that doesn't limit filename length and handles special characters"""
    def get_valid_name(self, name):
        """
        Return a filename with special characters replaced with underscores
        """
        # Decode URL-encoded characters
        name = unquote(name)
        # Replace special characters with underscores
        name = re.sub(r'[&\s\-\(\)]', '_', name)
        # Remove any other non-alphanumeric characters except dots and underscores
        name = re.sub(r'[^\w\.\-]', '', name)
        return name

    def get_available_name(self, name, max_length=None):
        """
        Returns a filename that's free on the target storage system.
        """
        name = self.get_valid_name(name)
        dir_name, file_name = os.path.split(name)
        file_root, file_ext = os.path.splitext(file_name)
        
        counter = 0
        while self.exists(name):
            counter += 1
            name = os.path.join(dir_name, f"{file_root}_{counter}{file_ext}")
        return name

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def save(self, *args, **kwargs):
        # Автоматически создаем slug при сохранении
        if not self.slug:
            self.slug = slugify(self.name)
            
            # Проверяем уникальность slug
            original_slug = self.slug
            counter = 1
            while Tag.objects.filter(slug=self.slug).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
                
        super().save(*args, **kwargs)
    
    def __str__(self):
        return self.name


class Channel(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channels', null=True, blank=True)
    imported_by = models.ForeignKey(User, on_delete=models.SET_NULL, related_name='imported_channels', null=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    avatar = models.ImageField(upload_to='channel_avatars/', blank=True, null=True)
    banner = models.ImageField(upload_to='channel_banners/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    subscribers = models.ManyToManyField(User, related_name='subscriptions', blank=True)
    
    # YouTube-specific fields
    youtube_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    youtube_url = models.URLField(max_length=255, blank=True, null=True)
    youtube_subscribers = models.PositiveIntegerField(default=0)
    youtube_avatar_url = models.URLField(max_length=255, blank=True, null=True)
    youtube_banner_url = models.URLField(max_length=255, blank=True, null=True)
    is_youtube_channel = models.BooleanField(default=False)

    def __str__(self):
        return self.name
    
    def subscriber_count(self):
        if self.is_youtube_channel:
            return self.youtube_subscribers
        return self.subscribers.count()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='user_avatars/', blank=True, null=True)
    bio = models.TextField(blank=True)
    karma = models.FloatField(default=0)
    karma_stability = models.FloatField(default=0.5)  # 0-1 value for H_u
    created_at = models.DateTimeField(auto_now_add=True)

    # Casino fields: user balance and debt
    casino_balance = models.DecimalField(max_digits=12, decimal_places=2, default=1000.00)
    casino_debt = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    debt_last_update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username
    
    def calculate_karma(self):
        # Fetch data needed for karma calculation
        uploaded_videos = self.user.uploaded_videos.all()
        total_likes = sum(video.likes.count() for video in uploaded_videos)
        comments = self.user.comments.all()
        comment_sentiments = [c.sentiment for c in comments]
        likes_given = self.user.liked_videos.count()
        videos_uploaded = uploaded_videos.count()
        
        # Get subscriber count
        try:
            subscribers = self.user.channels.first().subscribers.count() if self.user.channels.first() else 0
        except:
            subscribers = 0
        
        # Assume unsubscribers as 0 for now since it's not tracked
        unsubscribers = 0
        
        # Get sentiments for comments on user's videos
        comment_sentiments_on_videos = []
        for video in uploaded_videos:
            video_comments = video.comments.all()
            comment_sentiments_on_videos.extend([c.sentiment for c in video_comments])
        
        # Calculate averages
        avg_sentiment_comments = sum(comment_sentiments) / (len(comment_sentiments) or 1)
        avg_sentiment_video = sum(comment_sentiments_on_videos) / (len(comment_sentiments_on_videos) or 1)
        
        # Calculate karma components
        karma = 0
        karma += likes_given * 0.5
        karma += len(comments) * avg_sentiment_comments * 1.2
        karma += videos_uploaded * 10
        karma += (subscribers + unsubscribers) * 2
        karma += total_likes * 0.8
        karma += avg_sentiment_video * 50
        
        # Apply infernal multiplier
        karma *= 66.6
        
        self.karma = round(karma, 2)
        self.save()
        
        return self.karma

class Video(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='videos/', blank=True, null=True)
    tags = models.ManyToManyField(Tag, related_name='videos', blank=True)
    thumbnail = models.ImageField(upload_to='thumbnails/', blank=True, null=True)
    upload_date = models.DateTimeField(auto_now_add=True)
    views = models.PositiveIntegerField(default=0)
    duration = models.PositiveIntegerField(default=0)  # Duration in seconds
    
    # Video can be associated with a channel
    channel = models.ForeignKey(Channel, on_delete=models.SET_NULL, null=True, blank=True, related_name='videos')
    
    # User who uploaded the video (will be null for imported videos)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='uploaded_videos')
    
    # User who imported the video (only for YouTube imports)
    imported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='imported_videos')
    
    # YouTube specific fields
    is_youtube = models.BooleanField(default=False)
    youtube_id = models.CharField(max_length=20, blank=True, null=True, unique=True)
    youtube_views = models.PositiveIntegerField(default=0)
    youtube_likes = models.PositiveIntegerField(default=0)
    youtube_dislikes = models.PositiveIntegerField(default=0)
    youtube_thumbnail_url = models.URLField(blank=True, null=True)
    is_downloaded = models.BooleanField(default=False)
    
    # Rating calculations
    absolute_rating = models.FloatField(default=0)
    analysis = models.JSONField(blank=True, null=True, default=dict)  # JSON characteristics from video analysis

    def __str__(self):
        return self.title

    @property
    def likes_count(self):
        if self.is_youtube:
            print(f"Video {self.pk} is YouTube video, returning youtube_likes plus user likes: {self.youtube_likes + self.likes.count()}")
            return self.youtube_likes + self.likes.count()
        else:
            count = self.likes.count()
            print(f"Video {self.pk} is local video, returning likes count: {count}")
            return count

    def get_dislikes_count(self):
        """Get total dislikes count - only platform dislikes for non-YouTube videos"""
        if self.is_youtube:
            print(f"Video {self.pk} is YouTube video, returning 0 dislikes")
            return 0  # Не показываем дизлайки для YouTube видео
        count = self.dislikes.count()
        print(f"Video {self.pk} is local video, returning dislikes count: {count}")
        return count

    def recalculate_ratings(self):
        """Recalculate ratings"""
        self.calculate_absolute_rating()
        return self.absolute_rating

    def save(self, *args, **kwargs):
        # Если это YouTube видео, используем счетчик просмотров с YouTube
        if self.is_youtube and not self.is_downloaded:
            self.views = self.youtube_views
            
        # Strip storage-added random suffix from thumbnail filenames
        if self.thumbnail:
            basename = os.path.basename(self.thumbnail.name)
            m = re.match(r'(.+_thumb)_[A-Za-z0-9]+(\.[^.]+)$', basename)
            if m:
                new_basename = m.group(1) + m.group(2)
                self.thumbnail.name = f"thumbnails/{new_basename}"
        
        # Очистка пути к миниатюре, если необходимо
        if self.thumbnail:
            current_path = str(self.thumbnail)
            if 'thumbnails' in current_path and not current_path.startswith('thumbnails/'):
                self.thumbnail.name = f"thumbnails/{os.path.basename(current_path)}"
        
        super().save(*args, **kwargs)

    def calculate_absolute_rating(self):
        """
        Calculates the absolute rating for the video based on multiple factors:
        - Likes count (YouTube + local)
        - Comment sentiment and count
        - Views count (YouTube + local)
        - Video duration
        - Engagement rate (likes/views ratio)
        """
        try:
            # Get likes, dislikes and views count based on video type
            if self.is_youtube:
                likes = self.youtube_likes + self.likes.count()  # Combine YouTube and local likes
                views = max(self.youtube_views, 1)  # Avoid division by zero
                dislikes = self.youtube_dislikes
            else:
                likes = self.likes.count()
                views = max(self.views, 1)  # Avoid division by zero
                dislikes = self.dislikes.count()

            # Calculate engagement metrics
            engagement_rate = likes / views if views > 0 else 0
            
            # Calculate average sentiment from comments with more weight on recent comments
            comments = list(self.comments.all())
            comments_count = len(comments)
            
            if comments_count > 0:
                # Weight comments by recency (newer comments have more weight)
                now = timezone.now()
                total_weight = 0
                weighted_sentiment = 0
                
                for comment in comments:
                    # Calculate weight based on comment age (in days)
                    age_days = (now - comment.created_at).days
                    weight = 1.0 / (1 + age_days/30)  # 30-day half-life
                    weighted_sentiment += comment.sentiment * weight
                    total_weight += weight
                
                sentiment_avg = weighted_sentiment / total_weight if total_weight > 0 else 0.5
            else:
                sentiment_avg = 0.5  # Neutral sentiment if no comments
            
            # Calculate engagement score with diminishing returns
            engagement_score = (
                math.log1p(likes) * 1.5 +  # More weight to likes
                math.log1p(comments_count) * 1.2 * sentiment_avg +  # Weighted by sentiment
                math.log1p(self.duration / 60) * 0.8  # Duration in minutes
            )
            
            # Calculate view boost with diminishing returns
            view_boost = math.log10(1 + views) * 0.8
            
            # Apply penalties (if any)
            penalty = 1.0
            if dislikes > 0:
                # Reduce penalty based on like/dislike ratio
                like_ratio = likes / (likes + dislikes) if (likes + dislikes) > 0 else 1.0
                penalty *= like_ratio
            
            # Calculate final rating with Hell Multiplier
            HELL_MULTIPLIER = 666
            rating = HELL_MULTIPLIER * engagement_score * view_boost * penalty
            
            # Apply minimum and maximum bounds
            min_rating = 1.0
            max_rating = 10000.0
            rating = max(min_rating, min(max_rating, rating))
            
            # Smooth the rating changes to avoid big jumps
            if self.absolute_rating > 0:
                # Use weighted average to smooth changes (70% old, 30% new)
                rating = (self.absolute_rating * 0.7) + (rating * 0.3)
            
            self.absolute_rating = round(rating, 3)
            self.save(update_fields=['absolute_rating'])
            
            logger.info(f"Calculated rating for video {self.id} ({self.title}): {self.absolute_rating}")
            return self.absolute_rating
            
        except Exception as e:
            logger.error(f"Error calculating rating for video {self.id}: {str(e)}", exc_info=True)
            # Return current rating if calculation fails
            return self.absolute_rating if hasattr(self, 'absolute_rating') else 0

class Like(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='liked_videos')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('video', 'user')

class Dislike(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='dislikes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='disliked_videos')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('video', 'user')

class Comment(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    sentiment = models.FloatField(default=0.5)  # 0 = negative, 0.5 = neutral, 1 = positive
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} on {self.video.title}"

class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='channel_subscriptions')
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='channel_subscribers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'channel')

    def __str__(self):
        return f"{self.user.username} -> {self.channel.name}"

# Added Ad model for advertisements
class Ad(models.Model):
    title = models.CharField(max_length=200)
    video_file = models.FileField(upload_to='ads/')
    thumbnail = models.ImageField(upload_to='ads_thumbnails/')
    frequency = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class VideoTransition(models.Model):
    from_video = models.ForeignKey(Video, related_name='transitions_from', on_delete=models.CASCADE)
    to_video = models.ForeignKey(Video, related_name='transitions_to', on_delete=models.CASCADE)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('from_video', 'to_video')
        ordering = ['-count']

    def __str__(self):
        return f'Transition from "{self.from_video.title}" to "{self.to_video.title}" - {self.count} clicks'


class VideoDownloadQueue(models.Model):
    """
    Модель для управления очередью скачивания видео.
    Обеспечивает последовательное скачивание видео.
    """
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='download_queue_item')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[
        ('queued', 'В очереди'),
        ('downloading', 'Скачивание'),
        ('completed', 'Завершено'),
        ('failed', 'Ошибка')
    ], default='queued')
    position = models.IntegerField(default=0)
    progress = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)
    
    class Meta:
        ordering = ['position', 'added_at']
        verbose_name = 'Очередь скачивания'
        verbose_name_plural = 'Очередь скачивания'
    
    def __str__(self):
        return f"Download {self.video.title} ({self.status})"

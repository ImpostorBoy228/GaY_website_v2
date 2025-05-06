from django.db import models
from django.conf import settings

class Video(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video_file = models.FileField(upload_to='videos/')
    thumbnail = models.ImageField(upload_to='thumbnails/', blank=True)
    channel = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='videos')
    views = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    duration = models.DurationField(null=True, blank=True)
    tags = models.ManyToManyField('Tag', blank=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']

class Comment(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.TextField()
    sentiment = models.FloatField(default=0.5)  # 1.0 for positive, 0.0 for negative, 0.5 for neutral
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

class VideoVote(models.Model):
    VOTE_TYPES = (
        ('like', 'Like'),
        ('dislike', 'Dislike'),
    )
    
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    vote_type = models.CharField(max_length=7, choices=VOTE_TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('video', 'user')

class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name 
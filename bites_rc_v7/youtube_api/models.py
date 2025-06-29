from django.db import models

# Create your models here.

class Channel(models.Model):
    title = models.CharField(max_length=255)
    avatar_url = models.URLField()
    banner_url = models.URLField()
    subscribers = models.IntegerField()
    youtube_id = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.title


class Video(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    upload_date = models.DateTimeField()
    views = models.IntegerField()
    likes = models.IntegerField()
    dislikes = models.IntegerField()
    duration = models.DurationField()
    thumbnail_url = models.URLField()
    youtube_id = models.CharField(max_length=255, unique=True)
    channel = models.ForeignKey(Channel, on_delete=models.CASCADE, related_name='videos')

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-upload_date']

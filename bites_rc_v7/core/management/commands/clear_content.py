from django.core.management.base import BaseCommand
from core.models import Video, Comment, Like, Dislike, Channel, Subscription
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Deletes all videos, comments, likes, dislikes, and channels from the database'

    def handle(self, *args, **options):
        # Delete all subscriptions first
        self.stdout.write('Deleting subscriptions...')
        Subscription.objects.all().delete()
        
        # Delete all likes and dislikes
        self.stdout.write('Deleting likes and dislikes...')
        Like.objects.all().delete()
        Dislike.objects.all().delete()
        
        # Delete all comments
        self.stdout.write('Deleting comments...')
        Comment.objects.all().delete()
        
        # Delete all videos and their associated files
        self.stdout.write('Deleting videos and their files...')
        videos = Video.objects.all()
        for video in videos:
            # Delete video file if it exists
            if video.file and os.path.exists(video.file.path):
                try:
                    os.remove(video.file.path)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Could not delete video file {video.file.path}: {e}'))
            
            # Delete thumbnail if it exists
            if video.thumbnail and os.path.exists(video.thumbnail.path):
                try:
                    os.remove(video.thumbnail.path)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Could not delete thumbnail {video.thumbnail.path}: {e}'))
        
        videos.delete()
        
        # Delete all channels and their associated files
        self.stdout.write('Deleting channels and their files...')
        channels = Channel.objects.all()
        for channel in channels:
            # Delete channel avatar if it exists
            if channel.avatar and os.path.exists(channel.avatar.path):
                try:
                    os.remove(channel.avatar.path)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'Could not delete channel avatar {channel.avatar.path}: {e}'))
        
        channels.delete()
        
        self.stdout.write(self.style.SUCCESS('Successfully deleted all content!')) 
import os
import shutil
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Video, Channel, Comment, Like, Dislike, VideoDownloadQueue, UserProfile
from django.db import connection
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Reset all data including videos, channels, comments, likes, and files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete all data',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING('This command will delete ALL data, including all videos, channels, comments, likes and files.')
            )
            self.stdout.write(
                self.style.WARNING('Run with --confirm to proceed with deletion.')
            )
            return

        # Удаляем все записи из базы данных
        self.stdout.write(self.style.WARNING('Deleting all database records...'))
        
        # Очистка кэша
        self.stdout.write('Clearing cache...')
        cache.clear()
        
        # Удаление всех очередей загрузки
        count = VideoDownloadQueue.objects.count()
        VideoDownloadQueue.objects.all().delete()
        self.stdout.write(f'Deleted {count} download queue items')
        
        # Удаление всех дизлайков видео
        count = Dislike.objects.count()
        Dislike.objects.all().delete()
        self.stdout.write(f'Deleted {count} video dislikes')
        
        # Удаление всех лайков видео
        count = Like.objects.count()
        Like.objects.all().delete()
        self.stdout.write(f'Deleted {count} video likes')
        
        # Удаление всех комментариев
        count = Comment.objects.count()
        Comment.objects.all().delete()
        self.stdout.write(f'Deleted {count} comments')
        
        # Сброс профилей пользователей
        count = UserProfile.objects.count()
        for profile in UserProfile.objects.all():
            profile.karma = 0
            profile.karma_stability = 0.5
            profile.casino_balance = 1000.00
            profile.casino_debt = 0.00
            profile.save()
        self.stdout.write(f'Reset {count} user profiles to default')
        
        # Удаляем все видео (после удаления связанных объектов)
        count = Video.objects.count()
        Video.objects.all().delete()
        self.stdout.write(f'Deleted {count} videos')
        
        # Удаляем все каналы
        count = Channel.objects.count()
        Channel.objects.all().delete()
        self.stdout.write(f'Deleted {count} channels')

        # Удаляем физические файлы
        self.stdout.write(self.style.WARNING('Deleting all physical files...'))
        
        # Удаление медиа-файлов (видео, превью, аватары)
        media_dirs = [
            os.path.join(settings.MEDIA_ROOT, 'videos'),
            os.path.join(settings.MEDIA_ROOT, 'thumbnails'),
            os.path.join(settings.MEDIA_ROOT, 'channel_avatars'),
            os.path.join(settings.MEDIA_ROOT, 'user_avatars')
        ]
        
        for directory in media_dirs:
            if os.path.exists(directory):
                # Удаляем содержимое директории, но оставляем саму директорию
                for filename in os.listdir(directory):
                    file_path = os.path.join(directory, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'Failed to delete {file_path}. Reason: {e}')
                        )
                self.stdout.write(f'Cleared directory: {directory}')
            else:
                os.makedirs(directory, exist_ok=True)
                self.stdout.write(f'Created empty directory: {directory}')

        self.stdout.write(self.style.SUCCESS('Successfully reset all data. The system is now clean.'))

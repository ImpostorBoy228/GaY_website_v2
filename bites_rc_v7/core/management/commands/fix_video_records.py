from django.core.management.base import BaseCommand
from core.models import Video
import os
from django.conf import settings

class Command(BaseCommand):
    help = 'Fix video thumbnail records to point to existing files'

    def handle(self, *args, **options):
        # Map of video titles to their correct thumbnail files
        thumbnail_mapping = {
            'panty ep 1': 'thumbnails/Panty__Stocking_with_Garterbelt_6suIsWX.jpg',
            'sao A WIU': 'thumbnails/Sword_Art_Online_Alicization_-_War_of_Underworld_2020.jpg',
            'panty ep 2': 'thumbnails/Panty__Stocking_with_Garterbelt_yzregjZ.jpg',
        }

        for video in Video.objects.all():
            if video.title in thumbnail_mapping:
                thumbnail_path = thumbnail_mapping[video.title]
                full_path = os.path.join(settings.MEDIA_ROOT, thumbnail_path)
                
                if os.path.exists(full_path):
                    video.thumbnail.name = thumbnail_path
                    video.save()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Updated thumbnail for video {video.id} ({video.title}) to {thumbnail_path}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Thumbnail file not found: {full_path}'
                        )
                    ) 
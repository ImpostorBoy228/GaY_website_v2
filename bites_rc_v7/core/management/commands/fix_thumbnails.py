from django.core.management.base import BaseCommand
from core.models import Video
import os
from django.conf import settings
import shutil

class Command(BaseCommand):
    help = 'Fix video thumbnail filenames'

    def handle(self, *args, **options):
        storage = Video._meta.get_field('thumbnail').storage
        
        for video in Video.objects.all():
            if video.thumbnail:
                old_name = video.thumbnail.name
                # Get the actual file path
                old_path = video.thumbnail.path
                
                if os.path.exists(old_path):
                    # Generate new name using our storage class
                    new_name = storage.get_valid_name(old_name)
                    if new_name != old_name:
                        # Calculate new path
                        new_path = os.path.join(settings.MEDIA_ROOT, 'thumbnails', os.path.basename(new_name))
                        
                        # Create directory if it doesn't exist
                        os.makedirs(os.path.dirname(new_path), exist_ok=True)
                        
                        # Copy file to new location
                        shutil.copy2(old_path, new_path)
                        
                        # Update database
                        video.thumbnail.name = f'thumbnails/{os.path.basename(new_name)}'
                        video.save()
                        
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Successfully renamed thumbnail for video {video.id} from {old_name} to {new_name}'
                            )
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Thumbnail file not found for video {video.id}: {old_path}'
                        )
                    ) 
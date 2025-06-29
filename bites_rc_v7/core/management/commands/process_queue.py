from django.core.management.base import BaseCommand
from core.services.download_queue_service import DownloadQueueService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Process the next item in the video download queue'

    def handle(self, *args, **options):
        """Process the next item in the download queue"""
        try:
            from core.models import VideoDownloadQueue
            
            # Check if there are any items in the queue
            queued_count = VideoDownloadQueue.objects.filter(status='queued').count()
            downloading_count = VideoDownloadQueue.objects.filter(status='downloading').count()
            
            self.stdout.write(f"Items in queue: {queued_count}")
            self.stdout.write(f"Currently downloading: {downloading_count}")
            
            if queued_count == 0:
                self.stdout.write(self.style.WARNING("No items in the queue to process."))
                return
                
            # Process the next item
            result = DownloadQueueService.process_next_in_queue()
            
            if result is None:
                self.stdout.write(self.style.SUCCESS("No items to process or maximum concurrent downloads reached."))
            else:
                self.stdout.write(self.style.SUCCESS("Processing next item in the queue..."))
                self.stdout.write(f"Started download for video ID: {result.get('video_id')}")
                
        except Exception as e:
            logger.error(f"Error processing queue: {str(e)}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Error processing queue: {str(e)}"))

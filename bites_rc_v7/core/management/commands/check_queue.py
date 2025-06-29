from django.core.management.base import BaseCommand
from core.services.download_queue_service import DownloadQueueService
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Check the status of the video download queue'

    def handle(self, *args, **options):
        """Display the current status of the download queue"""
        try:
            stats = DownloadQueueService.get_queue_stats()
            
            self.stdout.write(self.style.SUCCESS('=== Video Download Queue Status ==='))
            self.stdout.write(f"Total items: {stats['total']}")
            self.stdout.write(f"Queued: {stats['queued']}")
            self.stdout.write(f"Downloading: {stats['downloading']}")
            self.stdout.write(f"Completed: {stats['completed']}")
            self.stdout.write(f"Failed: {stats['failed']}")
            
            if stats['current_downloads']:
                self.stdout.write("\n=== Currently Downloading ===")
                for item in stats['current_downloads']:
                    self.stdout.write(
                        f"- {item['title']} (ID: {item['video_id']}) - "
                        f"{item['progress']}% - {item['status']}"
                    )
            
            if stats['next_in_queue']:
                self.stdout.write("\n=== Next in Queue ===")
                for item in stats['next_in_queue']:
                    self.stdout.write(
                        f"{item['position']}. {item['title']} (ID: {item['video_id']})"
                    )
            
            self.stdout.write("\nUse './manage.py process_queue' to process the next item in the queue.")
            
        except Exception as e:
            logger.error(f"Error checking queue status: {str(e)}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"Error checking queue status: {str(e)}"))

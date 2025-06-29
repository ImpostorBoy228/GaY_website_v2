from django.core.management.base import BaseCommand
from core.models import VideoDownloadQueue
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up old failed downloads from the queue'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days to keep failed downloads (default: 7)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting anything'
        )

    def handle(self, *args, **options):
        """Clean up old failed downloads from the queue"""
        days = options['days']
        dry_run = options['dry_run']
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Get failed downloads older than the cutoff date
        old_failures = VideoDownloadQueue.objects.filter(
            status='failed',
            updated_at__lt=cutoff_date
        )
        
        count = old_failures.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS(f"No failed downloads older than {days} days found."))
            return
            
        self.stdout.write(f"Found {count} failed downloads older than {days} days:")
        
        # Display the items that would be deleted
        for item in old_failures[:10]:  # Show first 10 items
            self.stdout.write(f"- {item.video.title if item.video else 'Unknown'} (ID: {item.id}, Failed: {item.updated_at})")
        
        if count > 10:
            self.stdout.write(f"... and {count - 10} more")
        
        if not dry_run:
            # Ask for confirmation
            confirm = input(f"\nAre you sure you want to delete {count} failed downloads? [y/N] ")
            if confirm.lower() != 'y':
                self.stdout.write(self.style.NOTICE("Operation cancelled."))
                return
                
            # Delete the items
            deleted_count, _ = old_failures.delete()
            self.stdout.write(self.style.SUCCESS(f"Successfully deleted {deleted_count} failed downloads."))
        else:
            self.stdout.write(self.style.NOTICE("\nThis is a dry run. No changes were made."))

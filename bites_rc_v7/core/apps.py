from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        # Import and register signals
        try:
            import core.signals  # noqa F401
            logger.info("Successfully registered core signals")
        except Exception as e:
            logger.error(f"Failed to register core signals: {str(e)}", exc_info=True)

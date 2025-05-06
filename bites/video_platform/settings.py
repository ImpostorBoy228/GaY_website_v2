import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv('SECRET_KEY')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
DOMAIN = os.getenv('DOMAIN', '')

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
if DOMAIN:
    ALLOWED_HOSTS.append(DOMAIN)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'rest_framework',
    'rest_framework_simplejwt',
    'django_celery_results',
    'channels',
    'core',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'SIGNING_KEY': os.getenv('JWT_SECRET_KEY'),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.cache.UpdateCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.cache.FetchFromCacheMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'video_platform.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'video_platform.wsgi.application'
ASGI_APPLICATION = 'video_platform.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('PG_DATABASE'),
        'USER': os.getenv('PG_USER'),
        'PASSWORD': os.getenv('PG_PASSWORD'),
        'HOST': os.getenv('PG_HOST', 'localhost'),
        'PORT': os.getenv('PG_PORT', '5432'),
    }
}

AUTH_USER_MODEL = 'core.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# Media files (Uploaded videos, thumbnails, avatars)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')  # Changed back to media directory

# Ensure necessary directories exist
os.makedirs(os.path.join(MEDIA_ROOT, 'videos'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'thumbnails'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'avatars'), exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'temp'), exist_ok=True)

# Video settings
VIDEOS_DIR = os.path.join(MEDIA_ROOT, 'videos')
THUMBNAILS_DIR = os.path.join(MEDIA_ROOT, 'thumbnails')

# Create directories if they don't exist
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)
os.makedirs(os.path.join(MEDIA_ROOT, 'scaled'), exist_ok=True)

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [('localhost', 6379)],
        },
    },
}

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = 'django-db'
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')

SECURE_SSL_REDIRECT = not DEBUG and DOMAIN != ''

# Session settings
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_COOKIE_SECURE = True  # Always use HTTPS
SESSION_COOKIE_HTTPONLY = True  # Prevent XSS
SESSION_COOKIE_SAMESITE = 'Lax'  # Prevent CSRF
SESSION_SAVE_EVERY_REQUEST = False  # Don't save on every request
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep session alive
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'  # Use cached database backend

# CSRF settings
CSRF_COOKIE_AGE = SESSION_COOKIE_AGE
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Caching
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 5 minutes default
        'OPTIONS': {
            'MAX_ENTRIES': 1000,
            'CULL_FREQUENCY': 3,
        }
    }
}

# Cache middleware settings
CACHE_MIDDLEWARE_ALIAS = 'default'
CACHE_MIDDLEWARE_SECONDS = 600
CACHE_MIDDLEWARE_KEY_PREFIX = 'video_platform'

# Настройки для оптимизации статических файлов
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'

if DEBUG:
    print(f"[DEBUG] Celery: {CELERY_BROKER_URL}")
    print(f"[DEBUG] Channels: {CHANNEL_LAYERS}")
# Video Platform

A professional Django-based video-sharing platform with Supabase integration for storage and database.

## Features
- User authentication (register, login, logout)
- Video upload and playback with adaptive streaming (HLS)
- YouTube video import (single, search, tags, channel, mass)
- Social interactions (comments, likes/dislikes, subscriptions)
- Responsive UI with Tailwind CSS and dark/light themes
- Asynchronous task processing with Celery and Redis
- REST API with JWT authentication
- Supabase Storage for videos, thumbnails, and avatars

## Prerequisites
- Python 3.9+
- Docker and Docker Compose
- Supabase account with configured buckets (`videos`, `thumbnails`, `avatars`)
- YouTube Data API v3 key
- FFmpeg installed (`apt-get install ffmpeg`)

## Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd rework_apempt_3
   ```

2. **Configure Environment**
   Ensure `.env` is correctly set with your Supabase credentials and YouTube API key. The provided `.env` should work if using the same Supabase project.

3. **Set Up Supabase**
   - Log in to your Supabase dashboard.
   - Create storage buckets: `videos`, `thumbnails`, `avatars`. Set them to public access.
   - Verify the database connection details in `.env` (`PG_HOST`, `PG_USER`, etc.).
   - Ensure the Supabase JWT secret matches your project's JWT secret.

4. **Install Dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **Apply Migrations**
   ```bash
   python manage.py migrate
   ```

6. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

7. **Run Celery for Asynchronous Tasks**
   ```bash
   celery -A video_platform.celery worker --loglevel=info
   celery -A video_platform.celery beat --loglevel=info
   ```

8. **Run with Docker**
   ```bash
   docker-compose up -d
   ```

## Deployment
- **Production**: Use a cloud provider (e.g., AWS, Heroku) with a WSGI server (Gunicorn) and an ASGI server (Daphne for Channels).
- **Supabase Storage**: Ensure `SUPABASE_SERVICE_ROLE_KEY` is used for server-side operations.
- **Scaling**: Configure Celery workers and Redis for high concurrency. Use a CDN (e.g., Cloudflare) for video delivery.

## Notes
- Replace `default-thumbnail.jpg` with an actual image file.
- Sentiment analysis is not included but can be added using `transformers` with `seara/rubert-tiny2-russian-sentiment`.
- For WebRTC or advanced HLS, integrate `aiortc` or a streaming server like Nginx-RTMP.

## Troubleshooting
- **Supabase Errors**: Verify bucket permissions and API keys.
- **YouTube API Errors**: Check quota limits and API key validity.
- **Celery Issues**: Ensure Redis is running and accessible.

For further customization, contact the developer or refer to the Django/Supabase documentation.
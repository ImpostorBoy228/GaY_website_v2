# GaY_website_v2

A new-generation video platform for Russian users without permanent access to YouTube.

## Key Features

- **Automated YouTube Uploads**: Import videos from YouTube (single, search, tags, channel, mass).
- **AI Tag Generation**: Uses transformers for semantic analysis and automatic tagging.
- **AI Commentaries Semantic Range**: Advanced comment analysis with Russian language support.
- **Karma & Video Rating**: Users can upvote/downvote videos and rate content.
- **Skins System**: Customizable video player and grid themes.
- **User Authentication**: Register, login, logout via Django-based backend or Flask in some versions.
- **Video Playback**: Adaptive streaming (HLS), REST API with JWT authentication.
- **Social Interactions**: Comments, likes/dislikes, subscriptions, and notification system.
- **Supabase Integration**: Used for storage (videos, thumbnails, avatars) and database.
- **Asynchronous Processing**: Background tasks with Celery and Redis.
- **Responsive UI**: Tailwind CSS, dark/light themes, and mobile-friendly design.
- **CDN Delivery**: Integrate with Cloudflare for scalable video streaming.

## Main Application Structure

The platform has multiple versions (Django and Flask).  
Key modules (example: Flask version):
- `app.py`: Application factory, extension setup (DB, SocketIO, JWT, login manager), schema creation, component initialization.
- `routes.py`: Core endpoints for video upload, playback, comments, ratings, thumbnail streaming, and WebRTC signaling.
- `models.py`: Database models for users, videos, comments, ratings, etc.
- `templates/`: HTML with Tailwind for UI, notification system, and navigation.
- `static/`: CSS/JS, including fixes for video player and notification scripts.

**Django version (bites_rc_v7 directory)**:
- `core/apps.py`: Django app config and signal registration.
- `core/templates/base.html`: Main UI, navigation, and notification system.
- `bites_videos/asgi.py`: ASGI config for deployment.

## Setup Instructions

1. **Clone the Repository**
   ```bash
   git clone <repository-url>
   cd bites_rc_v7
   ```

2. **Configure Environment**
   - Set up `.env` with Supabase keys and YouTube API credentials.

3. **Supabase Setup**
   - Create buckets: `videos`, `thumbnails`, `avatars` (public access).
   - Configure database secrets.

4. **Python Dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Apply DB Migrations**
   ```bash
   python manage.py migrate
   ```

6. **Run Development Server**
   ```bash
   python manage.py runserver
   ```

7. **Run Celery for Tasks**
   ```bash
   celery -A video_platform.celery worker --loglevel=info
   celery -A video_platform.celery beat --loglevel=info
   ```

8. **Docker Deployment**
   ```bash
   docker-compose up -d
   ```

## API & Endpoints (Flask Example)

- `/upload` (GET/POST): Upload videos.
- `/video/<video_id>/upvote`, `/downvote`: Video rating.
- `/add_comment/<video_id>`: Add comment.
- `/stream/<filename>`: Stream video.
- `/static/thumbnails/<filename>`: Stream thumbnail.
- `/api/video_metadata/<video_id>`: Video metadata.
- `/api/register_peer`, `/api/peers/<video_id>`, `/api/signal`: WebRTC signaling for advanced streaming.

## Advanced Features

- **Notification System**: Live notifications for authenticated users.
- **WebRTC Streaming**: Peer-to-peer video streaming support (experimental).
- **AI Sentiment Analysis**: (Optional) via HuggingFace transformers.

## Deployment

- Use Gunicorn/Daphne for production (WSGI/ASGI).
- Scale Celery workers/Redis for concurrency.
- Use CDN for video delivery.

## Troubleshooting

- **Supabase Errors**: Check bucket permissions and keys.
- **YouTube API**: Validate API key and quota.
- **Celery/Redis**: Ensure services are running.

## License

MIT

---

_Last backup: bites_rc_v7_
_All backups are different by some elements of ui/ux. older versions, in my opinion are more stable by db"s and YouTube downloading

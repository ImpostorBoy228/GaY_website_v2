import yt_dlp
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile
import os
import requests
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from .models import Video, Channel
from django.contrib.auth.models import User
import tempfile
from django.conf import settings

class YouTubeService:
    def __init__(self):
        self.api_key = settings.YOUTUBE_API_KEY
        self.session = requests.Session()
        self.session.trust_env = False
        self.base_url = 'https://www.googleapis.com/youtube/v3'

    def extract_video_id(self, url):
        if 'youtube.com/watch?v=' in url:
            return url.split('watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in url:
            return url.split('youtu.be/')[1].split('?')[0]
        elif 'youtube.com/live/' in url:
            return url.split('live/')[1].split('?')[0]
        return None

    def get_video_info(self, video_id):
        url = f'{self.base_url}/videos'
        params = {
            'key': self.api_key,
            'id': video_id,
            'part': 'snippet,statistics,contentDetails'
        }
        response = self.session.get(url, params=params)
        data = response.json()
        
        if not data.get('items'):
            return None
            
        video_data = data['items'][0]
        return video_data

    def get_channel_info(self, channel_id):
        url = f'{self.base_url}/channels'
        params = {
            'key': self.api_key,
            'id': channel_id,
            'part': 'snippet,statistics,brandingSettings'
        }
        response = self.session.get(url, params=params)
        data = response.json()
        
        if not data.get('items'):
            return None
            
        channel_data = data['items'][0]
        return channel_data

    def download_video(self, video_id, output_path):
        url = f'https://www.youtube.com/watch?v={video_id}'
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([url])
                return True
            except Exception as e:
                print(f"Error downloading video: {e}")
                return False

    def download_image(self, url, save_path):
        """Download an image from URL and save it to the specified path."""
        if not url:
            return None
            
        try:
            response = self.session.get(url, stream=True)
            if response.status_code == 200:
                with open(save_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return save_path
        except Exception as e:
            print(f"Error downloading image: {e}")
        return None

    def import_channel(self, channel_id, user):
        """Import a YouTube channel with all its details."""
        channel_data = self.get_channel_info(channel_id)
        if not channel_data:
            return None, "Could not fetch channel information"

        # Get avatar and banner URLs
        avatar_url = channel_data['snippet']['thumbnails'].get('high', {}).get('url')
        banner_url = channel_data['brandingSettings'].get('image', {}).get('bannerExternalUrl')
        
        # Create channel instance first
        channel, created = Channel.objects.get_or_create(
            youtube_id=channel_id,
            defaults={
                'name': channel_data['snippet']['title'],
                'description': channel_data['snippet']['description'],
                'owner': user,
                'is_youtube_channel': True,
                'youtube_url': f'https://www.youtube.com/channel/{channel_id}',
                'youtube_subscribers': int(channel_data['statistics'].get('subscriberCount', 0)),
                'youtube_avatar_url': avatar_url,
                'youtube_banner_url': banner_url
            }
        )

        if not created:
            # Update existing channel
            channel.name = channel_data['snippet']['title']
            channel.description = channel_data['snippet']['description']
            channel.youtube_subscribers = int(channel_data['statistics'].get('subscriberCount', 0))
            channel.youtube_avatar_url = avatar_url
            channel.youtube_banner_url = banner_url

        # Download and save avatar
        if avatar_url:
            avatar_path = os.path.join(settings.MEDIA_ROOT, 'channel_avatars', f'{channel_id}_avatar.jpg')
            if self.download_image(avatar_url, avatar_path):
                channel.avatar = f'channel_avatars/{channel_id}_avatar.jpg'

        # Download and save banner
        if banner_url:
            banner_path = os.path.join(settings.MEDIA_ROOT, 'channel_banners', f'{channel_id}_banner.jpg')
            if self.download_image(banner_url, banner_path):
                channel.banner = f'channel_banners/{channel_id}_banner.jpg'

        channel.save()
        return channel, None

    def import_video(self, url, user):
        """Import a YouTube video with all its details."""
        video_id = self.extract_video_id(url)
        if not video_id:
            return None, "Invalid YouTube URL"

        video_data = self.get_video_info(video_id)
        if not video_data:
            return None, "Could not fetch video information"

        # Import channel first
        channel_id = video_data['snippet']['channelId']
        channel, error = self.import_channel(channel_id, user)
        if error:
            return None, error

        # Get likes count (dislikes are no longer available via API)
        likes = int(video_data['statistics'].get('likeCount', 0))
        
        # Create video instance
        video = Video.objects.create(
            title=video_data['snippet']['title'],
            description=video_data['snippet']['description'],
            channel=channel,
            youtube_id=video_id,
            views=int(video_data['statistics'].get('viewCount', 0)),
            likes=likes,
            youtube_likes=likes,  # Store YouTube likes separately
            upload_date=datetime.strptime(video_data['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ'),
            duration=self.parse_duration(video_data['contentDetails']['duration']),
            youtube_thumbnail_url=video_data['snippet']['thumbnails']['high']['url'],
            is_youtube=True
        )

        # Download video file
        video_path = os.path.join(settings.MEDIA_ROOT, 'videos', f'{video_id}.mp4')
        if self.download_video(video_id, video_path):
            video.file = f'videos/{video_id}.mp4'
            video.save()
            return video, None
        else:
            video.delete()
            return None, "Failed to download video"

class YouTubeDownloader:
    def __init__(self):
        self.ydl_opts = {
            'format': 'best[ext=mp4]',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

    def download_video(self, video_obj):
        """Download a YouTube video and attach it to the Video model"""
        if not video_obj.youtube_id:
            return False

        url = f'https://www.youtube.com/watch?v={video_obj.youtube_id}'
        
        try:
            # Create a temporary directory for the download
            with tempfile.TemporaryDirectory() as temp_dir:
                self.ydl_opts['outtmpl'] = os.path.join(temp_dir, '%(id)s.%(ext)s')
                
                # Download the video
                with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    video_path = os.path.join(temp_dir, f"{info['id']}.mp4")
                    
                    # Open the downloaded file and save it to the model
                    with open(video_path, 'rb') as video_file:
                        video_obj.file.save(f"{info['id']}.mp4", File(video_file), save=False)
                    
                    # Download thumbnail if not already present
                    if not video_obj.thumbnail and video_obj.youtube_thumbnail_url:
                        response = requests.get(video_obj.youtube_thumbnail_url)
                        if response.status_code == 200:
                            img_temp = NamedTemporaryFile(delete=True)
                            img_temp.write(response.content)
                            img_temp.flush()
                            video_obj.thumbnail.save(f"{info['id']}_thumb.jpg", File(img_temp), save=False)
                    
                    video_obj.is_downloaded = True
                    video_obj.save()
                    
                    return True
                    
        except Exception as e:
            print(f"Error downloading video {video_obj.youtube_id}: {str(e)}")
            return False

    def get_video_info(self, url):
        """Get video information without downloading"""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except:
            return None 
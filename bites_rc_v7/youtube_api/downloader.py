import yt_dlp
import os
import tempfile
import requests
from django.core.files import File
from django.core.files.temp import NamedTemporaryFile
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class YouTubeDownloader:
    def __init__(self, video_id=None, output_path=None, progress_hook=None):
        self.video_id = video_id
        self.output_path = output_path
        self.progress_hook = progress_hook
        self.ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,  # Enable warnings for debugging
            'extract_flat': False,
            'progress_hooks': [self._progress_hook],
        }
        
    def _progress_hook(self, d):
        """Progress hook for yt-dlp to update download status"""
        if d['status'] == 'downloading':
            try:
                # Calculate progress percentage
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    progress = (downloaded / total) * 100
                    # Update cache with progress
                    video_id = d['info_dict'].get('id')
                    if video_id:
                        cache_key = f'video_download_status_{video_id}'
                        from django.core.cache import cache
                        cache.set(cache_key, {
                            'status': 'downloading',
                            'progress': int(progress)
                        }, timeout=3600)
                    
                    # Call external progress hook if provided
                    if self.progress_hook:
                        self.progress_hook(int(progress))
            except Exception as e:
                logger.error(f"Error updating progress: {str(e)}")

    def download(self):
        """Download method for backwards compatibility"""
        if not self.video_id:
            return None
            
        url = f'https://www.youtube.com/watch?v={self.video_id}'
        
        try:
            # Set output file path if provided
            if self.output_path:
                # Fix: Ensure output_path is a directory and create a filename inside it
                video_dir = self.output_path
                os.makedirs(video_dir, exist_ok=True)
                
                # Configure YoutubeDL with a proper output template using the directory
                output_file = os.path.join(video_dir, f"{self.video_id}.%(ext)s")
                self.ydl_opts['outtmpl'] = output_file
                
                # Add lock management to prevent duplicate downloads
                lock_file = os.path.join(video_dir, ".download_lock")
                if os.path.exists(lock_file):
                    logger.warning(f"Download already in progress for {self.video_id}, skipping duplicate task")
                    return None
                    
                try:
                    # Create lock file
                    with open(lock_file, 'w') as f:
                        f.write(f"Download started at {os.path.getctime(lock_file)}")
                    
                    # Download the video
                    with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                        logger.info(f"Downloading {url} to {video_dir}")
                        info = ydl.extract_info(url, download=True)
                        
                        # Get actual output file path (could be .mp4 or other extension)
                        output_files = [os.path.join(video_dir, f) for f in os.listdir(video_dir) 
                                     if f.startswith(self.video_id) and not f.endswith('.part') and f != '.download_lock']
                        
                        if output_files:
                            video_path = output_files[0]
                            logger.info(f"Download complete! File: {video_path}, size: {os.path.getsize(video_path)} bytes")
                            return video_path
                        else:
                            logger.error(f"Download completed but cannot find output file in {video_dir}")
                            return None
                finally:
                    # Remove lock file even if there was an error
                    try:
                        if os.path.exists(lock_file):
                            os.remove(lock_file)
                    except Exception as e:
                        logger.warning(f"Failed to remove lock file: {str(e)}")
            
            return None
                    
        except Exception as e:
            logger.error(f"Error downloading video {self.video_id}: {str(e)}")
            return None

    def download_video(self, video_obj):
        """Download a YouTube video and attach it to the Video model"""
        if not video_obj.youtube_id:
            return False

        url = f'https://www.youtube.com/watch?v={video_obj.youtube_id}'
        
        try:
            # Create videos directory in media if it doesn't exist
            videos_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
            os.makedirs(videos_dir, exist_ok=True)
            
            # Set output file path
            video_filename = f"{video_obj.youtube_id}.mp4"
            video_path = os.path.join(videos_dir, video_filename)
            
            # Configure YoutubeDL output template (using extension placeholder)
            outtmpl_template = os.path.join(videos_dir, f"{video_obj.youtube_id}.%(ext)s")
            self.ydl_opts['outtmpl'] = outtmpl_template
            
            # Download the video
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                logger.info(f"Downloading {url} to {video_path}")
                info = ydl.extract_info(url, download=True)
                
                # Verify file was downloaded
                if not os.path.exists(video_path):
                    logger.error(f"Error: Downloaded file not found at {video_path}")
                    return False
                
                logger.info(f"Download complete! File size: {os.path.getsize(video_path)} bytes")
                
                # Set proper permissions
                os.chmod(video_path, 0o644)
                
                # Attach file to model - using relative path from MEDIA_ROOT
                relative_path = os.path.join('videos', video_filename)
                video_obj.file.name = relative_path
                
                # Mark as downloaded and save
                video_obj.is_downloaded = True
                video_obj.save()
                
                # Download thumbnail if not already present
                if not video_obj.thumbnail and video_obj.youtube_thumbnail_url:
                    try:
                        response = requests.get(video_obj.youtube_thumbnail_url)
                        if response.status_code == 200:
                            # Create thumbnails directory if it doesn't exist
                            thumbnails_dir = os.path.join(settings.MEDIA_ROOT, 'thumbnails')
                            os.makedirs(thumbnails_dir, exist_ok=True)
                            
                            # Save thumbnail
                            thumbnail_filename = f"{video_obj.youtube_id}_thumb.jpg"
                            thumbnail_path = os.path.join(thumbnails_dir, thumbnail_filename)
                            
                            with open(thumbnail_path, 'wb') as f:
                                f.write(response.content)
                            
                            # Set proper permissions
                            os.chmod(thumbnail_path, 0o644)
                            
                            # Attach thumbnail to model - using relative path
                            relative_thumb_path = os.path.join('thumbnails', thumbnail_filename)
                            video_obj.thumbnail.name = relative_thumb_path
                            video_obj.save()
                    except Exception as thumb_error:
                        logger.error(f"Error downloading thumbnail: {str(thumb_error)}")
                
                return True
                    
        except Exception as e:
            logger.error(f"Error downloading video {video_obj.youtube_id}: {str(e)}")
            return False

    def get_video_info(self, url):
        """Get video information without downloading"""
        try:
            with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except Exception as e:
            logger.error(f"Error getting video info: {str(e)}")
            return None

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import time

db = SQLAlchemy()

class Video(db.Model):
    __tablename__ = 'videos'
    id = db.Column(db.String(36), primary_key=True)  # UUID or YouTube ID
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)  # Use Text for longer descriptions
    upload_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    views = db.Column(db.Integer, default=0, nullable=False)
    uploader = db.Column(db.String(100), nullable=False)  # Limit length for consistency
    duration = db.Column(db.Integer, nullable=True)  # Duration in seconds
    file_extension = db.Column(db.String(10), default='mp4', nullable=False)  # No leading dot
    thumbnail_extension = db.Column(db.String(10), default='jpg', nullable=False)  # No leading dot
    thumbnail_path = db.Column(db.String(255), nullable=True)  # Store physical path to thumbnail

    def __repr__(self):
        return f'<Video {self.id}: {self.title}>'

class User(db.Model, UserMixin):
    __tablename__ = 'users'  # Explicit table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    avatar = db.Column(db.String(255), nullable=True)  # Increased length for URLs
    user_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class DownloadRequest(db.Model):
    __tablename__ = 'download_requests'  # Plural for consistency
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    request_type = db.Column(db.String(50), nullable=False)  # e.g., 'youtube_url', 'channel'
    request_value = db.Column(db.Text, nullable=False)  # URL or channel ID
    status = db.Column(db.String(50), default='pending', nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    count = db.Column(db.Integer, default=10, nullable=False)
    min_views = db.Column(db.Integer, default=0, nullable=False)
    min_duration = db.Column(db.Integer, default=0, nullable=False)
    max_duration = db.Column(db.Integer, default=3600, nullable=False)
    video_count = db.Column(db.Integer, default=0, nullable=False)
    estimated_time = db.Column(db.Integer, default=0, nullable=False)
    downloaded_count = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self):
        return f'<DownloadRequest {self.id}: {self.request_type}>'

class VideoCounter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_id = db.Column(db.Integer, nullable=False, default=-1)  # Начинаем с -1, чтобы первый ID был id_0

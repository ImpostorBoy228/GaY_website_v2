from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from extensions import db

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    avatar = db.Column(db.String(255))

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class Video(db.Model):
    __tablename__ = 'videos'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.String(50), primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    views = db.Column(db.Integer, default=0)
    uploader = db.Column(db.String(80), nullable=False)
    duration = db.Column(db.Float)
    file_extension = db.Column(db.String(10))
    thumbnail_extension = db.Column(db.String(10))

class Comment(db.Model):
    __tablename__ = 'comments'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), db.ForeignKey('app.videos.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sentiment = db.Column(db.String(20))

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)
    subscriber_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    channel_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))

class DownloadRequest(db.Model):
    __tablename__ = 'download_requests'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    request_type = db.Column(db.String(50))
    request_value = db.Column(db.Text)
    count = db.Column(db.Integer)
    min_views = db.Column(db.Integer)
    min_duration = db.Column(db.Integer)
    max_duration = db.Column(db.Integer)
    video_count = db.Column(db.Integer)
    estimated_time = db.Column(db.Float)
    status = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    downloaded_count = db.Column(db.Integer)

class VideoCounter(db.Model):
    __tablename__ = 'video_counters'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.String(50), db.ForeignKey('app.videos.id'))
    views = db.Column(db.Integer, default=0)

class VideoVote(db.Model):
    __tablename__ = 'video_votes'
    __table_args__ = {'schema': 'app'}

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('app.users.id'))
    video_id = db.Column(db.String(50), db.ForeignKey('app.videos.id'))
    action = db.Column(db.String(10))
from rest_framework import serializers
from .models import UserVideoView, VideoSeek, UserChannelView

class UserVideoViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserVideoView
        fields = ['id', 'video', 'timestamp', 'duration', 'is_active']
        read_only_fields = ['id', 'timestamp']

# UserLikeSerializer удален, так как используются модели Like и Dislike из core

class VideoSeekSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoSeek
        fields = ['id', 'video', 'timestamp', 'from_position', 'to_position']
        read_only_fields = ['id', 'timestamp']

class UserChannelViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserChannelView
        fields = ['id', 'channel', 'timestamp', 'duration', 'is_active']
        read_only_fields = ['id', 'timestamp']

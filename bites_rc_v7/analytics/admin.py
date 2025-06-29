from django.contrib import admin
from .models import UserVideoView, VideoSeek, UserChannelView

@admin.register(UserVideoView)
class UserVideoViewAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'timestamp', 'duration', 'is_active')
    list_filter = ('is_active', 'timestamp')
    search_fields = ('user__username', 'video__title')
    date_hierarchy = 'timestamp'

# Класс UserLikeAdmin удален, так как модель UserLike больше не используется

@admin.register(VideoSeek)
class VideoSeekAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'timestamp', 'from_position', 'to_position')
    list_filter = ('timestamp',)
    search_fields = ('user__username', 'video__title')
    date_hierarchy = 'timestamp'

@admin.register(UserChannelView)
class UserChannelViewAdmin(admin.ModelAdmin):
    list_display = ('user', 'channel', 'timestamp', 'duration', 'is_active')
    list_filter = ('is_active', 'timestamp')
    search_fields = ('user__username', 'channel__name')
    date_hierarchy = 'timestamp'

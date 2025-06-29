from django.contrib import admin
from .models import Video, Like, Dislike, Comment, Channel, UserProfile, Subscription, Tag, VideoDownloadQueue

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'channel', 'uploaded_by', 'views', 'upload_date', 'is_youtube', 'absolute_rating')
    list_filter = ('is_youtube', 'upload_date', 'channel')
    search_fields = ('title', 'description', 'uploaded_by__username', 'channel__name')
    readonly_fields = ('views', 'absolute_rating')
    date_hierarchy = 'upload_date'

@admin.register(Channel)
class ChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at', 'subscriber_count', 'is_youtube_channel')
    list_filter = ('is_youtube_channel', 'created_at')
    search_fields = ('name', 'owner__username', 'description')
    readonly_fields = ('created_at',)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'karma', 'karma_stability', 'casino_balance', 'casino_debt')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'bio')
    readonly_fields = ('created_at', 'karma_stability')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'sentiment', 'created_at')
    list_filter = ('created_at', 'sentiment')
    search_fields = ('content', 'user__username', 'video__title')
    readonly_fields = ('created_at',)

@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'video__title')
    readonly_fields = ('created_at',)

@admin.register(Dislike)
class DislikeAdmin(admin.ModelAdmin):
    list_display = ('user', 'video', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'video__title')
    readonly_fields = ('created_at',)

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'channel', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('user__username', 'channel__name')
    readonly_fields = ('created_at',)

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name',)
    readonly_fields = ('slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}

@admin.register(VideoDownloadQueue)
class VideoDownloadQueueAdmin(admin.ModelAdmin):
    list_display = ('video', 'user', 'status', 'progress', 'position', 'added_at')
    list_filter = ('status', 'added_at')
    search_fields = ('video__title', 'user__username')
    readonly_fields = ('added_at',)
    ordering = ['position', 'added_at']

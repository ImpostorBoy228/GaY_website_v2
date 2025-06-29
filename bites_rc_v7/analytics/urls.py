from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Video analytics
    path('track/video/view/', views.track_video_view, name='track_video_view'),
    path('track/video/end/', views.end_video_view, name='end_video_view'),
    # Маршрут track_like удален, так как лайки/дизлайки уже записываются напрямую
    path('track/seek/', views.track_seek, name='track_seek'),
    
    # Channel analytics
    path('track/channel/view/', views.track_channel_view, name='track_channel_view'),
    path('track/channel/end/', views.end_channel_view, name='end_channel_view'),
]

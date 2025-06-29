from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    # Home and authentication
    path('', views.home, name='home'),
    path('search/', views.search, name='search'),
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Video related
    path('video/<int:pk>/', views.video_detail, name='video_detail'),
    path('video/<int:pk>/stream/', views.stream_video, name='stream_video'),
    path('video/<int:pk>/like/', views.like_video, name='like_video'),
    path('video/<int:pk>/dislike/', views.dislike_video, name='dislike_video'),
    path('video/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('video/<int:pk>/edit/', views.edit_video, name='edit_video'),
    path('video/<int:pk>/delete/', views.delete_video, name='delete_video'),
    path('upload/', views.upload_video, name='upload_video'),
    path('random-video/', views.random_video, name='random_video'),
    path('recalculate-ratings/', views.recalculate_all_ratings, name='recalculate_all_ratings'),
    path('regenerate-all-tags/', views.regenerate_all_tags, name='regenerate_all_tags'),
    
    # Comment related
    path('comment/<int:comment_id>/delete/', views.delete_comment, name='delete_comment'),
    
    # User profile
    path('profile/<str:username>/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('karma/', views.user_karma, name='user_karma'),
    path('recalculate-karma/', views.recalculate_karma, name='recalculate_karma'),
    
    # Channel related
    path('channel/create/', views.create_channel, name='create_channel'),
    path('channel/<int:channel_id>/edit/', views.edit_channel, name='edit_channel'),
    path('channel/<int:channel_id>/', views.channel_detail, name='channel_detail'),
    path('channel/<int:channel_id>/videos/', views.channel_videos, name='channel_videos'),
    path('channel/<int:channel_id>/subscribe/', views.subscribe, name='subscribe'),
    path('channel/<int:channel_id>/unsubscribe/', views.unsubscribe, name='unsubscribe'),
    path('channels/', views.all_channels, name='all_channels'),
    
    path('ratings/', views.ratings, name='ratings'),
    path('ads/', views.ad_manager, name='ad_manager'),
    path('ads/<int:ad_id>/edit/', views.ad_edit, name='ad_edit'),
    path('ads/<int:ad_id>/delete/', views.ad_delete, name='ad_delete'),
    path('ads/<int:ad_id>/', views.ad_detail, name='ad_detail'),
    # Removed casino-related URLs
    # path('casino/', views.casino_view, name='casino'),
    
    # Тестовые страницы и прямая запись аналитики
    path('analytics-test/', views.analytics_test, name='analytics_test'),
    path('direct_seek_log/', views.direct_seek_log, name='direct_seek_log'),
    # path('casino/bet/', views.casino_bet, name='casino_bet'),
    # path('casino/debt/take/', views.casino_take_debt, name='casino_take_debt'),
    # path('casino/debt/pay/', views.casino_pay_debt, name='casino_pay_debt'),
    # path('casino/debt/accrue/', views.casino_accrue_debt, name='casino_accrue_debt'),
    path('api/video/<str:video_id>/download-status/', views.get_video_download_status, name='video_download_status'),
    path('api/video/<str:video_id>/download/', views.add_to_download_queue, name='add_to_download_queue'),
    path('api/random-ad/', views.api_random_ad, name='api_random_ad'),
    path('video/<int:video_id>/generate-tags/', views.generate_tags, name='generate_tags'),
    path('register-transition/', views.register_video_transition, name='register_video_transition'),
] 
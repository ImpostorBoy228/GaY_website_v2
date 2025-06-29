from django.urls import path
from . import views
 
urlpatterns = [
    path('videos/', views.VideoListView.as_view(), name='video_list'),
    path('recalculate-ratings/', views.recalculate_all_ratings, name='recalculate_ratings'),
    path('import/video/', views.import_video, name='import_video'),
    path('import/channel/', views.import_channel, name='import_channel'),
]
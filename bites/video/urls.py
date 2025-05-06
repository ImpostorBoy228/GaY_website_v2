from django.urls import path
from . import views

urlpatterns = [
    path('video/<int:video_id>/', views.video_detail, name='video_detail'),
    path('video/<int:video_id>/comment/', views.add_comment, name='add_comment'),
    path('video/<int:video_id>/vote/', views.vote_video, name='vote_video'),
] 
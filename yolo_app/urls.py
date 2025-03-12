from django.urls import path
from yolo_app import views

urlpatterns = [
    path('video_stream/', views.video_stream, name='video_stream'),
]
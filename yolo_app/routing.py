from django.urls import re_path
from yolo_app import consumers

websocket_urlpatterns = [
    re_path(r'^ws/camera/(?P<camera_id>\d+)/$', consumers.CameraConsumer.as_asgi()),
    re_path(r'^ws/home/$', consumers.HomeCommandConsumer.as_asgi()),
]

from django.urls import path
from yolo_app.views.camera_api import (
    camera_list, camera_detail, camera_stream,
    camera_events, all_events, camera_view,
    camera_snapshot, camera_status,
)
from yolo_app.views.home_api import (
    gesture_list, gesture_detail,
    command_list, command_detail, command_test,
    mapping_list, mapping_detail,
    trigger_logs,
)
from yolo_app.views.device_api import device_list, device_detail, device_control

urlpatterns = [
    # ── Camera management ─────────────────────────────────────────────────────
    path('cameras/', camera_list),
    path('cameras/<int:camera_id>/', camera_detail),
    path('cameras/<int:camera_id>/stream/', camera_stream),
    path('cameras/<int:camera_id>/snapshot/', camera_snapshot),
    path('cameras/<int:camera_id>/status/', camera_status),
    path('cameras/<int:camera_id>/events/', camera_events),
    path('events/', all_events),

    # ── Gesture actions ───────────────────────────────────────────────────────
    path('gestures/', gesture_list),
    path('gestures/<int:gesture_id>/', gesture_detail),

    # ── Home commands ─────────────────────────────────────────────────────────
    path('commands/', command_list),
    path('commands/<int:command_id>/', command_detail),
    path('commands/<int:command_id>/test/', command_test),

    # ── Gesture → Command mappings ────────────────────────────────────────────
    path('mappings/', mapping_list),
    path('mappings/<int:mapping_id>/', mapping_detail),

    # ── Trigger history ───────────────────────────────────────────────────────
    path('trigger-logs/', trigger_logs),

    # ── Smart devices ─────────────────────────────────────────────────────────
    path('devices/', device_list),
    path('devices/<int:device_id>/', device_detail),
    path('devices/<int:device_id>/control/', device_control),
]

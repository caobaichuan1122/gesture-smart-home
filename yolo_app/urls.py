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

urlpatterns = [
    # ── Camera management ─────────────────────────────────────────────────────
    path('api/cameras/', camera_list),
    path('api/cameras/<int:camera_id>/', camera_detail),
    path('api/cameras/<int:camera_id>/stream/', camera_stream),
    path('api/cameras/<int:camera_id>/snapshot/', camera_snapshot),
    path('api/cameras/<int:camera_id>/status/', camera_status),
    path('cameras/<int:camera_id>/', camera_view),
    path('api/cameras/<int:camera_id>/events/', camera_events),
    path('api/events/', all_events),

    # ── Gesture actions ───────────────────────────────────────────────────────
    path('api/gestures/', gesture_list),
    path('api/gestures/<int:gesture_id>/', gesture_detail),

    # ── Home commands ─────────────────────────────────────────────────────────
    path('api/commands/', command_list),
    path('api/commands/<int:command_id>/', command_detail),
    path('api/commands/<int:command_id>/test/', command_test),

    # ── Gesture → Command mappings ────────────────────────────────────────────
    path('api/mappings/', mapping_list),
    path('api/mappings/<int:mapping_id>/', mapping_detail),

    # ── Trigger history ───────────────────────────────────────────────────────
    path('api/trigger-logs/', trigger_logs),
]

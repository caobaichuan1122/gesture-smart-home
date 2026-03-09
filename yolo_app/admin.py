from django.contrib import admin
from yolo_app.models import (
    Camera, DetectionEvent,
    GestureAction, HomeCommand, GestureCommandMapping, GestureTriggerLog,
)


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'source_type', 'source', 'enabled', 'yolo_enabled', 'gesture_enabled', 'created_at']
    list_editable = ['enabled', 'yolo_enabled', 'gesture_enabled']


@admin.register(DetectionEvent)
class DetectionEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'camera', 'detected_at', 'labels']
    list_filter = ['camera']
    readonly_fields = ['snapshot', 'detected_at']


@admin.register(GestureAction)
class GestureActionAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'hold_frames', 'cooldown_seconds', 'enabled']
    list_editable = ['enabled']


@admin.register(HomeCommand)
class HomeCommandAdmin(admin.ModelAdmin):
    list_display = ['id', 'name', 'command_type', 'enabled']
    list_editable = ['enabled']


@admin.register(GestureCommandMapping)
class GestureCommandMappingAdmin(admin.ModelAdmin):
    list_display = ['id', 'gesture', 'command', 'camera', 'enabled']
    list_editable = ['enabled']
    list_filter = ['gesture', 'camera']


@admin.register(GestureTriggerLog)
class GestureTriggerLogAdmin(admin.ModelAdmin):
    list_display = ['id', 'camera', 'gesture', 'command', 'triggered_at', 'success']
    list_filter = ['camera', 'gesture', 'success']
    readonly_fields = ['snapshot', 'triggered_at']

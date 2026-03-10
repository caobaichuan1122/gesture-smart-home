from rest_framework import serializers
from yolo_app.models import (
    Camera, DetectionEvent,
    GestureAction, HomeCommand, GestureCommandMapping, GestureTriggerLog,
    SmartDevice,
)


class CameraSerializer(serializers.ModelSerializer):
    stream_url = serializers.SerializerMethodField()
    ws_url = serializers.SerializerMethodField()

    class Meta:
        model = Camera
        fields = [
            'id', 'name', 'source_type', 'source',
            'enabled', 'yolo_enabled', 'gesture_enabled',
            'created_at', 'stream_url', 'ws_url',
        ]

    def get_stream_url(self, obj):
        return f'/api/cameras/{obj.id}/stream/'

    def get_ws_url(self, obj):
        return f'/ws/camera/{obj.id}/'


class DetectionEventSerializer(serializers.ModelSerializer):
    snapshot_url = serializers.SerializerMethodField()

    class Meta:
        model = DetectionEvent
        fields = ['id', 'camera', 'detected_at', 'labels', 'snapshot_url']

    def get_snapshot_url(self, obj):
        return obj.snapshot.url if obj.snapshot else None


# ── Home Automation ───────────────────────────────────────────────────────────

class GestureActionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GestureAction
        fields = ['id', 'name', 'description', 'hold_frames', 'cooldown_seconds', 'enabled']


class HomeCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = HomeCommand
        fields = [
            'id', 'name', 'command_type', 'enabled',
            'http_url', 'http_method', 'http_body', 'http_headers',
            'mqtt_topic', 'mqtt_payload',
            'ws_message',
        ]


class GestureCommandMappingSerializer(serializers.ModelSerializer):
    gesture_name = serializers.CharField(source='gesture.name', read_only=True)
    command_name = serializers.CharField(source='command.name', read_only=True)
    camera_name = serializers.CharField(source='camera.name', read_only=True, default=None)

    class Meta:
        model = GestureCommandMapping
        fields = ['id', 'gesture', 'gesture_name', 'command', 'command_name',
                  'camera', 'camera_name', 'enabled']


class GestureTriggerLogSerializer(serializers.ModelSerializer):
    gesture_name = serializers.CharField(source='gesture.name', read_only=True)
    command_name = serializers.CharField(source='command.name', read_only=True)
    camera_name = serializers.CharField(source='camera.name', read_only=True)
    snapshot_url = serializers.SerializerMethodField()

    class Meta:
        model = GestureTriggerLog
        fields = ['id', 'camera', 'camera_name', 'gesture', 'gesture_name',
                  'command', 'command_name', 'triggered_at', 'success',
                  'error_message', 'snapshot_url']

    def get_snapshot_url(self, obj):
        return obj.snapshot.url if obj.snapshot else None


# ── Smart Devices ─────────────────────────────────────────────────────────────

_SUPPORTED_ACTIONS = {
    SmartDevice.DEVICE_LIGHT:   ['turn_on', 'turn_off', 'set_brightness'],
    SmartDevice.DEVICE_CURTAIN: ['open', 'close', 'set_position'],
    SmartDevice.DEVICE_TV:      ['turn_on', 'turn_off', 'set_volume', 'pause'],
    SmartDevice.DEVICE_AC:      ['turn_on', 'turn_off', 'set_temperature', 'set_mode'],
}


class SmartDeviceSerializer(serializers.ModelSerializer):
    device_type_display = serializers.CharField(source='get_device_type_display', read_only=True)
    protocol_display = serializers.CharField(source='get_protocol_display', read_only=True)
    supported_actions = serializers.SerializerMethodField()

    class Meta:
        model = SmartDevice
        fields = [
            'id', 'name', 'device_type', 'device_type_display',
            'protocol', 'protocol_display', 'room',
            'http_base_url', 'http_token', 'entity_id',
            'mqtt_topic_prefix',
            'is_on', 'extra_state',
            'enabled', 'created_at',
            'supported_actions',
        ]

    def get_supported_actions(self, obj):
        return _SUPPORTED_ACTIONS.get(obj.device_type, [])

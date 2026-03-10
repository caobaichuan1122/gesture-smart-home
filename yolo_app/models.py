from django.db import models


class Camera(models.Model):
    SOURCE_TYPE_LOCAL = 'local'
    SOURCE_TYPE_RTSP = 'rtsp'
    SOURCE_TYPE_HTTP = 'http'
    SOURCE_TYPES = [
        (SOURCE_TYPE_LOCAL, 'Local Camera'),
        (SOURCE_TYPE_RTSP, 'RTSP Stream'),
        (SOURCE_TYPE_HTTP, 'HTTP Stream'),
    ]

    name = models.CharField(max_length=100)
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPES, default=SOURCE_TYPE_LOCAL)
    # For local cameras: device index (e.g. "0"); for rtsp/http: full URL
    source = models.CharField(max_length=500)
    enabled = models.BooleanField(default=True)
    yolo_enabled = models.BooleanField(default=True)
    # Enable gesture-based home automation on this camera
    gesture_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['id']


class DetectionEvent(models.Model):
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE, related_name='events')
    detected_at = models.DateTimeField(auto_now_add=True)
    # e.g. [{"label": "person", "confidence": 0.92}, ...]
    labels = models.JSONField(default=list)
    snapshot = models.ImageField(upload_to='snapshots/', null=True, blank=True)

    class Meta:
        ordering = ['-detected_at']


# ── Home Automation ───────────────────────────────────────────────────────────

class GestureAction(models.Model):
    """
    A named gesture that the system can recognize.
    Built-in gesture names (matched by GestureRecognizer):
      raise_right_hand, raise_left_hand, raise_both_hands,
      thumbs_up, thumbs_down, wave, t_pose, clap
    Custom gestures can be added and matched via rule sets.
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    # Minimum consecutive frames the gesture must hold before triggering
    hold_frames = models.PositiveIntegerField(default=10)
    # Seconds to wait before the same gesture can trigger again
    cooldown_seconds = models.PositiveIntegerField(default=5)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class HomeCommand(models.Model):
    """
    A command that can be sent to a smart home device or service.
    """
    COMMAND_HTTP = 'http'
    COMMAND_MQTT = 'mqtt'
    COMMAND_WS = 'websocket'
    COMMAND_SHELL = 'shell'
    COMMAND_TYPES = [
        (COMMAND_HTTP, 'HTTP Request'),
        (COMMAND_MQTT, 'MQTT Publish'),
        (COMMAND_WS, 'WebSocket Broadcast'),
        (COMMAND_SHELL, 'Shell Command'),
    ]

    name = models.CharField(max_length=100)
    command_type = models.CharField(max_length=20, choices=COMMAND_TYPES)

    # ── HTTP fields ──────────────────────────────────────────────────────────
    # URL to call, HTTP method, optional JSON body, optional headers JSON
    http_url = models.CharField(max_length=500, blank=True)
    http_method = models.CharField(max_length=10, default='POST', blank=True)
    http_body = models.JSONField(null=True, blank=True)
    http_headers = models.JSONField(null=True, blank=True)

    # ── MQTT fields ──────────────────────────────────────────────────────────
    mqtt_topic = models.CharField(max_length=200, blank=True)
    mqtt_payload = models.CharField(max_length=500, blank=True)

    # ── WebSocket broadcast payload (sent to all connected app clients) ──────
    ws_message = models.JSONField(null=True, blank=True)

    # ── Shell command ─────────────────────────────────────────────────────────
    # Command string executed via subprocess (e.g. "notepad.exe", "python /path/script.py")
    shell_command = models.CharField(max_length=1000, blank=True)

    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class GestureCommandMapping(models.Model):
    """
    Binds a GestureAction to a HomeCommand on a specific camera.
    Leaving camera null means the mapping applies to all cameras.
    """
    gesture = models.ForeignKey(GestureAction, on_delete=models.CASCADE, related_name='mappings')
    command = models.ForeignKey(HomeCommand, on_delete=models.CASCADE, related_name='mappings')
    # Null camera = apply on every camera that has gesture_enabled=True
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE,
                               related_name='gesture_mappings', null=True, blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        cam = self.camera.name if self.camera else 'all cameras'
        return f'{self.gesture.name} → {self.command.name} ({cam})'


# ── Smart Devices ─────────────────────────────────────────────────────────────

class SmartDevice(models.Model):
    """
    Represents a physical smart home device (light, curtain, TV, AC, …).
    Control it via POST /api/devices/<id>/control/ with {"action": "...", "params": {...}}.
    """
    DEVICE_LIGHT = 'light'
    DEVICE_CURTAIN = 'curtain'
    DEVICE_TV = 'tv'
    DEVICE_AC = 'ac'
    DEVICE_TYPES = [
        (DEVICE_LIGHT, '灯光'),
        (DEVICE_CURTAIN, '窗帘'),
        (DEVICE_TV, '电视'),
        (DEVICE_AC, '空调'),
    ]

    PROTOCOL_HTTP = 'http'
    PROTOCOL_MQTT = 'mqtt'
    PROTOCOLS = [
        (PROTOCOL_HTTP, 'HTTP (Home Assistant)'),
        (PROTOCOL_MQTT, 'MQTT'),
    ]

    name = models.CharField(max_length=100)
    device_type = models.CharField(max_length=20, choices=DEVICE_TYPES)
    protocol = models.CharField(max_length=10, choices=PROTOCOLS, default=PROTOCOL_HTTP)
    room = models.CharField(max_length=100, blank=True, help_text='房间名，e.g. living_room')

    # ── HTTP / Home Assistant ──────────────────────────────────────────────────
    http_base_url = models.CharField(max_length=500, blank=True,
                                     help_text='HA 地址，e.g. http://192.168.1.10:8123')
    http_token = models.CharField(max_length=500, blank=True,
                                  help_text='HA 长期访问令牌 (Bearer token)')
    entity_id = models.CharField(max_length=200, blank=True,
                                 help_text='HA 实体 ID，e.g. light.living_room')

    # ── MQTT ──────────────────────────────────────────────────────────────────
    mqtt_topic_prefix = models.CharField(max_length=200, blank=True,
                                         help_text='MQTT 主题前缀，e.g. home/light/living_room')

    # ── Cached state (updated after each successful control call) ─────────────
    is_on = models.BooleanField(default=False)
    extra_state = models.JSONField(default=dict, blank=True,
                                   help_text='附加状态，e.g. {"brightness": 200, "temperature": 26}')

    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        prefix = f'[{self.room}] ' if self.room else ''
        return f'{prefix}{self.name}'

    class Meta:
        ordering = ['room', 'device_type', 'name']


class GestureTriggerLog(models.Model):
    """Audit log: every time a gesture fires a command."""
    camera = models.ForeignKey(Camera, on_delete=models.SET_NULL, null=True, related_name='trigger_logs')
    gesture = models.ForeignKey(GestureAction, on_delete=models.SET_NULL, null=True)
    command = models.ForeignKey(HomeCommand, on_delete=models.SET_NULL, null=True)
    triggered_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    snapshot = models.ImageField(upload_to='gesture_snapshots/', null=True, blank=True)

    class Meta:
        ordering = ['-triggered_at']

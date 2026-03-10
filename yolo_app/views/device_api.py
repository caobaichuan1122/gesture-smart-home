"""
Smart device control API.

Endpoints:
  GET/POST   /api/devices/              list / create devices
  GET/PUT/DELETE /api/devices/<id>/     retrieve / update / delete
  POST       /api/devices/<id>/control/ send a control action to the device

Control request body:
  {"action": "<action>", "params": {...}}

Supported actions per device type:
  light   : turn_on  | turn_off  | set_brightness(brightness: 0-255)
  curtain : open     | close     | set_position(position: 0-100)
  tv      : turn_on  | turn_off  | set_volume(volume_level: 0.0-1.0) | pause
  ac      : turn_on  | turn_off  | set_temperature(temperature: int) | set_mode(hvac_mode: str)
"""

import json
import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from yolo_app.models import SmartDevice, HomeCommand
from yolo_app.serializers import SmartDeviceSerializer
from yolo_app.utils import command_executor

logger = logging.getLogger(__name__)

# ── HA service names per (device_type, action) ────────────────────────────────

_HA_SERVICE = {
    # light
    ('light', 'turn_on'):        ('light', 'turn_on'),
    ('light', 'turn_off'):       ('light', 'turn_off'),
    ('light', 'set_brightness'): ('light', 'turn_on'),
    # curtain (cover)
    ('curtain', 'open'):         ('cover', 'open_cover'),
    ('curtain', 'close'):        ('cover', 'close_cover'),
    ('curtain', 'set_position'): ('cover', 'set_cover_position'),
    # tv (media_player)
    ('tv', 'turn_on'):           ('media_player', 'turn_on'),
    ('tv', 'turn_off'):          ('media_player', 'turn_off'),
    ('tv', 'set_volume'):        ('media_player', 'volume_set'),
    ('tv', 'pause'):             ('media_player', 'media_pause'),
    # ac (climate)
    ('ac', 'turn_on'):           ('climate', 'turn_on'),
    ('ac', 'turn_off'):          ('climate', 'turn_off'),
    ('ac', 'set_temperature'):   ('climate', 'set_temperature'),
    ('ac', 'set_mode'):          ('climate', 'set_hvac_mode'),
}

# ── MQTT payload builders ─────────────────────────────────────────────────────

def _mqtt_payload(action: str, params: dict) -> dict:
    mapping = {
        'turn_on':        {'state': 'ON'},
        'turn_off':       {'state': 'OFF'},
        'open':           {'state': 'OPEN'},
        'close':          {'state': 'CLOSE'},
        'set_brightness': {'state': 'ON', 'brightness': params.get('brightness', 255)},
        'set_position':   {'position': params.get('position', 0)},
        'set_volume':     {'volume': params.get('volume_level', 0.5)},
        'pause':          {'state': 'PAUSE'},
        'set_temperature':{'state': 'ON', 'temperature': params.get('temperature', 26)},
        'set_mode':       {'state': 'ON', 'mode': params.get('hvac_mode', 'cool')},
    }
    return mapping.get(action, {'state': 'ON'})


# ── Command builder ───────────────────────────────────────────────────────────

def _build_http_command(device: SmartDevice, action: str, params: dict):
    """Build an unsaved HomeCommand for an HTTP/HA action."""
    key = (device.device_type, action)
    if key not in _HA_SERVICE:
        return None, f'Action "{action}" not supported for {device.device_type}'

    domain, service = _HA_SERVICE[key]
    url = f'{device.http_base_url.rstrip("/")}/api/services/{domain}/{service}'
    headers = {'Content-Type': 'application/json'}
    if device.http_token:
        headers['Authorization'] = f'Bearer {device.http_token}'

    body = {'entity_id': device.entity_id}
    # Merge action-specific params into the body
    if action == 'set_brightness':
        body['brightness'] = params.get('brightness', 255)
    elif action == 'set_position':
        body['position'] = params.get('position', 0)
    elif action == 'set_volume':
        body['volume_level'] = params.get('volume_level', 0.5)
    elif action == 'set_temperature':
        body['temperature'] = params.get('temperature', 26)
    elif action == 'set_mode':
        body['hvac_mode'] = params.get('hvac_mode', 'cool')

    cmd = HomeCommand(
        name=f'{device.name} / {action}',
        command_type=HomeCommand.COMMAND_HTTP,
        http_url=url,
        http_method='POST',
        http_body=body,
        http_headers=headers,
    )
    return cmd, None


def _build_mqtt_command(device: SmartDevice, action: str, params: dict):
    """Build an unsaved HomeCommand for an MQTT action."""
    supported = {
        'light':   ['turn_on', 'turn_off', 'set_brightness'],
        'curtain': ['open', 'close', 'set_position'],
        'tv':      ['turn_on', 'turn_off', 'set_volume', 'pause'],
        'ac':      ['turn_on', 'turn_off', 'set_temperature', 'set_mode'],
    }
    if action not in supported.get(device.device_type, []):
        return None, f'Action "{action}" not supported for {device.device_type}'

    topic = f'{device.mqtt_topic_prefix.rstrip("/")}/set'
    payload = _mqtt_payload(action, params)

    cmd = HomeCommand(
        name=f'{device.name} / {action}',
        command_type=HomeCommand.COMMAND_MQTT,
        mqtt_topic=topic,
        mqtt_payload=json.dumps(payload),
    )
    return cmd, None


# ── State update after successful action ──────────────────────────────────────

def _update_state(device: SmartDevice, action: str, params: dict):
    if action in ('turn_on', 'open'):
        device.is_on = True
    elif action in ('turn_off', 'close'):
        device.is_on = False

    state = device.extra_state or {}
    if action == 'set_brightness':
        state['brightness'] = params.get('brightness', 255)
        device.is_on = True
    elif action == 'set_position':
        state['position'] = params.get('position', 0)
    elif action == 'set_volume':
        state['volume_level'] = params.get('volume_level', 0.5)
    elif action == 'set_temperature':
        state['temperature'] = params.get('temperature', 26)
        device.is_on = True
    elif action == 'set_mode':
        state['hvac_mode'] = params.get('hvac_mode', 'cool')
        device.is_on = True
    device.extra_state = state
    device.save(update_fields=['is_on', 'extra_state'])


# ── Views ─────────────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def device_list(request):
    if request.method == 'GET':
        qs = SmartDevice.objects.all()
        device_type = request.query_params.get('type')
        room = request.query_params.get('room')
        if device_type:
            qs = qs.filter(device_type=device_type)
        if room:
            qs = qs.filter(room=room)
        return Response(SmartDeviceSerializer(qs, many=True).data)

    serializer = SmartDeviceSerializer(data=request.data)
    if serializer.is_valid():
        obj = serializer.save()
        logger.info('SmartDevice created: %s (%s)', obj.name, obj.device_type)
        return Response(SmartDeviceSerializer(obj).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def device_detail(request, device_id):
    try:
        obj = SmartDevice.objects.get(pk=device_id)
    except SmartDevice.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(SmartDeviceSerializer(obj).data)
    if request.method == 'PUT':
        serializer = SmartDeviceSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(SmartDeviceSerializer(obj).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    obj.delete()
    logger.info('SmartDevice deleted: id=%d', device_id)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def device_control(request, device_id):
    """
    Control a smart device.

    Request body:
      {
        "action": "turn_on" | "turn_off" | "open" | "close" | ...,
        "params": { "brightness": 200, "temperature": 26, ... }   // optional
      }

    Response (success):
      {"status": "ok", "device": "<name>", "action": "<action>", "state": {...}}

    Response (error):
      {"status": "error", "detail": "<reason>"}
    """
    try:
        device = SmartDevice.objects.get(pk=device_id)
    except SmartDevice.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if not device.enabled:
        return Response({'error': 'Device is disabled'}, status=status.HTTP_403_FORBIDDEN)

    action = request.data.get('action', '').strip()
    params = request.data.get('params') or {}

    if not action:
        return Response({'error': '"action" is required'}, status=status.HTTP_400_BAD_REQUEST)

    # Build command
    if device.protocol == SmartDevice.PROTOCOL_HTTP:
        cmd, err = _build_http_command(device, action, params)
    else:
        cmd, err = _build_mqtt_command(device, action, params)

    if err:
        return Response({'status': 'error', 'detail': err}, status=status.HTTP_400_BAD_REQUEST)

    # Execute
    success, error = command_executor.execute(cmd, context={'source': 'device_control', 'device_id': device_id})
    if not success:
        logger.warning('Device control failed  device=%d action=%s error=%s', device_id, action, error)
        return Response({'status': 'error', 'detail': error}, status=status.HTTP_502_BAD_GATEWAY)

    _update_state(device, action, params)
    logger.info('Device control ok  device=%s action=%s params=%s', device.name, action, params)
    return Response({
        'status': 'ok',
        'device': device.name,
        'action': action,
        'state': {'is_on': device.is_on, **device.extra_state},
    })

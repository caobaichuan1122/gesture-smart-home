"""
Comprehensive test suite for gesture-smart-home.

Coverage areas:
  Models          — str, defaults, FK relations, ordering
  Serializers     — fields, method fields, read-only, supported_actions
  Camera API      — CRUD, 404 handling, events
  Home API        — gesture / command / mapping / log CRUD, command_test
  Device API      — CRUD, control actions (all types × both protocols), error paths
  CommandExecutor — HTTP, MQTT, Shell, WebSocket dispatch
  GestureEngine   — hold debounce, cooldown, mapping lookup, trigger logging
  WS Consumers    — connect / disconnect / message routing
"""

import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch, call

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase

from yolo_app.models import (
    Camera, DetectionEvent,
    GestureAction, HomeCommand, GestureCommandMapping, GestureTriggerLog,
    SmartDevice,
)
from yolo_app.serializers import (
    CameraSerializer, HomeCommandSerializer,
    SmartDeviceSerializer, GestureCommandMappingSerializer,
    GestureTriggerLogSerializer,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_camera(**kwargs):
    defaults = dict(name='Test Cam', source_type='local', source='0')
    defaults.update(kwargs)
    return Camera.objects.create(**defaults)


def make_gesture(**kwargs):
    defaults = dict(name='thumbs_up', hold_frames=5, cooldown_seconds=3)
    defaults.update(kwargs)
    return GestureAction.objects.create(**defaults)


def make_command(**kwargs):
    defaults = dict(
        name='Test Cmd', command_type='shell',
        shell_command='echo ok',
    )
    defaults.update(kwargs)
    return HomeCommand.objects.create(**defaults)


def make_device(**kwargs):
    defaults = dict(
        name='Living Room Light', device_type='light', protocol='http',
        room='living_room', http_base_url='http://ha:8123',
        http_token='TOKEN', entity_id='light.living_room',
    )
    defaults.update(kwargs)
    return SmartDevice.objects.create(**defaults)


# ══════════════════════════════════════════════════════════════════════════════
# MODEL TESTS
# ══════════════════════════════════════════════════════════════════════════════

class CameraModelTests(TestCase):
    def test_str(self):
        cam = make_camera(name='Front Door')
        self.assertEqual(str(cam), 'Front Door')

    def test_defaults(self):
        cam = make_camera()
        self.assertTrue(cam.enabled)
        self.assertTrue(cam.yolo_enabled)
        self.assertFalse(cam.gesture_enabled)

    def test_ordering_by_id(self):
        c1 = make_camera(name='A')
        c2 = make_camera(name='B')
        self.assertEqual(list(Camera.objects.all()), [c1, c2])


class GestureActionModelTests(TestCase):
    def test_str(self):
        g = make_gesture(name='victory')
        self.assertEqual(str(g), 'victory')

    def test_defaults(self):
        g = make_gesture()
        self.assertTrue(g.enabled)

    def test_unique_name(self):
        make_gesture(name='fist')
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            make_gesture(name='fist')


class HomeCommandModelTests(TestCase):
    def test_str(self):
        cmd = make_command(name='Open Gate')
        self.assertEqual(str(cmd), 'Open Gate')

    def test_command_type_choices(self):
        valid = ['http', 'mqtt', 'websocket', 'shell']
        for t in valid:
            cmd = HomeCommand(name='x', command_type=t)
            self.assertEqual(cmd.command_type, t)

    def test_enabled_default(self):
        cmd = make_command()
        self.assertTrue(cmd.enabled)


class GestureCommandMappingModelTests(TestCase):
    def test_str_with_camera(self):
        cam = make_camera()
        g = make_gesture()
        cmd = make_command()
        m = GestureCommandMapping.objects.create(gesture=g, command=cmd, camera=cam)
        self.assertIn(g.name, str(m))
        self.assertIn(cmd.name, str(m))
        self.assertIn(cam.name, str(m))

    def test_str_all_cameras(self):
        g = make_gesture()
        cmd = make_command()
        m = GestureCommandMapping.objects.create(gesture=g, command=cmd)
        self.assertIn('all cameras', str(m))

    def test_enabled_default(self):
        g = make_gesture()
        cmd = make_command()
        m = GestureCommandMapping.objects.create(gesture=g, command=cmd)
        self.assertTrue(m.enabled)


class GestureTriggerLogModelTests(TestCase):
    def test_ordering_newest_first(self):
        cam = make_camera()
        g = make_gesture()
        cmd = make_command()
        l1 = GestureTriggerLog.objects.create(camera=cam, gesture=g, command=cmd)
        l2 = GestureTriggerLog.objects.create(camera=cam, gesture=g, command=cmd)
        logs = list(GestureTriggerLog.objects.all())
        self.assertEqual(logs[0], l2)
        self.assertEqual(logs[1], l1)


class SmartDeviceModelTests(TestCase):
    def test_str_with_room(self):
        d = make_device(name='Light', room='bedroom')
        self.assertEqual(str(d), '[bedroom] Light')

    def test_str_without_room(self):
        d = make_device(name='Light', room='')
        self.assertEqual(str(d), 'Light')

    def test_defaults(self):
        d = make_device()
        self.assertFalse(d.is_on)
        self.assertEqual(d.extra_state, {})
        self.assertTrue(d.enabled)

    def test_ordering(self):
        d1 = make_device(room='bedroom', name='AC', device_type='ac')
        d2 = make_device(room='bedroom', name='Light', device_type='light')
        d3 = make_device(room='living_room', name='TV', device_type='tv')
        qs = list(SmartDevice.objects.all())
        self.assertEqual(qs[0], d1)   # bedroom / ac
        self.assertEqual(qs[1], d2)   # bedroom / light
        self.assertEqual(qs[2], d3)   # living_room / tv


# ══════════════════════════════════════════════════════════════════════════════
# SERIALIZER TESTS
# ══════════════════════════════════════════════════════════════════════════════

class CameraSerializerTests(TestCase):
    def test_stream_and_ws_urls(self):
        cam = make_camera()
        data = CameraSerializer(cam).data
        self.assertEqual(data['stream_url'], f'/api/cameras/{cam.id}/stream/')
        self.assertEqual(data['ws_url'], f'/ws/camera/{cam.id}/')

    def test_required_fields(self):
        s = CameraSerializer(data={})
        self.assertFalse(s.is_valid())
        self.assertIn('name', s.errors)

    def test_valid_data(self):
        s = CameraSerializer(data={'name': 'Cam', 'source': '0', 'source_type': 'local'})
        self.assertTrue(s.is_valid(), s.errors)


class HomeCommandSerializerTests(TestCase):
    def test_all_fields_present(self):
        cmd = make_command()
        data = HomeCommandSerializer(cmd).data
        for f in ['id', 'name', 'command_type', 'enabled',
                  'http_url', 'http_method', 'http_body', 'http_headers',
                  'mqtt_topic', 'mqtt_payload', 'ws_message']:
            self.assertIn(f, data)


class SmartDeviceSerializerTests(TestCase):
    def _check_actions(self, device_type, expected):
        d = make_device(device_type=device_type)
        data = SmartDeviceSerializer(d).data
        self.assertEqual(sorted(data['supported_actions']), sorted(expected))

    def test_light_actions(self):
        self._check_actions('light', ['turn_on', 'turn_off', 'set_brightness'])

    def test_curtain_actions(self):
        self._check_actions('curtain', ['open', 'close', 'set_position'])

    def test_tv_actions(self):
        self._check_actions('tv', ['turn_on', 'turn_off', 'set_volume', 'pause'])

    def test_ac_actions(self):
        self._check_actions('ac', ['turn_on', 'turn_off', 'set_temperature', 'set_mode'])

    def test_display_fields(self):
        d = make_device(device_type='light', protocol='http')
        data = SmartDeviceSerializer(d).data
        self.assertEqual(data['device_type_display'], '灯光')
        self.assertEqual(data['protocol_display'], 'HTTP (Home Assistant)')


class GestureCommandMappingSerializerTests(TestCase):
    def test_read_only_name_fields(self):
        cam = make_camera()
        g = make_gesture()
        cmd = make_command()
        m = GestureCommandMapping.objects.create(gesture=g, command=cmd, camera=cam)
        data = GestureCommandMappingSerializer(m).data
        self.assertEqual(data['gesture_name'], g.name)
        self.assertEqual(data['command_name'], cmd.name)
        self.assertEqual(data['camera_name'], cam.name)

    def test_camera_name_none_when_global(self):
        g = make_gesture()
        cmd = make_command()
        m = GestureCommandMapping.objects.create(gesture=g, command=cmd)
        data = GestureCommandMappingSerializer(m).data
        self.assertIsNone(data['camera_name'])


class GestureTriggerLogSerializerTests(TestCase):
    def test_snapshot_url_none_when_no_snapshot(self):
        cam = make_camera()
        g = make_gesture()
        cmd = make_command()
        log = GestureTriggerLog.objects.create(camera=cam, gesture=g, command=cmd)
        data = GestureTriggerLogSerializer(log).data
        self.assertIsNone(data['snapshot_url'])

    def test_name_fields(self):
        cam = make_camera(name='MyCam')
        g = make_gesture(name='fist')
        cmd = make_command(name='MyCmd')
        log = GestureTriggerLog.objects.create(camera=cam, gesture=g, command=cmd)
        data = GestureTriggerLogSerializer(log).data
        self.assertEqual(data['camera_name'], 'MyCam')
        self.assertEqual(data['gesture_name'], 'fist')
        self.assertEqual(data['command_name'], 'MyCmd')


# ══════════════════════════════════════════════════════════════════════════════
# CAMERA API TESTS
# ══════════════════════════════════════════════════════════════════════════════

@patch('yolo_app.views.camera_api.camera_manager')
class CameraAPITests(APITestCase):
    def test_list_empty(self, mock_mgr):
        r = self.client.get('/api/cameras/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, [])

    def test_list_returns_cameras(self, mock_mgr):
        make_camera(name='Cam1')
        make_camera(name='Cam2')
        r = self.client.get('/api/cameras/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 2)

    def test_create_camera(self, mock_mgr):
        payload = {'name': 'Front Door', 'source': '0', 'source_type': 'local'}
        r = self.client.post('/api/cameras/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Camera.objects.count(), 1)
        mock_mgr.start_camera.assert_called_once()

    def test_create_camera_disabled_does_not_start(self, mock_mgr):
        payload = {'name': 'X', 'source': '0', 'source_type': 'local', 'enabled': False}
        r = self.client.post('/api/cameras/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        mock_mgr.start_camera.assert_not_called()

    def test_create_camera_invalid(self, mock_mgr):
        r = self.client.post('/api/cameras/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve_camera(self, mock_mgr):
        cam = make_camera()
        r = self.client.get(f'/api/cameras/{cam.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['name'], cam.name)

    def test_retrieve_camera_not_found(self, mock_mgr):
        r = self.client.get('/api/cameras/9999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_camera(self, mock_mgr):
        cam = make_camera(name='Old')
        r = self.client.put(f'/api/cameras/{cam.id}/', {'name': 'New'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cam.refresh_from_db()
        self.assertEqual(cam.name, 'New')
        mock_mgr.stop_camera.assert_called_once_with(cam.id)
        mock_mgr.start_camera.assert_called_once()

    def test_update_camera_not_found(self, mock_mgr):
        r = self.client.put('/api/cameras/9999/', {'name': 'X'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_camera(self, mock_mgr):
        cam = make_camera()
        r = self.client.delete(f'/api/cameras/{cam.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Camera.objects.filter(pk=cam.id).exists())
        mock_mgr.stop_camera.assert_called_once_with(cam.id)

    def test_delete_camera_not_found(self, mock_mgr):
        r = self.client.delete('/api/cameras/9999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_camera_events(self, mock_mgr):
        cam = make_camera()
        DetectionEvent.objects.create(camera=cam, labels=[{'label': 'person'}])
        r = self.client.get(f'/api/cameras/{cam.id}/events/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)

    def test_camera_events_not_found(self, mock_mgr):
        r = self.client.get('/api/cameras/9999/events/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_all_events(self, mock_mgr):
        cam = make_camera()
        DetectionEvent.objects.create(camera=cam, labels=[])
        DetectionEvent.objects.create(camera=cam, labels=[])
        r = self.client.get('/api/events/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 2)


# ══════════════════════════════════════════════════════════════════════════════
# HOME API TESTS
# ══════════════════════════════════════════════════════════════════════════════

class GestureAPITests(APITestCase):
    def test_list_empty(self):
        r = self.client.get('/api/gestures/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, [])

    def test_create_gesture(self):
        payload = {'name': 'thumbs_up', 'hold_frames': 10, 'cooldown_seconds': 5}
        r = self.client.post('/api/gestures/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(GestureAction.objects.count(), 1)

    def test_create_invalid(self):
        r = self.client.post('/api/gestures/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve(self):
        g = make_gesture()
        r = self.client.get(f'/api/gestures/{g.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['name'], g.name)

    def test_retrieve_not_found(self):
        r = self.client.get('/api/gestures/9999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_gesture(self):
        g = make_gesture(hold_frames=5)
        r = self.client.put(f'/api/gestures/{g.id}/', {'hold_frames': 15}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        g.refresh_from_db()
        self.assertEqual(g.hold_frames, 15)

    def test_delete_gesture(self):
        g = make_gesture()
        r = self.client.delete(f'/api/gestures/{g.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GestureAction.objects.filter(pk=g.id).exists())


class CommandAPITests(APITestCase):
    def test_list(self):
        make_command()
        r = self.client.get('/api/commands/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)

    def test_create_http_command(self):
        payload = {
            'name': 'Turn On Light',
            'command_type': 'http',
            'http_url': 'http://ha:8123/api/services/light/turn_on',
            'http_method': 'POST',
            'http_body': {'entity_id': 'light.living_room'},
        }
        r = self.client.post('/api/commands/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_create_mqtt_command(self):
        payload = {
            'name': 'Open Curtain',
            'command_type': 'mqtt',
            'mqtt_topic': 'home/curtain/set',
            'mqtt_payload': '{"state":"OPEN"}',
        }
        r = self.client.post('/api/commands/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)

    def test_create_invalid(self):
        r = self.client.post('/api/commands/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve(self):
        cmd = make_command()
        r = self.client.get(f'/api/commands/{cmd.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_retrieve_not_found(self):
        r = self.client.get('/api/commands/9999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_update(self):
        cmd = make_command(name='Old')
        r = self.client.put(f'/api/commands/{cmd.id}/', {'name': 'New'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cmd.refresh_from_db()
        self.assertEqual(cmd.name, 'New')

    def test_delete(self):
        cmd = make_command()
        r = self.client.delete(f'/api/commands/{cmd.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)

    @patch('yolo_app.utils.command_executor.execute', return_value=(True, ''))
    def test_command_test_success(self, mock_exec):
        cmd = make_command()
        r = self.client.post(f'/api/commands/{cmd.id}/test/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['status'], 'ok')
        mock_exec.assert_called_once()

    @patch('yolo_app.utils.command_executor.execute', return_value=(False, 'timeout'))
    def test_command_test_failure(self, mock_exec):
        cmd = make_command()
        r = self.client.post(f'/api/commands/{cmd.id}/test/')
        self.assertEqual(r.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn('timeout', r.data['detail'])

    def test_command_test_not_found(self):
        r = self.client.post('/api/commands/9999/test/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)


class MappingAPITests(APITestCase):
    def setUp(self):
        self.gesture = make_gesture()
        self.command = make_command()
        self.camera = make_camera()

    def test_list(self):
        GestureCommandMapping.objects.create(gesture=self.gesture, command=self.command)
        r = self.client.get('/api/mappings/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)

    def test_create_global_mapping(self):
        payload = {'gesture': self.gesture.id, 'command': self.command.id}
        r = self.client.post('/api/mappings/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(r.data['camera'])

    def test_create_camera_specific_mapping(self):
        payload = {
            'gesture': self.gesture.id,
            'command': self.command.id,
            'camera': self.camera.id,
        }
        r = self.client.post('/api/mappings/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(r.data['camera'], self.camera.id)

    def test_retrieve(self):
        m = GestureCommandMapping.objects.create(gesture=self.gesture, command=self.command)
        r = self.client.get(f'/api/mappings/{m.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)

    def test_retrieve_not_found(self):
        r = self.client.get('/api/mappings/9999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_update(self):
        m = GestureCommandMapping.objects.create(
            gesture=self.gesture, command=self.command, enabled=True)
        r = self.client.put(f'/api/mappings/{m.id}/', {'enabled': False}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        m.refresh_from_db()
        self.assertFalse(m.enabled)

    def test_delete(self):
        m = GestureCommandMapping.objects.create(gesture=self.gesture, command=self.command)
        r = self.client.delete(f'/api/mappings/{m.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)


class TriggerLogAPITests(APITestCase):
    def test_list_empty(self):
        r = self.client.get('/api/trigger-logs/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, [])

    def test_list_returns_logs(self):
        cam = make_camera()
        g = make_gesture()
        cmd = make_command()
        GestureTriggerLog.objects.create(camera=cam, gesture=g, command=cmd, success=True)
        r = self.client.get('/api/trigger-logs/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)
        self.assertTrue(r.data[0]['success'])


# ══════════════════════════════════════════════════════════════════════════════
# DEVICE API TESTS
# ══════════════════════════════════════════════════════════════════════════════

class DeviceAPITests(APITestCase):
    def test_list_empty(self):
        r = self.client.get('/api/devices/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data, [])

    def test_list_all(self):
        make_device(name='Light', device_type='light')
        make_device(name='AC', device_type='ac')
        r = self.client.get('/api/devices/')
        self.assertEqual(len(r.data), 2)

    def test_filter_by_type(self):
        make_device(name='Light', device_type='light')
        make_device(name='AC', device_type='ac')
        r = self.client.get('/api/devices/?type=light')
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['device_type'], 'light')

    def test_filter_by_room(self):
        make_device(name='L1', room='bedroom')
        make_device(name='L2', room='living_room')
        r = self.client.get('/api/devices/?room=bedroom')
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['room'], 'bedroom')

    def test_create_device(self):
        payload = {
            'name': 'Bedroom AC', 'device_type': 'ac', 'protocol': 'mqtt',
            'room': 'bedroom', 'mqtt_topic_prefix': 'home/ac/bedroom',
        }
        r = self.client.post('/api/devices/', payload, format='json')
        self.assertEqual(r.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SmartDevice.objects.count(), 1)

    def test_create_invalid(self):
        r = self.client.post('/api/devices/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_retrieve(self):
        d = make_device()
        r = self.client.get(f'/api/devices/{d.id}/')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(r.data['name'], d.name)

    def test_retrieve_not_found(self):
        r = self.client.get('/api/devices/9999/')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    def test_update_device(self):
        d = make_device(name='Old Name')
        r = self.client.put(f'/api/devices/{d.id}/', {'name': 'New Name'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        d.refresh_from_db()
        self.assertEqual(d.name, 'New Name')

    def test_delete_device(self):
        d = make_device()
        r = self.client.delete(f'/api/devices/{d.id}/')
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SmartDevice.objects.filter(pk=d.id).exists())

    def test_control_requires_action(self):
        d = make_device()
        r = self.client.post(f'/api/devices/{d.id}/control/', {}, format='json')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

    def test_control_disabled_device(self):
        d = make_device(enabled=False)
        r = self.client.post(f'/api/devices/{d.id}/control/', {'action': 'turn_on'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_403_FORBIDDEN)

    def test_control_not_found(self):
        r = self.client.post('/api/devices/9999/control/', {'action': 'turn_on'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_404_NOT_FOUND)

    @patch('yolo_app.utils.command_executor.execute', return_value=(False, 'connection refused'))
    def test_control_executor_failure(self, mock_exec):
        d = make_device()
        r = self.client.post(f'/api/devices/{d.id}/control/', {'action': 'turn_on'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertIn('connection refused', r.data['detail'])


class DeviceControlHTTPTests(APITestCase):
    """Verify correct HomeCommand is built for each HTTP action."""

    def setUp(self):
        self.device = make_device(
            device_type='light', protocol='http',
            http_base_url='http://ha:8123', http_token='TOKEN',
            entity_id='light.living_room',
        )

    def _control(self, action, params=None):
        payload = {'action': action}
        if params:
            payload['params'] = params
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as mock_exec:
            r = self.client.post(f'/api/devices/{self.device.id}/control/', payload, format='json')
            return r, mock_exec

    def _assert_http_cmd(self, mock_exec, expected_service, expected_body_subset):
        cmd = mock_exec.call_args[0][0]
        self.assertEqual(cmd.command_type, 'http')
        self.assertIn(expected_service, cmd.http_url)
        self.assertEqual(cmd.http_method, 'POST')
        self.assertIn('Authorization', cmd.http_headers)
        for k, v in expected_body_subset.items():
            self.assertEqual(cmd.http_body[k], v)

    def test_light_turn_on(self):
        r, m = self._control('turn_on')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self._assert_http_cmd(m, 'light/turn_on', {'entity_id': 'light.living_room'})
        self.device.refresh_from_db()
        self.assertTrue(self.device.is_on)

    def test_light_turn_off(self):
        r, m = self._control('turn_off')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self._assert_http_cmd(m, 'light/turn_off', {'entity_id': 'light.living_room'})
        self.device.refresh_from_db()
        self.assertFalse(self.device.is_on)

    def test_light_set_brightness(self):
        r, m = self._control('set_brightness', {'brightness': 128})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self._assert_http_cmd(m, 'light/turn_on', {'brightness': 128})
        self.device.refresh_from_db()
        self.assertEqual(self.device.extra_state['brightness'], 128)
        self.assertTrue(self.device.is_on)

    def test_curtain_open(self):
        d = make_device(device_type='curtain', entity_id='cover.living_room')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')):
            r = self.client.post(f'/api/devices/{d.id}/control/', {'action': 'open'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        d.refresh_from_db()
        self.assertTrue(d.is_on)

    def test_curtain_close(self):
        d = make_device(device_type='curtain', entity_id='cover.living_room')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')):
            r = self.client.post(f'/api/devices/{d.id}/control/', {'action': 'close'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        d.refresh_from_db()
        self.assertFalse(d.is_on)

    def test_curtain_set_position(self):
        d = make_device(device_type='curtain', entity_id='cover.living_room')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(
                f'/api/devices/{d.id}/control/',
                {'action': 'set_position', 'params': {'position': 75}},
                format='json',
            )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cmd = m.call_args[0][0]
        self.assertEqual(cmd.http_body['position'], 75)

    def test_tv_turn_on(self):
        d = make_device(device_type='tv', entity_id='media_player.tv')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(f'/api/devices/{d.id}/control/', {'action': 'turn_on'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('media_player/turn_on', m.call_args[0][0].http_url)

    def test_tv_set_volume(self):
        d = make_device(device_type='tv', entity_id='media_player.tv')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(
                f'/api/devices/{d.id}/control/',
                {'action': 'set_volume', 'params': {'volume_level': 0.6}},
                format='json',
            )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cmd = m.call_args[0][0]
        self.assertAlmostEqual(cmd.http_body['volume_level'], 0.6)

    def test_tv_pause(self):
        d = make_device(device_type='tv', entity_id='media_player.tv')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(f'/api/devices/{d.id}/control/', {'action': 'pause'}, format='json')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertIn('media_pause', m.call_args[0][0].http_url)

    def test_ac_set_temperature(self):
        d = make_device(device_type='ac', entity_id='climate.ac')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(
                f'/api/devices/{d.id}/control/',
                {'action': 'set_temperature', 'params': {'temperature': 24}},
                format='json',
            )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cmd = m.call_args[0][0]
        self.assertEqual(cmd.http_body['temperature'], 24)
        d.refresh_from_db()
        self.assertEqual(d.extra_state['temperature'], 24)

    def test_ac_set_mode(self):
        d = make_device(device_type='ac', entity_id='climate.ac')
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(
                f'/api/devices/{d.id}/control/',
                {'action': 'set_mode', 'params': {'hvac_mode': 'heat'}},
                format='json',
            )
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        cmd = m.call_args[0][0]
        self.assertEqual(cmd.http_body['hvac_mode'], 'heat')

    def test_unsupported_action_returns_400(self):
        r, _ = self._control('fly')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


class DeviceControlMQTTTests(APITestCase):
    """Verify correct MQTT topic and payload for each action."""

    def _make_mqtt_device(self, device_type, prefix='home/device'):
        return make_device(
            device_type=device_type, protocol='mqtt',
            mqtt_topic_prefix=prefix,
        )

    def _control(self, device, action, params=None):
        payload = {'action': action}
        if params:
            payload['params'] = params
        with patch('yolo_app.utils.command_executor.execute', return_value=(True, '')) as m:
            r = self.client.post(f'/api/devices/{device.id}/control/', payload, format='json')
            return r, m

    def _mqtt_payload(self, mock_exec):
        cmd = mock_exec.call_args[0][0]
        self.assertEqual(cmd.command_type, 'mqtt')
        self.assertTrue(cmd.mqtt_topic.endswith('/set'))
        return json.loads(cmd.mqtt_payload)

    def test_light_turn_on(self):
        d = self._make_mqtt_device('light', 'home/light/lr')
        r, m = self._control(d, 'turn_on')
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(self._mqtt_payload(m)['state'], 'ON')

    def test_light_turn_off(self):
        d = self._make_mqtt_device('light')
        r, m = self._control(d, 'turn_off')
        self.assertEqual(self._mqtt_payload(m)['state'], 'OFF')

    def test_light_set_brightness(self):
        d = self._make_mqtt_device('light')
        r, m = self._control(d, 'set_brightness', {'brightness': 200})
        payload = self._mqtt_payload(m)
        self.assertEqual(payload['state'], 'ON')
        self.assertEqual(payload['brightness'], 200)

    def test_curtain_open(self):
        d = self._make_mqtt_device('curtain', 'home/curtain')
        r, m = self._control(d, 'open')
        self.assertEqual(self._mqtt_payload(m)['state'], 'OPEN')

    def test_curtain_close(self):
        d = self._make_mqtt_device('curtain', 'home/curtain')
        r, m = self._control(d, 'close')
        self.assertEqual(self._mqtt_payload(m)['state'], 'CLOSE')

    def test_curtain_set_position(self):
        d = self._make_mqtt_device('curtain')
        r, m = self._control(d, 'set_position', {'position': 50})
        self.assertEqual(self._mqtt_payload(m)['position'], 50)

    def test_ac_turn_on(self):
        d = self._make_mqtt_device('ac', 'home/ac/bedroom')
        r, m = self._control(d, 'turn_on')
        self.assertEqual(self._mqtt_payload(m)['state'], 'ON')

    def test_ac_set_temperature(self):
        d = self._make_mqtt_device('ac')
        r, m = self._control(d, 'set_temperature', {'temperature': 22})
        payload = self._mqtt_payload(m)
        self.assertEqual(payload['temperature'], 22)

    def test_ac_set_mode(self):
        d = self._make_mqtt_device('ac')
        r, m = self._control(d, 'set_mode', {'hvac_mode': 'dry'})
        self.assertEqual(self._mqtt_payload(m)['mode'], 'dry')

    def test_tv_turn_on(self):
        d = self._make_mqtt_device('tv', 'home/tv')
        r, m = self._control(d, 'turn_on')
        self.assertEqual(self._mqtt_payload(m)['state'], 'ON')

    def test_tv_pause(self):
        d = self._make_mqtt_device('tv')
        r, m = self._control(d, 'pause')
        self.assertEqual(self._mqtt_payload(m)['state'], 'PAUSE')

    def test_unsupported_action_returns_400(self):
        d = self._make_mqtt_device('light')
        r, _ = self._control(d, 'nonexistent_action')
        self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)


# ══════════════════════════════════════════════════════════════════════════════
# COMMAND EXECUTOR TESTS
# ══════════════════════════════════════════════════════════════════════════════

class CommandExecutorHTTPTests(TestCase):
    def _make_http_cmd(self, **kwargs):
        defaults = dict(
            name='HTTP Cmd', command_type='http',
            http_url='http://example.com/api', http_method='POST',
            http_body={'key': 'value'}, http_headers={},
        )
        defaults.update(kwargs)
        return HomeCommand(**defaults)

    @patch('urllib.request.urlopen')
    def test_http_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_http_cmd())
        self.assertTrue(ok)
        self.assertEqual(err, '')

    @patch('urllib.request.urlopen')
    def test_http_sets_content_type(self, mock_urlopen):
        import urllib.request as ur
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        from yolo_app.utils import command_executor
        cmd = self._make_http_cmd(http_headers={})
        command_executor.execute(cmd)
        req = mock_urlopen.call_args[0][0]
        self.assertIn('Content-Type', req.headers)

    @patch('urllib.request.urlopen', side_effect=Exception('timeout'))
    def test_http_failure(self, mock_urlopen):
        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_http_cmd())
        self.assertFalse(ok)
        self.assertIn('timeout', err)

    @patch('urllib.request.urlopen')
    def test_http_error_status(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url='http://x', code=503, msg='Service Unavailable',
            hdrs=None, fp=None,
        )
        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_http_cmd())
        self.assertFalse(ok)
        self.assertIn('503', err)


class CommandExecutorMQTTTests(TestCase):
    def _make_mqtt_cmd(self):
        return HomeCommand(
            name='MQTT Cmd', command_type='mqtt',
            mqtt_topic='home/light/set', mqtt_payload='{"state":"ON"}',
        )

    @patch('yolo_app.utils.command_executor._get_mqtt_client')
    def test_mqtt_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_client.publish.return_value = mock_result
        mock_get_client.return_value = mock_client

        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_mqtt_cmd())
        self.assertTrue(ok)
        mock_client.publish.assert_called_once_with('home/light/set', '{"state":"ON"}')

    @patch('yolo_app.utils.command_executor._get_mqtt_client', return_value=None)
    def test_mqtt_no_client(self, mock_get_client):
        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_mqtt_cmd())
        self.assertFalse(ok)
        self.assertIn('not available', err)

    @patch('yolo_app.utils.command_executor._get_mqtt_client')
    def test_mqtt_publish_failure(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.publish.side_effect = Exception('broker down')
        mock_get_client.return_value = mock_client

        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_mqtt_cmd())
        self.assertFalse(ok)
        self.assertIn('broker down', err)


class CommandExecutorShellTests(TestCase):
    def _make_shell_cmd(self, cmd_str='echo hello'):
        return HomeCommand(
            name='Shell Cmd', command_type='shell', shell_command=cmd_str,
        )

    @patch('subprocess.Popen')
    def test_shell_success(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_shell_cmd())
        self.assertTrue(ok)
        self.assertEqual(err, '')
        mock_popen.assert_called_once()

    @patch('subprocess.Popen', side_effect=OSError('not found'))
    def test_shell_failure(self, mock_popen):
        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_shell_cmd())
        self.assertFalse(ok)
        self.assertIn('not found', err)


class CommandExecutorWebSocketTests(TestCase):
    def _make_ws_cmd(self):
        return HomeCommand(
            name='WS Cmd', command_type='websocket',
            ws_message={'event': 'light_on'},
        )

    @patch('channels.layers.get_channel_layer')
    @patch('asgiref.sync.async_to_sync')
    def test_websocket_success(self, mock_async_to_sync, mock_get_layer):
        mock_layer = MagicMock()
        mock_get_layer.return_value = mock_layer
        mock_send = MagicMock()
        mock_async_to_sync.return_value = mock_send

        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_ws_cmd())
        self.assertTrue(ok)
        mock_send.assert_called_once()
        args = mock_send.call_args[0]
        self.assertEqual(args[0], 'home_commands')

    @patch('channels.layers.get_channel_layer', side_effect=Exception('no layer'))
    def test_websocket_failure(self, mock_get_layer):
        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(self._make_ws_cmd())
        self.assertFalse(ok)


class CommandExecutorUnknownTypeTests(TestCase):
    def test_unknown_type(self):
        cmd = HomeCommand(name='X', command_type='grpc')
        from yolo_app.utils import command_executor
        ok, err = command_executor.execute(cmd)
        self.assertFalse(ok)
        self.assertIn('Unknown', err)


# ══════════════════════════════════════════════════════════════════════════════
# GESTURE ENGINE TESTS
# ══════════════════════════════════════════════════════════════════════════════

class GestureEngineTests(TestCase):
    def setUp(self):
        self.camera = make_camera()
        self.gesture_action = GestureAction.objects.create(
            name='thumbs_up', hold_frames=3, cooldown_seconds=5, enabled=True,
        )
        self.command = make_command()
        GestureCommandMapping.objects.create(
            gesture=self.gesture_action, command=self.command,
        )

    def _make_engine(self, mock_recognizer_cls):
        """Create a GestureEngine with a mocked GestureRecognizer."""
        mock_recognizer_cls.return_value = MagicMock()
        from yolo_app.utils.gesture_engine import GestureEngine
        engine = GestureEngine(self.camera.id)
        return engine

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    def test_no_gesture_returns_none(self, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = (None, [])
        frame = MagicMock()
        result = engine.process(frame)
        self.assertIsNone(result)
        self.assertIsNone(engine.latest_gesture)

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    def test_gesture_detected_but_hold_not_reached(self, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        with patch('yolo_app.utils.command_executor.execute') as mock_exec:
            engine.process(frame)   # frame 1 — hold_frames=3, count=1
            engine.process(frame)   # frame 2 — count=2
            mock_exec.assert_not_called()

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    @patch('yolo_app.utils.command_executor.execute', return_value=(True, ''))
    def test_gesture_triggers_after_hold_frames(self, mock_exec, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [(10, 10, 100, 100)])
        frame = MagicMock()

        for _ in range(3):   # hold_frames=3
            engine.process(frame)

        mock_exec.assert_called_once()

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    @patch('yolo_app.utils.command_executor.execute', return_value=(True, ''))
    def test_cooldown_prevents_retrigger(self, mock_exec, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        # First trigger
        for _ in range(3):
            engine.process(frame)
        self.assertEqual(mock_exec.call_count, 1)

        # Gesture continues holding — should NOT retrigger due to cooldown
        for _ in range(10):
            engine.process(frame)
        self.assertEqual(mock_exec.call_count, 1)

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    @patch('yolo_app.utils.command_executor.execute', return_value=(True, ''))
    def test_cooldown_expires_and_retriggers(self, mock_exec, mock_cls):
        import time as _time
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        # First trigger
        for _ in range(3):
            engine.process(frame)

        # Simulate cooldown expiry
        engine._last_trigger['thumbs_up'] = _time.monotonic() - 10
        engine._hold_counts['thumbs_up'] = 0

        for _ in range(3):
            engine.process(frame)

        self.assertEqual(mock_exec.call_count, 2)

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    def test_unregistered_gesture_does_not_trigger(self, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('victory', [])  # no DB entry
        frame = MagicMock()

        with patch('yolo_app.utils.command_executor.execute') as mock_exec:
            for _ in range(10):
                engine.process(frame)
            mock_exec.assert_not_called()

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    def test_different_gesture_resets_hold_count(self, mock_cls):
        engine = self._make_engine(mock_cls)
        frame = MagicMock()

        engine._recognizer.process.return_value = ('thumbs_up', [])
        engine.process(frame)
        engine.process(frame)
        self.assertEqual(engine._hold_counts.get('thumbs_up', 0), 2)

        # Switch to different gesture — thumbs_up count resets
        engine._recognizer.process.return_value = ('fist', [])
        engine.process(frame)
        self.assertEqual(engine._hold_counts.get('thumbs_up', 0), 0)

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    @patch('yolo_app.utils.command_executor.execute', return_value=(True, ''))
    def test_trigger_log_saved_on_success(self, mock_exec, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        for _ in range(3):
            engine.process(frame)

        self.assertEqual(GestureTriggerLog.objects.count(), 1)
        log = GestureTriggerLog.objects.first()
        self.assertEqual(log.gesture.name, 'thumbs_up')
        self.assertEqual(log.camera.id, self.camera.id)
        self.assertTrue(log.success)

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    @patch('yolo_app.utils.command_executor.execute', return_value=(False, 'timeout'))
    def test_trigger_log_saved_on_failure(self, mock_exec, mock_cls):
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        for _ in range(3):
            engine.process(frame)

        log = GestureTriggerLog.objects.first()
        self.assertFalse(log.success)
        self.assertEqual(log.error_message, 'timeout')

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    def test_disabled_gesture_action_not_triggered(self, mock_cls):
        self.gesture_action.enabled = False
        self.gesture_action.save()
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        with patch('yolo_app.utils.command_executor.execute') as mock_exec:
            for _ in range(10):
                engine.process(frame)
            mock_exec.assert_not_called()

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    @patch('yolo_app.utils.command_executor.execute', return_value=(True, ''))
    def test_disabled_command_skipped(self, mock_exec, mock_cls):
        self.command.enabled = False
        self.command.save()
        engine = self._make_engine(mock_cls)
        engine._recognizer.process.return_value = ('thumbs_up', [])
        frame = MagicMock()

        for _ in range(3):
            engine.process(frame)

        mock_exec.assert_not_called()

    @patch('yolo_app.utils.gesture_engine.GestureRecognizer')
    def test_close_calls_recognizer_close(self, mock_cls):
        engine = self._make_engine(mock_cls)
        engine.close()
        engine._recognizer.close.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET CONSUMER TESTS
# ══════════════════════════════════════════════════════════════════════════════

class CameraConsumerTests(TestCase):
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_connect_and_disconnect(self):
        from channels.testing import WebsocketCommunicator
        from yolo.asgi import application

        async def _test():
            comm = WebsocketCommunicator(application, '/ws/camera/1/')
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.disconnect()

        self._run(_test())

    def test_detection_event_broadcast(self):
        from channels.testing import WebsocketCommunicator
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        from yolo.asgi import application

        async def _test():
            comm = WebsocketCommunicator(application, '/ws/camera/42/')
            connected, _ = await comm.connect()
            self.assertTrue(connected)

            # Simulate a detection event broadcast from the server side
            channel_layer = get_channel_layer()
            await channel_layer.group_send('camera_42', {
                'type': 'detection_event',
                'event_id': 99,
                'labels': [{'label': 'person', 'confidence': 0.9}],
            })

            response = await comm.receive_json_from(timeout=3)
            self.assertEqual(response['event_id'], 99)
            self.assertEqual(response['labels'][0]['label'], 'person')
            await comm.disconnect()

        self._run(_test())


class HomeCommandConsumerTests(TestCase):
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_connect_and_disconnect(self):
        from channels.testing import WebsocketCommunicator
        from yolo.asgi import application

        async def _test():
            comm = WebsocketCommunicator(application, '/ws/home/')
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            await comm.disconnect()

        self._run(_test())

    def test_home_command_broadcast(self):
        from channels.testing import WebsocketCommunicator
        from channels.layers import get_channel_layer
        from yolo.asgi import application

        async def _test():
            comm = WebsocketCommunicator(application, '/ws/home/')
            connected, _ = await comm.connect()
            self.assertTrue(connected)

            channel_layer = get_channel_layer()
            await channel_layer.group_send('home_commands', {
                'type': 'home_command',
                'command': 'Turn On Light',
                'camera_id': 1,
                'gesture': 'thumbs_up',
            })

            response = await comm.receive_json_from(timeout=3)
            self.assertEqual(response['command'], 'Turn On Light')
            self.assertEqual(response['gesture'], 'thumbs_up')
            await comm.disconnect()

        self._run(_test())

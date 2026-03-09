"""
CommandExecutor: dispatches HomeCommand instances to their target systems.

Supported command types:
  http      — send an HTTP request (GET / POST / PUT / etc.)
  mqtt      — publish a message to an MQTT broker
  websocket — broadcast a JSON message to all connected WebSocket clients
  shell     — run a shell command / program via subprocess
"""

import json
import logging
import subprocess
import threading
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Optional MQTT client (lazy-loaded)
_mqtt_client = None
_mqtt_lock = threading.Lock()


def _get_mqtt_client():
    global _mqtt_client
    with _mqtt_lock:
        if _mqtt_client is None:
            try:
                import paho.mqtt.client as mqtt
                from django.conf import settings
                host = getattr(settings, 'MQTT_HOST', 'localhost')
                port = getattr(settings, 'MQTT_PORT', 1883)
                client = mqtt.Client()
                user = getattr(settings, 'MQTT_USER', None)
                password = getattr(settings, 'MQTT_PASSWORD', None)
                if user:
                    client.username_pw_set(user, password)
                client.connect(host, port, keepalive=60)
                client.loop_start()
                _mqtt_client = client
                logger.info('MQTT connected to %s:%d', host, port)
            except Exception as exc:
                logger.error('MQTT connection failed: %s', exc)
        return _mqtt_client


# ── Dispatcher ────────────────────────────────────────────────────────────────

def execute(command, context=None):
    """
    Execute a HomeCommand instance.
    context: optional dict merged into WebSocket broadcast payload.
    Returns (success: bool, error_message: str).
    """
    from yolo_app.models import HomeCommand
    try:
        if command.command_type == HomeCommand.COMMAND_HTTP:
            return _exec_http(command)
        elif command.command_type == HomeCommand.COMMAND_MQTT:
            return _exec_mqtt(command)
        elif command.command_type == HomeCommand.COMMAND_WS:
            return _exec_websocket(command, context)
        elif command.command_type == HomeCommand.COMMAND_SHELL:
            return _exec_shell(command)
        else:
            return False, f'Unknown command type: {command.command_type}'
    except Exception as exc:
        logger.exception('Unexpected error executing command %d (%s)', command.id, command.name)
        return False, str(exc)


def _exec_http(command):
    try:
        body = json.dumps(command.http_body).encode() if command.http_body else None
        headers = command.http_headers or {}
        if body and 'Content-Type' not in headers:
            headers['Content-Type'] = 'application/json'

        req = urllib.request.Request(
            url=command.http_url,
            data=body,
            headers=headers,
            method=command.http_method.upper(),
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
        logger.info('HTTP command "%s" → %s %s — status %d',
                    command.name, command.http_method, command.http_url, status)
        return True, ''
    except urllib.error.HTTPError as exc:
        msg = f'HTTP {exc.code}: {exc.reason}'
        logger.warning('HTTP command "%s" failed: %s', command.name, msg)
        return False, msg
    except Exception as exc:
        logger.warning('HTTP command "%s" error: %s', command.name, exc)
        return False, str(exc)


def _exec_mqtt(command):
    client = _get_mqtt_client()
    if client is None:
        return False, 'MQTT client not available'
    try:
        result = client.publish(command.mqtt_topic, command.mqtt_payload)
        result.wait_for_publish(timeout=3)
        logger.info('MQTT command "%s" → topic=%s payload=%s',
                    command.name, command.mqtt_topic, command.mqtt_payload)
        return True, ''
    except Exception as exc:
        logger.warning('MQTT command "%s" failed: %s', command.name, exc)
        return False, str(exc)


def _exec_shell(command):
    try:
        proc = subprocess.Popen(
            command.shell_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        # Don't wait — fire and forget so the gesture pipeline isn't blocked
        logger.info('Shell command "%s" launched  pid=%d cmd=%r',
                    command.name, proc.pid, command.shell_command)
        return True, ''
    except Exception as exc:
        logger.warning('Shell command "%s" failed: %s', command.name, exc)
        return False, str(exc)


def _exec_websocket(command, context=None):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        payload = dict(command.ws_message or {})
        payload['type'] = 'home_command'
        payload['command'] = command.name
        if context:
            payload.update(context)

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)('home_commands', payload)
        logger.info('WebSocket command "%s" broadcast', command.name)
        return True, ''
    except Exception as exc:
        logger.warning('WebSocket command "%s" failed: %s', command.name, exc)
        return False, str(exc)

import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)


class CameraConsumer(AsyncWebsocketConsumer):
    """
    WebSocket endpoint: ws://<host>/ws/camera/<camera_id>/

    Receives real-time detection alerts for a specific camera.
    """

    async def connect(self):
        self.camera_id = self.scope['url_route']['kwargs']['camera_id']
        self.group_name = f'camera_{self.camera_id}'
        client = self._client_info()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info('WebSocket CONNECT  camera=%s client=%s channel=%s',
                    self.camera_id, client, self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        logger.info('WebSocket DISCONNECT  camera=%s client=%s code=%s channel=%s',
                    self.camera_id, self._client_info(), close_code, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        logger.debug('WebSocket RECEIVE (unexpected)  camera=%s data=%r',
                     self.camera_id, text_data or bytes_data)

    async def detection_event(self, event):
        labels = event.get('labels', [])
        logger.debug('WebSocket SEND detection  camera=%s event_id=%s labels=%s',
                     self.camera_id, event.get('event_id'), [l['label'] for l in labels])
        await self.send(text_data=json.dumps(event))

    def _client_info(self):
        client = self.scope.get('client')
        if client:
            return f'{client[0]}:{client[1]}'
        headers = dict(self.scope.get('headers', []))
        return headers.get(b'x-forwarded-for', b'').decode() or 'unknown'


class HomeCommandConsumer(AsyncWebsocketConsumer):
    """
    WebSocket endpoint: ws://<host>/ws/home/

    App clients connect here to receive real-time home automation events:
    gesture triggers, command results, etc.
    """

    GROUP = 'home_commands'

    async def connect(self):
        client = self._client_info()
        await self.channel_layer.group_add(self.GROUP, self.channel_name)
        await self.accept()
        logger.info('HomeWS CONNECT  client=%s channel=%s', client, self.channel_name)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.GROUP, self.channel_name)
        logger.info('HomeWS DISCONNECT  client=%s code=%s channel=%s',
                    self._client_info(), close_code, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        logger.debug('HomeWS RECEIVE (unexpected)  data=%r', text_data or bytes_data)

    # Called when command_executor broadcasts a home_command event
    async def home_command(self, event):
        logger.info('HomeWS SEND home_command  command=%s camera=%s gesture=%s',
                    event.get('command'), event.get('camera_id'), event.get('gesture'))
        await self.send(text_data=json.dumps(event))

    def _client_info(self):
        client = self.scope.get('client')
        if client:
            return f'{client[0]}:{client[1]}'
        headers = dict(self.scope.get('headers', []))
        return headers.get(b'x-forwarded-for', b'').decode() or 'unknown'

import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from yolo_app.models import GestureAction, HomeCommand, GestureCommandMapping, GestureTriggerLog
from yolo_app.serializers import (
    GestureActionSerializer, HomeCommandSerializer,
    GestureCommandMappingSerializer, GestureTriggerLogSerializer,
)

logger = logging.getLogger(__name__)


# ── GestureAction ─────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def gesture_list(request):
    if request.method == 'GET':
        return Response(GestureActionSerializer(GestureAction.objects.all(), many=True).data)
    serializer = GestureActionSerializer(data=request.data)
    if serializer.is_valid():
        obj = serializer.save()
        logger.info('GestureAction created: %s', obj.name)
        return Response(GestureActionSerializer(obj).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def gesture_detail(request, gesture_id):
    try:
        obj = GestureAction.objects.get(pk=gesture_id)
    except GestureAction.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(GestureActionSerializer(obj).data)
    if request.method == 'PUT':
        serializer = GestureActionSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    obj.delete()
    logger.info('GestureAction deleted: id=%d', gesture_id)
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── HomeCommand ───────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def command_list(request):
    if request.method == 'GET':
        return Response(HomeCommandSerializer(HomeCommand.objects.all(), many=True).data)
    serializer = HomeCommandSerializer(data=request.data)
    if serializer.is_valid():
        obj = serializer.save()
        logger.info('HomeCommand created: %s (%s)', obj.name, obj.command_type)
        return Response(HomeCommandSerializer(obj).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def command_detail(request, command_id):
    try:
        obj = HomeCommand.objects.get(pk=command_id)
    except HomeCommand.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(HomeCommandSerializer(obj).data)
    if request.method == 'PUT':
        serializer = HomeCommandSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    obj.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
def command_test(request, command_id):
    """Manually fire a command for testing without needing a gesture."""
    try:
        obj = HomeCommand.objects.get(pk=command_id)
    except HomeCommand.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    from yolo_app.utils import command_executor
    success, error = command_executor.execute(obj, context={'source': 'manual_test'})
    logger.info('Command manual test  id=%d success=%s', command_id, success)
    if success:
        return Response({'status': 'ok'})
    return Response({'status': 'error', 'detail': error}, status=status.HTTP_502_BAD_GATEWAY)


# ── GestureCommandMapping ─────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
def mapping_list(request):
    if request.method == 'GET':
        return Response(GestureCommandMappingSerializer(
            GestureCommandMapping.objects.select_related('gesture', 'command', 'camera').all(),
            many=True,
        ).data)
    serializer = GestureCommandMappingSerializer(data=request.data)
    if serializer.is_valid():
        obj = serializer.save()
        logger.info('Mapping created: %s → %s', obj.gesture.name, obj.command.name)
        return Response(GestureCommandMappingSerializer(obj).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
def mapping_detail(request, mapping_id):
    try:
        obj = GestureCommandMapping.objects.get(pk=mapping_id)
    except GestureCommandMapping.DoesNotExist:
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(GestureCommandMappingSerializer(obj).data)
    if request.method == 'PUT':
        serializer = GestureCommandMappingSerializer(obj, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    obj.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Trigger Logs ──────────────────────────────────────────────────────────────

@api_view(['GET'])
def trigger_logs(request):
    logs = GestureTriggerLog.objects.select_related('camera', 'gesture', 'command')[:100]
    return Response(GestureTriggerLogSerializer(logs, many=True).data)

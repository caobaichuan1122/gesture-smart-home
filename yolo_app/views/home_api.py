import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse, inline_serializer
from rest_framework import serializers as drf_serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from yolo_app.models import GestureAction, HomeCommand, GestureCommandMapping, GestureTriggerLog
from yolo_app.serializers import (
    GestureActionSerializer, HomeCommandSerializer,
    GestureCommandMappingSerializer, GestureTriggerLogSerializer,
)

logger = logging.getLogger(__name__)


# ── GestureAction ─────────────────────────────────────────────────────────────

@extend_schema(
    tags=['gestures'],
    responses={200: GestureActionSerializer(many=True), 201: GestureActionSerializer},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def gesture_list(request):
    if request.method == 'GET':
        return Response(GestureActionSerializer(GestureAction.objects.all(), many=True).data)
    serializer = GestureActionSerializer(data=request.data)
    if serializer.is_valid():
        obj = serializer.save()
        logger.info('GestureAction created: %s', obj.name)
        return Response(GestureActionSerializer(obj).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['gestures'], responses={200: GestureActionSerializer, 204: None, 404: None})
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
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

@extend_schema(
    tags=['commands'],
    responses={200: HomeCommandSerializer(many=True), 201: HomeCommandSerializer},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def command_list(request):
    if request.method == 'GET':
        return Response(HomeCommandSerializer(HomeCommand.objects.all(), many=True).data)
    serializer = HomeCommandSerializer(data=request.data)
    if serializer.is_valid():
        obj = serializer.save()
        logger.info('HomeCommand created: %s (%s)', obj.name, obj.command_type)
        return Response(HomeCommandSerializer(obj).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['commands'], responses={200: HomeCommandSerializer, 204: None, 404: None})
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
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


@extend_schema(
    tags=['commands'],
    summary='Manually execute a command',
    description='Fire a HomeCommand immediately without waiting for a gesture trigger. Useful for testing device connectivity.',
    request=None,
    responses={
        200: inline_serializer('CommandTestOk', {'status': drf_serializers.CharField()}),
        502: inline_serializer('CommandTestError', {
            'status': drf_serializers.CharField(),
            'detail': drf_serializers.CharField(),
        }),
        404: None,
    },
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
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

@extend_schema(
    tags=['mappings'],
    responses={200: GestureCommandMappingSerializer(many=True), 201: GestureCommandMappingSerializer},
)
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
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


@extend_schema(tags=['mappings'], responses={200: GestureCommandMappingSerializer, 204: None, 404: None})
@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
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

@extend_schema(tags=['logs'], responses={200: GestureTriggerLogSerializer(many=True)})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trigger_logs(request):
    logs = GestureTriggerLog.objects.select_related('camera', 'gesture', 'command')[:100]
    return Response(GestureTriggerLogSerializer(logs, many=True).data)

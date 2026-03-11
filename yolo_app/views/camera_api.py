import cv2
import logging
import numpy as np
import time

from django.http import StreamingHttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_http_methods
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from yolo_app.models import Camera, DetectionEvent
from yolo_app.serializers import CameraSerializer, DetectionEventSerializer
from yolo_app.utils.camera_manager import camera_manager

logger = logging.getLogger(__name__)


# ── Camera CRUD ───────────────────────────────────────────────────────────────

@extend_schema(
    tags=['cameras'],
    responses={200: CameraSerializer(many=True), 201: CameraSerializer},
)
@api_view(['GET', 'POST'])
def camera_list(request):
    if request.method == 'GET':
        cameras = Camera.objects.all()
        logger.debug('GET camera_list  count=%d', cameras.count())
        return Response(CameraSerializer(cameras, many=True).data)

    serializer = CameraSerializer(data=request.data)
    if serializer.is_valid():
        camera = serializer.save()
        logger.info('Camera created  id=%d name=%r source=%r', camera.id, camera.name, camera.source)
        if camera.enabled:
            camera_manager.start_camera(camera)
        return Response(CameraSerializer(camera).data, status=status.HTTP_201_CREATED)

    logger.warning('Camera create validation failed  errors=%s', serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=['cameras'], responses={200: CameraSerializer, 204: None, 404: None})
@api_view(['GET', 'PUT', 'DELETE'])
def camera_detail(request, camera_id):
    try:
        camera = Camera.objects.get(pk=camera_id)
    except Camera.DoesNotExist:
        logger.warning('Camera not found  id=%d method=%s', camera_id, request.method)
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        logger.debug('GET camera_detail  id=%d', camera_id)
        return Response(CameraSerializer(camera).data)

    if request.method == 'PUT':
        serializer = CameraSerializer(camera, data=request.data, partial=True)
        if serializer.is_valid():
            camera = serializer.save()
            logger.info('Camera updated  id=%d enabled=%s yolo=%s', camera.id, camera.enabled, camera.yolo_enabled)
            camera_manager.stop_camera(camera.id)
            if camera.enabled:
                camera_manager.start_camera(camera)
            return Response(CameraSerializer(camera).data)
        logger.warning('Camera update validation failed  id=%d errors=%s', camera_id, serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE
    logger.info('Camera deleted  id=%d name=%r', camera.id, camera.name)
    camera_manager.stop_camera(camera.id)
    camera.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── MJPEG Video Stream ────────────────────────────────────────────────────────

def _blank_frame(message='Connecting...'):
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(blank, message, (140, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    _, buf = cv2.imencode('.jpg', blank)
    return buf.tobytes()


# Plain Django view — do NOT wrap with @api_view, it breaks StreamingHttpResponse
@require_http_methods(['GET'])
def camera_stream(request, camera_id):
    try:
        camera = Camera.objects.get(pk=camera_id)
    except Camera.DoesNotExist:
        logger.warning('Stream requested for unknown camera  id=%d', camera_id)
        return JsonResponse({'error': 'Not found'}, status=404)

    if not camera.enabled:
        logger.warning('Stream requested for disabled camera  id=%d', camera_id)
        return JsonResponse({'error': 'Camera is disabled'}, status=400)

    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
    logger.info('Stream OPEN  camera=%d client=%s', camera_id, client_ip)

    # Capture directly in the request thread — avoids Windows DirectShow
    # threading issues where cap.read() silently fails in background threads.
    def generate():
        import sys
        # Increment stream-client counter so self-capture stands down immediately
        camera_manager.mark_stream_active(camera_id)

        src = camera.source
        try:
            src = int(src)
        except (ValueError, TypeError):
            pass

        # On Windows use DirectShow; it works reliably in the request thread
        def _open_cap(source):
            if sys.platform == 'win32' and isinstance(source, int):
                c = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                c = cv2.VideoCapture(source)
            if c.isOpened():
                # Request a reasonable resolution; some drivers default to max
                c.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                c.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                c.set(cv2.CAP_PROP_FPS, 30)
            return c

        cap = _open_cap(src)

        if not cap.isOpened():
            logger.error('Stream: cannot open camera %d (source=%r)', camera_id, camera.source)
            camera_manager.mark_stream_inactive(camera_id)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + _blank_frame('Cannot open camera') + b'\r\n')
            return

        # Warm up: DirectShow needs many frames before it produces clean output.
        # Keep reading until we get a non-black frame (or hit the 5 s deadline).
        logger.info('Stream: warming up camera %d ...', camera_id)
        frame = None
        deadline = time.time() + 5.0
        warm_count = 0
        while time.time() < deadline:
            try:
                ret, f = cap.read()
            except cv2.error as exc:
                logger.warning('Stream: warm-up cv2.error camera=%d, reopening: %s', camera_id, exc)
                cap.release()
                time.sleep(1.0)
                cap = _open_cap(src)
                continue
            if ret and f is not None:
                warm_count += 1
                frame = f          # keep latest valid frame
                if warm_count >= 5:  # 5 frames is enough to settle
                    break
            else:
                time.sleep(0.05)

        logger.info('Stream: camera %d warm-up read %d frames', camera_id, warm_count)

        if frame is None:
            logger.error('Stream: camera %d failed to produce a frame during warm-up', camera_id)
            cap.release()
            camera_manager.mark_stream_inactive(camera_id)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                   + _blank_frame('Camera not ready') + b'\r\n')
            return

        logger.info('Stream: camera %d warm-up done, streaming', camera_id)

        # Start the background processor (handles detection events + WebSocket)
        camera_manager.ensure_processor(camera)

        try:
            frame_count = 0
            consecutive_failures = 0
            while True:
                try:
                    ret, frame = cap.read()
                except cv2.error as exc:
                    logger.warning('Stream: cap.read() cv2.error camera=%d, reopening: %s', camera_id, exc)
                    cap.release()
                    time.sleep(1.0)
                    cap = _open_cap(src)
                    consecutive_failures = 0
                    continue

                if not ret:
                    consecutive_failures += 1
                    if consecutive_failures >= 30:
                        logger.error('Stream: camera %d too many read failures, closing', camera_id)
                        break
                    time.sleep(0.033)
                    continue
                consecutive_failures = 0
                frame_count += 1

                # Push every 3rd frame to the processor (detection doesn't need 30fps)
                if frame_count % 3 == 0:
                    try:
                        camera_manager.push_frame(camera_id, frame.copy())
                    except Exception as exc:
                        logger.warning('Stream: push_frame error: %s', exc)

                # Draw gesture overlay if available
                gesture_name, boxes = camera_manager.get_gesture_overlay(camera_id)
                if boxes:
                    overlay = frame.copy()
                    for (x1, y1, x2, y2) in boxes:
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 128), 2)
                    if gesture_name:
                        cv2.putText(overlay, gesture_name, (boxes[0][0], max(boxes[0][1] - 10, 20)),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 128), 2)
                    encode_frame = overlay
                else:
                    encode_frame = frame

                _, buffer = cv2.imencode('.jpg', encode_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if buffer is not None:
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n'
                           + buffer.tobytes() + b'\r\n')
                time.sleep(0.033)   # ~30 fps
        except GeneratorExit:
            logger.info('Stream CLOSED  camera=%d client=%s', camera_id, client_ip)
        except Exception as exc:
            logger.error('Stream: unexpected error camera=%d: %s', camera_id, exc, exc_info=True)
        finally:
            cap.release()
            camera_manager.mark_stream_inactive(camera_id)
            logger.info('Stream: camera %d released', camera_id)

    response = StreamingHttpResponse(
        generate(),
        content_type='multipart/x-mixed-replace; boundary=frame',
    )
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ── Detection Events ──────────────────────────────────────────────────────────

@extend_schema(tags=['events'], responses={200: DetectionEventSerializer(many=True), 404: None})
@api_view(['GET'])
def camera_events(request, camera_id):
    try:
        Camera.objects.get(pk=camera_id)
    except Camera.DoesNotExist:
        logger.warning('Events requested for unknown camera  id=%d', camera_id)
        return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    events = DetectionEvent.objects.filter(camera_id=camera_id)[:50]
    logger.debug('GET camera_events  camera=%d count=%d', camera_id, events.count())
    return Response(DetectionEventSerializer(events, many=True).data)


@extend_schema(tags=['events'], responses={200: DetectionEventSerializer(many=True)})
@api_view(['GET'])
def all_events(request):
    events = DetectionEvent.objects.select_related('camera')[:100]
    logger.debug('GET all_events  count=%d', events.count())
    return Response(DetectionEventSerializer(events, many=True).data)


# ── Single snapshot (for debugging) ──────────────────────────────────────────

@require_http_methods(['GET'])
def camera_snapshot(request, camera_id):
    """Return a single JPEG frame captured directly from the camera."""
    try:
        camera = Camera.objects.get(pk=camera_id)
    except Camera.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    import sys
    from django.http import HttpResponse
    src = camera.source
    try:
        src = int(src)
    except (ValueError, TypeError):
        pass

    if sys.platform == 'win32' and isinstance(src, int):
        cap = cv2.VideoCapture(src, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        return JsonResponse({'error': 'Cannot open camera'}, status=503)

    # Discard the first few frames — DirectShow needs a moment to warm up
    # before it produces a clean image.
    frame = None
    for _ in range(5):
        ret, frame = cap.read()
    cap.release()

    if frame is None or not ret:
        return JsonResponse({'error': 'No frame available'}, status=503)

    _, buf = cv2.imencode('.jpg', frame)
    return HttpResponse(buf.tobytes(), content_type='image/jpeg')


@extend_schema(tags=['cameras'])
@api_view(['GET'])
def camera_status(request, camera_id):
    """Return worker status — useful for debugging."""
    worker = camera_manager._workers.get(camera_id)
    frame = camera_manager.get_frame(camera_id)
    return Response({
        'camera_id': camera_id,
        'worker_running': worker.is_alive() if worker else False,
        'has_frame': frame is not None,
        'frame_size': len(frame) if frame else 0,
    })


# ── HTML viewer page ──────────────────────────────────────────────────────────

def camera_view(request, camera_id):
    get_object_or_404(Camera, pk=camera_id)
    return render(request, 'camera_view.html', {'camera_id': camera_id})

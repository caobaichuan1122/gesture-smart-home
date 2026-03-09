"""
CameraManager: frame processing pipeline.

Architecture
------------
CameraProcessor (one per camera) runs in a background thread.
It processes frames from two sources:

  1. push_frame()  — frames pushed by the HTTP stream view (browser watching).
  2. Self-capture  — when gesture_enabled=True, the processor opens the camera
                     itself so gesture recognition works with no browser open.

Self-capture automatically yields to the HTTP stream: as long as push_frame()
is being called (stream is open), the self-capture loop stays idle and releases
the camera device.  When the stream closes the self-capture resumes after ~2 s.
"""

import queue
import sys
import threading
import time
import logging
import cv2

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def _open_cap(source):
    """Open a cv2.VideoCapture, using DirectShow on Windows for local cameras."""
    if sys.platform == 'win32' and isinstance(source, int):
        cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(source)
    if cap.isOpened():
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
    return cap


class CameraProcessor(threading.Thread):
    """
    Background thread that processes frames for one camera.
    Runs YOLO detection and/or gesture recognition.
    """

    def __init__(self, camera_id, camera_source, yolo_enabled=True, gesture_enabled=False):
        super().__init__(daemon=True, name=f'cam-proc-{camera_id}')
        self.camera_id = camera_id
        self.camera_source = camera_source
        self.yolo_enabled = yolo_enabled
        self.gesture_enabled = gesture_enabled

        self._stop_event = threading.Event()
        # Only keep the latest frame; drop stale ones
        self._frame_queue = queue.Queue(maxsize=2)
        self._yolo = None
        self._gesture_engine = None

        # Number of active HTTP stream clients on this camera
        self._stream_clients = 0
        self._stream_lock = threading.Lock()
        # Set when self-capture is NOT holding the camera device
        self._capture_idle = threading.Event()
        self._capture_idle.set()  # initially idle

    # ── Setup ──────────────────────────────────────────────────────────────────

    def _load_yolo(self):
        if not self.yolo_enabled:
            return
        try:
            from yolo_app.utils.yolo import YOLO
            self._yolo = YOLO('yolov5s.pt')
            logger.info('Processor %d: YOLO loaded', self.camera_id)
        except Exception as exc:
            logger.warning('Processor %d: YOLO load failed: %s', self.camera_id, exc)

    def _load_gesture_engine(self):
        if not self.gesture_enabled:
            return
        try:
            from yolo_app.utils.gesture_engine import GestureEngine
            self._gesture_engine = GestureEngine(self.camera_id)
            logger.info('Processor %d: gesture engine loaded', self.camera_id)
        except Exception as exc:
            logger.warning('Processor %d: gesture engine load failed: %s', self.camera_id, exc)

    # ── Self-capture thread ────────────────────────────────────────────────────

    def _self_capture_loop(self):
        """
        Opens the camera and pushes frames when no HTTP stream is active.
        Yields automatically when push_frame() is being called externally.
        """
        logger.info('Processor %d: self-capture thread started', self.camera_id)
        cap = None
        frame_count = 0

        try:
            src = self.camera_source
            try:
                src = int(src)
            except (ValueError, TypeError):
                pass

            while not self._stop_event.is_set():
                with self._stream_lock:
                    stream_active = self._stream_clients > 0

                if stream_active:
                    # HTTP stream is feeding frames — release camera if open
                    if cap is not None:
                        cap.release()
                        cap = None
                        self._capture_idle.set()
                        logger.info('Processor %d: self-capture paused (stream active)', self.camera_id)
                    time.sleep(0.5)
                    continue

                # No external stream — open camera if needed
                if cap is None or not cap.isOpened():
                    logger.info('Processor %d: self-capture opening camera source=%r', self.camera_id, src)
                    self._capture_idle.clear()
                    cap = _open_cap(src)
                    frame_count = 0
                    if not cap.isOpened():
                        logger.warning('Processor %d: self-capture cannot open camera, retry in 5s', self.camera_id)
                        cap = None
                        time.sleep(5.0)
                        continue
                    # Warm-up frames
                    for _ in range(5):
                        cap.read()
                    logger.info('Processor %d: self-capture ready', self.camera_id)

                ret, frame = cap.read()
                if not ret or frame is None:
                    logger.warning('Processor %d: self-capture read failed, reopening', self.camera_id)
                    cap.release()
                    cap = None
                    time.sleep(1.0)
                    continue

                frame_count += 1
                # Push every 3rd frame (gesture doesn't need 30 fps)
                if frame_count % 3 == 0:
                    self._enqueue(frame)

                time.sleep(0.033)  # ~30 fps capture rate

        except Exception as exc:
            logger.error('Processor %d: self-capture unexpected error: %s', self.camera_id, exc, exc_info=True)
        finally:
            if cap is not None:
                cap.release()
            self._capture_idle.set()
            logger.info('Processor %d: self-capture thread stopped', self.camera_id)

    # ── Main processing loop ───────────────────────────────────────────────────

    def run(self):
        self._load_yolo()
        self._load_gesture_engine()

        # Start self-capture if gesture recognition is enabled
        if self.gesture_enabled:
            t = threading.Thread(target=self._self_capture_loop, daemon=True,
                                 name=f'cam-capture-{self.camera_id}')
            t.start()

        logger.info('Processor %d: ready', self.camera_id)

        while not self._stop_event.is_set():
            try:
                frame = self._frame_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            # ── YOLO detection ─────────────────────────────────────────────
            detections = []
            if self._yolo:
                try:
                    detections = self._yolo.detect(frame)
                except Exception as exc:
                    logger.warning('Processor %d: YOLO error: %s', self.camera_id, exc)

            if detections:
                annotated = frame.copy()
                for d in detections:
                    x1, y1 = int(d['xmin']), int(d['ymin'])
                    x2, y2 = int(d['xmax']), int(d['ymax'])
                    label = f"{d['name']} {d['confidence']:.2f}"
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(annotated, label, (x1, y1 - 8),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                _, snap_buf = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if snap_buf is not None:
                    self._save_event_and_notify(snap_buf.tobytes(), detections)

            # ── Gesture recognition ────────────────────────────────────────
            if self._gesture_engine:
                try:
                    _, jpeg_buf = cv2.imencode('.jpg', frame)
                    self._gesture_engine.process(
                        frame, jpeg_buf.tobytes() if jpeg_buf is not None else None
                    )
                except Exception as exc:
                    logger.warning('Processor %d: gesture error: %s', self.camera_id, exc)

        if self._gesture_engine:
            self._gesture_engine.close()
        logger.info('Processor %d: stopped', self.camera_id)

    # ── Public API ─────────────────────────────────────────────────────────────

    def push_frame(self, frame):
        """Called from the HTTP stream view with each captured BGR frame."""
        self._enqueue(frame)

    def stop(self):
        self._stop_event.set()

    # ── Internals ──────────────────────────────────────────────────────────────

    def _enqueue(self, frame):
        try:
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
            self._frame_queue.put_nowait(frame)
        except queue.Full:
            pass

    def _save_event_and_notify(self, jpeg_bytes, detections):
        try:
            from django.core.files.base import ContentFile
            from yolo_app.models import DetectionEvent, Camera

            camera = Camera.objects.get(pk=self.camera_id)
            labels = [
                {'label': d['name'], 'confidence': round(float(d['confidence']), 3)}
                for d in detections
            ]
            event = DetectionEvent(camera=camera, labels=labels)
            filename = f'cam{self.camera_id}_{int(time.time())}.jpg'
            event.snapshot.save(filename, ContentFile(jpeg_bytes), save=True)

            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'camera_{self.camera_id}',
                {
                    'type': 'detection_event',
                    'event_id': event.id,
                    'camera_id': self.camera_id,
                    'labels': labels,
                    'detected_at': event.detected_at.isoformat(),
                }
            )
        except Exception as exc:
            logger.warning('Processor %d: event save error: %s', self.camera_id, exc)


class CameraManager:
    """
    Singleton registry of CameraProcessor instances.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._processors = {}
        return cls._instance

    def ensure_processor(self, camera):
        """Start a processor for this camera if not already running."""
        cid = camera.id
        proc = self._processors.get(cid)
        if proc and proc.is_alive():
            return proc
        proc = CameraProcessor(
            cid,
            camera_source=camera.source,
            yolo_enabled=camera.yolo_enabled,
            gesture_enabled=camera.gesture_enabled,
        )
        self._processors[cid] = proc
        proc.start()
        return proc

    def mark_stream_active(self, camera_id):
        """
        Call before the HTTP stream opens the camera device.
        Increments the stream-client counter and waits until self-capture has
        released the camera (up to 2 s) before returning.
        """
        proc = self._processors.get(camera_id)
        if proc and proc.is_alive():
            with proc._stream_lock:
                proc._stream_clients += 1
            # Wait for self-capture to release the device (normally < 50 ms)
            proc._capture_idle.wait(timeout=2.0)

    def mark_stream_inactive(self, camera_id):
        """Call when an HTTP stream closes."""
        proc = self._processors.get(camera_id)
        if proc and proc.is_alive():
            with proc._stream_lock:
                proc._stream_clients = max(0, proc._stream_clients - 1)

    def get_gesture_overlay(self, camera_id):
        """Return (gesture_name, boxes) from the latest processed frame."""
        proc = self._processors.get(camera_id)
        if proc and proc.is_alive() and proc._gesture_engine:
            return proc._gesture_engine.latest_gesture, proc._gesture_engine.latest_boxes
        return None, []

    def push_frame(self, camera_id, frame):
        """Forward a captured frame to the processor for detection."""
        proc = self._processors.get(camera_id)
        if proc and proc.is_alive():
            proc.push_frame(frame)

    def stop_camera(self, camera_id):
        proc = self._processors.pop(camera_id, None)
        if proc:
            proc.stop()

    def start_all(self):
        """Start processors for every enabled camera in the database."""
        from yolo_app.models import Camera
        for cam in Camera.objects.filter(enabled=True):
            self.ensure_processor(cam)

    def stop_all(self):
        for cid in list(self._processors.keys()):
            self.stop_camera(cid)

    # Keep old name for compatibility
    def start_camera(self, camera):
        self.ensure_processor(camera)

    @property
    def _workers(self):
        return self._processors


camera_manager = CameraManager()

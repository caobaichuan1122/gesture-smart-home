"""
GestureEngine: wraps GestureRecognizer with hold-frame debouncing,
per-gesture cooldown, DB mapping lookup, command execution, and logging.

Usage (inside CameraWorker):
    engine = GestureEngine(camera_id)
    engine.process(frame, jpeg_bytes)   # call every frame
    engine.close()
"""

import logging
import time

from yolo_app.utils.gesture_recognizer import GestureRecognizer
from yolo_app.utils import command_executor

logger = logging.getLogger(__name__)


class GestureEngine:
    def __init__(self, camera_id):
        self.camera_id = camera_id
        self._recognizer = GestureRecognizer()

        # gesture_name → consecutive frame count
        self._hold_counts = {}
        # gesture_name → last trigger timestamp
        self._last_trigger = {}

        # Latest overlay data for the stream view to draw
        self.latest_gesture = None   # str or None
        self.latest_boxes = []       # list of (x1,y1,x2,y2)

    def process(self, frame_bgr, jpeg_bytes=None):
        """
        Analyse one frame. Fires a command if a gesture is held long enough
        and is past its cooldown period.
        Returns the detected gesture name (str) or None.
        """
        gesture, boxes = self._recognizer.process(frame_bgr)

        # Update overlay data (read by stream view)
        self.latest_gesture = gesture
        self.latest_boxes = boxes

        if gesture:
            self._hold_counts[gesture] = self._hold_counts.get(gesture, 0) + 1
            # Reset counts for any other gesture
            for g in list(self._hold_counts):
                if g != gesture:
                    self._hold_counts[g] = 0
            logger.debug('Gesture detected  camera=%d gesture=%s hold=%d',
                         self.camera_id, gesture, self._hold_counts[gesture])
        else:
            self._hold_counts = {}

        if gesture:
            self._maybe_trigger(gesture, frame_bgr, jpeg_bytes)

        return gesture

    def _maybe_trigger(self, gesture_name, frame_bgr, jpeg_bytes):
        from yolo_app.models import GestureAction, GestureCommandMapping

        try:
            action = GestureAction.objects.get(name=gesture_name, enabled=True)
        except GestureAction.DoesNotExist:
            return  # No DB entry for this gesture — ignore

        hold = self._hold_counts.get(gesture_name, 0)
        if hold < action.hold_frames:
            return  # Not held long enough yet

        now = time.monotonic()
        last = self._last_trigger.get(gesture_name, 0)
        if now - last < action.cooldown_seconds:
            return  # Still in cooldown

        # Find all applicable mappings for this camera
        mappings = GestureCommandMapping.objects.filter(
            gesture=action,
            enabled=True,
        ).filter(
            # camera-specific OR global (camera=None)
            camera_id__in=[self.camera_id, None]
        ).select_related('command')

        if not mappings.exists():
            return

        self._last_trigger[gesture_name] = now
        self._hold_counts[gesture_name] = 0  # reset so it must be held again

        logger.info('Gesture TRIGGERED  camera=%d gesture=%s', self.camera_id, gesture_name)

        for mapping in mappings:
            cmd = mapping.command
            if not cmd.enabled:
                continue
            context = {'camera_id': self.camera_id, 'gesture': gesture_name}
            success, error = command_executor.execute(cmd, context=context)
            self._log_trigger(action, cmd, success, error, jpeg_bytes)

    def _log_trigger(self, action, command, success, error, jpeg_bytes):
        from yolo_app.models import GestureTriggerLog, Camera
        from django.core.files.base import ContentFile

        try:
            camera = Camera.objects.get(pk=self.camera_id)
            log = GestureTriggerLog(
                camera=camera,
                gesture=action,
                command=command,
                success=success,
                error_message=error or '',
            )
            if jpeg_bytes:
                filename = f'gesture_{self.camera_id}_{action.name}_{int(time.time())}.jpg'
                log.snapshot.save(filename, ContentFile(jpeg_bytes), save=False)
            log.save()
        except Exception as exc:
            logger.warning('Failed to save GestureTriggerLog: %s', exc)

    def close(self):
        self._recognizer.close()

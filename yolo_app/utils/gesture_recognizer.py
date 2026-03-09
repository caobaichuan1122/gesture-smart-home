"""
GestureRecognizer: detects body and hand gestures from a BGR frame.

Uses MediaPipe Tasks API (0.10+):
  - GestureRecognizer task  → hand gestures
  - PoseLandmarker task     → body pose gestures

Built-in gestures
-----------------
Body pose (requires upper body visible):
  raise_right_hand  — right wrist above right shoulder
  raise_left_hand   — left wrist above left shoulder
  raise_both_hands  — both wrists above both shoulders
  t_pose            — both wrists level with shoulders, arms spread wide
  clap              — both wrists close together at chest height

Hand gesture (from MediaPipe built-in model):
  thumbs_up, thumbs_down, victory, pointing_up, open_palm, fist, wave (inferred)
"""

import logging
import os
import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Paths to .task model files (relative to project root)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GESTURE_MODEL = os.path.join(_BASE_DIR, 'gesture_recognizer.task')
_POSE_MODEL = os.path.join(_BASE_DIR, 'pose_landmarker.task')

_mp_tasks = None


def _load_mediapipe():
    global _mp_tasks
    if _mp_tasks is not None:
        return True
    try:
        from mediapipe.tasks.python import vision  # noqa: F401
        import mediapipe as mp
        _mp_tasks = mp.tasks
        logger.info('MediaPipe Tasks API loaded')
        return True
    except ImportError:
        logger.error('mediapipe not installed — gesture recognition disabled')
        return False


# ── Pose landmark indices (MediaPipe Pose) ────────────────────────────────────
_L_SHOULDER = 11
_R_SHOULDER = 12
_L_ELBOW    = 13
_R_ELBOW    = 14
_L_WRIST    = 15
_R_WRIST    = 16
_L_HIP      = 23
_R_HIP      = 24


def _classify_body(landmarks):
    """Return a body gesture name or None from PoseLandmarker results."""
    if not landmarks:
        return None

    def lm(idx):
        l = landmarks[idx]
        return l.x, l.y, l.visibility if hasattr(l, 'visibility') else 1.0

    rx, ry, rv = lm(_R_WRIST)
    lx, ly, lv = lm(_L_WRIST)
    rsx, rsy, _ = lm(_R_SHOULDER)
    lsx, lsy, _ = lm(_L_SHOULDER)
    rhx, rhy, _ = lm(_R_HIP)
    lhx, lhy, _ = lm(_L_HIP)

    r_vis = rv > 0.5
    l_vis = lv > 0.5

    r_raised = r_vis and (ry < rsy - 0.1)
    l_raised = l_vis and (ly < lsy - 0.1)

    if r_raised and l_raised:
        return 'raise_both_hands'
    if r_raised:
        return 'raise_right_hand'
    if l_raised:
        return 'raise_left_hand'

    r_tpose = r_vis and abs(ry - rsy) < 0.1 and abs(rx - rsx) > 0.25
    l_tpose = l_vis and abs(ly - lsy) < 0.1 and abs(lx - lsx) > 0.25
    if r_tpose and l_tpose:
        return 't_pose'

    mid_y = (rsy + lsy + rhy + lhy) / 4
    wrist_dist = np.sqrt((rx - lx) ** 2 + (ry - ly) ** 2)
    if wrist_dist < 0.12 and r_vis and l_vis and abs(ry - mid_y) < 0.2:
        return 'clap'

    return None


def _hand_boxes(hand_landmarks_list, w, h, pad=20):
    """Return bounding boxes for each detected hand."""
    boxes = []
    for hand_lm in hand_landmarks_list:
        xs = [lm.x * w for lm in hand_lm]
        ys = [lm.y * h for lm in hand_lm]
        x1 = max(0, int(min(xs)) - pad)
        y1 = max(0, int(min(ys)) - pad)
        x2 = min(w, int(max(xs)) + pad)
        y2 = min(h, int(max(ys)) + pad)
        boxes.append((x1, y1, x2, y2))
    return boxes


def _pose_boxes(landmarks, w, h, pad=20):
    """Return a bounding box around the upper body joints."""
    joints = [_L_SHOULDER, _R_SHOULDER, _L_ELBOW, _R_ELBOW, _L_WRIST, _R_WRIST]
    xs, ys = [], []
    for idx in joints:
        lm = landmarks[idx]
        vis = lm.visibility if hasattr(lm, 'visibility') else 1.0
        if vis > 0.4:
            xs.append(lm.x * w)
            ys.append(lm.y * h)
    if not xs:
        return []
    x1 = max(0, int(min(xs)) - pad)
    y1 = max(0, int(min(ys)) - pad)
    x2 = min(w, int(max(xs)) + pad)
    y2 = min(h, int(max(ys)) + pad)
    return [(x1, y1, x2, y2)]


class GestureRecognizer:
    """
    Stateful recognizer: call process(frame) each frame.
    Returns the currently held gesture name (str) or None.
    """

    def __init__(self):
        self._gesture_rec = None
        self._pose_rec = None
        self._wrist_history = []
        self._loaded = False

    def _ensure_loaded(self):
        if self._loaded:
            return self._gesture_rec is not None or self._pose_rec is not None
        self._loaded = True

        if not _load_mediapipe():
            return False

        import mediapipe as mp
        BaseOptions = mp.tasks.BaseOptions
        VisionRunningMode = mp.tasks.vision.RunningMode

        # ── Gesture recognizer ────────────────────────────────────────────────
        if os.path.exists(_GESTURE_MODEL):
            try:
                GestureRecognizerTask = mp.tasks.vision.GestureRecognizer
                opts = mp.tasks.vision.GestureRecognizerOptions(
                    base_options=BaseOptions(model_asset_path=_GESTURE_MODEL),
                    running_mode=VisionRunningMode.IMAGE,
                    num_hands=2,
                )
                self._gesture_rec = GestureRecognizerTask.create_from_options(opts)
                logger.info('GestureRecognizer task loaded')
            except Exception as e:
                logger.warning('GestureRecognizer task load failed: %s', e)
        else:
            logger.warning('gesture_recognizer.task not found at %s', _GESTURE_MODEL)

        # ── Pose landmarker ───────────────────────────────────────────────────
        if os.path.exists(_POSE_MODEL):
            try:
                PoseLandmarker = mp.tasks.vision.PoseLandmarker
                pose_opts = mp.tasks.vision.PoseLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=_POSE_MODEL),
                    running_mode=VisionRunningMode.IMAGE,
                )
                self._pose_rec = PoseLandmarker.create_from_options(pose_opts)
                logger.info('PoseLandmarker task loaded')
            except Exception as e:
                logger.warning('PoseLandmarker task load failed: %s', e)
        else:
            logger.warning('pose_landmarker.task not found at %s', _POSE_MODEL)

        return self._gesture_rec is not None or self._pose_rec is not None

    def process(self, frame_bgr):
        """
        Process one BGR frame.
        Returns (gesture_name, boxes) where:
          gesture_name — str or None
          boxes        — list of (x1, y1, x2, y2) pixel rects to highlight
        """
        if not self._ensure_loaded():
            return None, []

        import mediapipe as mp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # ── Body pose ─────────────────────────────────────────────────────────
        if self._pose_rec:
            try:
                pose_result = self._pose_rec.detect(mp_image)
                if pose_result.pose_landmarks:
                    gesture = _classify_body(pose_result.pose_landmarks[0])
                    if gesture:
                        boxes = _pose_boxes(pose_result.pose_landmarks[0], w, h)
                        return gesture, boxes
            except Exception as e:
                logger.debug('Pose detection error: %s', e)

        # ── Hand gesture ──────────────────────────────────────────────────────
        if self._gesture_rec:
            try:
                result = self._gesture_rec.recognize(mp_image)
                if result.gestures:
                    name = result.gestures[0][0].category_name.lower()
                    _name_map = {
                        'thumb_up': 'thumbs_up',
                        'thumb_down': 'thumbs_down',
                        'open_palm': 'open_palm',
                        'closed_fist': 'fist',
                        'victory': 'victory',
                        'pointing_up': 'pointing_up',
                        'iloveyou': 'iloveyou',
                        'none': None,
                    }
                    mapped = _name_map.get(name, name)
                    if mapped:
                        boxes = _hand_boxes(result.hand_landmarks, w, h)
                        return mapped, boxes
            except Exception as e:
                logger.debug('Hand gesture error: %s', e)

        return None, []

    def close(self):
        if self._gesture_rec:
            self._gesture_rec.close()
            self._gesture_rec = None
        if self._pose_rec:
            self._pose_rec.close()
            self._pose_rec = None

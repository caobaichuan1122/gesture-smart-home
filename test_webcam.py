"""
Quick webcam test — runs YOLO detection and gesture recognition
on the local camera and shows results in the terminal.
No server needed.

Usage:
    python test_webcam.py            # YOLO + gesture, camera 0
    python test_webcam.py --no-yolo  # gesture only (faster)
    python test_webcam.py --no-gesture
    python test_webcam.py --camera 1 # use a different camera index
"""

import argparse
import time
import cv2

parser = argparse.ArgumentParser()
parser.add_argument('--camera', type=int, default=0)
parser.add_argument('--no-yolo', action='store_true')
parser.add_argument('--no-gesture', action='store_true')
args = parser.parse_args()

print(f'Opening camera {args.camera} ...')
import sys
# Prefer DirectShow on Windows — more reliable for local webcams
if sys.platform == 'win32':
    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
else:
    cap = cv2.VideoCapture(args.camera)
if not cap.isOpened():
    print(f'ERROR: cannot open camera {args.camera}')
    raise SystemExit(1)

# ── Load YOLO ─────────────────────────────────────────────────────────────────
yolo = None
if not args.no_yolo:
    print('Loading YOLO model (yolov5s.pt) ...')
    try:
        from yolo_app.utils.yolo import YOLO
        yolo = YOLO('yolov5s.pt')
        print('YOLO ready.')
    except Exception as e:
        print(f'YOLO load failed: {e}')

# ── Load gesture recognizer ───────────────────────────────────────────────────
gesture_rec = None
if not args.no_gesture:
    print('Loading MediaPipe gesture recognizer ...')
    try:
        from yolo_app.utils.gesture_recognizer import GestureRecognizer
        gesture_rec = GestureRecognizer()
        print('Gesture recognizer ready.')
    except Exception as e:
        print(f'Gesture recognizer load failed: {e}')

print('\n--- Starting capture. Press Ctrl+C to stop. ---\n')

frame_count = 0
last_gesture = None
last_gesture_time = 0

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print('Frame read failed.')
            time.sleep(0.1)
            continue

        frame_count += 1

        # ── YOLO detection ────────────────────────────────────────────────────
        if yolo and frame_count % 3 == 0:   # run every 3rd frame
            try:
                detections = yolo.detect(frame)
                if detections:
                    labels = [(d['name'], round(d['confidence'], 2)) for d in detections]
                    print(f'[YOLO]    frame={frame_count:5d}  detected={labels}')
            except Exception as e:
                print(f'[YOLO] error: {e}')

        # ── Gesture recognition ───────────────────────────────────────────────
        if gesture_rec:
            try:
                gesture = gesture_rec.process(frame)
                now = time.time()
                if gesture and (gesture != last_gesture or now - last_gesture_time > 2):
                    print(f'[GESTURE] frame={frame_count:5d}  gesture="{gesture}"')
                    last_gesture = gesture
                    last_gesture_time = now
                elif not gesture and last_gesture:
                    last_gesture = None
            except Exception as e:
                print(f'[GESTURE] error: {e}')

        time.sleep(0.033)   # ~30 fps

except KeyboardInterrupt:
    print('\nStopped.')
finally:
    cap.release()
    if gesture_rec:
        gesture_rec.close()

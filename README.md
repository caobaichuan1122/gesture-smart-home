# YOLO Gesture Home Automation

A Django-based computer vision server that combines real-time camera streaming, YOLOv5 object detection, and MediaPipe gesture recognition with smart home automation. Detected gestures trigger commands over HTTP, MQTT, WebSocket, or shell.

---

## Features

- **Live MJPEG stream** — view cameras in the browser with detection overlays
- **Object detection** — YOLOv5 detects objects and saves snapshot events
- **Gesture recognition** — MediaPipe detects hand and body gestures in real time
- **Smart home commands** — gestures trigger HTTP requests, MQTT publishes, WebSocket broadcasts, or shell commands
- **Auto self-capture** — gesture recognition runs automatically on server start with no browser required
- **REST API** — full CRUD for cameras, gestures, commands, and mappings
- **WebSocket events** — real-time push for detection and automation events
- **Trigger history** — every gesture trigger is logged with a snapshot

---

## Built-in Gestures

**Body pose** (requires upper body visible):

| Gesture | Description |
|---------|-------------|
| `raise_right_hand` | Right wrist above right shoulder |
| `raise_left_hand` | Left wrist above left shoulder |
| `raise_both_hands` | Both wrists above shoulders |
| `t_pose` | Arms spread wide, wrists level with shoulders |
| `clap` | Both wrists close together at chest height |

**Hand gestures** (MediaPipe built-in model):

`thumbs_up` · `thumbs_down` · `victory` · `pointing_up` · `open_palm` · `fist` · `iloveyou`

---

## Requirements

- Python 3.8+
- PostgreSQL
- MQTT broker (optional)
- Model files: `gesture_recognizer.task`, `pose_landmarker.task` (place in project root)

---

## Installation

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
copy .env.example .env        # edit DB credentials and settings

# 4. Create database and apply migrations
python manage.py migrate

# 5. Create admin user
python manage.py createsuperuser
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=*

# PostgreSQL
DB_NAME=yolo
DB_USER=postgres
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=5432

# MQTT (optional)
MQTT_HOST=localhost
MQTT_PORT=1883
MQTT_USER=
MQTT_PASSWORD=
```

---

## Running

```bash
# Development server
python manage.py runserver

# Production (ASGI — required for WebSocket support)
daphne -b 0.0.0.0 -p 8000 yolo.asgi:application
```

On startup, enabled cameras with `gesture_enabled=True` automatically begin capturing frames and recognizing gestures — no browser connection needed.

---

## Quick Setup: Gesture → Command

```bash
python manage.py shell -c "
from yolo_app.models import GestureAction, HomeCommand, GestureCommandMapping

gesture = GestureAction.objects.create(
    name='thumbs_up', hold_frames=10, cooldown_seconds=5
)
cmd = HomeCommand.objects.create(
    name='Open Calculator', command_type='shell', shell_command='calc.exe'
)
GestureCommandMapping.objects.create(gesture=gesture, command=cmd)
print('Done')
"
```

Or configure everything through the Django Admin at `http://localhost:8000/admin/`.

---

## API Endpoints

### Cameras
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/cameras/` | List / create cameras |
| GET/PUT/DELETE | `/api/cameras/<id>/` | Retrieve / update / delete |
| GET | `/api/cameras/<id>/stream/` | Live MJPEG stream |
| GET | `/api/cameras/<id>/snapshot/` | Single JPEG frame |
| GET | `/api/cameras/<id>/events/` | Detection events (last 50) |
| GET | `/cameras/<id>/` | Browser viewer page |

### Gestures & Commands
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/gestures/` | List / create gesture actions |
| GET/PUT/DELETE | `/api/gestures/<id>/` | Retrieve / update / delete |
| GET/POST | `/api/commands/` | List / create home commands |
| POST | `/api/commands/<id>/test/` | Manually execute a command |
| GET/POST | `/api/mappings/` | List / create gesture→command mappings |
| GET | `/api/trigger-logs/` | Gesture trigger history (last 100) |

### WebSocket
| URL | Description |
|-----|-------------|
| `ws://<host>/ws/camera/<id>/` | Real-time detection events for a camera |
| `ws://<host>/ws/home/` | Real-time home automation events |

---

## Camera Sources

| Type | `source` example | Notes |
|------|-----------------|-------|
| Local webcam | `0` | Device index; uses DirectShow on Windows |
| RTSP | `rtsp://192.168.1.100:554/stream` | IP cameras, NVRs |
| HTTP | `http://192.168.1.100/video` | MJPEG HTTP streams |

---

## Architecture

```
Django startup
  └─ CameraProcessor thread (per enabled camera)
       ├─ YOLO detection  (saves DetectionEvent, broadcasts via WebSocket)
       ├─ Gesture engine  (debounce → cooldown → lookup mapping → execute command)
       └─ Self-capture    (opens camera if no HTTP stream is active)

HTTP stream request
  └─ Captures frames in request thread (DirectShow-safe on Windows)
       ├─ Pushes frames to CameraProcessor
       ├─ Draws gesture overlay (bounding box + label)
       └─ Yields MJPEG to browser
```

Self-capture automatically pauses when an HTTP stream opens the camera device, and resumes when the stream closes.

---

## Command Types

| Type | Description |
|------|-------------|
| `http` | Send HTTP request (GET/POST/PUT/…) with optional JSON body and headers |
| `mqtt` | Publish a message to an MQTT topic |
| `websocket` | Broadcast a JSON payload to all connected WebSocket clients |
| `shell` | Execute a shell command or program via subprocess (fire-and-forget) |

# YOLO Gesture Home Automation

[![CI](https://github.com/<your-org>/<your-repo>/actions/workflows/ci.yml/badge.svg)](https://github.com/<your-org>/<your-repo>/actions/workflows/ci.yml)
[![CD](https://github.com/<your-org>/<your-repo>/actions/workflows/cd.yml/badge.svg)](https://github.com/<your-org>/<your-repo>/actions/workflows/cd.yml)

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

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Web framework** | [Django 4.x](https://www.djangoproject.com/) + Django REST Framework |
| **Async / WebSocket** | Django Channels + Daphne (ASGI) |
| **Computer vision** | OpenCV, YOLOv5, MediaPipe |
| **Database** | PostgreSQL (via `psycopg2`) |
| **Messaging** | MQTT (`paho-mqtt`) |
| **Task / threading** | Python `threading` (per-camera processor) |

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

## API Documentation

Interactive API documentation is available automatically once the server is running.

| URL | Tool | Description |
|-----|------|-------------|
| `/api/docs/` | **ReDoc** | Clean, readable reference documentation (recommended) |
| `/api/swagger/` | **Swagger UI** | Interactive "try it out" console |
| `/api/schema/` | OpenAPI 3.0 | Raw YAML/JSON schema — import into Postman, Insomnia, etc. |

The schema is generated automatically from the code by [drf-spectacular](https://github.com/tfranzel/drf-spectacular). All endpoints are grouped into logical tags: `cameras`, `events`, `gestures`, `commands`, `mappings`, `logs`, `devices`.

### Export the schema

```bash
# Save schema to a file (YAML by default)
python manage.py spectacular --file schema.yml

# JSON format
python manage.py spectacular --file schema.json --format json
```

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

### Smart Devices
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET/POST | `/api/devices/` | List / create smart devices (`?type=light&room=living_room` filter) |
| GET/PUT/DELETE | `/api/devices/<id>/` | Retrieve / update / delete |
| POST | `/api/devices/<id>/control/` | Send a control action to the device |

**Control request body:**
```json
{"action": "turn_on", "params": {"brightness": 200}}
```

Supported actions per device type:

| Device | Actions |
|--------|---------|
| `light` | `turn_on` `turn_off` `set_brightness(brightness: 0-255)` |
| `curtain` | `open` `close` `set_position(position: 0-100)` |
| `tv` | `turn_on` `turn_off` `set_volume(volume_level: 0.0-1.0)` `pause` |
| `ac` | `turn_on` `turn_off` `set_temperature(temperature)` `set_mode(hvac_mode)` |

**Control response:**
```json
{"status": "ok", "device": "Living Room Light", "action": "turn_on", "state": {"is_on": true, "brightness": 200}}
```

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

---

## Smart Home Command Examples

The examples below show how to wire common gestures to smart home devices using the low-level `HomeCommand` API (HTTP or MQTT). For a higher-level device abstraction use the `/api/devices/` endpoints instead.

### Curtain

**HTTP (Home Assistant / REST gateway)**

```json
POST /api/commands/
{
  "name": "Open Curtain",
  "command_type": "http",
  "http_url": "http://192.168.1.10:8123/api/services/cover/open_cover",
  "http_method": "POST",
  "http_headers": {"Authorization": "Bearer <HA_TOKEN>", "Content-Type": "application/json"},
  "http_body": {"entity_id": "cover.living_room_curtain"}
}
```

**MQTT (Zigbee2MQTT / Tuya)**

```json
POST /api/commands/
{
  "name": "Open Curtain",
  "command_type": "mqtt",
  "mqtt_topic": "zigbee2mqtt/curtain/set",
  "mqtt_payload": "{\"state\": \"OPEN\"}"
}
```

---

### Light

**HTTP**

```json
POST /api/commands/
{
  "name": "Turn On Living Room Light",
  "command_type": "http",
  "http_url": "http://192.168.1.10:8123/api/services/light/turn_on",
  "http_method": "POST",
  "http_headers": {"Authorization": "Bearer <HA_TOKEN>", "Content-Type": "application/json"},
  "http_body": {"entity_id": "light.living_room", "brightness": 255}
}
```

**MQTT**

```json
POST /api/commands/
{
  "name": "Turn On Living Room Light",
  "command_type": "mqtt",
  "mqtt_topic": "home/light/living_room/set",
  "mqtt_payload": "{\"state\": \"ON\", \"brightness\": 255}"
}
```

---

### TV

**HTTP (Home Assistant media_player)**

```json
POST /api/commands/
{
  "name": "Turn On TV",
  "command_type": "http",
  "http_url": "http://192.168.1.10:8123/api/services/media_player/turn_on",
  "http_method": "POST",
  "http_headers": {"Authorization": "Bearer <HA_TOKEN>", "Content-Type": "application/json"},
  "http_body": {"entity_id": "media_player.living_room_tv"}
}
```

**MQTT**

```json
POST /api/commands/
{
  "name": "Turn On TV",
  "command_type": "mqtt",
  "mqtt_topic": "home/tv/set",
  "mqtt_payload": "{\"state\": \"ON\"}"
}
```

---

### Air Conditioner

**HTTP**

```json
POST /api/commands/
{
  "name": "Turn On AC",
  "command_type": "http",
  "http_url": "http://192.168.1.10:8123/api/services/climate/turn_on",
  "http_method": "POST",
  "http_headers": {"Authorization": "Bearer <HA_TOKEN>", "Content-Type": "application/json"},
  "http_body": {"entity_id": "climate.bedroom_ac", "temperature": 26, "hvac_mode": "cool"}
}
```

**MQTT**

```json
POST /api/commands/
{
  "name": "Turn On AC",
  "command_type": "mqtt",
  "mqtt_topic": "home/ac/bedroom/set",
  "mqtt_payload": "{\"state\": \"ON\", \"mode\": \"cool\", \"temperature\": 26}"
}
```

---

### Recommended Gesture Mappings

| Gesture | Action |
|---------|--------|
| `thumbs_up` | Turn on living room light |
| `thumbs_down` | Turn off living room light |
| `open_palm` | Open curtain |
| `fist` | Close curtain |
| `raise_right_hand` | Turn on AC (cool, 26°C) |
| `raise_left_hand` | Turn off AC |
| `victory` | Turn on TV |
| `raise_both_hands` | Turn off all devices |

Example — create a mapping via the Django shell:

```bash
python manage.py shell -c "
from yolo_app.models import GestureAction, HomeCommand, GestureCommandMapping

gesture = GestureAction.objects.create(name='open_palm', hold_frames=8, cooldown_seconds=5)
cmd = HomeCommand.objects.create(
    name='Open Curtain',
    command_type='mqtt',
    mqtt_topic='zigbee2mqtt/curtain/set',
    mqtt_payload='{\"state\": \"OPEN\"}'
)
GestureCommandMapping.objects.create(gesture=gesture, command=cmd)
print('Done')
"
```

---

## CI/CD

Two GitHub Actions workflows are included under `.github/workflows/`.

### CI (`ci.yml`)

Runs on every push and pull request to `master` / `main`.

| Job | What it does |
|-----|-------------|
| **lint** | Runs `flake8` (max line length 120, migrations excluded) |
| **test** | Spins up a PostgreSQL 15 service, applies migrations, and runs `manage.py test` against Python 3.10 and 3.11 |

> Heavy ML packages (PyTorch, MediaPipe, Ultralytics) are excluded from the CI install to keep the runner fast. Add them back if your tests require them.

### CD (`cd.yml`)

Runs on push to `master` / `main` and on version tags (`v*`).

| Job | What it does |
|-----|-------------|
| **docker** | Builds the Docker image and pushes it to GitHub Container Registry (`ghcr.io`) |
| **deploy** | SSHes into the production server, pulls the new image, and runs `docker compose up -d` + migrations |

#### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `DEPLOY_HOST` | Production server IP or hostname |
| `DEPLOY_USER` | SSH username |
| `DEPLOY_SSH_KEY` | Private SSH key (the server must have the matching public key) |

> `GITHUB_TOKEN` is provided automatically by GitHub Actions — no manual setup needed.

### Docker

A `Dockerfile` and `docker-compose.yml` are included for local and production use.

```bash
# Build and start locally
docker compose up --build

# Apply migrations inside the running container
docker compose exec web python manage.py migrate

# Create a superuser
docker compose exec web python manage.py createsuperuser
```

---

## Testing

All tests live in `yolo_app/tests.py` and use Django's built-in test runner.

### Run the test suite

```bash
# Run all tests
python manage.py test yolo_app --verbosity=2

# Run a single test class
python manage.py test yolo_app.tests.GestureEngineTests

# Run a single test method
python manage.py test yolo_app.tests.DeviceControlHTTPTests.test_light_set_brightness
```

> The test suite mocks all external I/O (camera hardware, HTTP calls, MQTT broker, WebSocket layer, subprocess) so no physical devices or services are required.

### Test coverage

| Area | Test class(es) | What is covered |
|------|---------------|-----------------|
| **Models** | `CameraModelTests` `GestureActionModelTests` `HomeCommandModelTests` `GestureCommandMappingModelTests` `GestureTriggerLogModelTests` `SmartDeviceModelTests` | `__str__`, field defaults, FK relations, ordering, unique constraints |
| **Serializers** | `CameraSerializerTests` `HomeCommandSerializerTests` `SmartDeviceSerializerTests` `GestureCommandMappingSerializerTests` `GestureTriggerLogSerializerTests` | Field presence, read-only fields, `stream_url` / `ws_url` generation, `supported_actions` per device type |
| **Camera API** | `CameraAPITests` | CRUD, disabled camera skips `start_camera`, 404 handling, detection event list |
| **Gesture API** | `GestureAPITests` | CRUD, 404, unique name constraint |
| **Command API** | `CommandAPITests` | CRUD, `POST /test/` success / failure / 404, HTTP & MQTT command creation |
| **Mapping API** | `MappingAPITests` | Global and camera-specific mappings, CRUD |
| **Trigger Log API** | `TriggerLogAPITests` | List, `success` field |
| **Device API** | `DeviceAPITests` | CRUD, `?type` and `?room` query filters, disabled device → 403, missing action → 400, executor failure → 502 |
| **Device control — HTTP** | `DeviceControlHTTPTests` | All actions for `light` / `curtain` / `tv` / `ac` via HTTP (Home Assistant); verifies HA service URL, request body, and `is_on` / `extra_state` updates |
| **Device control — MQTT** | `DeviceControlMQTTTests` | All actions for all device types via MQTT; verifies topic (`{prefix}/set`) and JSON payload |
| **Command executor** | `CommandExecutorHTTPTests` `CommandExecutorMQTTTests` `CommandExecutorShellTests` `CommandExecutorWebSocketTests` `CommandExecutorUnknownTypeTests` | HTTP success / 4xx / network error, MQTT success / no client / publish failure, Shell `Popen` success / OSError, WebSocket `group_send`, unknown type |
| **Gesture engine** | `GestureEngineTests` | Hold-frame debounce (too few frames → no fire), cooldown blocks re-trigger, cooldown expiry re-enables trigger, unregistered gesture ignored, gesture switch resets hold count, disabled `GestureAction` skipped, disabled `HomeCommand` skipped, trigger log written on success and failure |
| **WebSocket consumers** | `CameraConsumerTests` `HomeCommandConsumerTests` | Connect / disconnect, `detection_event` broadcast received, `home_command` broadcast received |

### Writing new tests

All test helpers are defined at the top of `tests.py`:

```python
make_camera(**kwargs)   # creates a Camera with sensible defaults
make_gesture(**kwargs)  # creates a GestureAction
make_command(**kwargs)  # creates a HomeCommand (shell type by default)
make_device(**kwargs)   # creates a SmartDevice (HTTP light by default)
```

External dependencies to mock:

| Dependency | Patch target |
|------------|-------------|
| Camera manager | `yolo_app.views.camera_api.camera_manager` |
| Command executor | `yolo_app.utils.command_executor.execute` |
| HTTP requests | `urllib.request.urlopen` |
| MQTT client | `yolo_app.utils.command_executor._get_mqtt_client` |
| Shell subprocess | `subprocess.Popen` |
| WebSocket layer | `channels.layers.get_channel_layer` |
| Gesture recognizer | `yolo_app.utils.gesture_engine.GestureRecognizer` |

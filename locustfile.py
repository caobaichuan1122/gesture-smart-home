"""
Locust load test for Gesture Smart Home API.

Usage:
  locust -f locustfile.py --host http://localhost:8000
  # or headless:
  locust -f locustfile.py --host http://localhost:8000 \
         --users 50 --spawn-rate 5 --run-time 60s --headless

Environment variables:
  LOCUST_USERNAME  (default: admin)
  LOCUST_PASSWORD  (default: admin)
"""

import os
import random

from locust import HttpUser, between, task


class GestureSmartHomeUser(HttpUser):
    wait_time = between(0.5, 2)

    # Shared JWT token acquired in on_start
    _token: str = ""

    def on_start(self):
        """Authenticate and store JWT token."""
        username = os.getenv("LOCUST_USERNAME", "admin")
        password = os.getenv("LOCUST_PASSWORD", "admin")
        resp = self.client.post(
            "/api/v1/auth/token/",
            json={"username": username, "password": password},
            name="/api/v1/auth/token/ [login]",
        )
        if resp.status_code == 200:
            self._token = resp.json().get("access", "")
        else:
            self._token = ""

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    # ── Camera endpoints ──────────────────────────────────────────────────────

    @task(3)
    def list_cameras(self):
        self.client.get("/api/v1/cameras/", headers=self._auth_headers(), name="GET /cameras/")

    @task(1)
    def camera_status(self):
        self.client.get(
            "/api/v1/cameras/1/status/",
            headers=self._auth_headers(),
            name="GET /cameras/{id}/status/",
        )

    # ── Device endpoints ──────────────────────────────────────────────────────

    @task(3)
    def list_devices(self):
        self.client.get("/api/v1/devices/", headers=self._auth_headers(), name="GET /devices/")

    @task(2)
    def list_devices_by_type(self):
        device_type = random.choice(["light", "curtain", "tv", "ac"])
        self.client.get(
            f"/api/v1/devices/?type={device_type}",
            headers=self._auth_headers(),
            name="GET /devices/?type=*",
        )

    @task(1)
    def control_device(self):
        action = random.choice(["turn_on", "turn_off"])
        self.client.post(
            "/api/v1/devices/1/control/",
            json={"action": action},
            headers=self._auth_headers(),
            name="POST /devices/{id}/control/",
        )

    # ── Gesture / Command / Mapping endpoints ─────────────────────────────────

    @task(2)
    def list_gestures(self):
        self.client.get("/api/v1/gestures/", headers=self._auth_headers(), name="GET /gestures/")

    @task(2)
    def list_commands(self):
        self.client.get("/api/v1/commands/", headers=self._auth_headers(), name="GET /commands/")

    @task(2)
    def list_mappings(self):
        self.client.get("/api/v1/mappings/", headers=self._auth_headers(), name="GET /mappings/")

    # ── Trigger logs ──────────────────────────────────────────────────────────

    @task(2)
    def trigger_logs(self):
        self.client.get(
            "/api/v1/trigger-logs/",
            headers=self._auth_headers(),
            name="GET /trigger-logs/",
        )

    # ── Auth / token refresh ──────────────────────────────────────────────────

    @task(1)
    def refresh_token(self):
        # Simulate token refresh (would need refresh token in real scenario)
        self.client.post(
            "/api/v1/auth/token/",
            json={"username": os.getenv("LOCUST_USERNAME", "admin"),
                  "password": os.getenv("LOCUST_PASSWORD", "admin")},
            name="/api/v1/auth/token/ [refresh]",
        )

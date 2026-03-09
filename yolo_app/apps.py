import os
from django.apps import AppConfig


class YoloAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'yolo_app'

    def ready(self):
        # Auto-start camera workers only in the main server process,
        # not during management commands (makemigrations, shell, etc.)
        if os.environ.get('RUN_MAIN') or os.environ.get('DAPHNE'):
            import threading

            def start_cameras():
                import time
                time.sleep(3)   # allow the server to finish initializing
                from yolo_app.utils.camera_manager import camera_manager
                try:
                    camera_manager.start_all()
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning('Camera auto-start failed: %s', exc)

            threading.Thread(target=start_cameras, daemon=True).start()

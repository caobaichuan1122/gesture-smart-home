from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def execute_home_command(self, command_id, context=None):
    """Execute a HomeCommand asynchronously with automatic retry on failure."""
    from yolo_app.models import HomeCommand
    from yolo_app.utils import command_executor
    try:
        cmd = HomeCommand.objects.get(pk=command_id)
        success, error = command_executor.execute(cmd, context=context or {})
        if not success:
            raise Exception(error)
        return {'status': 'ok', 'command_id': command_id}
    except HomeCommand.DoesNotExist:
        return {'status': 'error', 'detail': 'Command not found'}
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def log_gesture_trigger(camera_id, gesture_id, command_id, success, error_message=''):
    """Write a GestureTriggerLog entry asynchronously to avoid blocking the gesture pipeline."""
    from yolo_app.models import GestureTriggerLog
    GestureTriggerLog.objects.create(
        camera_id=camera_id,
        gesture_id=gesture_id,
        command_id=command_id,
        success=success,
        error_message=error_message,
    )

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('yolo_app', '0002_gestureaction_homecommand_camera_gesture_enabled_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='homecommand',
            name='shell_command',
            field=models.CharField(blank=True, max_length=1000),
        ),
        migrations.AlterField(
            model_name='homecommand',
            name='command_type',
            field=models.CharField(
                choices=[
                    ('http', 'HTTP Request'),
                    ('mqtt', 'MQTT Publish'),
                    ('websocket', 'WebSocket Broadcast'),
                    ('shell', 'Shell Command'),
                ],
                max_length=20,
            ),
        ),
    ]

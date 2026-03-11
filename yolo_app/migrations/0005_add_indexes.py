from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('yolo_app', '0004_smartdevice'),
    ]

    operations = [
        # DetectionEvent: index on detected_at for fast ordering/filtering
        migrations.AlterField(
            model_name='detectionevent',
            name='detected_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        # GestureCommandMapping: index on enabled for fast filtering
        migrations.AlterField(
            model_name='gesturecommandmapping',
            name='enabled',
            field=models.BooleanField(default=True, db_index=True),
        ),
        # GestureTriggerLog: indexes on triggered_at and success
        migrations.AlterField(
            model_name='gesturetriggerlog',
            name='triggered_at',
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='gesturetriggerlog',
            name='success',
            field=models.BooleanField(default=True, db_index=True),
        ),
        # SmartDevice: indexes on device_type and room + composite index
        migrations.AlterField(
            model_name='smartdevice',
            name='device_type',
            field=models.CharField(
                choices=[('light', '灯光'), ('curtain', '窗帘'), ('tv', '电视'), ('ac', '空调')],
                db_index=True, max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name='smartdevice',
            name='room',
            field=models.CharField(
                blank=True, db_index=True, max_length=100,
                help_text='房间名，e.g. living_room',
            ),
        ),
        migrations.AddIndex(
            model_name='smartdevice',
            index=models.Index(fields=['room', 'device_type'], name='device_room_type_idx'),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('yolo_app', '0003_homecommand_shell_command'),
    ]

    operations = [
        migrations.CreateModel(
            name='SmartDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('device_type', models.CharField(
                    choices=[('light', '灯光'), ('curtain', '窗帘'), ('tv', '电视'), ('ac', '空调')],
                    max_length=20,
                )),
                ('protocol', models.CharField(
                    choices=[('http', 'HTTP (Home Assistant)'), ('mqtt', 'MQTT')],
                    default='http',
                    max_length=10,
                )),
                ('room', models.CharField(blank=True, max_length=100,
                                          help_text='房间名，e.g. living_room')),
                ('http_base_url', models.CharField(blank=True, max_length=500,
                                                    help_text='HA 地址，e.g. http://192.168.1.10:8123')),
                ('http_token', models.CharField(blank=True, max_length=500,
                                                 help_text='HA 长期访问令牌 (Bearer token)')),
                ('entity_id', models.CharField(blank=True, max_length=200,
                                                help_text='HA 实体 ID，e.g. light.living_room')),
                ('mqtt_topic_prefix', models.CharField(blank=True, max_length=200,
                                                        help_text='MQTT 主题前缀，e.g. home/light/living_room')),
                ('is_on', models.BooleanField(default=False)),
                ('extra_state', models.JSONField(blank=True, default=dict,
                                                  help_text='附加状态，e.g. {"brightness": 200}')),
                ('enabled', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['room', 'device_type', 'name'],
            },
        ),
    ]

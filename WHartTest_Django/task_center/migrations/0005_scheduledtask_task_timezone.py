from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('task_center', '0004_remove_executing_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='scheduledtask',
            name='task_timezone',
            field=models.CharField(
                default='Asia/Shanghai',
                help_text='定时任务调度使用的时区，填写标准时区名称如 Asia/Shanghai、Asia/Dubai、UTC',
                max_length=64,
                verbose_name='时区',
            ),
        ),
    ]

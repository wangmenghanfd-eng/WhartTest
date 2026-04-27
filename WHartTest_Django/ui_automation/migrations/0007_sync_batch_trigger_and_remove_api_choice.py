from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def sync_execution_records(apps, schema_editor):
    UiExecutionRecord = apps.get_model('ui_automation', 'UiExecutionRecord')
    UiExecutionRecord.objects.filter(batch__trigger_type='scheduled').update(trigger_type='scheduled')
    for record in UiExecutionRecord.objects.filter(batch__isnull=False, executor__isnull=True, batch__executor__isnull=False):
        record.executor_id = record.batch.executor_id
        record.save(update_fields=['executor'])


class Migration(migrations.Migration):

    dependencies = [
        ('ui_automation', '0006_cleanup_public_data'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='uibatchexecutionrecord',
            name='trigger_type',
            field=models.CharField(choices=[('manual', '手动执行'), ('scheduled', '定时执行')], default='manual', max_length=20, verbose_name='触发类型'),
        ),
        migrations.AlterField(
            model_name='uiexecutionrecord',
            name='trigger_type',
            field=models.CharField(choices=[('manual', '手动执行'), ('scheduled', '定时执行')], default='manual', max_length=20, verbose_name='触发类型'),
        ),
        migrations.RunPython(sync_execution_records, migrations.RunPython.noop),
    ]

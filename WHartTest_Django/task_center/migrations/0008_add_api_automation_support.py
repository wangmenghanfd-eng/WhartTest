from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("api_automation", "0001_initial"),
        ("task_center", "0005_scheduledtask_task_timezone"),
    ]

    operations = [
        migrations.AddField(
            model_name="scheduledtask",
            name="api_testcases",
            field=models.ManyToManyField(blank=True, help_text='模块为"接口自动化"时选择要执行的用例', related_name="scheduled_tasks", to="api_automation.apitestcase", verbose_name="关联接口用例"),
        ),
        migrations.AlterField(
            model_name="scheduledtask",
            name="module",
            field=models.CharField(choices=[("ui_automation", "UI 自动化"), ("api_automation", "接口自动化"), ("test_suite", "测试套件")], max_length=20, verbose_name="所属模块"),
        ),
        migrations.AlterField(
            model_name="scheduledtask",
            name="execution_target",
            field=models.CharField(choices=[("actuator", "执行器"), ("backend", "后端执行")], default="actuator", max_length=20, verbose_name="执行目标"),
        ),
    ]

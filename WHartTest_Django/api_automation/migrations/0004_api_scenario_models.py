from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("api_automation", "0003_remove_duplicate_jsonplaceholder_envs"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiScenario",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="场景名称")),
                ("description", models.TextField(blank=True, default="", verbose_name="场景描述")),
                ("status", models.SmallIntegerField(choices=[(0, "未执行"), (1, "执行中"), (2, "成功"), (3, "失败")], default=0, verbose_name="状态")),
                ("last_result", models.JSONField(blank=True, default=dict, verbose_name="最近执行结果")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("creator", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_api_scenarios", to=settings.AUTH_USER_MODEL, verbose_name="创建人")),
                ("module", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scenarios", to="api_automation.apimodule", verbose_name="所属模块")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_scenarios", to="projects.project", verbose_name="所属项目")),
            ],
            options={"verbose_name": "接口场景", "verbose_name_plural": "接口场景", "db_table": "api_scenario", "ordering": ["module_id", "name", "id"]},
        ),
        migrations.CreateModel(
            name="ApiScenarioExecutionRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.SmallIntegerField(choices=[(0, "待执行"), (1, "执行中"), (2, "成功"), (3, "失败")], default=0, verbose_name="状态")),
                ("trigger_type", models.CharField(choices=[("manual", "手动执行"), ("scheduled", "定时执行")], default="manual", max_length=20, verbose_name="触发类型")),
                ("variables_snapshot", models.JSONField(blank=True, default=dict, verbose_name="变量快照")),
                ("result_summary", models.JSONField(blank=True, default=dict, verbose_name="结果摘要")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("duration", models.FloatField(blank=True, null=True, verbose_name="耗时秒")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("start_time", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("end_time", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
                ("environment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scenario_execution_records", to="api_automation.apienvironmentconfig", verbose_name="环境")),
                ("executor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="api_scenario_execution_records", to=settings.AUTH_USER_MODEL, verbose_name="执行人")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_scenario_execution_records", to="projects.project", verbose_name="所属项目")),
                ("scenario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="execution_records", to="api_automation.apiscenario", verbose_name="接口场景")),
            ],
            options={"verbose_name": "接口场景执行记录", "verbose_name_plural": "接口场景执行记录", "db_table": "api_scenario_execution_record", "ordering": ["-id"]},
        ),
        migrations.CreateModel(
            name="ApiScenarioStep",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=1, verbose_name="顺序")),
                ("name", models.CharField(blank=True, default="", max_length=255, verbose_name="步骤名称")),
                ("is_enabled", models.BooleanField(default=True, verbose_name="启用")),
                ("stop_on_failure", models.BooleanField(default=True, verbose_name="失败即停止")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("scenario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="steps", to="api_automation.apiscenario", verbose_name="所属场景")),
                ("test_case", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scenario_steps", to="api_automation.apitestcase", verbose_name="接口用例")),
            ],
            options={"verbose_name": "接口场景步骤", "verbose_name_plural": "接口场景步骤", "db_table": "api_scenario_step", "ordering": ["order", "id"], "unique_together": {("scenario", "order")}},
        ),
        migrations.CreateModel(
            name="ApiScenarioStepRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order", models.PositiveIntegerField(default=1, verbose_name="顺序")),
                ("status", models.SmallIntegerField(choices=[(0, "待执行"), (1, "执行中"), (2, "成功"), (3, "失败"), (4, "跳过")], default=0, verbose_name="状态")),
                ("extracted_variables", models.JSONField(blank=True, default=dict, verbose_name="提取变量")),
                ("error_message", models.TextField(blank=True, default="", verbose_name="错误信息")),
                ("duration", models.FloatField(blank=True, null=True, verbose_name="耗时秒")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("start_time", models.DateTimeField(blank=True, null=True, verbose_name="开始时间")),
                ("end_time", models.DateTimeField(blank=True, null=True, verbose_name="结束时间")),
                ("execution_record", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scenario_step_records", to="api_automation.apiexecutionrecord", verbose_name="接口执行记录")),
                ("scenario_execution", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="step_records", to="api_automation.apiscenarioexecutionrecord", verbose_name="所属场景执行")),
                ("step", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="step_records", to="api_automation.apiscenariostep", verbose_name="场景步骤")),
                ("test_case", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="scenario_step_records", to="api_automation.apitestcase", verbose_name="接口用例")),
            ],
            options={"verbose_name": "接口场景步骤执行记录", "verbose_name_plural": "接口场景步骤执行记录", "db_table": "api_scenario_step_record", "ordering": ["order", "id"]},
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api_automation", "0005_align_definitions_per_module"),
    ]

    operations = [
        migrations.AddField(
            model_name="apienvironmentconfig",
            name="env_type",
            field=models.CharField(
                choices=[("dev", "开发"), ("test", "测试"), ("staging", "预发布"), ("prod", "生产")],
                default="dev",
                max_length=16,
                verbose_name="环境类型",
            ),
        ),
    ]

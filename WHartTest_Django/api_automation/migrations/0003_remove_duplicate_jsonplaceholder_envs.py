from django.db import migrations


def remove_duplicate_jsonplaceholder_envs(apps, schema_editor):
    ApiEnvironmentConfig = apps.get_model("api_automation", "ApiEnvironmentConfig")
    ApiTestCase = apps.get_model("api_automation", "ApiTestCase")
    ApiExecutionRecord = apps.get_model("api_automation", "ApiExecutionRecord")

    for env in ApiEnvironmentConfig.objects.filter(name="JSONPlaceholder-Staging"):
        replacement = ApiEnvironmentConfig.objects.filter(
            project_id=env.project_id,
            name="JSONPlaceholder",
        ).exclude(id=env.id).first()
        if replacement:
            ApiTestCase.objects.filter(environment_id=env.id).update(environment_id=replacement.id)
            ApiExecutionRecord.objects.filter(environment_id=env.id).update(environment_id=replacement.id)
        env.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api_automation", "0002_remove_unused_default_user_id"),
    ]

    operations = [
        migrations.RunPython(remove_duplicate_jsonplaceholder_envs, migrations.RunPython.noop),
    ]

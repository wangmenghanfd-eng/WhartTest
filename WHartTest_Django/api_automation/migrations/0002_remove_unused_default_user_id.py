from django.db import migrations


def remove_unused_default_user_id(apps, schema_editor):
    ApiPublicData = apps.get_model("api_automation", "ApiPublicData")
    ApiPublicData.objects.filter(key="default_user_id").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api_automation", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(remove_unused_default_user_id, migrations.RunPython.noop),
    ]

from __future__ import annotations

import re

from django.db import migrations


KEEP_KEY_RE = re.compile(r"(username|user_name|password|account|email|phone|token|name)", re.I)
NOISY_KEY_RE = re.compile(r"(wrong|invalid|error|fail|failed|negative|success|assert|message|text|temp|random|auto|case)", re.I)


def _should_keep_public_key(key: str) -> bool:
    key = key or ""
    return bool(KEEP_KEY_RE.search(key)) and not NOISY_KEY_RE.search(key)


def _replace_value(value, replacement_map: dict[str, str]):
    if isinstance(value, str):
        new_value = value
        for key, replacement in replacement_map.items():
            new_value = new_value.replace(f"${{{{{key}}}}}", replacement)
        return new_value

    if isinstance(value, list):
        return [_replace_value(item, replacement_map) for item in value]

    if isinstance(value, dict):
        return {key: _replace_value(item, replacement_map) for key, item in value.items()}

    return value


def cleanup_public_data(apps, schema_editor):
    UiPublicData = apps.get_model("ui_automation", "UiPublicData")
    UiPageSteps = apps.get_model("ui_automation", "UiPageSteps")
    UiPageStepsDetailed = apps.get_model("ui_automation", "UiPageStepsDetailed")
    UiTestCase = apps.get_model("ui_automation", "UiTestCase")
    UiElement = apps.get_model("ui_automation", "UiElement")

    removable_records = [
        item
        for item in UiPublicData.objects.all()
        if not _should_keep_public_key(item.key)
    ]
    replacement_map = {
        item.key: item.value
        for item in removable_records
        if item.key
    }

    if not replacement_map:
        return

    def update_instances(model, fields):
        for instance in model.objects.all():
            changed_fields = []
            for field in fields:
                original = getattr(instance, field, None)
                updated = _replace_value(original, replacement_map)
                if updated != original:
                    setattr(instance, field, updated)
                    changed_fields.append(field)
            if changed_fields:
                instance.save(update_fields=changed_fields)

    update_instances(UiPageStepsDetailed, ["ope_value", "sql_execute", "custom", "condition_value", "func", "description"])
    update_instances(UiPageSteps, ["description", "run_flow", "flow_data"])
    update_instances(UiTestCase, ["description", "front_custom", "front_sql", "posterior_sql", "parametrize", "case_flow"])
    update_instances(UiElement, [
        "locator_value",
        "locator_value_2",
        "locator_value_3",
        "iframe_locator",
        "description",
    ])

    UiPublicData.objects.filter(id__in=[item.id for item in removable_records]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ui_automation", "0005_deduplicate_semantic_elements"),
    ]

    operations = [
        migrations.RunPython(cleanup_public_data, migrations.RunPython.noop),
    ]

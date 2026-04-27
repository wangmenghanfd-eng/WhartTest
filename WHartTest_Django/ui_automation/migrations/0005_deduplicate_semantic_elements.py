from django.db import migrations


def locator_rank(locator_type):
    return {
        "test_id": 1,
        "id": 2,
        "name": 3,
        "label": 4,
        "placeholder": 5,
        "role": 6,
        "css": 7,
        "text": 8,
        "xpath": 9,
    }.get(locator_type or "", 99)


def add_locator(element, locator_type, locator_value):
    if not locator_type or not locator_value:
        return
    locators = [
        (element.locator_type, element.locator_value),
        (element.locator_type_2, element.locator_value_2),
        (element.locator_type_3, element.locator_value_3),
    ]
    if (locator_type, locator_value) in locators:
        return
    if locator_rank(locator_type) < locator_rank(element.locator_type):
        old_type, old_value = element.locator_type, element.locator_value
        element.locator_type = locator_type
        element.locator_value = locator_value
        locator_type, locator_value = old_type, old_value
    if not element.locator_type_2 or not element.locator_value_2:
        element.locator_type_2 = locator_type
        element.locator_value_2 = locator_value
    elif not element.locator_type_3 or not element.locator_value_3:
        element.locator_type_3 = locator_type
        element.locator_value_3 = locator_value


def deduplicate_elements(apps, schema_editor):
    UiElement = apps.get_model("ui_automation", "UiElement")
    UiPageStepsDetailed = apps.get_model("ui_automation", "UiPageStepsDetailed")

    duplicate_keys = (
        UiElement.objects.values("page_id", "name")
        .order_by()
    )
    seen = set()
    for item in duplicate_keys:
        key = (item["page_id"], item["name"])
        if key in seen:
            continue
        seen.add(key)
        elements = list(
            UiElement.objects.filter(page_id=key[0], name=key[1]).order_by("id")
        )
        if len(elements) <= 1:
            continue

        elements.sort(key=lambda element: (locator_rank(element.locator_type), element.id))
        primary = elements[0]
        for duplicate in elements[1:]:
            add_locator(primary, duplicate.locator_type, duplicate.locator_value)
            add_locator(primary, duplicate.locator_type_2, duplicate.locator_value_2)
            add_locator(primary, duplicate.locator_type_3, duplicate.locator_value_3)
            UiPageStepsDetailed.objects.filter(element_id=duplicate.id).update(element_id=primary.id)
            duplicate.delete()
        primary.save()


class Migration(migrations.Migration):

    dependencies = [
        ("ui_automation", "0004_uirecordingsession"),
    ]

    operations = [
        migrations.RunPython(deduplicate_elements, migrations.RunPython.noop),
    ]

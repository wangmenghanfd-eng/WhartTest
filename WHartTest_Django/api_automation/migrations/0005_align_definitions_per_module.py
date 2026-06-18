from django.db import migrations


def align_definitions_per_module(apps, schema_editor):
    ApiDefinition = apps.get_model("api_automation", "ApiDefinition")
    ApiTestCase = apps.get_model("api_automation", "ApiTestCase")

    fields_to_clone = [
        "name",
        "operation_id",
        "summary",
        "description",
        "tags",
        "parameters",
        "request_body",
        "responses",
        "source",
        "creator_id",
    ]

    cache: dict[tuple[int, int, str, str], int] = {}

    def ensure_definition(case):
        if not case.definition_id:
            key = (case.project_id, case.module_id, case.method, case.path)
            if key in cache:
                return cache[key]
            existing = ApiDefinition.objects.filter(
                project_id=case.project_id,
                module_id=case.module_id,
                method=case.method,
                path=case.path,
            ).order_by("id").first()
            if existing:
                cache[key] = existing.id
                return existing.id
            created = ApiDefinition.objects.create(
                project_id=case.project_id,
                module_id=case.module_id,
                name=case.name[:200],
                method=case.method,
                path=case.path,
                summary=case.name[:300],
                description="由历史接口用例自动补齐的接口定义",
                source=case.source or "manual",
                creator_id=case.creator_id,
            )
            cache[key] = created.id
            return created.id

        definition = case.definition
        if definition.module_id == case.module_id:
            key = (case.project_id, case.module_id, definition.method, definition.path)
            cache[key] = definition.id
            return definition.id

        key = (case.project_id, case.module_id, definition.method, definition.path)
        if key in cache:
            return cache[key]

        existing = ApiDefinition.objects.filter(
            project_id=case.project_id,
            module_id=case.module_id,
            method=definition.method,
            path=definition.path,
        ).order_by("id").first()
        if existing:
            cache[key] = existing.id
            return existing.id

        payload = {field: getattr(definition, field) for field in fields_to_clone}
        payload.update(
            {
                "project_id": case.project_id,
                "module_id": case.module_id,
                "method": definition.method,
                "path": definition.path,
            }
        )
        cloned = ApiDefinition.objects.create(**payload)
        cache[key] = cloned.id
        return cloned.id

    for case in (
        ApiTestCase.objects.select_related("definition")
        .filter(definition__isnull=False)
        .order_by("id")
    ):
        new_definition_id = ensure_definition(case)
        if new_definition_id and case.definition_id != new_definition_id:
            case.definition_id = new_definition_id
            case.save(update_fields=["definition"])


class Migration(migrations.Migration):

    dependencies = [
        ("api_automation", "0004_api_scenario_models"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="apidefinition",
            unique_together={("project", "module", "method", "path")},
        ),
        migrations.RunPython(align_definitions_per_module, migrations.RunPython.noop),
    ]

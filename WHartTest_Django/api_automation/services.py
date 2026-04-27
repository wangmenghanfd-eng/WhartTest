import json
import re
import time
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml
from django.db import transaction
from django.utils import timezone

from .models import (
    ApiBatchExecutionRecord,
    ApiDefinition,
    ApiEnvironmentConfig,
    ApiExecutionRecord,
    ApiModule,
    ApiPublicData,
    ApiTestCase,
)


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
VAR_RE = re.compile(r"\$\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def load_openapi_spec(raw: str) -> dict[str, Any]:
    """Load OpenAPI JSON/YAML text into a dictionary."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("OpenAPI 内容必须是 JSON/YAML 对象")
    if "paths" not in data:
        raise ValueError("未找到 paths，无法识别为 OpenAPI/Swagger 文档")
    return data


def _module_for_tag(project, creator, tag: str | None) -> ApiModule:
    name = (tag or "未分组接口").strip() or "未分组接口"
    module, _ = ApiModule.objects.get_or_create(
        project=project,
        parent=None,
        name=name[:100],
        defaults={"creator": creator},
    )
    return module


def _default_assertions(responses: dict[str, Any]) -> list[dict[str, Any]]:
    status_codes = [code for code in responses.keys() if str(code).isdigit()]
    expected = int(status_codes[0]) if status_codes else 200
    return [{"type": "status_code", "operator": "eq", "expected": expected}]


def import_openapi_spec(project, creator, spec: dict[str, Any], create_cases: bool = True) -> dict[str, int]:
    """Import OpenAPI paths as API definitions and optional smoke test cases."""
    created_definitions = 0
    updated_definitions = 0
    created_cases = 0
    server_url = ""
    servers = spec.get("servers") or []
    if servers and isinstance(servers, list) and isinstance(servers[0], dict):
        server_url = servers[0].get("url") or ""

    with transaction.atomic():
        if server_url:
            ApiEnvironmentConfig.objects.get_or_create(
                project=project,
                name="OpenAPI 默认环境",
                defaults={
                    "base_url": server_url,
                    "is_default": not ApiEnvironmentConfig.objects.filter(project=project).exists(),
                    "creator": creator,
                },
            )

        for path, path_item in (spec.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            shared_parameters = path_item.get("parameters") or []
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                tags = operation.get("tags") or []
                module = _module_for_tag(project, creator, tags[0] if tags else None)
                summary = operation.get("summary") or operation.get("operationId") or f"{method.upper()} {path}"
                parameters = list(shared_parameters) + list(operation.get("parameters") or [])
                definition, created = ApiDefinition.objects.update_or_create(
                    project=project,
                    method=method.upper(),
                    path=path,
                    defaults={
                        "module": module,
                        "name": str(summary)[:200],
                        "operation_id": operation.get("operationId") or "",
                        "summary": operation.get("summary") or "",
                        "description": operation.get("description") or "",
                        "tags": tags,
                        "parameters": parameters,
                        "request_body": operation.get("requestBody") or {},
                        "responses": operation.get("responses") or {},
                        "source": "openapi",
                        "creator": creator,
                    },
                )
                created_definitions += int(created)
                updated_definitions += int(not created)

                if create_cases and not ApiTestCase.objects.filter(definition=definition, source="openapi").exists():
                    ApiTestCase.objects.create(
                        project=project,
                        module=module,
                        definition=definition,
                        name=f"OpenAPI-{definition.name}"[:255],
                        method=definition.method,
                        path=definition.path,
                        assertions=_default_assertions(definition.responses),
                        source="openapi",
                        creator=creator,
                    )
                    created_cases += 1

    return {
        "created_definitions": created_definitions,
        "updated_definitions": updated_definitions,
        "created_cases": created_cases,
    }


def _public_variables(project) -> dict[str, str]:
    return {
        item.key: item.value
        for item in ApiPublicData.objects.filter(project=project, is_enabled=True)
    }


def _render_value(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return VAR_RE.sub(lambda m: str(variables.get(m.group(1), m.group(0))), value)
    if isinstance(value, dict):
        return {k: _render_value(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    return value


def _build_url(env: ApiEnvironmentConfig | None, path: str) -> str:
    if path.startswith(("http://", "https://")):
        return path
    base_url = env.base_url if env else ""
    if not base_url:
        raise ValueError("接口路径是相对路径，请先选择或配置接口环境 base_url")
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _assert_response(response: httpx.Response, assertions: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    results = []
    ok = True
    body_text = response.text
    for assertion in assertions or [{"type": "status_code", "operator": "lt", "expected": 500}]:
        typ = assertion.get("type")
        operator = assertion.get("operator", "eq")
        expected = assertion.get("expected")
        actual: Any = None
        passed = False
        if typ == "status_code":
            actual = response.status_code
            if operator == "eq":
                passed = actual == int(expected)
            elif operator == "lt":
                passed = actual < int(expected)
            elif operator == "in":
                passed = actual in [int(v) for v in expected]
        elif typ == "body_contains":
            actual = body_text
            passed = str(expected) in body_text
        elif typ == "header_exists":
            actual = dict(response.headers)
            passed = str(expected).lower() in {k.lower() for k in response.headers.keys()}
        else:
            actual = None
            passed = True
        ok = ok and passed
        results.append({**assertion, "actual": actual, "passed": passed})
    return ok, results


def execute_api_case(record_id: int) -> dict[str, Any]:
    record = ApiExecutionRecord.objects.select_related("test_case", "environment", "project").get(id=record_id)
    case = record.test_case
    env = record.environment or case.environment or ApiEnvironmentConfig.objects.filter(project=case.project, is_default=True).first()
    variables = _public_variables(case.project)
    if env:
        variables.update({str(k): str(v) for k, v in (env.variables or {}).items()})

    record.status = 1
    record.start_time = timezone.now()
    record.save(update_fields=["status", "start_time"])

    start = time.perf_counter()
    try:
        headers = deepcopy(env.headers if env else {})
        headers.update(_render_value(case.headers or {}, variables))
        query_params = _render_value(case.query_params or {}, variables)
        body = _render_value(case.body or {}, variables)
        url = _build_url(env, _render_value(case.path, variables))

        request_data = {
            "method": case.method,
            "url": url,
            "headers": headers,
            "query_params": query_params,
            "body": body,
        }
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.request(
                case.method,
                url,
                headers=headers,
                params=query_params,
                json=body if body not in ({}, None, "") else None,
            )
        passed, assertion_results = _assert_response(response, case.assertions or [])
        duration = time.perf_counter() - start
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "text": response.text[:20000],
            "assertions": assertion_results,
        }
        status = 2 if passed else 3
        error = "" if passed else "接口断言未通过"
        record.status = status
        record.request_data = request_data
        record.response_data = response_data
        record.error_message = error
        record.duration = duration
        record.end_time = timezone.now()
        record.save()
        ApiTestCase.objects.filter(id=case.id).update(status=status, result_data=response_data, error_message=error)
        return {"status": "success" if passed else "failed", "record_id": record.id}
    except Exception as exc:
        duration = time.perf_counter() - start
        record.status = 3
        record.error_message = str(exc)
        record.duration = duration
        record.end_time = timezone.now()
        record.save()
        ApiTestCase.objects.filter(id=case.id).update(status=3, error_message=str(exc))
        return {"status": "failed", "record_id": record.id, "error": str(exc)}


def update_batch_summary(batch_id: int) -> None:
    batch = ApiBatchExecutionRecord.objects.get(id=batch_id)
    records = list(batch.execution_records.all())
    total = len(records)
    passed = sum(1 for record in records if record.status == 2)
    failed = sum(1 for record in records if record.status == 3)
    if total == 0:
        status = 4
    elif failed == 0 and passed == total:
        status = 2
    elif passed == 0:
        status = 4
    else:
        status = 3
    durations = [record.duration or 0 for record in records]
    batch.total_cases = total
    batch.passed_cases = passed
    batch.failed_cases = failed
    batch.status = status
    batch.duration = sum(durations)
    batch.end_time = timezone.now()
    batch.save()


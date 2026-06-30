import base64
import json
import subprocess
import re
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
import yaml
from django.db import models, transaction
from django.utils import timezone

from .models import (
    ApiBatchExecutionRecord,
    ApiDefinition,
    ApiEnvironmentConfig,
    ApiExecutionRecord,
    ApiModule,
    ApiPublicData,
    ApiScenario,
    ApiScenarioExecutionRecord,
    ApiScenarioStepRecord,
    ApiScript,
    ApiTestCase,
)


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
VAR_RE = re.compile(r"\$\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
BROWSER_LIKE_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-CH-UA": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": '"macOS"',
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/148.0.0.0 Safari/537.36",
}
JS_SCRIPT_RUNNER = Path(__file__).resolve().with_name("js_script_runner.js")


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


_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def _get_by_path(data: Any, path: str) -> Any:
    """按点路径访问嵌套对象，支持数组下标。

    支持的语法：
    - `data.token`、`user.id`
    - `items[0].name`
    - `$.data.token`（jsonpath 风格的根标记，会被忽略）

    返回 None 表示路径不存在。
    """
    if data is None or not path:
        return None
    raw = path.strip().lstrip("$")
    if raw.startswith("."):
        raw = raw[1:]
    current = data
    for match in _PATH_TOKEN_RE.finditer(raw):
        key, index = match.group(1), match.group(2)
        if index is not None:
            if not isinstance(current, list):
                return None
            try:
                current = current[int(index)]
            except (IndexError, ValueError):
                return None
        else:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        if current is None:
            return None
    return current


def _json_type_name(value: Any) -> str:
    """返回值的 JSON 类型名:null/boolean/number/string/array/object。"""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _safe_response_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return None


def _compare(actual: Any, operator: str, expected: Any) -> bool:
    """通用断言运算符。actual/expected 都可能为 None。"""
    op = (operator or "eq").lower()

    if op in ("is_empty",):
        return actual in (None, "", [], {})
    if op in ("is_not_empty", "exists"):
        return actual not in (None, "", [], {})

    if op == "eq":
        return str(actual) == str(expected)
    if op == "neq":
        return str(actual) != str(expected)
    if op in ("contains", "include"):
        return str(expected) in str(actual or "")
    if op in ("not_contains", "exclude"):
        return str(expected) not in str(actual or "")
    if op == "regex":
        try:
            return re.search(str(expected), str(actual or "")) is not None
        except re.error:
            return False
    if op == "in":
        try:
            collection = expected if isinstance(expected, (list, tuple, set)) else [expected]
            return actual in [type(actual)(v) if isinstance(actual, (int, float)) else v for v in collection]
        except (TypeError, ValueError):
            return actual in (expected or [])
    if op == "not_in":
        return not _compare(actual, "in", expected)

    # 数值比较：尝试转 float，失败则降级为字符串比较
    try:
        actual_n = float(actual)
        expected_n = float(expected)
    except (TypeError, ValueError):
        if op == "lt":
            return str(actual) < str(expected)
        if op == "lte":
            return str(actual) <= str(expected)
        if op == "gt":
            return str(actual) > str(expected)
        if op == "gte":
            return str(actual) >= str(expected)
        return False
    if op == "lt":
        return actual_n < expected_n
    if op == "lte":
        return actual_n <= expected_n
    if op == "gt":
        return actual_n > expected_n
    if op == "gte":
        return actual_n >= expected_n
    return False


def _assert_response(response: httpx.Response, assertions: list[dict[str, Any]]) -> tuple[bool, list[dict[str, Any]]]:
    results = []
    ok = True
    body_text = response.text
    parsed_body: Any = None
    for assertion in assertions or [{"type": "status_code", "operator": "lt", "expected": 500}]:
        typ = (assertion.get("type") or "").lower()
        operator = assertion.get("operator", "eq")
        expected = assertion.get("expected")
        actual: Any = None
        passed = False

        if typ == "status_code":
            actual = response.status_code
            if operator == "eq":
                try:
                    passed = actual == int(expected)
                except (TypeError, ValueError):
                    passed = False
            elif operator == "lt":
                try:
                    passed = actual < int(expected)
                except (TypeError, ValueError):
                    passed = False
            elif operator == "in":
                try:
                    passed = actual in [int(v) for v in expected]
                except (TypeError, ValueError):
                    passed = False
            else:
                passed = _compare(actual, operator, expected)
        elif typ == "body_contains":
            actual = body_text
            passed = str(expected) in body_text
        elif typ == "body_not_contains":
            actual = body_text
            passed = str(expected) not in body_text
        elif typ == "header_exists":
            header_name = str(
                assertion.get("path") or assertion.get("header") or expected or ""
            ).lower()
            keys = {k.lower() for k in response.headers.keys()}
            actual = header_name in keys
            passed = bool(actual)
        elif typ == "header_value":
            header_name = str(assertion.get("path") or assertion.get("header") or "").lower()
            actual = next(
                (v for k, v in response.headers.items() if k.lower() == header_name),
                None,
            )
            passed = _compare(actual, operator, expected)
        elif typ == "json_path":
            if parsed_body is None:
                parsed_body = _safe_response_json(response)
            actual = _get_by_path(parsed_body, assertion.get("path") or "")
            passed = _compare(actual, operator, expected)
        elif typ == "json_path_type":
            if parsed_body is None:
                parsed_body = _safe_response_json(response)
            path = assertion.get("path") or ""
            value = parsed_body if not path.strip().lstrip("$").lstrip(".") else _get_by_path(parsed_body, path)
            actual = _json_type_name(value)
            passed = _compare(actual, operator, expected)
        elif typ == "json_path_length":
            if parsed_body is None:
                parsed_body = _safe_response_json(response)
            path = assertion.get("path") or ""
            value = parsed_body if not path.strip().lstrip("$").lstrip(".") else _get_by_path(parsed_body, path)
            try:
                actual = len(value) if value is not None else 0
            except TypeError:
                actual = None
            passed = _compare(actual, operator, expected)
        else:
            actual = None
            passed = False
        ok = ok and passed
        results.append({**assertion, "actual": actual, "passed": passed})
    return ok, results


def _extract_variables(response: httpx.Response, extractors: list[dict[str, Any]]) -> dict[str, Any]:
    """根据用例的 extractors 配置从响应中提取变量。

    支持的 source（兼容 type 字段同义）：
    - `json_path`: 从 JSON 响应体按点路径取值
    - `header`: 从响应头取值（path 即头名）
    - `regex`: 用正则在响应体上匹配，返回第一个分组（无分组则整体）

    返回 {name: value} 字典；解析失败的 extractor 该 key 设为 None。
    """
    if not extractors:
        return {}
    extracted: dict[str, Any] = {}
    parsed_body: Any = None
    body_text = response.text
    for extractor in extractors:
        if not isinstance(extractor, dict):
            continue
        name = (extractor.get("name") or "").strip()
        if not name:
            continue
        source = (extractor.get("source") or extractor.get("type") or "json_path").lower()
        path = extractor.get("path") or extractor.get("expression") or ""
        try:
            if source == "json_path":
                if parsed_body is None:
                    parsed_body = _safe_response_json(response)
                extracted[name] = _get_by_path(parsed_body, path)
            elif source == "header":
                target = path.lower()
                extracted[name] = next(
                    (v for k, v in response.headers.items() if k.lower() == target),
                    None,
                )
            elif source == "regex":
                match = re.search(path, body_text) if path else None
                if match:
                    extracted[name] = match.group(1) if match.groups() else match.group(0)
                else:
                    extracted[name] = None
            else:
                extracted[name] = None
        except Exception:
            extracted[name] = None
    return extracted


def execute_api_case(record_id: int) -> dict[str, Any]:
    record = ApiExecutionRecord.objects.select_related("test_case", "environment", "project").get(id=record_id)
    return _execute_api_record(record)


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


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    try:
        parts = (token or "").split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return None


def _jwt_seconds_left(token: str) -> int | None:
    payload = _decode_jwt_payload(token)
    if not payload or "exp" not in payload:
        return None
    try:
        return int(payload["exp"]) - int(time.time())
    except Exception:
        return None


def _parse_cookie_header(cookie_header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in (cookie_header or "").split(";"):
        chunk = part.strip()
        if not chunk or "=" not in chunk:
            continue
        key, value = chunk.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _build_cookie_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


def _extract_set_cookie_map(response: httpx.Response) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        if not header or "=" not in header:
            continue
        pair = header.split(";", 1)[0]
        if "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        cookie_map[key.strip()] = value.strip()
    return cookie_map


def _module_lineage_ids(module: ApiModule | None) -> list[int]:
    lineage: list[int] = []
    current = module
    while current:
        lineage.append(current.id)
        current = getattr(current, "parent", None)
    return list(reversed(lineage))


def _collect_module_scripts(case: ApiTestCase, script_type: str) -> list[str]:
    lineage_ids = _module_lineage_ids(case.module)
    scripts = list(
        ApiScript.objects.filter(project=case.project, script_type=script_type)
        .filter(models.Q(module__isnull=True) | models.Q(module_id__in=lineage_ids))
        .select_related("module")
    )
    scripts.sort(
        key=lambda item: (
            0 if item.module_id is None else lineage_ids.index(item.module_id) + 1,
            item.id,
        )
    )
    return [str(item.content or "").strip() for item in scripts if str(item.content or "").strip()]


def _run_js_script(content: str, state: dict[str, Any], *, label: str) -> dict[str, Any]:
    script = str(content or "").strip()
    if not script:
        return state
    payload = {
        "script": script,
        "state": {
            "request": deepcopy(state.get("request") or {}),
            "response": deepcopy(state.get("response") or {}),
            "variables": deepcopy(state.get("variables") or {}),
            "extracted": deepcopy(state.get("extracted") or {}),
            "assertions": deepcopy(state.get("assertions") or []),
        },
    }
    try:
        result = subprocess.run(
            ["node", str(JS_SCRIPT_RUNNER)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{label}执行超时") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip() or "未知错误"
        raise RuntimeError(f"{label}执行失败：{detail}")
    try:
        output = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{label}返回了不可解析的结果") from exc
    return {
        "request": output.get("request") or deepcopy(state.get("request") or {}),
        "response": output.get("response") or deepcopy(state.get("response") or {}),
        "variables": output.get("variables") or deepcopy(state.get("variables") or {}),
        "extracted": output.get("extracted") or deepcopy(state.get("extracted") or {}),
        "assertions": output.get("assertions") or deepcopy(state.get("assertions") or []),
        "logs": output.get("logs") or [],
    }


def _refresh_env_auth_headers(env: ApiEnvironmentConfig, force: bool = False) -> tuple[dict[str, Any], bool]:
    headers = deepcopy(env.headers or {})
    cookie_map = _parse_cookie_header(str(headers.get("Cookie") or ""))
    auth_header = str(headers.get("Authorization") or "")
    access_token = auth_header.split(" ", 1)[1].strip() if auth_header.lower().startswith("bearer ") else ""
    if not access_token:
        access_token = cookie_map.get("SAFAR_ACCESS_TOKEN", "")
    refresh_token = cookie_map.get("SAFAR_REFRESH_TOKEN", "")
    xsrf_token = str(
        headers.get("X-CSRF-Token")
        or headers.get("x-csrf-token")
        or headers.get("X-XSRF-Token")
        or cookie_map.get("XSRF_TOKEN")
        or ""
    )

    if not refresh_token:
        return headers, False

    seconds_left = _jwt_seconds_left(access_token) if access_token else None
    if not force and seconds_left is not None and seconds_left > 300:
        return headers, False

    base_url = (env.base_url or "").rstrip("/")
    if not base_url:
        return headers, False

    refresh_headers = deepcopy(headers)
    if xsrf_token:
        refresh_headers["X-XSRF-Token"] = xsrf_token
        refresh_headers["X-CSRF-Token"] = xsrf_token
    refresh_headers["Cookie"] = _build_cookie_header(cookie_map)
    if access_token:
        refresh_headers["Authorization"] = f"Bearer {access_token}"

    refresh_url = urljoin(f"{base_url}/", "api/v1/auth/refresh")
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.post(refresh_url, headers=refresh_headers, json=None)
    response.raise_for_status()

    new_cookies = _extract_set_cookie_map(response)
    access_token = new_cookies.get("SAFAR_ACCESS_TOKEN") or access_token
    refresh_token = new_cookies.get("SAFAR_REFRESH_TOKEN") or refresh_token
    xsrf_token = new_cookies.get("XSRF_TOKEN") or xsrf_token
    if not access_token:
        return headers, False

    cookie_map["SAFAR_ACCESS_TOKEN"] = access_token
    cookie_map["SAFAR_REFRESH_TOKEN"] = refresh_token
    if xsrf_token:
        cookie_map["XSRF_TOKEN"] = xsrf_token

    headers["Authorization"] = f"Bearer {access_token}"
    headers["Cookie"] = _build_cookie_header(cookie_map)
    if xsrf_token:
        headers["X-XSRF-Token"] = xsrf_token
        headers["X-CSRF-Token"] = xsrf_token

    env.headers = headers
    env.save(update_fields=["headers", "updated_at"])
    return headers, True


def _apply_browser_like_headers(headers: dict[str, Any]) -> dict[str, Any]:
    normalized = {str(k).lower(): k for k in headers.keys()}
    for key, value in BROWSER_LIKE_HEADERS.items():
        if key.lower() not in normalized:
            headers[key] = value
    if "x-trace-id" not in normalized:
        headers["X-Trace-Id"] = f"whart-{uuid.uuid4().hex[:12]}"
    return headers


def _execute_api_record(record: ApiExecutionRecord, inherited_variables: dict[str, Any] | None = None) -> dict[str, Any]:
    case = record.test_case
    env = record.environment or case.environment or ApiEnvironmentConfig.objects.filter(project=case.project, is_default=True).first()
    variables = _public_variables(case.project)
    if env:
        variables.update({str(k): str(v) for k, v in (env.variables or {}).items()})
    if inherited_variables:
        variables.update({str(k): v for k, v in inherited_variables.items() if v is not None})

    record.status = 1
    record.start_time = timezone.now()
    record.save(update_fields=["status", "start_time"])

    start = time.perf_counter()
    try:
        env_headers = deepcopy(env.headers if env else {})
        if env:
            env_headers, _ = _refresh_env_auth_headers(env)
        case_headers = _render_value(case.headers or {}, variables)
        request_context = {
            "method": case.method,
            "url": _build_url(env, _render_value(case.path, variables)),
            "headers": {**deepcopy(env_headers), **deepcopy(case_headers)},
            "query_params": _render_value(case.query_params or {}, variables),
            "body": _render_value(case.body or {}, variables),
        }

        for content in [*_collect_module_scripts(case, "pre"), str(case.pre_script or "").strip()]:
            if not content:
                continue
            state = _run_js_script(
                content,
                {"request": request_context, "variables": variables},
                label=f"前置脚本[{case.name}]",
            )
            request_context = deepcopy(state["request"])
            variables = deepcopy(state["variables"])

        headers = _apply_browser_like_headers(deepcopy(request_context.get("headers") or {}))
        query_params = deepcopy(request_context.get("query_params") or {})
        body = deepcopy(request_context.get("body") or {})
        url = str(request_context.get("url") or "")
        if not url:
            raise RuntimeError("请求 URL 不能为空")

        if "X-XSRF-Token" in headers and "X-CSRF-Token" not in headers:
            headers["X-CSRF-Token"] = headers["X-XSRF-Token"]
        if case.path.startswith("/api/v1/admin/dashboard/tactical-overview") and env and env.base_url:
            headers["Referer"] = f"{env.base_url.rstrip('/')}/dashboard"

        request_data = {
            "method": str(request_context.get("method") or case.method),
            "url": url,
            "headers": headers,
            "query_params": query_params,
            "body": body,
        }
        dashboard_page_url = (
            urljoin(f"{env.base_url.rstrip('/')}/", "dashboard")
            if case.path.startswith("/api/v1/admin/dashboard/tactical-overview") and env and env.base_url
            else ""
        )

        def _send(current_headers: dict[str, Any]):
            with httpx.Client(timeout=30.0, follow_redirects=True) as client:
                if dashboard_page_url:
                    client.get(dashboard_page_url, headers=current_headers)
                return client.request(
                    str(request_data["method"] or case.method),
                    url,
                    headers=current_headers,
                    params=query_params,
                    json=body if body not in ({}, None, "") else None,
                )

        response = _send(headers)
        if response.status_code == 403 and "not allowed for portal" in (response.text or "") and dashboard_page_url:
            time.sleep(0.15)
            response = _send(headers)
        if response.status_code == 401 and env:
            refreshed_headers, refreshed = _refresh_env_auth_headers(env, force=True)
            if refreshed:
                headers = deepcopy(refreshed_headers)
                headers.update(case_headers)
                headers = _apply_browser_like_headers(headers)
                if case.path.startswith("/api/v1/admin/dashboard/tactical-overview") and env and env.base_url:
                    headers["Referer"] = f"{env.base_url.rstrip('/')}/dashboard"
                request_data["headers"] = headers
                response = _send(headers)
        rendered_assertions = _render_value(deepcopy(case.assertions or []), variables)
        passed, assertion_results = _assert_response(response, rendered_assertions)
        extracted = _extract_variables(response, case.extractors or [])
        duration = time.perf_counter() - start
        response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "json": _safe_response_json(response),
            "text": response.text[:20000],
            "assertions": assertion_results,
            "extracted": extracted,
        }
        for content in [*_collect_module_scripts(case, "post"), str(case.post_script or "").strip()]:
            if not content:
                continue
            state = _run_js_script(
                content,
                {
                    "request": request_data,
                    "response": response_data,
                    "variables": variables,
                    "extracted": extracted,
                    "assertions": assertion_results,
                },
                label=f"后置脚本[{case.name}]",
            )
            request_data = deepcopy(state["request"])
            response_data = deepcopy(state["response"])
            variables = deepcopy(state["variables"])
            extracted = deepcopy(state["extracted"])
            assertion_results = deepcopy(state["assertions"])

        response_data["assertions"] = assertion_results
        response_data["extracted"] = extracted
        response_data["runtime_variables"] = deepcopy(variables)
        passed = all(bool(item.get("passed", True)) for item in assertion_results) if assertion_results else passed
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


def execute_api_scenario(record_id: int) -> dict[str, Any]:
    scenario_record = ApiScenarioExecutionRecord.objects.select_related("scenario", "environment", "project").get(id=record_id)
    scenario = scenario_record.scenario
    steps = list(
        scenario.steps.select_related("test_case", "test_case__environment")
        .filter(is_enabled=True)
        .order_by("order", "id")
    )

    scenario_record.status = 1
    scenario_record.start_time = timezone.now()
    scenario_record.save(update_fields=["status", "start_time"])
    ApiScenario.objects.filter(id=scenario.id).update(status=1, error_message="")

    shared_variables: dict[str, Any] = deepcopy(scenario_record.variables_snapshot or {})
    start = time.perf_counter()
    passed = 0
    failed = 0
    step_summaries: list[dict[str, Any]] = []
    last_error = ""

    for step in steps:
        case = step.test_case
        execution_record = ApiExecutionRecord.objects.create(
            project=case.project,
            test_case=case,
            environment=scenario_record.environment or case.environment,
            status=0,
            trigger_type=scenario_record.trigger_type,
            executor=scenario_record.executor,
        )
        step_record = ApiScenarioStepRecord.objects.create(
            scenario_execution=scenario_record,
            step=step,
            test_case=case,
            execution_record=execution_record,
            order=step.order,
            status=1,
            start_time=timezone.now(),
        )
        result = _execute_api_record(execution_record, inherited_variables=shared_variables)
        execution_record.refresh_from_db()
        runtime_variables = ((execution_record.response_data or {}).get("runtime_variables") or {}) if execution_record.status == 2 else {}
        extracted = ((execution_record.response_data or {}).get("extracted") or {}) if execution_record.status == 2 else {}
        shared_variables.update({str(k): v for k, v in runtime_variables.items() if v not in (None, "")})
        shared_variables.update({str(k): v for k, v in extracted.items() if v not in (None, "")})

        step_record.status = 2 if execution_record.status == 2 else 3
        step_record.extracted_variables = extracted
        step_record.error_message = execution_record.error_message
        step_record.duration = execution_record.duration
        step_record.end_time = timezone.now()
        step_record.save()

        if execution_record.status == 2:
            passed += 1
        else:
            failed += 1
            last_error = execution_record.error_message or result.get("error") or "接口断言未通过"

        step_summaries.append({
            "order": step.order,
            "name": step.name or case.name,
            "test_case_id": case.id,
            "status": execution_record.status,
            "duration": execution_record.duration,
            "error_message": execution_record.error_message,
            "extracted": extracted,
        })

        if execution_record.status != 2 and step.stop_on_failure:
            remaining_steps = scenario.steps.filter(is_enabled=True, order__gt=step.order).order_by("order", "id")
            for pending in remaining_steps:
                ApiScenarioStepRecord.objects.create(
                    scenario_execution=scenario_record,
                    step=pending,
                    test_case=pending.test_case,
                    order=pending.order,
                    status=4,
                    error_message="前置步骤失败，已跳过",
                )
            break

    duration = time.perf_counter() - start
    final_status = 2 if failed == 0 and steps else 3
    summary = {
        "total_steps": len(steps),
        "passed_steps": passed,
        "failed_steps": failed,
        "shared_variables": shared_variables,
        "steps": step_summaries,
    }
    scenario_record.status = final_status
    scenario_record.result_summary = summary
    scenario_record.variables_snapshot = shared_variables
    scenario_record.error_message = "" if final_status == 2 else last_error
    scenario_record.duration = duration
    scenario_record.end_time = timezone.now()
    scenario_record.save()
    ApiScenario.objects.filter(id=scenario.id).update(
        status=final_status,
        last_result=summary,
        error_message="" if final_status == 2 else last_error,
    )
    return {"status": "success" if final_status == 2 else "failed", "record_id": scenario_record.id}

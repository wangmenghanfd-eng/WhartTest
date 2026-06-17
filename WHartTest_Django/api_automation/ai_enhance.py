# -*- coding: utf-8 -*-
"""AI 增强：让 LLM 给现有的接口用例补全断言、变量提取器、参数化建议。

入口：
    enhance_api_case(case_id, apply: bool = False) -> dict

返回结构：
    {
      "case_id": int,
      "current": {"assertions": [...], "extractors": [...]},
      "suggested": {"assertions": [...], "extractors": [...]},
      "merged":    {"assertions": [...], "extractors": [...]},
      "rationale": str,
      "applied": bool,
    }
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from langgraph_integration.models import LLMConfig
from requirements.services import (
    create_llm_instance,
    extract_json_from_response,
    safe_llm_invoke,
)
from .services import _get_by_path

from .models import ApiExecutionRecord, ApiTestCase

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是 API 测试领域的资深工程师。给你一份现有的接口用例（含 method/path/headers/body/已有断言/已有提取器），还可能有它最近一次执行返回的样本响应。

请给这条用例**补全**：
1. 更全的 assertions（覆盖状态码、关键字段、长度/类型校验等）
2. 必要的 extractors（把响应里"后续用例可能需要的"字段提取成变量）

严格输出如下 JSON：
{
  "assertions": [
    {"type": "status_code|json_path|json_path_length|json_path_type|body_contains|body_not_contains|header_exists|header_value",
     "operator": "eq|neq|gt|gte|lt|lte|contains|not_contains|regex|is_empty|is_not_empty|in|not_in",
     "expected": <值>,
     "target": "可选：json_path 表达式或 header 名称"}
  ],
  "extractors": [
    {"name": "提取后变量名",
     "source": "json_path|header|status_code|body",
     "expression": "提取表达式，例如 data.token"}
  ],
  "rationale": "中文解释，不超过 200 字"
}

硬性要求：
- 输出必须是合法 JSON，不要添加 Markdown 代码块以外的内容
- 不要重复用户已有的 assertions/extractors
- 不要生成大量重复的 json_path_type=string 断言；优先保留关键字段的少量高价值类型校验
- 如果没有需要新增的项，对应数组就给空 []
- status_code 的期望值要按方法选择默认：POST 用 201，DELETE 用 204，PUT/PATCH 多数 200，GET 200。如果上次执行（last_execution）给出了真实 status_code，请优先以它为准。
"""


def _summarize_last_execution(case: ApiTestCase) -> dict[str, Any] | None:
    rec = (
        ApiExecutionRecord.objects.filter(test_case=case, status=2)
        .exclude(response_data={})
        .order_by("-id")
        .first()
    )
    if not rec:
        rec = (
            ApiExecutionRecord.objects.filter(test_case=case)
            .exclude(response_data={})
            .order_by("-id")
            .first()
        )
    if not rec or not rec.response_data:
        return None
    rd = rec.response_data
    text = rd.get("text") or ""
    return {
        "status_code": rd.get("status_code"),
        "headers_sample": dict(list((rd.get("headers") or {}).items())[:8]),
        "body_text_excerpt": text[:1500],
    }


def _dedup_dicts(items: list[dict[str, Any]], keys: list[str]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = tuple(json.dumps(item.get(k), sort_keys=True, ensure_ascii=False) for k in keys)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _normalize_suggestion(payload: Any) -> dict[str, list[dict[str, Any]]] | None:
    if not isinstance(payload, dict):
        return None
    assertions = payload.get("assertions") or []
    extractors = payload.get("extractors") or []
    if not isinstance(assertions, list) or not isinstance(extractors, list):
        return None
    normalized_assertions: list[dict[str, Any]] = []
    for raw in assertions:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        typ = str(item.get("type") or "").strip().lower()
        target = (item.get("target") or item.get("path") or item.get("header") or "").strip()
        operator = str(item.get("operator") or "").strip().lower()
        if typ == "header":
            item["type"] = "header_value" if target else "header_exists"
        elif typ == "body_text":
            item["type"] = "body_not_contains" if operator == "not_contains" else "body_contains"
        elif typ == "response_time":
            continue
        if target:
            item["target"] = target
            item["path"] = target
        normalized_assertions.append(item)
    return {
        "assertions": normalized_assertions,
        "extractors": [
            {
                **e,
                "expression": (e.get("expression") or e.get("path") or "").strip(),
                "path": (e.get("path") or e.get("expression") or "").strip(),
            }
            for e in extractors
            if isinstance(e, dict) and (e.get("name") or "").strip()
        ],
    }


def _try_parse_json_excerpt(text: str) -> Any | None:
    if not text or not isinstance(text, str):
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except Exception:
        return None


def _to_snake_case(name: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z]+", "_", name or "").strip("_")
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()
    return value


def _collect_scalar_paths(node: Any, prefix: str = "", depth: int = 0) -> list[tuple[str, Any]]:
    if depth > 3:
        return []
    items: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (str, int, float, bool)) or value is None:
                items.append((path, value))
            else:
                items.extend(_collect_scalar_paths(value, path, depth + 1))
    elif isinstance(node, list) and node:
        first = node[0]
        path = f"{prefix}[0]" if prefix else "[0]"
        if isinstance(first, (str, int, float, bool)) or first is None:
            items.append((path, first))
        else:
            items.extend(_collect_scalar_paths(first, path, depth + 1))
    return items


def _build_heuristic_extractors(case: ApiTestCase, last_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    body_text = (last_summary or {}).get("body_text_excerpt") or ""
    parsed = _try_parse_json_excerpt(body_text)
    if parsed is None:
        return []

    preferred_tokens = (
        "token", "access_token", "refresh_token", "id", "user_id", "crisis_id",
        "code", "crisis_no", "username", "user_type", "no",
    )

    candidates: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for path, _value in _collect_scalar_paths(parsed):
        key_name = path.split(".")[-1].replace("[0]", "").strip()
        normalized_key = _to_snake_case(key_name)
        if not normalized_key:
            continue
        score = 0
        lowered = normalized_key.lower()
        for idx, token in enumerate(preferred_tokens):
            if token in lowered:
                score = max(score, len(preferred_tokens) - idx)
        if score <= 0:
            continue
        name = normalized_key
        if name in seen_names:
            continue
        seen_names.add(name)
        candidates.append(
            {
                "name": name,
                "source": "json_path",
                "expression": path,
                "path": path,
                "_score": score,
            }
        )

    candidates.sort(key=lambda item: (-int(item.get("_score") or 0), len(str(item.get("path") or ""))))
    return [{k: v for k, v in item.items() if not k.startswith("_")} for item in candidates[:4]]


def _compact_extractors(extractors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preferred_suffixes = (
        "token", "access_token", "refresh_token", "id", "_id", "code", "_code",
        "crisis_no", "_no", "username", "user_type",
    )
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in extractors:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        name = str(item.get("name") or "").strip().lower()
        source = str(item.get("source") or item.get("type") or "").strip().lower()
        path = str(item.get("expression") or item.get("path") or "").strip()
        if not name or not path:
            continue
        key = (name, source, path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    prioritized = [
        item for item in deduped
        if any(str(item.get("name") or "").strip().lower().endswith(suffix) for suffix in preferred_suffixes)
    ]
    if not prioritized:
        prioritized = deduped
    return prioritized[:4]


def _build_final_rationale(
    assertions: list[dict[str, Any]],
    extractors: list[dict[str, Any]],
    raw_rationale: str,
) -> str:
    assertion_count = len(assertions or [])
    extractor_count = len(extractors or [])
    if assertion_count == 0 and extractor_count == 0:
        return "当前无稳定新增建议；动态字段、空值等值断言和重复提取器已自动过滤。"

    parts: list[str] = []
    if assertion_count:
        parts.append(f"保留了 {assertion_count} 条稳定断言建议")
    if extractor_count:
        parts.append(f"保留了 {extractor_count} 条关键提取建议")
    if raw_rationale and not parts:
        return raw_rationale[:200]
    if raw_rationale and "关键" in raw_rationale and extractor_count:
        parts.append("已优先收敛为后续复用价值更高的关键字段")
    return "，".join(parts) + "。"


def _build_method_default_assertions(case: ApiTestCase, last_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    method = (case.method or "").upper()
    parsed = _try_parse_json_excerpt((last_summary or {}).get("body_text_excerpt") or "")
    status_code = (last_summary or {}).get("status_code")
    defaults: list[dict[str, Any]] = []

    if isinstance(status_code, int):
        defaults.append({"type": "status_code", "operator": "eq", "expected": status_code})

    defaults.append({"type": "header_value", "target": "content-type", "path": "content-type", "operator": "contains", "expected": "application/json"})

    if parsed is None:
        return defaults

    if method in {"POST", "PUT", "PATCH"} and isinstance(parsed, dict):
        stable_fields = ["title", "severity", "classificationLevel", "status"]
        for field in stable_fields:
            if field in parsed and isinstance(parsed.get(field), (str, int, float, bool)):
                defaults.append({
                    "type": "json_path",
                    "operator": "eq",
                    "target": field,
                    "path": field,
                    "expected": parsed.get(field),
                })
        for field in ["id", "declaredBy", "lat", "lng", "radiusKm"]:
            if field in parsed:
                defaults.append({
                    "type": "json_path_type",
                    "operator": "eq",
                    "target": field,
                    "path": field,
                    "expected": "number",
                })
        for field in ["crisisNo", "code", "no"]:
            if field in parsed and isinstance(parsed.get(field), str):
                value = str(parsed.get(field) or "")
                needle = value[:11] if value.startswith("CRISIS-") else value[:8]
                defaults.append({
                    "type": "json_path",
                    "operator": "contains",
                    "target": field,
                    "path": field,
                    "expected": needle,
                })
                break

    if method == "GET":
        if isinstance(parsed, dict):
            if isinstance(parsed.get("items"), list):
                defaults.append({
                    "type": "json_path_type",
                    "operator": "eq",
                    "target": "items",
                    "path": "items",
                    "expected": "array",
                })
                first = parsed["items"][0] if parsed["items"] else None
                if isinstance(first, dict):
                    for field in ["id", "title", "status", "severity", "crisisNo"]:
                        if field in first:
                            value = first.get(field)
                            expected_type = "number" if isinstance(value, (int, float)) else "string"
                            defaults.append({
                                "type": "json_path_type",
                                "operator": "eq",
                                "target": f"items[0].{field}",
                                "path": f"items[0].{field}",
                                "expected": expected_type,
                            })
                return defaults
            if isinstance(parsed.get("stats"), dict):
                defaults.append({
                    "type": "json_path_type",
                    "operator": "eq",
                    "target": "stats",
                    "path": "stats",
                    "expected": "object",
                })
                for field in ["totalIncidents", "totalEvidence", "totalFatalities", "totalInjuries"]:
                    if field in parsed["stats"]:
                        defaults.append({
                            "type": "json_path_type",
                            "operator": "eq",
                            "target": f"stats.{field}",
                            "path": f"stats.{field}",
                            "expected": "number",
                        })
                return defaults
            for field in ["id", "status", "title", "name", "crisisNo", "severity", "realName", "username", "userType"]:
                if field in parsed:
                    expected_type = "number" if isinstance(parsed.get(field), (int, float)) else "string"
                    defaults.append({
                        "type": "json_path_type",
                        "operator": "eq",
                        "target": field,
                        "path": field,
                        "expected": expected_type,
                    })
        elif isinstance(parsed, list) and parsed:
            defaults.append({
                "type": "json_path_type",
                "operator": "eq",
                "target": "[0]",
                "path": "[0]",
                "expected": "object",
            })
            first = parsed[0]
            if isinstance(first, dict):
                for field in ["id", "status", "title", "name", "crisisNo", "severity", "type", "timestamp", "read"]:
                    if field in first:
                        value = first.get(field)
                        if isinstance(value, bool):
                            expected_type = "boolean"
                        elif isinstance(value, (int, float)):
                            expected_type = "number"
                        else:
                            expected_type = "string"
                        defaults.append({
                            "type": "json_path_type",
                            "operator": "eq",
                            "target": f"[0].{field}",
                            "path": f"[0].{field}",
                            "expected": expected_type,
                        })

    return defaults


def _normalize_path_by_response_root(path: str, parsed_body: Any) -> str:
    raw = (path or "").strip()
    if not raw or parsed_body is None:
        return raw
    candidates = [raw]
    if raw.startswith("data."):
        candidates.append(raw[5:])
    elif raw.startswith("data["):
        candidates.append(raw[4:])
    elif raw == "data":
        candidates.append("")
    if isinstance(parsed_body, dict) and "data" in parsed_body and raw and not raw.startswith("data."):
        candidates.append(f"data.{raw}")
    for candidate in candidates:
        try:
            value = _get_by_path(parsed_body, candidate)
        except Exception:
            value = None
        if value is not None:
            return candidate
    return raw


def _path_exists_in_body(path: str, parsed_body: Any) -> bool:
    if parsed_body is None:
        return False
    try:
        return _get_by_path(parsed_body, path) is not None
    except Exception:
        return False


def _normalize_assertions_by_response_root(assertions: list[dict[str, Any]], last_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    parsed_body = _try_parse_json_excerpt((last_summary or {}).get("body_text_excerpt") or "")
    if parsed_body is None:
        return assertions
    normalized: list[dict[str, Any]] = []
    for raw in assertions:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if item.get("type") in {"json_path", "json_path_length", "json_path_type"}:
            target = _normalize_assertion_target(item.get("target") or item.get("path"))
            normalized_target = _normalize_path_by_response_root(target, parsed_body)
            item["target"] = normalized_target
            item["path"] = normalized_target
        normalized.append(item)
    return normalized


def _filter_assertions_by_response_root(assertions: list[dict[str, Any]], last_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    parsed_body = _try_parse_json_excerpt((last_summary or {}).get("body_text_excerpt") or "")
    if parsed_body is None:
        return assertions
    filtered: list[dict[str, Any]] = []
    for raw in assertions:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if item.get("type") in {"json_path", "json_path_length", "json_path_type"}:
            target = str(item.get("target") or item.get("path") or "").strip()
            if not target or not _path_exists_in_body(target, parsed_body):
                continue
        filtered.append(item)
    return filtered


def _normalize_extractors_by_response_root(extractors: list[dict[str, Any]], last_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    parsed_body = _try_parse_json_excerpt((last_summary or {}).get("body_text_excerpt") or "")
    if parsed_body is None:
        return extractors
    normalized: list[dict[str, Any]] = []
    for raw in extractors:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if item.get("source") == "json_path":
            expr = str(item.get("expression") or item.get("path") or "").strip()
            normalized_expr = _normalize_path_by_response_root(expr, parsed_body)
            item["expression"] = normalized_expr
            item["path"] = normalized_expr
        normalized.append(item)
    return normalized


def _filter_extractors_by_response_root(extractors: list[dict[str, Any]], last_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    parsed_body = _try_parse_json_excerpt((last_summary or {}).get("body_text_excerpt") or "")
    if parsed_body is None:
        return extractors
    filtered: list[dict[str, Any]] = []
    for raw in extractors:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        if item.get("source") == "json_path":
            expr = str(item.get("expression") or item.get("path") or "").strip()
            if not expr or not _path_exists_in_body(expr, parsed_body):
                continue
        filtered.append(item)
    return filtered


def _merge_assertions(current: list[dict[str, Any]], suggested: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str, str], int] = {}

    def key_of(item: dict[str, Any]) -> tuple[str, str, str]:
        typ = str(item.get("type") or "").strip()
        target = str(item.get("target") or item.get("path") or "").strip()
        operator = str(item.get("operator") or "").strip()
        return (typ, target, operator)

    for source in current or []:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        index_by_key[key_of(item)] = len(merged)
        merged.append(item)
    for source in suggested or []:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        key = key_of(item)
        if key in index_by_key:
            merged[index_by_key[key]] = item
        else:
            index_by_key[key] = len(merged)
            merged.append(item)
    return merged


def _merge_extractors(current: list[dict[str, Any]], suggested: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str], int] = {}

    def key_of(item: dict[str, Any]) -> tuple[str, str]:
        return (
            str(item.get("name") or "").strip(),
            str(item.get("source") or item.get("type") or "").strip(),
        )

    for source in current or []:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        index_by_key[key_of(item)] = len(merged)
        merged.append(item)
    for source in suggested or []:
        if not isinstance(source, dict):
            continue
        item = dict(source)
        key = key_of(item)
        if key in index_by_key:
            merged[index_by_key[key]] = item
        else:
            index_by_key[key] = len(merged)
            merged.append(item)
    return merged


def _assertion_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("type") or "").strip(),
        str(item.get("operator") or "").strip(),
        str(item.get("target") or item.get("path") or "").strip(),
        json.dumps(item.get("expected"), sort_keys=True, ensure_ascii=False),
    )


def _extractor_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("name") or "").strip(),
        str(item.get("source") or item.get("type") or "").strip(),
        str(item.get("expression") or item.get("path") or "").strip(),
    )


def _subtract_assertions(full_items: list[dict[str, Any]], current_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_keys = {_assertion_key(item) for item in current_items or [] if isinstance(item, dict)}
    return [item for item in full_items or [] if isinstance(item, dict) and _assertion_key(item) not in current_keys]


def _subtract_extractors(full_items: list[dict[str, Any]], current_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current_keys = {_extractor_key(item) for item in current_items or [] if isinstance(item, dict)}
    return [item for item in full_items or [] if isinstance(item, dict) and _extractor_key(item) not in current_keys]


def _adjust_status_code_assertions(
    assertions: list[dict[str, Any]],
    method: str,
    last_status_code: int | None = None,
) -> list[dict[str, Any]]:
    """LLM 偶尔会把 POST/DELETE 的 status_code 也写成 200。这里按方法兜底修正。

    优先级：last_execution 真实状态码 > 方法默认值。
    """
    method = (method or "").upper()
    method_default = {"POST": 201, "DELETE": 204}.get(method)
    if last_status_code is None and method_default is None:
        return assertions
    fixed: list[dict[str, Any]] = []
    for raw in assertions:
        if not isinstance(raw, dict):
            fixed.append(raw)
            continue
        item = dict(raw)
        if (
            item.get("type") == "status_code"
            and item.get("operator") == "eq"
            and isinstance(item.get("expected"), int)
            and item.get("expected") == 200
        ):
            target = last_status_code if last_status_code is not None else method_default
            if target and target != 200:
                item["expected"] = target
        fixed.append(item)
    return fixed


def _normalize_assertion_target(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _compact_assertions(assertions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    收紧 AI 生成的断言，避免大量低价值的重复 json_path_type/string 断言。
    """
    value_targets = {
        _normalize_assertion_target(item.get("target"))
        for item in assertions
        if isinstance(item, dict)
        and item.get("type") in {"json_path", "json_path_length"}
        and _normalize_assertion_target(item.get("target"))
    }

    string_type_assertions: list[dict[str, Any]] = []
    other_assertions: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for raw in assertions:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item_type = str(item.get("type") or "").strip()
        operator = str(item.get("operator") or "").strip()
        target = _normalize_assertion_target(item.get("target"))
        expected = str(item.get("expected") or "").strip().lower()
        dedup_key = (item_type, operator, target, expected)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        if item_type == "json_path_type" and expected == "string":
            if target in value_targets:
                continue
            string_type_assertions.append(item)
            continue

        other_assertions.append(item)

    keep_string_type = string_type_assertions[:3]
    return other_assertions + keep_string_type


def _last_path_segment(path: str) -> str:
    if not path:
        return ""
    segment = re.sub(r"\[\d+\]", "", path).split(".")[-1]
    return segment.strip()


def _infer_json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return ""


def _sanitize_assertions_for_case(
    assertions: list[dict[str, Any]],
    case: ApiTestCase,
    last_summary: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    parsed_body = _try_parse_json_excerpt((last_summary or {}).get("body_text_excerpt") or "")
    method = (case.method or "").upper()
    stable_enum_fields = {"status", "severity", "classificationLevel", "userType", "type", "read"}
    stable_get_item_presence_fields = {"crisisNo", "title", "status", "type", "id", "username", "realName", "userType"}
    dynamic_fields = {
        "id", "crisisNo", "code", "no", "link", "href", "url", "timestamp",
        "createdAt", "updatedAt", "declaredAt", "resolvedAt", "description", "message",
    }
    volatile_text_fields = {"link", "href", "url", "timestamp", "description", "message"}
    optional_empty_fields = {"dateFrom", "dateTo", "resolvedAt", "titleAr", "areaSpec"}

    sanitized: list[dict[str, Any]] = []
    for raw in assertions:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item_type = str(item.get("type") or "").strip()
        operator = str(item.get("operator") or "").strip().lower()
        target = _normalize_assertion_target(item.get("target") or item.get("path"))
        target_segment = _last_path_segment(target)
        actual = None
        if item_type in {"json_path", "json_path_length", "json_path_type"} and parsed_body is not None and target:
            try:
                actual = _get_by_path(parsed_body, target)
            except Exception:
                actual = None

        if item_type == "json_path_type" and actual is None:
            continue
        if item_type == "json_path_type" and actual is not None:
            actual_type = _infer_json_type(actual)
            expected_type = str(item.get("expected") or "").strip().lower()
            if actual_type and expected_type and actual_type != expected_type:
                item["expected"] = actual_type

        if item_type == "json_path" and operator == "eq":
            if actual is None:
                continue
            if target_segment == "portal" and method == "GET":
                continue
            if target_segment in dynamic_fields:
                continue
            if method == "GET" and re.search(r"\[\d+\]\.", target):
                continue
            if method == "GET" and (target.startswith("items[") or target.startswith("[0].")):
                if target_segment not in stable_enum_fields:
                    continue
            if isinstance(actual, (int, float)) and method == "GET":
                continue
            if isinstance(actual, (int, float)) and method in {"POST", "PUT", "PATCH"}:
                continue
            if item.get("expected") == "" and method in {"POST", "PUT", "PATCH"}:
                continue
            if actual is not None and item.get("expected") != actual and (
                method == "GET" or target_segment in stable_enum_fields or target_segment in dynamic_fields
            ):
                continue

        if item_type == "json_path" and operator == "regex":
            if target_segment in dynamic_fields:
                continue

        if item_type == "json_path" and operator == "is_not_empty":
            if target_segment in optional_empty_fields and actual in {"", None}:
                continue
            if target_segment in volatile_text_fields:
                continue
            if method == "GET" and (target.startswith("items[0].") or target.startswith("[0].")) and target_segment not in stable_get_item_presence_fields:
                continue
            if method == "GET" and target.count(".") >= 2 and target_segment not in stable_enum_fields:
                continue

        if item_type == "json_path" and operator in {"in", "not_in"}:
            if method == "GET":
                continue

        if item_type == "json_path" and target in {"$.length"}:
            continue

        if item_type == "json_path" and operator == "is_not_empty" and target.endswith(".length"):
            continue

        if item_type == "header_exists":
            if target.lower() not in {"content-type", "x-trace-id"}:
                continue

        if item_type == "header_value":
            if target.lower() != "content-type":
                continue
            if operator not in {"contains", "eq"}:
                continue

        if item_type == "json_path_length":
            if actual is None:
                continue
            if target in {"$.length"} or target.endswith(".length"):
                continue
            if isinstance(actual, str):
                continue
            if target_segment in dynamic_fields:
                if operator == "eq":
                    item["operator"] = "gte"
                    item["expected"] = 1
                elif operator in {"gt", "gte"}:
                    item["expected"] = max(1, int(item.get("expected") or 1))
            if target_segment == "portal" and method == "GET":
                continue

        sanitized.append(item)

    return _compact_assertions(sanitized)


def _build_messages(case: ApiTestCase) -> list:
    last_resp = _summarize_last_execution(case)
    payload = {
        "case": {
            "id": case.id,
            "name": case.name,
            "method": case.method,
            "path": case.path,
            "headers": case.headers,
            "query_params": case.query_params,
            "body": case.body,
            "current_assertions": case.assertions or [],
            "current_extractors": case.extractors or [],
        },
        "last_execution": last_resp,
    }
    user_text = (
        "请为下面的接口用例补全 assertions / extractors。返回 JSON：\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]


def enhance_api_case(
    case_id: int,
    apply: bool = False,
    suggested_override: dict[str, Any] | None = None,
    fast_mode: bool = False,
) -> dict[str, Any]:
    """让 LLM 给用例补充断言/提取器。

    apply=False（默认）只返回建议；apply=True 会把建议合并写回用例。
    """
    case = ApiTestCase.objects.get(id=case_id)
    if suggested_override is not None:
        payload = {"assertions": [], "extractors": [], "rationale": ""}
        if isinstance(suggested_override, dict):
            payload.update(suggested_override)
        rationale = payload.get("rationale", "") if isinstance(payload, dict) else ""
        suggestion = _normalize_suggestion(payload) or {"assertions": [], "extractors": []}
    else:
        config = LLMConfig.objects.filter(is_active=True).first()
        if fast_mode or not config:
            payload = {"assertions": [], "extractors": [], "rationale": ""}
            if fast_mode:
                payload["rationale"] = "已基于最近一次真实响应和接口方法快速生成增强建议。"
            elif not config:
                payload["rationale"] = ""
            rationale = payload.get("rationale", "") if isinstance(payload, dict) else ""
            suggestion = _normalize_suggestion(payload) or {"assertions": [], "extractors": []}
        else:
            llm = create_llm_instance(config, temperature=0.2)
            messages = _build_messages(case)
            response = safe_llm_invoke(llm, messages, max_retries=3, retry_delay=2)
            content = getattr(response, "content", "") or ""
            payload = extract_json_from_response(content) or {}
            rationale = payload.get("rationale", "") if isinstance(payload, dict) else ""
            suggestion = _normalize_suggestion(payload) or {"assertions": [], "extractors": []}

    last_summary = _summarize_last_execution(case)
    last_status_code = (last_summary or {}).get("status_code") if last_summary else None
    suggestion["assertions"] = _adjust_status_code_assertions(
        suggestion["assertions"], case.method, last_status_code
    )
    method_default_assertions = _build_method_default_assertions(case, last_summary)
    suggestion["assertions"] = _dedup_dicts(
        method_default_assertions + list(suggestion["assertions"]),
        ["type", "operator", "expected", "target", "path"],
    )
    suggestion["assertions"] = _normalize_assertions_by_response_root(suggestion["assertions"], last_summary)
    suggestion["assertions"] = _filter_assertions_by_response_root(suggestion["assertions"], last_summary)
    suggestion["assertions"] = _sanitize_assertions_for_case(suggestion["assertions"], case, last_summary)
    heuristic_extractors = _build_heuristic_extractors(case, last_summary)
    suggestion["extractors"] = _dedup_dicts(
        list(suggestion["extractors"]) + heuristic_extractors,
        ["name", "source", "expression", "path"],
    )
    suggestion["extractors"] = _normalize_extractors_by_response_root(suggestion["extractors"], last_summary)
    suggestion["extractors"] = _filter_extractors_by_response_root(suggestion["extractors"], last_summary)
    suggestion["extractors"] = _compact_extractors(suggestion["extractors"])

    current_assertions = _adjust_status_code_assertions(
        list(case.assertions or []), case.method, last_status_code
    )
    current_assertions = _normalize_assertions_by_response_root(current_assertions, last_summary)
    current_assertions = _filter_assertions_by_response_root(current_assertions, last_summary)
    current_assertions = _sanitize_assertions_for_case(current_assertions, case, last_summary)
    current_extractors = case.extractors or []
    current_extractors = _normalize_extractors_by_response_root(list(current_extractors), last_summary)
    current_extractors = _compact_extractors(current_extractors)
    merged_assertions = _merge_assertions(list(current_assertions), suggestion["assertions"])
    suggestion["assertions"] = _compact_assertions(suggestion["assertions"])
    merged_assertions = _compact_assertions(merged_assertions)
    merged_extractors = _merge_extractors(list(current_extractors), suggestion["extractors"])
    merged_extractors = _compact_extractors(merged_extractors)
    suggestion["assertions"] = _subtract_assertions(merged_assertions, current_assertions)
    suggestion["extractors"] = _subtract_extractors(merged_extractors, current_extractors)
    rationale = _build_final_rationale(suggestion["assertions"], suggestion["extractors"], rationale)

    applied = False
    if apply and (
        suggestion["assertions"]
        or suggestion["extractors"]
        or current_assertions != list(case.assertions or [])
        or current_extractors != list(case.extractors or [])
    ):
        case.assertions = merged_assertions
        case.extractors = merged_extractors
        case.save(update_fields=["assertions", "extractors", "updated_at"])
        applied = True

    return {
        "case_id": case.id,
        "current": {"assertions": current_assertions, "extractors": current_extractors},
        "suggested": suggestion,
        "merged": {"assertions": merged_assertions, "extractors": merged_extractors},
        "rationale": rationale[:500] if isinstance(rationale, str) else "",
        "applied": applied,
    }

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
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from langgraph_integration.models import LLMConfig
from requirements.services import (
    create_llm_instance,
    extract_json_from_response,
    safe_llm_invoke,
)

from .models import ApiExecutionRecord, ApiTestCase

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是 API 测试领域的资深工程师。给你一份现有的接口用例（含 method/path/headers/body/已有断言/已有提取器），还可能有它最近一次执行返回的样本响应。

请给这条用例**补全**：
1. 更全的 assertions（覆盖状态码、关键字段、长度/类型校验等）
2. 必要的 extractors（把响应里"后续用例可能需要的"字段提取成变量）

严格输出如下 JSON：
{
  "assertions": [
    {"type": "status_code|body_contains|body_not_contains|header_exists|header_value|json_path",
     "operator": "eq|neq|gt|gte|lt|lte|contains|not_contains|regex|is_empty|is_not_empty|in|not_in",
     "expected": <值>,
     "path": "仅 json_path / header_value 需要：json_path 表达式（如 data.token）或响应头名"}
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
- type 只能是上面 6 种之一；不要使用其它类型
- 字段约定：json_path / header_value 把 json 路径或响应头名写在 path 字段（不要用 target）；header_exists 把响应头名写在 expected；body_contains / body_not_contains 把子串写在 expected；status_code 把状态码写在 expected
- 不要重复用户已有的 assertions/extractors
- 如果没有需要新增的项，对应数组就给空 []
- status_code 的期望值要按方法选择默认：POST 用 201，DELETE 用 204，PUT/PATCH 多数 200，GET 200。如果上次执行（last_execution）给出了真实 status_code，请优先以它为准。
"""


def _summarize_last_execution(case: ApiTestCase) -> dict[str, Any] | None:
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
    return {
        "assertions": [a for a in assertions if isinstance(a, dict)],
        "extractors": [e for e in extractors if isinstance(e, dict) and (e.get("name") or "").strip()],
    }


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
    - suggested_override: 直接用传入的建议（{assertions, extractors}），跳过 LLM —— 供批量 apply 复用预览结果。
    - fast_mode: 跳过 LLM，快速返回空建议（批量预览的快速档；本平台保持 #1 断言 schema，不做老式启发式）。
    所有建议仍只走 dev 的 #1 schema（path 字段 + 6 种执行器支持类型），不引入 target/json_path_length 等。
    """
    case = ApiTestCase.objects.get(id=case_id)
    last_summary = _summarize_last_execution(case)
    last_status_code = (last_summary or {}).get("status_code") if last_summary else None

    rationale = ""
    if suggested_override is not None:
        suggestion = _normalize_suggestion(suggested_override) or {"assertions": [], "extractors": []}
    elif fast_mode:
        suggestion = {"assertions": [], "extractors": []}
        rationale = "快速模式：未调用 LLM，仅基于已有信息合并。"
    else:
        config = LLMConfig.objects.filter(is_active=True).first()
        if not config:
            return {
                "case_id": case.id,
                "current": {"assertions": case.assertions or [], "extractors": case.extractors or []},
                "suggested": {"assertions": [], "extractors": []},
                "merged": {"assertions": case.assertions or [], "extractors": case.extractors or []},
                "rationale": "",
                "applied": False,
                "error": "未找到激活的 LLM 配置",
            }

        llm = create_llm_instance(config, temperature=0.2)
        messages = _build_messages(case)
        response = safe_llm_invoke(llm, messages, max_retries=3, retry_delay=2)
        content = getattr(response, "content", "") or ""
        payload = extract_json_from_response(content) or {}
        rationale = payload.get("rationale", "") if isinstance(payload, dict) else ""
        suggestion = _normalize_suggestion(payload) or {"assertions": [], "extractors": []}

    suggestion["assertions"] = _adjust_status_code_assertions(
        suggestion["assertions"], case.method, last_status_code
    )

    current_assertions = _adjust_status_code_assertions(
        list(case.assertions or []), case.method, last_status_code
    )
    current_extractors = case.extractors or []
    merged_assertions = _dedup_dicts(
        list(current_assertions) + suggestion["assertions"],
        ["type", "operator", "expected", "target"],
    )
    merged_extractors = _dedup_dicts(
        list(current_extractors) + suggestion["extractors"],
        ["name", "source", "expression"],
    )

    applied = False
    if apply and (suggestion["assertions"] or suggestion["extractors"]):
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

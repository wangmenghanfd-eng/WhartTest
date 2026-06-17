# -*- coding: utf-8 -*-
"""
功能用例 → 接口用例 AI 辅助生成。

入口：
    preview_from_functional_case(testcase_id, project_id=None) -> dict
    materialize_from_functional_case(testcase_id, project_id, module_id, ...) -> dict

依赖 langgraph_integration.LLMConfig 与 requirements.services 的 LLM 工具：
    - create_llm_instance
    - safe_llm_invoke
    - extract_json_from_response（仅处理 dict，所以这里我们让 LLM 返回 {"cases": [...]}）
"""

import json
import logging
from typing import Any

from django.db import transaction
from langchain_core.messages import HumanMessage, SystemMessage

from langgraph_integration.models import LLMConfig
from requirements.services import (
    create_llm_instance,
    extract_json_from_response,
    safe_llm_invoke,
)

from .models import (
    ApiDefinition,
    ApiEnvironmentConfig,
    ApiModule,
    ApiTestCase,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一名资深 API 测试工程师。用户会给你一份功能用例（自然语言描述），同时告诉你这个项目里已经有哪些 OpenAPI 风格的接口定义。

你的任务：把功能用例**翻译**成可以直接落库到接口自动化平台的接口用例草稿。

输出严格的 JSON，shape 如下：
{
  "cases": [
    {
      "name": "中文用例名（不超过 60 字）",
      "method": "GET|POST|PUT|PATCH|DELETE",
      "path": "/相对路径，可包含 {id} 等占位",
      "headers": { "Content-Type": "application/json" },
      "query_params": { "key": "值或 ${{ var }}" },
      "body": { ... },
      "assertions": [
        { "type": "status_code", "operator": "eq", "expected": 200 }
      ],
      "extractors": [],
      "matched_definition_id": 123,
      "rationale": "解释这条用例为什么这么写（一两句中文）"
    }
  ]
}

硬性要求：
1. 输出必须是合法 JSON，不要包含 Markdown 代码块以外的内容
2. 所有字段必须填齐，可以为空对象 {} 或空数组 []，但不能省略
3. 优先匹配 definitions 列表里给的 method+path；如果功能用例描述了未在定义里的能力，可以新建路径但需写明 rationale
4. 至少给出 1 条 happy-path 用例 + 1 条异常/边界用例（status_code != 200 的）
5. 不要捏造业务，所有 path / 字段都要从 definitions 或功能用例文本中能找到依据
6. assertions 里 operator 必须是这些之一：eq, neq, gt, gte, lt, lte, contains, not_contains, regex, is_empty, is_not_empty, in, not_in
"""


def _summarize_definitions(definitions: list[ApiDefinition]) -> list[dict[str, Any]]:
    summarized = []
    for d in definitions[:50]:  # 太多会爆 token
        summarized.append({
            "id": d.id,
            "method": d.method,
            "path": d.path,
            "summary": d.summary or d.name,
            "tags": d.tags or [],
        })
    return summarized


def _format_steps(steps_qs) -> str:
    lines = []
    for step in steps_qs:
        lines.append(f"{step.step_number}. {step.description}  → 期望: {step.expected_result}")
    return "\n".join(lines) if lines else "（用例没有详细步骤）"


def _build_messages(testcase, definitions: list[ApiDefinition]) -> list:
    summary_defs = _summarize_definitions(definitions)
    steps_text = _format_steps(testcase.steps.all().order_by("step_number"))

    user_payload = {
        "functional_case": {
            "name": testcase.name,
            "level": testcase.level,
            "test_type": testcase.test_type,
            "precondition": testcase.precondition or "",
            "steps": steps_text,
        },
        "available_api_definitions": summary_defs,
    }
    user_text = (
        "请根据以下信息生成接口用例草稿。返回 JSON：\n\n"
        f"{json.dumps(user_payload, ensure_ascii=False, indent=2)}"
    )
    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]


def _normalize_case(raw: dict[str, Any]) -> dict[str, Any] | None:
    """把 LLM 输出的单条用例归一化；缺字段则丢弃。"""
    method = (raw.get("method") or "").upper().strip()
    path = (raw.get("path") or "").strip()
    name = (raw.get("name") or "").strip()
    if not method or not path or not name:
        return None
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        return None

    return {
        "name": name[:200],
        "method": method,
        "path": path[:500],
        "headers": raw.get("headers") if isinstance(raw.get("headers"), dict) else {},
        "query_params": raw.get("query_params") if isinstance(raw.get("query_params"), dict) else {},
        "body": raw.get("body") if isinstance(raw.get("body"), (dict, list)) else {},
        "assertions": raw.get("assertions") if isinstance(raw.get("assertions"), list) else [],
        "extractors": raw.get("extractors") if isinstance(raw.get("extractors"), list) else [],
        "matched_definition_id": raw.get("matched_definition_id"),
        "rationale": (raw.get("rationale") or "")[:500],
    }


def _invoke_llm(messages) -> dict[str, Any]:
    """调用 LLM，返回 {"cases": [...], "raw_content": str}。

    需要项目里已经有可用的 LLMConfig (is_active=True)。
    """
    config = LLMConfig.objects.filter(is_active=True).first()
    if not config:
        raise RuntimeError("未找到激活的 LLM 配置，请先在 LLM 设置中启用一个模型")

    llm = create_llm_instance(config, temperature=0.2)
    response = safe_llm_invoke(llm, messages, max_retries=3, retry_delay=2)
    content = getattr(response, "content", "") or ""
    payload = extract_json_from_response(content)

    cases_raw: list[Any]
    if isinstance(payload, dict):
        cases_raw = payload.get("cases") or []
    elif isinstance(payload, list):
        cases_raw = payload
    else:
        cases_raw = []

    normalized: list[dict[str, Any]] = []
    for raw in cases_raw:
        if not isinstance(raw, dict):
            continue
        case = _normalize_case(raw)
        if case:
            normalized.append(case)

    return {"cases": normalized, "raw_content": content}


def preview_from_functional_case(testcase_id: int) -> dict[str, Any]:
    """dry_run：拉功能用例 + 已有定义，让 LLM 生成接口用例草稿（不入库）。"""
    from testcases.models import TestCase

    testcase = TestCase.objects.select_related("project").prefetch_related("steps").get(id=testcase_id)
    project = testcase.project

    definitions = list(
        ApiDefinition.objects.filter(project=project).order_by("id")
    )
    messages = _build_messages(testcase, definitions)

    try:
        result = _invoke_llm(messages)
    except Exception as exc:
        logger.exception("LLM 调用失败")
        return {
            "project_id": project.id,
            "testcase_id": testcase.id,
            "testcase_name": testcase.name,
            "candidates": [],
            "error": str(exc),
        }

    candidates = []
    for idx, c in enumerate(result["cases"]):
        candidates.append({"index": idx, **c})

    return {
        "project_id": project.id,
        "testcase_id": testcase.id,
        "testcase_name": testcase.name,
        "definitions_count": len(definitions),
        "candidates": candidates,
    }


def materialize_from_functional_case(
    testcase_id: int,
    module_id: int,
    selected_indexes: list[int] | None,
    environment_id: int | None,
    creator,
) -> dict[str, Any]:
    """落库选中的候选用例。"""
    from testcases.models import TestCase

    testcase = TestCase.objects.select_related("project").prefetch_related("steps").get(id=testcase_id)
    project = testcase.project

    module = ApiModule.objects.get(id=module_id, project=project)
    env = (
        ApiEnvironmentConfig.objects.get(id=environment_id, project=project)
        if environment_id
        else ApiEnvironmentConfig.objects.filter(project=project, is_default=True).first()
    )

    definitions = list(ApiDefinition.objects.filter(project=project).order_by("id"))
    messages = _build_messages(testcase, definitions)
    result = _invoke_llm(messages)
    cases = result["cases"]

    if selected_indexes is None:
        chosen = cases
    else:
        chosen = [cases[i] for i in selected_indexes if 0 <= i < len(cases)]

    created = []
    with transaction.atomic():
        for c in chosen:
            definition = None
            if c.get("matched_definition_id"):
                definition = next(
                    (d for d in definitions if d.id == c["matched_definition_id"]),
                    None,
                )
            api_case = ApiTestCase.objects.create(
                project=project,
                module=module,
                definition=definition,
                environment=env,
                name=c["name"],
                method=c["method"],
                path=c["path"],
                headers=c["headers"],
                query_params=c["query_params"],
                body=c["body"],
                assertions=c["assertions"],
                extractors=c["extractors"],
                source="ai_from_functional",
                creator=creator,
            )
            created.append({
                "id": api_case.id,
                "name": api_case.name,
                "method": api_case.method,
                "path": api_case.path,
            })

    return {
        "project_id": project.id,
        "testcase_id": testcase.id,
        "module_id": module.id,
        "created_count": len(created),
        "created": created,
    }

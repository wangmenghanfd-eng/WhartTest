# -*- coding: utf-8 -*-
"""
UI Trace 网络请求 → 接口用例 提取器

将 UiExecutionRecord 关联的 trace 文件解析后，按照规则把其中的 xhr/fetch
请求转换为 ApiTestCase 候选。

支持两种调用形态：
- preview(): 仅返回候选数据，不入库
- materialize(): 按 selected_indexes 实际创建 ApiTestCase
"""

from __future__ import annotations

import json
from typing import Any, Iterable
from urllib.parse import urlparse, parse_qsl

from django.db import transaction

from .models import ApiEnvironmentConfig, ApiModule, ApiTestCase
from ui_automation.models import UiExecutionRecord
from ui_automation.trace_parser import parse_trace_file


# 默认保留的资源类型（mime_type 的主类型部分），其他视为静态资源过滤
ALLOWED_RESOURCE_TYPES = {
    "application",  # application/json, application/x-www-form-urlencoded, ...
    "text",         # text/plain, text/html (some APIs return)
    "xhr",          # 兼容某些客户端
    "fetch",
    "other",        # 兼容字段缺失场景
}

# 永远过滤的扩展名（即便 mime_type 命中 application/javascript 也过滤）
STATIC_EXTENSIONS = {
    ".js", ".css", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2", ".ttf", ".eot", ".webp", ".mp4",
    ".webm", ".pdf",
}

# 永远过滤的 mime 子类型（脚本/样式/图像/字体）
SKIP_MIME_KEYWORDS = (
    "javascript", "css", "image/", "font/", "video/", "audio/", "html",
)

# 敏感请求头：复制时清除
SENSITIVE_HEADER_NAMES = {
    "authorization", "cookie", "set-cookie", "x-api-key",
    "x-csrf-token", "x-csrftoken",
}


def _is_static_resource(req: dict) -> bool:
    url = (req.get("url") or "").split("?")[0].lower()
    for ext in STATIC_EXTENSIONS:
        if url.endswith(ext):
            return True
    mime = (req.get("mime_type") or "").lower()
    for keyword in SKIP_MIME_KEYWORDS:
        if keyword in mime:
            return True
    return False


def _split_url(url: str) -> tuple[str, str, dict]:
    """
    返回 (base_url, path, query_params)
    base_url: scheme + host (+ port)
    path: 单纯路径（不带 query）
    query_params: dict[str, str]
    """
    if not url:
        return "", "", {}
    parsed = urlparse(url)
    if not parsed.scheme:
        return "", url, {}
    base = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path or "/"
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return base, path, query_params


def _parse_body(raw: Any) -> Any:
    """尝试把 request_body 字符串转成 JSON dict；不行就保留字符串"""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return {"_raw": text[:5000]}
    return {}


def _sanitize_headers(headers: dict | None) -> dict:
    if not headers:
        return {}
    result: dict[str, str] = {}
    for k, v in headers.items():
        if not k:
            continue
        if k.lower() in SENSITIVE_HEADER_NAMES:
            continue
        # Hop-by-hop / 浏览器自动补的不必复制
        if k.lower().startswith(":"):
            continue
        if k.lower() in {"host", "content-length", "connection", "accept-encoding"}:
            continue
        result[k] = str(v)
    return result


def _build_default_assertions(status: int) -> list[dict]:
    """根据原始响应状态码生成一条断言：=200 默认；其他保留实际值。"""
    if not status:
        return [{"type": "status_code", "operator": "lt", "expected": 500}]
    return [{"type": "status_code", "operator": "eq", "expected": int(status)}]


def _suggest_case_name(method: str, path: str) -> str:
    """根据 method+path 生成默认用例名（最多 100 字符）。"""
    return f"{(method or 'GET').upper()} {path or '/'}".strip()[:200]


def extract_candidate_requests(
    trace_data: dict | None,
    *,
    skip_static: bool = True,
) -> list[dict]:
    """从 trace_data 中提取候选接口请求。

    返回的每个 dict 字段：
    - index: 在原列表中的下标（用于前端选中传回）
    - url, method, status, mime_type
    - base_url, path, query_params
    - request_headers, request_body
    - response_status, response_size, duration_ms
    """
    if not trace_data:
        return []
    network = trace_data.get("network_requests") or []
    candidates: list[dict] = []
    for idx, req in enumerate(network):
        if skip_static and _is_static_resource(req):
            continue
        # 过滤 OPTIONS 预检
        if (req.get("method") or "").upper() == "OPTIONS":
            continue
        url = req.get("url") or ""
        if not url.startswith(("http://", "https://")):
            continue
        base_url, path, query_params = _split_url(url)
        candidates.append({
            "index": idx,
            "url": url,
            "method": (req.get("method") or "GET").upper(),
            "base_url": base_url,
            "path": path,
            "query_params": query_params,
            "request_headers": _sanitize_headers(req.get("request_headers")),
            "request_body": _parse_body(req.get("request_body")),
            "response_status": req.get("status") or 0,
            "response_size": req.get("response_size") or 0,
            "mime_type": req.get("mime_type") or "",
            "duration_ms": req.get("duration") or 0,
        })
    return candidates


def _resolve_trace_data(execution_record: UiExecutionRecord) -> dict | None:
    """优先用已落库的 trace_data；落库为空则解析 trace_path。"""
    if execution_record.trace_data:
        return execution_record.trace_data
    if execution_record.trace_path:
        return parse_trace_file(execution_record.trace_path)
    return None


def preview_from_execution(
    execution_record: UiExecutionRecord,
    *,
    skip_static: bool = True,
) -> dict[str, Any]:
    trace = _resolve_trace_data(execution_record)
    candidates = extract_candidate_requests(trace, skip_static=skip_static)
    return {
        "execution_record_id": execution_record.id,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }


def _ensure_environment(project, base_url: str, creator) -> ApiEnvironmentConfig | None:
    """如果 project 下已经有同 base_url 的环境就复用，否则创建一个。"""
    if not base_url:
        return None
    env = ApiEnvironmentConfig.objects.filter(project=project, base_url=base_url).first()
    if env:
        return env
    return ApiEnvironmentConfig.objects.create(
        project=project,
        name=f"Trace 提取-{base_url[-32:]}",
        base_url=base_url,
        is_default=not ApiEnvironmentConfig.objects.filter(project=project).exists(),
        creator=creator,
    )


def materialize_from_execution(
    execution_record: UiExecutionRecord,
    *,
    project,
    module: ApiModule,
    creator,
    selected_indexes: Iterable[int] | None = None,
    environment: ApiEnvironmentConfig | None = None,
    skip_static: bool = True,
) -> dict[str, Any]:
    """根据用户选中（或全选）创建 ApiTestCase 实例。

    参数：
    - selected_indexes: 在候选列表中的下标；None 表示全部创建。
    - environment: 用户显式指定的环境；None 时按 base_url 自动查找/创建。
    """
    trace = _resolve_trace_data(execution_record)
    candidates = extract_candidate_requests(trace, skip_static=skip_static)

    if selected_indexes is not None:
        wanted = set(int(i) for i in selected_indexes)
        candidates = [c for c in candidates if c["index"] in wanted]

    created_ids: list[int] = []
    with transaction.atomic():
        for candidate in candidates:
            env = environment or _ensure_environment(project, candidate["base_url"], creator)
            case = ApiTestCase.objects.create(
                project=project,
                module=module,
                environment=env,
                name=_suggest_case_name(candidate["method"], candidate["path"]),
                method=candidate["method"],
                path=candidate["path"],
                headers=candidate["request_headers"],
                query_params=candidate["query_params"],
                body=candidate["request_body"] if isinstance(candidate["request_body"], (dict, list)) else {},
                assertions=_build_default_assertions(candidate["response_status"]),
                extractors=[],
                source="ui_trace",
                creator=creator,
            )
            created_ids.append(case.id)
    return {
        "execution_record_id": execution_record.id,
        "created_count": len(created_ids),
        "created_case_ids": created_ids,
    }

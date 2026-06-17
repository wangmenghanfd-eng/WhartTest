"""
Agent Loop API 视图 (LangChain v1 重构版)

使用 LangChain v1 的 create_agent + middleware 模式，
替代原有的手动 AgentOrchestrator 循环。

核心变更：
- 使用 create_agent() 统一创建 Agent
- 使用 SummarizationMiddleware 自动处理上下文压缩
- 使用 HumanInTheLoopMiddleware 处理 HITL 审批
- 在流处理层检测工具调用，生成 step_start/step_complete 事件
- 支持 stream 参数控制流式/非流式输出
- SSE 事件格式与旧版保持兼容，前端无需修改
"""

import asyncio
import base64
import json
import logging
import os
import re
import shlex
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from django.http import StreamingHttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from asgiref.sync import sync_to_async

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool as langchain_tool
from langchain.agents import create_agent
from wharttest_django.checkpointer import get_async_checkpointer

from .middleware_config import (
    get_middleware_from_config,
    get_user_tool_approvals,
    get_user_friendly_llm_error,
)
from .playwright_instructions import (
    PLAYWRIGHT_SCRIPT_INSTRUCTION,
    TEST_CASE_EXECUTION_INSTRUCTION,
)
from .stop_signal import should_stop, clear_stop_signal
from langgraph_integration.models import ChatSession, LLMConfig
from langgraph_integration.views import (
    create_llm_instance,
    create_sse_data,
    get_effective_system_prompt_async,
    check_project_permission,
)
from projects.models import Project
from prompts.models import UserPrompt
from mcp_tools.models import RemoteMCPConfig
from mcp_tools.persistent_client import mcp_session_manager
from ui_automation.functional_case_bridge import (
    generate_ui_case_from_functional_execution,
)
from requirements.context_limits import (
    MODEL_CONTEXT_LIMITS,
    context_checker,
    get_context_limit_from_llm,
)

logger = logging.getLogger(__name__)


# 仅当出现“(请/帮我/麻烦)? 使用|调用|跑|运行|执行 … context7/firecrawl”这类带明确祈使动词的
# 表达，或英文 use/run/call context7|firecrawl 时才算“显式点名”；疑问句、闲聊或叙述句里
# 顺口提到名字（含裸“用”）一律不触发。context7 优先于 firecrawl，与原行为一致。
_EXPLICIT_SKILL_PATTERNS = (
    ("context7-mcp", re.compile(
        r"(?:请|帮我|帮|麻烦)?\s*(?:使用|调用|跑|运行|执行)\s*(?:一下)?\s*context7(?:-mcp)?",
        re.IGNORECASE)),
    ("context7-mcp", re.compile(r"\b(?:use|run|call)\s+context7(?:-mcp)?\b", re.IGNORECASE)),
    ("firecrawl", re.compile(
        r"(?:请|帮我|帮|麻烦)?\s*(?:使用|调用|跑|运行|执行)\s*(?:一下)?\s*firecrawl",
        re.IGNORECASE)),
    ("firecrawl", re.compile(r"\b(?:use|run|call)\s+firecrawl\b", re.IGNORECASE)),
)


def _detect_explicit_skill_request(user_message: str) -> Optional[str]:
    """识别“显式祈使要求使用某外部技能”的意图，命中返回技能名，否则 None。

    与纯字符串包含不同：必须有明确祈使动词（使用/调用/跑/运行/执行 或 use/run/call）紧接技能名。
    """
    text = (user_message or "").strip()
    if not text:
        return None
    for skill_name, pattern in _EXPLICIT_SKILL_PATTERNS:
        if pattern.search(text):
            return skill_name
    return None


def _message_prefers_external_skill_docs(user_message: str) -> bool:
    """
    当用户明确点名外部文档/网页技能时，避免知识库把问题带偏。
    """
    return _detect_explicit_skill_request(user_message) is not None


def _build_explicit_skill_shortcut(user_message: str) -> Optional[Dict[str, str]]:
    """
    当用户明确点名 context7-mcp / firecrawl 时，直接构造一次可执行命令，
    避免模型只读取 Skill 说明而不真正执行。
    """
    skill = _detect_explicit_skill_request(user_message)
    if skill is None:
        return None
    text = (user_message or "").strip()

    if skill == "context7-mcp":
        cleaned_query = re.sub(
            r"请?帮?我?(使用|用)?\s*context7(?:-mcp)?\s*(来|看下|查看|查询|检索|搜索)?",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip(" ：:，,。.？?！!;；")
        cleaned_query = re.sub(r"^(看下|看看|查看|查询|检索|搜索)\s*[，,：:]?\s*", "", cleaned_query)
        library_match = re.search(r"[a-zA-Z][a-zA-Z0-9_.-]{2,}", cleaned_query)
        library_name = library_match.group(0) if library_match else ""
        if library_name:
            command = (
                f"python run.py ask --library {shlex.quote(library_name)} "
                f"--query {shlex.quote(cleaned_query or text)}"
            )
        else:
            command = f"python run.py search --query {shlex.quote(cleaned_query or text)}"
        return {
            "skill_name": "context7-mcp",
            "command": command,
            "label": "context7-mcp",
            "fallback_skill_name": "firecrawl",
            "fallback_command": f"python run.py search --query {shlex.quote(cleaned_query or text)}",
        }

    if skill == "firecrawl":
        cleaned_query = re.sub(
            r"请?帮?我?(使用|用)?\s*firecrawl\s*(来|看下|查看|查询|检索|搜索)?",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip(" ：:，,。.？?！!;；")
        command = f"python run.py search --query {shlex.quote(cleaned_query or text)}"
        return {
            "skill_name": "firecrawl",
            "command": command,
            "label": "firecrawl",
        }

    return None


def _extract_message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


async def _summarize_explicit_skill_result(
    llm: Any, user_message: str, skill_label: str, tool_content: str
) -> str:
    """
    把显式 Skill 查询结果整理成自然语言回答，避免直接把 Skill 原始说明/片段整段暴露给用户。
    """
    if not tool_content.strip():
        return f"已使用 {skill_label} 查询，但没有返回可展示内容。"

    prompt = (
        "你是一个技术助理。用户明确要求使用某个外部文档/网页技能查询。\n"
        "请基于下面的技能查询结果，直接回答用户问题，不要解释技能，不要输出 tool_call，不要重复原始文档。\n"
        "要求：\n"
        "1. 用简体中文。\n"
        "2. 先给结论，再给 2-5 条可执行排查步骤。\n"
        "3. 如果结果里有命中的库名或最佳匹配，顺手提一下。\n"
        "4. 若证据不足，明确指出还缺什么信息。\n"
        "5. 不要输出 Markdown 标题。\n\n"
        f"用户问题：{user_message}\n\n"
        f"技能：{skill_label}\n\n"
        f"技能查询结果：\n{tool_content}"
    )
    try:
        summary = await llm.ainvoke([HumanMessage(content=prompt)])
        summarized_text = _extract_message_text(summary)
        return summarized_text or f"已使用 {skill_label} 查询，但未生成可读总结。"
    except Exception:
        logger.warning("AgentLoopStreamAPI: summarize explicit skill result failed", exc_info=True)
        return f"已使用 {skill_label} 查询，结果如下：\n\n{tool_content}"


def _build_sse_error_event(exc: Exception) -> Dict[str, Any]:
    friendly_error = get_user_friendly_llm_error(exc)
    if friendly_error:
        event = {
            "type": "error",
            "message": friendly_error["message"],
            "code": friendly_error["status_code"],
            "error_code": friendly_error["error_code"],
            "errors": friendly_error["errors"],
        }
        if friendly_error.get("model"):
            event["model"] = friendly_error["model"]
        if friendly_error.get("reset_time"):
            event["retry_after"] = friendly_error["reset_time"]
        if friendly_error.get("reset_seconds") is not None:
            event["retry_after_seconds"] = friendly_error["reset_seconds"]
        return event

    return {"type": "error", "message": f"执行错误: {str(exc)}", "code": 500}


# ============== 统一响应辅助函数 ==============


def api_success_response(
    message: str, data: Any = None, code: int = 200
) -> JsonResponse:
    """构建统一格式的成功响应"""
    return JsonResponse(
        {
            "status": "success",
            "code": code,
            "message": message,
            "data": data,
            "errors": None,
        },
        json_dumps_params={"ensure_ascii": False},
    )


def api_error_response(
    message: str, code: int = 400, errors: Any = None
) -> JsonResponse:
    """构建统一格式的错误响应"""
    if errors is None:
        errors = {"detail": [message]}
    return JsonResponse(
        {
            "status": "error",
            "code": code,
            "message": message,
            "data": None,
            "errors": errors,
        },
        status=code,
        json_dumps_params={"ensure_ascii": False},
    )


_MARKDOWN_IMAGE_URL_RE = re.compile(
    r"!\[[^\]]*?\]\((?P<url>https?://[^)\s]+)\)", re.IGNORECASE
)
_PLAIN_HTTP_URL_RE = re.compile(r'(?P<url>https?://[^\s<>"\']+)', re.IGNORECASE)
_URL_LEADING_WRAP_CHARS = "([<{\"'“‘（【《「『"
_URL_TRAILING_WRAP_CHARS = ")]}>\"'”’）】》」』.,;!?，。；！？、"
_URL_HARD_STOP_CHARS = "\r\n\t ,;)}]>\"'，。；！？、：”’）】》」』"


def _get_env_int(name: str, default: int, min_value: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(min_value, int(raw))
    except ValueError:
        logger.warning(
            "AgentLoopStreamAPI: Invalid int env %s=%s, fallback=%s", name, raw, default
        )
        return default


def _get_env_float(name: str, default: float, min_value: float = 0.1) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(min_value, float(raw))
    except ValueError:
        logger.warning(
            "AgentLoopStreamAPI: Invalid float env %s=%s, fallback=%s",
            name,
            raw,
            default,
        )
        return default


def _normalize_uploaded_image_base64_list(
    raw_images: Any, raw_image: Any = None
) -> List[str]:
    """兼容旧 image 字段与新 images 数组，返回去重后的上传图片列表。"""

    normalized: List[str] = []

    def _append(candidate: Any) -> None:
        if not isinstance(candidate, str):
            return
        value = candidate.strip()
        if not value or value in normalized:
            return
        normalized.append(value)

    if isinstance(raw_images, list):
        for item in raw_images:
            _append(item)
    else:
        _append(raw_images)

    _append(raw_image)
    return normalized


_LINKED_IMAGE_URL_ALLOWLIST = {
    host.strip().lower()
    for host in os.getenv("AGENT_LOOP_IMAGE_URL_ALLOWLIST", "*").split(",")
    if host.strip()
}
_MAX_LINKED_IMAGES_PER_REQUEST = _get_env_int(
    "AGENT_LOOP_MAX_LINKED_IMAGES", 3, min_value=1
)
_MAX_LINKED_IMAGE_BYTES = _get_env_int(
    "AGENT_LOOP_MAX_LINKED_IMAGE_BYTES", 5 * 1024 * 1024, min_value=1024
)
_LINKED_IMAGE_FETCH_TIMEOUT = _get_env_float(
    "AGENT_LOOP_LINKED_IMAGE_FETCH_TIMEOUT", 8.0, min_value=1.0
)
_MAX_SAFE_TOOL_MESSAGE_CHARS = _get_env_int(
    "AGENT_LOOP_MAX_SAFE_TOOL_MESSAGE_CHARS", 20000, min_value=1000
)
_MAX_TEST_CASE_TOOL_MESSAGE_CHARS = _get_env_int(
    "AGENT_LOOP_TESTCASE_MAX_TOOL_MESSAGE_CHARS", 4000, min_value=500
)
_MAX_TEST_CASE_AGENT_STEPS = _get_env_int(
    "AGENT_LOOP_TESTCASE_AGENT_STEPS", 12, min_value=2
)
_MAX_TEST_CASE_AI_SNIPPET_CHARS = _get_env_int(
    "AGENT_LOOP_TESTCASE_AI_SNIPPET_CHARS", 500, min_value=100
)
_MAX_TEST_CASE_COMPLETION_TOKENS = _get_env_int(
    "AGENT_LOOP_TESTCASE_MAX_COMPLETION_TOKENS", 384, min_value=64
)


def _extract_linked_image_urls(text: str) -> List[str]:
    """从用户消息中提取图片 URL（支持 Markdown 图片语法和纯 URL）。"""
    if not text:
        return []

    urls: List[str] = []
    seen: set[str] = set()

    def _normalize_url(candidate: str) -> str:
        url = (candidate or "").strip()
        while url and url[0] in _URL_LEADING_WRAP_CHARS:
            url = url[1:]
        hard_stop_indexes = [
            url.find(char) for char in _URL_HARD_STOP_CHARS if char in url
        ]
        if hard_stop_indexes:
            url = url[: min(index for index in hard_stop_indexes if index >= 0)]
        while url and url[-1] in _URL_TRAILING_WRAP_CHARS:
            url = url[:-1]
        return url

    for pattern in (_MARKDOWN_IMAGE_URL_RE, _PLAIN_HTTP_URL_RE):
        for match in pattern.finditer(text):
            url = _normalize_url(match.group("url") or "")
            if not url or url in seen:
                continue

            try:
                parsed = urlparse(url)
            except ValueError:
                continue
            if parsed.scheme.lower() not in ("http", "https"):
                continue
            if not parsed.netloc:
                continue

            seen.add(url)
            urls.append(url)

    return urls


def _is_linked_image_url_allowed(url: str) -> bool:
    """校验图片 URL 是否在允许的 host 白名单中（支持 * 全放开）。"""
    if "*" in _LINKED_IMAGE_URL_ALLOWLIST or "all" in _LINKED_IMAGE_URL_ALLOWLIST:
        return True

    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").strip().lower()
    return bool(host and host in _LINKED_IMAGE_URL_ALLOWLIST)


async def _download_linked_image_as_data_url(url: str) -> Optional[str]:
    """下载图片 URL 并转为 data URL，供视觉模型消费。"""
    if not _is_linked_image_url_allowed(url):
        logger.warning(
            "AgentLoopStreamAPI: Skip linked image URL not in allowlist. url=%s, allowlist=%s",
            url,
            sorted(_LINKED_IMAGE_URL_ALLOWLIST),
        )
        return None

    timeout = httpx.Timeout(
        _LINKED_IMAGE_FETCH_TIMEOUT, connect=_LINKED_IMAGE_FETCH_TIMEOUT
    )
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            async with client.stream(
                "GET", url, headers={"Accept": "image/*"}
            ) as response:
                response.raise_for_status()
                content_type = (
                    (response.headers.get("Content-Type") or "")
                    .split(";")[0]
                    .strip()
                    .lower()
                )
                if not content_type.startswith("image/"):
                    logger.warning(
                        "AgentLoopStreamAPI: Skip linked URL with non-image content-type. url=%s, content_type=%s",
                        url,
                        content_type or "unknown",
                    )
                    return None

                data = bytearray()
                async for chunk in response.aiter_bytes():
                    if not chunk:
                        continue
                    if len(data) + len(chunk) > _MAX_LINKED_IMAGE_BYTES:
                        logger.warning(
                            "AgentLoopStreamAPI: Skip linked image over size limit. url=%s, max_bytes=%s",
                            url,
                            _MAX_LINKED_IMAGE_BYTES,
                        )
                        return None
                    data.extend(chunk)

                if not data:
                    logger.warning(
                        "AgentLoopStreamAPI: Skip empty linked image response. url=%s",
                        url,
                    )
                    return None

                encoded = base64.b64encode(bytes(data)).decode("utf-8")
                return f"data:{content_type};base64,{encoded}"
    except Exception as e:
        logger.warning(
            "AgentLoopStreamAPI: Failed to fetch linked image url=%s, error=%s", url, e
        )
        return None


async def _collect_linked_image_data_urls(
    user_message: str,
    linked_urls: Optional[List[str]] = None,
) -> List[str]:
    """从用户消息 URL 中收集可用图片，并转换为 data URL 列表。"""
    if linked_urls is None:
        linked_urls = _extract_linked_image_urls(user_message)
    if not linked_urls:
        return []

    limited_urls = linked_urls[:_MAX_LINKED_IMAGES_PER_REQUEST]
    if len(linked_urls) > len(limited_urls):
        logger.info(
            "AgentLoopStreamAPI: Truncated linked image URLs from %s to %s",
            len(linked_urls),
            len(limited_urls),
        )

    download_tasks = [_download_linked_image_as_data_url(url) for url in limited_urls]
    results = await asyncio.gather(*download_tasks, return_exceptions=True)

    data_urls: List[str] = []
    for url, result in zip(limited_urls, results):
        if isinstance(result, Exception):
            logger.warning(
                "AgentLoopStreamAPI: Linked image download task failed. url=%s, error=%s",
                url,
                result,
            )
            continue
        if result:
            data_urls.append(result)

    return data_urls


def process_mcp_tool_output(content: Any) -> tuple:
    """
    处理 MCP 工具返回的内容，提取实际数据并生成摘要

    Args:
        content: 工具返回的原始内容

    Returns:
        tuple: (processed_content, summary)
    """
    # 处理 MCP 工具返回的结构化 content block，尽量提取纯文本
    content = _normalize_mcp_content_to_text(content)

    # 确保 content 可序列化
    if content is None:
        content = ""
    elif not isinstance(content, (str, dict, list, int, float, bool)):
        content = str(content)

    # 生成摘要
    if isinstance(content, str):
        summary = content[:200]
    else:
        try:
            summary = json.dumps(content, ensure_ascii=False)[:200]
        except (TypeError, ValueError):
            summary = str(content)[:200]

    return content, summary


def _normalize_mcp_content_to_text(content: Any) -> Any:
    """
    将 MCP 常见的结构化 content block 压平成纯文本，避免后续 ToolMessage
    以 list/dict 形式进入下一轮模型调用。

    对图片/文件等非文本块，仅保留简短占位，避免把 base64/二进制元数据塞进上下文。
    """
    if content is None or isinstance(content, (str, int, float, bool)):
        return content

    if isinstance(content, dict):
        if content.get("type") == "text" and content.get("text") is not None:
            return str(content.get("text"))
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)

    if isinstance(content, list):
        text_parts: List[str] = []
        placeholders: List[str] = []

        for item in content:
            if isinstance(item, dict):
                item_type = str(item.get("type", "")).lower()

                if item_type == "text":
                    text_value = item.get("text")
                    if text_value is not None:
                        text_parts.append(str(text_value))
                    continue

                if item_type == "image" or isinstance(item.get("base64"), str):
                    placeholders.append("[工具返回了图片]")
                    continue

                if item_type == "file":
                    file_name = item.get("name") or item.get("path") or "未命名文件"
                    placeholders.append(f"[工具返回了文件: {file_name}]")
                    continue

                try:
                    text_parts.append(json.dumps(item, ensure_ascii=False))
                except (TypeError, ValueError):
                    text_parts.append(str(item))
                continue

            if item is None:
                continue
            text_parts.append(str(item))

        normalized_parts = [part for part in text_parts if isinstance(part, str) and part.strip()]
        if normalized_parts:
            return "\n".join(normalized_parts)
        if placeholders:
            return "\n".join(placeholders)
        try:
            return json.dumps(content, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(content)

    return str(content)


def _build_sanitized_messages(messages: List[Any]) -> tuple[List[Any], int]:
    """
    构建合法的消息列表：
    1) 为缺失 ToolMessage 响应的 tool_call 插入占位 ToolMessage
    2) 清理悬空的 ToolMessage（无匹配 tool_call）
    3) 清理有问题的 ToolMessage（content 非字符串 / 过长 / 含 base64）
    返回 (clean_messages, fix_count)
    """
    result: List[Any] = []
    fix_count = 0

    # 当前 pending 的 tool_call IDs 及其工具名
    pending_call_ids: List[str] = []
    pending_call_names: Dict[str, str] = {}

    def _flush_pending() -> None:
        nonlocal fix_count
        for tc_id in pending_call_ids:
            result.append(
                ToolMessage(
                    content="[Tool execution was interrupted]",
                    tool_call_id=tc_id,
                    name=pending_call_names.get(tc_id, "unknown"),
                )
            )
            fix_count += 1
        pending_call_ids.clear()
        pending_call_names.clear()

    def _sanitize_tool_message(msg: ToolMessage) -> tuple[ToolMessage, bool]:
        content = getattr(msg, "content", None)
        normalized = _normalize_mcp_content_to_text(content)

        if normalized is None:
            normalized = ""
        elif not isinstance(normalized, str):
            normalized = str(normalized)

        normalized = normalized.strip()

        if (
            not normalized
            or len(normalized) > _MAX_SAFE_TOOL_MESSAGE_CHARS
            or ("data:image/" in normalized and "base64," in normalized)
        ):
            return (
                ToolMessage(
                    content="[Tool output removed: content was invalid or too large]",
                    tool_call_id=str(getattr(msg, "tool_call_id", "") or ""),
                    name=getattr(msg, "name", None) or "unknown",
                ),
                True,
            )

        content_changed = normalized != content
        if content_changed:
            return (
                ToolMessage(
                    content=normalized,
                    tool_call_id=str(getattr(msg, "tool_call_id", "") or ""),
                    name=getattr(msg, "name", None) or "unknown",
                ),
                True,
            )

        return msg, False

    for msg in messages:
        # 带 tool_calls 的 AIMessage
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            _flush_pending()
            result.append(msg)

            for tc in msg.tool_calls:
                tc_id = (
                    tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                )
                tc_name = (
                    tc.get("name")
                    if isinstance(tc, dict)
                    else getattr(tc, "name", None)
                )
                if tc_id:
                    tc_id = str(tc_id)
                    pending_call_ids.append(tc_id)
                    pending_call_names[tc_id] = tc_name or "unknown"
            continue

        # ToolMessage 消息
        if isinstance(msg, ToolMessage):
            tc_id = str(getattr(msg, "tool_call_id", "") or "")
            if tc_id in pending_call_ids:
                pending_call_ids.remove(tc_id)
                sanitized_msg, changed = _sanitize_tool_message(msg)
                if changed:
                    sanitized_name = getattr(sanitized_msg, "name", None) or pending_call_names.get(tc_id, "unknown")
                    result.append(
                        ToolMessage(
                            content=sanitized_msg.content,
                            tool_call_id=tc_id,
                            name=sanitized_name,
                        )
                    )
                    fix_count += 1
                else:
                    result.append(msg)
            else:
                # 悬空 ToolMessage，丢弃
                fix_count += 1
            continue

        # 其他消息类型
        _flush_pending()
        result.append(msg)

    _flush_pending()
    return result, fix_count


async def _sanitize_history_before_model_call(
    agent: Any,
    invoke_config: Dict[str, Any],
    log_prefix: str,
) -> Dict[str, Any]:
    """
    统一历史修复入口：读取状态，构建合法消息列表，若有修复则用 REMOVE_ALL + 完整列表覆写。
    """
    try:
        current_state = await agent.aget_state(invoke_config)
    except Exception as e:
        logger.warning("%s: Failed to load state for sanitize: %s", log_prefix, e)
        return {"removed_count": 0, "sanitized": False}

    values = (
        current_state.values
        if hasattr(current_state, "values") and current_state.values
        else {}
    )
    messages = values.get("messages", []) if isinstance(values, dict) else []
    if not messages:
        return {"removed_count": 0, "sanitized": False}

    clean_msgs, fix_count = _build_sanitized_messages(messages)
    if fix_count == 0:
        return {"removed_count": 0, "sanitized": False}

    # 用 REMOVE_ALL + 完整干净列表替换状态
    update_payload = [RemoveMessage(id="__remove_all__"), *clean_msgs]

    available_nodes = list(getattr(agent, "nodes", {}).keys())
    preferred_nodes = [n for n in ("model", "agent", "tools") if n in available_nodes]
    if available_nodes and available_nodes[0] not in preferred_nodes:
        preferred_nodes.append(available_nodes[0])
    preferred_nodes.append(None)

    success = False
    last_error: Optional[Exception] = None
    for as_node in preferred_nodes:
        try:
            if as_node is None:
                await agent.aupdate_state(invoke_config, {"messages": update_payload})
            else:
                await agent.aupdate_state(
                    invoke_config, {"messages": update_payload}, as_node=as_node
                )
            success = True
            logger.info(
                "%s: Sanitized history via REMOVE_ALL, fixed %d issues, %d clean messages (as_node=%s)",
                log_prefix,
                fix_count,
                len(clean_msgs),
                as_node or "auto",
            )
            break
        except Exception as e:
            last_error = e

    if not success:
        logger.error(
            "%s: Failed to sanitize history. fix_count=%d, available_nodes=%s, error=%s",
            log_prefix,
            fix_count,
            available_nodes,
            last_error,
        )
        return {"removed_count": 0, "sanitized": False}

    return {"removed_count": fix_count, "sanitized": True}


def _tool_messages_need_sanitization(tool_messages: List[Any]) -> bool:
    """
    在工具节点完成后做一次轻量判断：
    只要 ToolMessage 含有非字符串 content、超长文本或 base64，就立刻触发状态修复。
    """
    for tool_msg in tool_messages:
        content = getattr(tool_msg, "content", None)
        if not isinstance(content, str):
            return True
        if len(content) > _MAX_SAFE_TOOL_MESSAGE_CHARS:
            return True
        if "data:image/" in content and "base64," in content:
            return True
    return False


def _extract_usage_metadata(message: Any) -> tuple[int, int, int]:
    usage = getattr(message, "usage_metadata", None) or {}
    if not isinstance(usage, dict):
        return 0, 0, 0
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    output_tokens = int(usage.get("output_tokens", 0) or 0)
    total_tokens = int(usage.get("total_tokens", 0) or (input_tokens + output_tokens))
    return input_tokens, output_tokens, total_tokens


def _compact_test_case_detail_output_for_model(raw_output: Any) -> str:
    """
    将 get_testcase_detail 的 JSON 输出压成短文本，避免小模型复述整段 JSON。
    """
    normalized = _normalize_mcp_content_to_text(raw_output)
    text = normalized if isinstance(normalized, str) else str(normalized)
    text = text.strip()
    if not text:
        return "(无测试用例详情)"

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        if len(text) <= _MAX_TEST_CASE_TOOL_MESSAGE_CHARS:
            return text
        return f"{text[:_MAX_TEST_CASE_TOOL_MESSAGE_CHARS]}\n...[测试用例详情已截断]"

    if not isinstance(payload, dict):
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized) <= _MAX_TEST_CASE_TOOL_MESSAGE_CHARS:
            return serialized
        return f"{serialized[:_MAX_TEST_CASE_TOOL_MESSAGE_CHARS]}\n...[测试用例详情已截断]"

    lines: List[str] = []
    name = str(payload.get("name") or "").strip()
    if name:
        lines.append(f"用例名称: {name}")

    precondition = str(payload.get("precondition") or "").strip()
    if precondition:
        lines.append(f"前置条件: {precondition}")

    level = str(payload.get("level") or "").strip()
    if level:
        lines.append(f"优先级: {level}")

    test_type = str(payload.get("test_type") or "").strip()
    if test_type:
        lines.append(f"测试类型: {test_type}")

    steps = payload.get("steps") or []
    if isinstance(steps, list) and steps:
        lines.append("步骤:")
        for raw_step in steps[:20]:
            if not isinstance(raw_step, dict):
                continue
            step_number = raw_step.get("step_number") or len(lines)
            description = str(raw_step.get("description") or "").strip()
            expected = str(raw_step.get("expected_result") or "").strip()
            if description or expected:
                lines.append(f"{step_number}. {description} => {expected}".strip())

    summary = "\n".join(line for line in lines if line).strip()
    if not summary:
        summary = text

    if len(summary) > _MAX_TEST_CASE_TOOL_MESSAGE_CHARS:
        summary = f"{summary[:_MAX_TEST_CASE_TOOL_MESSAGE_CHARS]}\n...[测试用例详情已截断]"
    return summary


def _compact_tool_output_for_test_case_execution(
    tool_name: str,
    tool_args: Optional[Dict[str, Any]],
    raw_output: Any,
) -> str:
    """
    给专用测试用例执行器压缩工具输出，减少模型在后续轮次中被长文本带偏。
    """
    normalized = _normalize_mcp_content_to_text(raw_output)
    text = normalized if isinstance(normalized, str) else str(normalized)
    text = text.strip() or "(无输出)"

    tool_args = tool_args or {}
    if tool_name == "execute_skill_script":
        skill_name = str(tool_args.get("skill_name") or "").strip()
        command = str(tool_args.get("command") or "").strip()
        if skill_name == "whart-test" and "--action get_testcase_detail" in command:
            return _compact_test_case_detail_output_for_model(text)

    if len(text) > _MAX_TEST_CASE_TOOL_MESSAGE_CHARS:
        return f"{text[:_MAX_TEST_CASE_TOOL_MESSAGE_CHARS]}\n...[工具输出已截断]"

    return text


def _infer_target_url_hint_from_test_case_detail(raw_output: Any) -> Optional[str]:
    """
    基于测试用例详情推断更精确的目标页面 URL。

    目前先覆盖本轮联调用到的 Expand Testing 常见入口，避免模型总是从首页开始误操作。
    """
    normalized = _normalize_mcp_content_to_text(raw_output)
    text = normalized if isinstance(normalized, str) else str(normalized)

    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None

    precondition = str(payload.get("precondition") or "")
    base_url_match = re.search(r"https?://[^\s,，]+", precondition)
    if not base_url_match:
        return None

    base_url = base_url_match.group(0).rstrip("/")
    lowered_base = base_url.lower()
    if "practice.expandtesting.com" not in lowered_base:
        return None

    parts: List[str] = []
    for key in ("name", "module_detail", "notes"):
        value = str(payload.get(key) or "").strip()
        if value:
            parts.append(value.lower())

    steps = payload.get("steps") or []
    if isinstance(steps, list):
        for step in steps:
            if not isinstance(step, dict):
                continue
            for key in ("description", "expected_result"):
                value = str(step.get(key) or "").strip()
                if value:
                    parts.append(value.lower())

    combined = "\n".join(parts)
    route_map = [
        (("/login",), ("登录", "login", "secure area")),
        (("/register",), ("注册", "register")),
        (("/forgot-password",), ("忘记密码", "forgot password", "retrieve password")),
        (("/otp-login",), ("otp", "验证码", "one time password")),
        (("/dynamic-loading", "/dynamic-loading/2"), ("动态加载", "dynamic loading")),
    ]

    for routes, keywords in route_map:
        if any(keyword in combined for keyword in keywords):
            return f"{base_url}{routes[0]}"

    return None


def _extract_inline_execute_skill_call(content: str) -> Optional[Dict[str, Any]]:
    """
    当模型没有产出标准 tool_calls，而是把工具参数写进 Markdown JSON 代码块时，
    尝试提取 execute_skill_script 的调用参数，作为测试执行模式兜底。
    """
    text = (content or "").strip()
    if not text:
        return None

    candidates: List[str] = []
    fenced_matches = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates.extend(fenced_matches)
    if text.startswith("{") and text.endswith("}"):
        candidates.append(text)

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        skill_name = str(payload.get("skill_name") or "").strip()
        command = str(payload.get("command") or "").strip()
        if not skill_name or not command:
            continue
        parsed: Dict[str, Any] = {
            "skill_name": skill_name,
            "command": command,
        }
        session_id = payload.get("session_id")
        if session_id not in (None, ""):
            parsed["session_id"] = session_id
        return parsed

    return None


def _extract_inline_upload_screenshot_call(
    content: str,
    *,
    project_id: int,
    test_case_id: int,
) -> Optional[Dict[str, Any]]:
    """
    当模型只用自然语言表达“上传步骤截图”时，自动补成 whart-test 调用。
    """
    text = (content or "").strip()
    if not text:
        return None

    filename_match = re.search(r"([A-Za-z0-9._-]+\.(?:png|jpg|jpeg|webp))", text, re.IGNORECASE)
    if not filename_match:
        return None

    step_match = re.search(r"步骤\s*(\d+)\s*截图", text)
    filename = filename_match.group(1)
    command = (
        "python whart_tools.py --action upload_screenshot "
        f"--project_id {project_id} --case_id {test_case_id} "
        f"--file_path {filename}"
    )
    if step_match:
        command += f" --step_number {step_match.group(1)}"

    return {
        "skill_name": "whart-test",
        "command": command,
    }


def _extract_inline_login_playwright_call(
    content: str,
    case_detail_summary: str,
    *,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """
    当模型只说“输入用户名密码并提交”却没有真的调工具时，为常见登录流生成稳健的 playwright 命令。
    """
    text = (content or "").strip()
    lowered = text.lower()
    if not text or ("用户名" not in text and "password" not in lowered and "登录" not in text):
        return None
    if "playwright-skill" not in text and "输入正确用户名和密码并提交" not in text:
        return None

    summary = case_detail_summary or ""
    username_match = re.search(r"(?:账号|用户名)[:：]\s*([^\s,，]+)", summary)
    password_match = re.search(r"密码[:：]\s*([^\s,，]+)", summary)
    if not username_match or not password_match:
        return None

    username = username_match.group(1).strip()
    password = password_match.group(1).strip()
    success_text_match = re.search(r"([A-Z][A-Z ]{2,}[A-Z])", summary)
    success_text = success_text_match.group(1).strip() if success_text_match else ""

    command_parts = [
        "const usernameField = page.locator('#username, input[name=\"username\"], input[type=\"text\"]').first();",
        "await usernameField.waitFor({ state: 'visible', timeout: 30000 });",
        f"await usernameField.fill({json.dumps(username, ensure_ascii=False)});",
        "const passwordField = page.locator('#password, input[name=\"password\"], input[type=\"password\"]').first();",
        "await passwordField.waitFor({ state: 'visible', timeout: 30000 });",
        f"await passwordField.fill({json.dumps(password, ensure_ascii=False)});",
        "const submitButton = page.locator('button[type=\"submit\"], button:has-text(\"Login\")').first();",
        "await submitButton.click();",
        "await page.waitForLoadState('domcontentloaded');",
    ]
    if success_text:
        command_parts.append(
            f"await page.waitForSelector('text=/{re.escape(success_text)}/i', {{ timeout: 30000 }});"
        )
    command_parts.extend(
        [
            "console.log(page.url());",
            "const desc = await helpers.describePageForAI(page);",
            "console.log(desc);",
        ]
    )

    return {
        "skill_name": "playwright-skill",
        "command": 'node run.js "' + " ".join(command_parts).replace('"', '\\"') + '"',
        "session_id": session_id,
    }


def _extract_test_case_execution_signals(text: Any) -> set[str]:
    normalized = _normalize_mcp_content_to_text(text)
    content = normalized if isinstance(normalized, str) else str(normalized)
    lowered = content.lower()
    signals: set[str] = set()

    success_markers = {
        "secure_area_text": "you logged into a secure area!" in lowered,
        "welcome_secure_area": "welcome to the secure area" in lowered,
        "logout_found": (
            "logout link found" in lowered
            or "退出登录入口存在" in content
            or "href === '/logout'" in content
        ),
        "secure_path": "/secure" in lowered,
        "flash_success": "logged into a secure area" in lowered,
        "secure_heading": bool(
            re.search(r"(^|\n)\s*secure area\s*($|\n)", lowered)
        )
        or "secure area page for automation testing practice" in lowered,
    }
    failure_markers = {
        # 只把真实页面错误提示当成失败信号，避免把示例标题
        # "Test Case 2: Invalid Username" / "Test Case 3: Invalid Password"
        # 误识别成执行结果。
        "invalid_username": "your username is invalid" in lowered,
        "invalid_password": "your password is invalid" in lowered,
        "selector_timeout": "waitforselector: timeout" in lowered,
        "playwright_error": any(
            marker in lowered
            for marker in (
                "error: playwright",
                "referenceerror:",
                "syntaxerror:",
                "typeerror:",
                "execution context was destroyed",
                "target page, context or browser has been closed",
                "timeout 60000ms exceeded",
                "node.js v",
            )
        ),
    }

    for key, present in success_markers.items():
        if present:
            signals.add(key)
    for key, present in failure_markers.items():
        if present:
            signals.add(key)
    return signals


def _is_clear_final_test_case_summary(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False

    lowered = content.lower()
    continuation_markers = (
        "接下来",
        "下一步",
        "我将",
        "继续验证",
        "继续检查",
        "然后我会",
        "然后将",
        "需要继续",
        "还要验证",
    )
    if any(marker in content for marker in continuation_markers):
        return False

    final_markers = (
        "测试通过",
        "测试失败",
        "验证通过",
        "验证失败",
        "执行完成",
        "执行成功",
        "执行失败",
        "登录成功",
        "登录失败",
        "结论",
        "passed",
        "failed",
        "success",
    )
    return any(marker in content for marker in final_markers) or any(
        marker in lowered for marker in ("passed", "failed", "success")
    )


def calculate_context_tokens(
    messages: List[Any], model_name: str = "gpt-4o"
) -> tuple[int, int, int]:
    """
    计算当前上下文 Token

    - input_tokens / output_tokens: 优先取最后一条带 usage_metadata 的模型调用统计，
      用于记录最近一次 provider 实际消耗。
    - total_tokens: 始终基于当前消息栈内容估算，
      用于展示“当前上下文占用率”，避免把“上一轮调用消耗”误当成“当前上下文大小”。
    """
    input_tokens = 0
    output_tokens = 0

    # 1) 提取最近一轮模型调用的 usage_metadata（用于日志与统计）
    for msg in reversed(messages):
        if hasattr(msg, "usage_metadata") and msg.usage_metadata:
            usage = msg.usage_metadata
            input_tokens = usage.get("input_tokens", 0) or 0
            output_tokens = usage.get("output_tokens", 0) or 0
            break

    # 2) 始终按当前消息内容估算上下文占用（避免 100%/80% 之类的假波动）
    content_tokens = 0
    for msg in messages:
        if hasattr(msg, "content") and msg.content:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            content_tokens += context_checker.count_tokens(content, model_name)

    estimated_total = content_tokens * 3
    return input_tokens, output_tokens, estimated_total


def _is_unreliable_default_detected_limit(
    model_name: str, detected_limit: Optional[int]
) -> bool:
    """
    判断检测上限是否仅来自未知模型的默认回退值（如 128000）。
    该场景下应优先信任用户配置的 context_limit。
    """
    if not isinstance(detected_limit, int) or detected_limit <= 0:
        return False

    default_limit = int(MODEL_CONTEXT_LIMITS.get("default", 128000))
    if detected_limit != default_limit:
        return False

    normalized_name = (model_name or "").lower()
    for model_key in MODEL_CONTEXT_LIMITS.keys():
        if model_key == "default":
            continue
        if model_key in normalized_name:
            return False

    return True


def resolve_runtime_context_limit(
    config_context_limit: Optional[int], llm, model_name: str
) -> int:
    """
    运行时上下文限制（与 middleware_config 保持一致，用户优先）：
    - 用户配置存在时：直接使用 config
    - 无 config 时：profile > 可靠 detected > 默认值
    """
    config_limit = (
        config_context_limit
        if isinstance(config_context_limit, int) and config_context_limit > 0
        else None
    )
    detected_limit = (
        get_context_limit_from_llm(llm, fallback_model_name=model_name)
        if llm is not None
        else None
    )

    profile_limit = None
    if llm is not None:
        profile = getattr(llm, "profile", None)
        if isinstance(profile, dict):
            max_input_tokens = profile.get("max_input_tokens")
            if isinstance(max_input_tokens, int) and max_input_tokens > 0:
                profile_limit = max_input_tokens

    unreliable_detected_limit = _is_unreliable_default_detected_limit(
        model_name, detected_limit
    )

    if config_limit:
        return config_limit

    if profile_limit:
        return profile_limit

    if (
        isinstance(detected_limit, int)
        and detected_limit > 0
        and not unreliable_detected_limit
    ):
        return detected_limit

    return 128000


@method_decorator(csrf_exempt, name="dispatch")
class AgentLoopStreamAPIView(View):
    """
    Agent Loop 聊天 API (LangChain v1 重构版)

    核心特性：
    - 使用 create_agent() 统一创建 Agent
    - SummarizationMiddleware 自动上下文压缩
    - HumanInTheLoopMiddleware 处理 HITL 审批
    - 在流处理层检测工具调用生成步骤事件
    - 支持 stream 参数：
      - stream=true (默认)：返回 SSE 流式响应
      - stream=false：返回普通 JSON 响应
    """

    # 最大步骤数（用于前端显示）
    MAX_STEPS = 500

    def _update_session_token_usage(
        self, session_id: str, input_tokens: int, output_tokens: int
    ):
        """更新会话的 Token 使用统计"""
        try:
            from django.db.models import F
            from django.utils import timezone

            ChatSession.objects.filter(session_id=session_id).update(
                total_input_tokens=F("total_input_tokens") + input_tokens,
                total_output_tokens=F("total_output_tokens") + output_tokens,
                total_tokens=F("total_tokens") + input_tokens + output_tokens,
                request_count=F("request_count") + 1,
                updated_at=timezone.now(),
            )
        except Exception as e:
            logger.warning(f"Failed to update session token usage: {e}")

    async def authenticate_request(self, request):
        """JWT 认证"""
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Authentication credentials were not provided.")

        token = auth_header.split(" ")[1]
        jwt_auth = JWTAuthentication()

        try:
            validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
            user = await sync_to_async(jwt_auth.get_user)(validated_token)
            return user
        except Exception as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}")

    async def _run_dedicated_test_case_execution(
        self,
        *,
        llm: Any,
        session_id: str,
        project_id: str,
        test_case_id: int,
        user_message: str,
        effective_prompt: Optional[str],
        context_limit: int,
        model_name: str,
        builtin_tools: List[Any],
        generate_playwright_script: bool,
        creator_id: Optional[int],
    ):
        """
        专用测试用例执行器。

        避开通用 Agent Loop 的自由文本回复，强制执行固定流程：
        1. 后端先确定性读取测试用例详情
        2. 模型只能在 execute_skill_script / finish_test_case_execution 两个工具间选择
        3. 如果模型没有给出 tool_call，则立刻失败，避免长时间卡在 100%
        """
        if not builtin_tools:
            yield create_sse_data(
                {"type": "error", "message": "未找到可用的内置执行工具"}
            )
            yield create_sse_data({"type": "complete", "status": "error", "steps": 0})
            yield "data: [DONE]\n\n"
            return

        execute_skill_tool = builtin_tools[0]
        usage_input_tokens = 0
        usage_output_tokens = 0
        step_count = 0
        finished = False
        final_summary = ""
        final_success = True
        observed_signals: set[str] = set()
        executed_playwright_records: List[Dict[str, Any]] = []
        no_tool_call_retries = 0

        @langchain_tool
        def finish_test_case_execution(
            success: bool,
            summary: str,
        ) -> str:
            """
            在已经完成测试执行且结论明确时调用。

            Args:
                success: 测试是否通过
                summary: 基于实际执行结果的简短总结

            Returns:
                JSON 字符串，供后端收尾并展示给前端
            """
            return json.dumps(
                {"success": bool(success), "summary": str(summary or "").strip()},
                ensure_ascii=False,
            )

        # 第 1 步固定走后端读取测试用例详情，减少模型第一跳发散。
        step_count += 1
        yield create_sse_data(
            {
                "type": "step_start",
                "step": step_count,
                "max_steps": self.MAX_STEPS,
                "tools": [execute_skill_tool.name],
            }
        )

        initial_command = (
            "python whart_tools.py --action get_testcase_detail "
            f"--project_id {project_id} --case_id {test_case_id}"
        )
        detail_result = await sync_to_async(execute_skill_tool.invoke)(
            {
                "skill_name": "whart-test",
                "command": initial_command,
            }
        )
        detail_content, detail_summary = process_mcp_tool_output(detail_result)
        yield create_sse_data(
            {
                "type": "tool_result",
                "tool_name": execute_skill_tool.name,
                "tool_output": detail_content,
                "summary": detail_summary,
                "step": step_count,
            }
        )
        yield create_sse_data({"type": "step_complete", "step": step_count})

        detail_text = detail_content if isinstance(detail_content, str) else str(detail_content)
        if detail_text.startswith("错误:") or "命令执行失败" in detail_text:
            yield create_sse_data(
                {
                    "type": "error",
                    "message": "读取测试用例详情失败，已停止执行。请先检查该用例是否存在且当前 API 凭证可用。",
                }
            )
            yield create_sse_data(
                {"type": "complete", "status": "error", "steps": step_count}
            )
            yield "data: [DONE]\n\n"
            return

        compact_case_detail = _compact_test_case_detail_output_for_model(detail_content)
        session_key = f"case_{test_case_id}"
        target_url_hint = _infer_target_url_hint_from_test_case_detail(detail_content)

        initial_page_snapshot = ""
        if target_url_hint:
            step_count += 1
            yield create_sse_data(
                {
                    "type": "step_start",
                    "step": step_count,
                    "max_steps": self.MAX_STEPS,
                    "tools": [execute_skill_tool.name],
                }
            )

            goto_command = (
                f"node run.js \"await page.goto({json.dumps(target_url_hint)}); "
                "const desc = await helpers.describePageForAI(page); console.log(desc);\""
            )
            goto_result = await sync_to_async(execute_skill_tool.invoke)(
                {
                    "skill_name": "playwright-skill",
                    "command": goto_command,
                    "session_id": session_key,
                }
            )
            goto_content, goto_summary = process_mcp_tool_output(goto_result)
            observed_signals.update(_extract_test_case_execution_signals(goto_content))
            executed_playwright_records.append(
                {
                    "command": goto_command,
                    "output": goto_content,
                }
            )
            yield create_sse_data(
                {
                    "type": "tool_result",
                    "tool_name": execute_skill_tool.name,
                    "tool_output": goto_content,
                    "summary": goto_summary,
                    "step": step_count,
                }
            )
            yield create_sse_data({"type": "step_complete", "step": step_count})
            initial_page_snapshot = _compact_tool_output_for_test_case_execution(
                execute_skill_tool.name,
                {"skill_name": "playwright-skill", "command": goto_command},
                goto_content,
            )

        script_generation_note = (
            "\n当前请求还打开了“生成 UI 自动化用例”选项。功能测试执行完成后，"
            "后端会基于真实浏览器步骤自动保存到 UI 自动化模块；"
            "如果你已经完成测试，再调用 finish_test_case_execution 结束。"
            if generate_playwright_script
            else ""
        )
        dedicated_prompt = (
            (effective_prompt or "").strip()
            + "\n\n你正在执行 WHartTest 的功能测试用例，当前处于严格工具模式。\n"
            "规则：\n"
            "1. 优先调用工具，禁止输出解释性长文本；如果确实可以结束，只允许给出一句简短总结。\n"
            "2. 只允许调用 execute_skill_script 或 finish_test_case_execution。\n"
            f"3. 浏览器会话固定使用 session_id=\"{session_key}\"。\n"
            "4. 第一次浏览器调用必须使用 playwright-skill 打开目标页面，并立刻执行 "
            "`helpers.describePageForAI(page)` 获取真实 selector；如果后端已经预打开页面，就直接复用当前页面。\n"
            "5. 之后基于真实 selector 继续执行，run.js 双引号内只能是可执行 JavaScript，禁止自然语言。\n"
            "6. 如果某个 selector 不存在，不要连续重复同一条 fill/waitForSelector 命令，先重新查看当前页面结构或 URL。\n"
            "7. 如果是登录场景，必须先确认当前页面就是登录页，再执行输入。\n"
            "8. 不要复述测试用例 JSON，不要说“接下来我将”，直接调用工具。\n"
            "9. 验证跳转/登录成功时优先用 `await page.waitForURL('**/secure');` 或 `console.log(page.url());`；"
            "禁止用不加 /i 的正则选择器如 `text=/secure/`，大小写不匹配会导致 30s 超时；"
            "`waitForURL` 无异常完成即代表跳转成功，截图后立刻调用 finish_test_case_execution，不要再用 waitForSelector 重复验证。\n"
            "10. 如果是错误用户名/密码等异常登录场景，优先验证页面仍停留在 `/login` 或未进入 `/secure`，"
            "并结合截图或页面文本判断，不要硬编码完整英文报错句后长时间等待。\n"
            "11. 当结论明确后，调用 finish_test_case_execution，总结必须基于真实执行结果。"
            + script_generation_note
        ).strip()

        human_text = (
            f"请执行项目 {project_id} 的功能测试用例 {test_case_id}。\n"
            f"用户原始请求：{user_message}\n\n"
            "测试用例摘要如下：\n"
            f"{compact_case_detail}\n\n"
            + (
                f"后端已预打开目标页面：{target_url_hint}\n"
                f"当前页面结构摘要：\n{initial_page_snapshot}\n\n"
                if target_url_hint and initial_page_snapshot
                else ""
            )
            +
            "现在继续调用工具执行浏览器步骤。"
        )

        messages: List[Any] = [
            SystemMessage(content=dedicated_prompt),
            HumanMessage(content=human_text),
        ]

        tool_runnable = llm.bind_tools(
            [execute_skill_tool, finish_test_case_execution],
            parallel_tool_calls=False,
        ).bind(max_tokens=_MAX_TEST_CASE_COMPLETION_TOKENS)

        for _ in range(_MAX_TEST_CASE_AGENT_STEPS):
            if should_stop(session_id):
                clear_stop_signal(session_id)
                yield create_sse_data(
                    {"type": "stopped", "message": "已停止生成", "step": step_count}
                )
                yield create_sse_data(
                    {"type": "complete", "status": "stopped", "steps": step_count}
                )
                yield "data: [DONE]\n\n"
                return

            ai_msg = await tool_runnable.ainvoke(messages)
            input_tokens, output_tokens, _ = _extract_usage_metadata(ai_msg)
            usage_input_tokens += input_tokens
            usage_output_tokens += output_tokens

            tool_calls = getattr(ai_msg, "tool_calls", None) or []
            if not tool_calls:
                content = str(getattr(ai_msg, "content", "") or "").strip()
                if len(content) > _MAX_TEST_CASE_AI_SNIPPET_CHARS:
                    content = f"{content[:_MAX_TEST_CASE_AI_SNIPPET_CHARS]}..."
                _positive_signals = observed_signals & {
                    "secure_area_text",
                    "welcome_secure_area",
                    "logout_found",
                    "secure_path",
                    "flash_success",
                    "secure_heading",
                }
                clear_success = (
                    len(_positive_signals) >= 2
                    or "secure_path" in observed_signals  # URL 跳转成功是登录成功的权威依据
                    or (
                        "secure_heading" in observed_signals
                        and "logout_found" in observed_signals
                    )
                )
                # clear_success 优先；只有未确认成功时才允许失败信号覆盖
                clear_failure = not clear_success and bool(
                    observed_signals
                    & {
                        "invalid_username",
                        "invalid_password",
                        "selector_timeout",
                        "playwright_error",
                    }
                )
                if step_count > 1 and (
                    _is_clear_final_test_case_summary(content)
                    or clear_success
                    or clear_failure
                ):
                    if clear_success and not _is_clear_final_test_case_summary(content):
                        final_summary = "测试通过：已进入安全区域页面，并观察到登录成功提示与 Logout 入口。"
                    elif clear_failure and not _is_clear_final_test_case_summary(content):
                        final_summary = "测试失败：执行过程中出现错误或未观察到预期页面信号。"
                    else:
                        final_summary = content
                    finished = True
                    final_success = clear_success or not any(
                        marker in final_summary
                        for marker in ("失败", "未通过", "错误", "异常")
                    )
                    logger.info(
                        "AgentLoopStreamAPI: Dedicated testcase executor accepted short final text. "
                        "session_id=%s, test_case_id=%s, content_snippet=%s, signals=%s",
                        session_id,
                        test_case_id,
                        content,
                        sorted(observed_signals),
                    )
                    break
                logger.warning(
                    "AgentLoopStreamAPI: Dedicated testcase executor got no tool call. "
                    "session_id=%s, test_case_id=%s, content_snippet=%s, signals=%s",
                    session_id,
                    test_case_id,
                    content,
                    sorted(observed_signals),
                )
                inline_execute_call = _extract_inline_execute_skill_call(content)
                if inline_execute_call:
                    logger.info(
                        "AgentLoopStreamAPI: Dedicated testcase executor recovered inline tool payload. "
                        "session_id=%s, test_case_id=%s, payload=%s",
                        session_id,
                        test_case_id,
                        inline_execute_call,
                    )
                    tool_calls = [
                        {
                            "name": execute_skill_tool.name,
                            "args": inline_execute_call,
                            "id": f"inline-execute-{step_count}",
                        }
                    ]
                else:
                    inline_login_call = _extract_inline_login_playwright_call(
                        content,
                        compact_case_detail,
                        session_id=session_key,
                    )
                    if inline_login_call:
                        logger.info(
                            "AgentLoopStreamAPI: Dedicated testcase executor recovered inline login action. "
                            "session_id=%s, test_case_id=%s, payload=%s",
                            session_id,
                            test_case_id,
                            inline_login_call,
                        )
                        tool_calls = [
                            {
                                "name": execute_skill_tool.name,
                                "args": inline_login_call,
                                "id": f"inline-login-{step_count}",
                            }
                        ]
                        no_tool_call_retries = 0
                    else:
                        inline_upload_call = _extract_inline_upload_screenshot_call(
                            content,
                            project_id=project_id,
                            test_case_id=test_case_id,
                        )
                        if inline_upload_call:
                            logger.info(
                                "AgentLoopStreamAPI: Dedicated testcase executor recovered inline screenshot upload. "
                                "session_id=%s, test_case_id=%s, payload=%s",
                                session_id,
                                test_case_id,
                                inline_upload_call,
                            )
                            tool_calls = [
                                {
                                    "name": execute_skill_tool.name,
                                    "args": inline_upload_call,
                                    "id": f"inline-upload-{step_count}",
                                }
                            ]
                            no_tool_call_retries = 0
                        else:
                            if no_tool_call_retries < 2:
                                no_tool_call_retries += 1
                                messages.append(ai_msg)
                                messages.append(
                                    HumanMessage(
                                        content=(
                                            "不要继续解释。请直接调用工具完成下一步。"
                                            "如果需要上传截图，也必须使用 execute_skill_script 调用 whart-test；"
                                            "如果需要浏览器操作，使用 execute_skill_script 调用 playwright-skill。"
                                            "只返回工具调用，不要返回 JSON 示例。"
                                        )
                                    )
                                )
                                continue
                            yield create_sse_data(
                                {
                                    "type": "error",
                                    "message": "测试执行代理没有产出工具调用，已中止本轮执行。请优先换用更强的支持工具调用模型，或稍后重试。",
                                }
                            )
                            yield create_sse_data(
                                {"type": "complete", "status": "error", "steps": step_count}
                            )
                            yield "data: [DONE]\n\n"
                            return
                no_tool_call_retries = 0

            messages.append(ai_msg)

            for tool_call in tool_calls:
                tool_name = str(tool_call.get("name") or "").strip()
                tool_args = tool_call.get("args") or {}
                tool_call_id = str(tool_call.get("id") or "")

                step_count += 1
                yield create_sse_data(
                    {
                        "type": "step_start",
                        "step": step_count,
                        "max_steps": self.MAX_STEPS,
                        "tools": [tool_name or "unknown"],
                    }
                )

                try:
                    if tool_name == finish_test_case_execution.name:
                        tool_result = await sync_to_async(
                            finish_test_case_execution.invoke
                        )(tool_args)
                    elif tool_name == execute_skill_tool.name:
                        tool_result = await sync_to_async(execute_skill_tool.invoke)(
                            tool_args
                        )
                    else:
                        tool_result = f"错误: 不支持的工具 `{tool_name}`"
                except Exception as e:
                    logger.error(
                        "AgentLoopStreamAPI: Dedicated testcase tool failed. "
                        "session_id=%s, test_case_id=%s, tool=%s, error=%s",
                        session_id,
                        test_case_id,
                        tool_name,
                        e,
                        exc_info=True,
                    )
                    tool_result = f"错误: {str(e)}"

                tool_content, tool_summary = process_mcp_tool_output(tool_result)
                # 只从 playwright-skill 输出提取信号，避免测试用例元数据（whart-test）产生假阳性
                _skill_name_arg = (tool_args.get("skill_name") or "").lower()
                if "playwright" in _skill_name_arg:
                    executed_playwright_records.append(
                        {
                            "command": tool_args.get("command") or "",
                            "output": tool_content,
                        }
                    )
                    observed_signals.update(
                        _extract_test_case_execution_signals(tool_content)
                    )
                    # waitForURL 成功时直接注入 secure_path 信号（成功时无输出，无法靠文本检测）
                    _cmd = (tool_args.get("command") or "").lower()
                    _no_error = not any(
                        k in tool_content.lower()
                        for k in ("error", "timeout", "❌")
                    )
                    if "waitforurl" in _cmd and "/secure" in _cmd and _no_error:
                        observed_signals.add("secure_path")
                yield create_sse_data(
                    {
                        "type": "tool_result",
                        "tool_name": tool_name or "unknown",
                        "tool_output": tool_content,
                        "summary": tool_summary,
                        "step": step_count,
                    }
                )
                yield create_sse_data({"type": "step_complete", "step": step_count})

                compact_tool_output = _compact_tool_output_for_test_case_execution(
                    tool_name,
                    tool_args,
                    tool_content,
                )
                messages.append(
                    ToolMessage(
                        content=compact_tool_output,
                        tool_call_id=tool_call_id,
                        name=tool_name or "unknown",
                    )
                )

                if tool_name == finish_test_case_execution.name:
                    try:
                        payload = json.loads(str(tool_result))
                    except (TypeError, ValueError):
                        payload = {}
                    final_success = bool(payload.get("success", True))
                    final_summary = str(
                        payload.get("summary")
                        or tool_args.get("summary")
                        or "测试执行已结束"
                    ).strip()
                    if not final_summary:
                        final_summary = "测试执行已结束"
                    finished = True
                    break

            if finished:
                break

        if usage_input_tokens > 0 or usage_output_tokens > 0:
            await sync_to_async(self._update_session_token_usage)(
                session_id, usage_input_tokens, usage_output_tokens
            )
            logger.info(
                "AgentLoopStreamAPI: Dedicated testcase executor token usage recorded - "
                "input=%s, output=%s",
                usage_input_tokens,
                usage_output_tokens,
            )

        estimated_total = usage_input_tokens + usage_output_tokens
        if estimated_total <= 0:
            estimated_total = calculate_context_tokens(messages, model_name)[2]
        yield create_sse_data(
            {
                "type": "context_update",
                "context_token_count": estimated_total,
                "context_limit": context_limit,
            }
        )

        if not finished:
            yield create_sse_data(
                {
                    "type": "error",
                    "message": "测试执行代理在限定步数内未能正常结束，已强制停止。建议检查模型工具调用能力或更换模型。",
                }
            )
            yield create_sse_data(
                {"type": "complete", "status": "error", "steps": step_count}
            )
            yield "data: [DONE]\n\n"
            return

        _positive_generation_signals = observed_signals & {
            "secure_area_text",
            "welcome_secure_area",
            "logout_found",
            "secure_path",
            "flash_success",
            "secure_heading",
        }
        if (
            not final_success
            and (
                len(_positive_generation_signals) >= 2
                or "secure_path" in observed_signals
            )
        ):
            final_success = True
            if not final_summary or "未通过" in final_summary or "失败" in final_summary:
                final_summary = "测试通过：已进入安全区域页面，并观察到登录成功相关页面信号。"

        generation_meta: Optional[Dict[str, Any]] = None
        generation_error = ""
        generation_allowed = bool(executed_playwright_records)
        if generate_playwright_script:
            if generation_allowed:
                try:
                    generation_meta = await sync_to_async(
                        generate_ui_case_from_functional_execution
                    )(
                        project_id=int(project_id),
                        creator_id=creator_id,
                        test_case_detail=detail_content,
                        command_records=executed_playwright_records,
                        observed_signals=sorted(observed_signals),
                        target_url_hint=target_url_hint,
                    )
                    yield create_sse_data(
                        {
                            "type": "info",
                            "message": (
                                f"已保存 UI 自动化用例：{generation_meta['ui_testcase_name']} "
                                f"(ID: {generation_meta['ui_testcase_id']})，"
                                f"模块：{generation_meta['ui_module_name']}"
                            ),
                        }
                    )
                except Exception as generation_exc:
                    generation_error = str(generation_exc)
                    logger.warning(
                        "AgentLoopStreamAPI: UI case generation failed. "
                        "session_id=%s, test_case_id=%s, error=%s",
                        session_id,
                        test_case_id,
                        generation_exc,
                        exc_info=True,
                    )
                    yield create_sse_data(
                        {
                            "type": "warning",
                            "message": f"UI 自动化用例生成失败：{generation_error}",
                        }
                    )
            else:
                generation_error = "本次执行未提取到足够稳定的浏览器动作，无法保存为 UI 自动化用例"
                yield create_sse_data(
                    {
                        "type": "warning",
                        "message": generation_error,
                    }
                )

        if generation_meta:
            suffix = (
                f" 已生成 UI 自动化用例《{generation_meta['ui_testcase_name']}》"
                f"（模块：{generation_meta['ui_module_name']}，ID: {generation_meta['ui_testcase_id']}）。"
            )
            final_summary = (final_summary or "测试执行完成。").rstrip("。") + "。" + suffix
        elif generate_playwright_script and generation_error:
            final_summary = (final_summary or "测试执行完成。").rstrip("。") + f"。{generation_error}。"

        if final_summary:
            yield create_sse_data({"type": "stream", "data": final_summary})
        yield create_sse_data(
            {
                "type": "complete",
                "total_steps": step_count,
                "status": "success" if final_success else "failed",
            }
        )
        yield "data: [DONE]\n\n"
        return

    async def _create_stream_generator(
        self,
        request,
        user_message: str,
        session_id: str,
        project_id: str,
        project: Project,
        knowledge_base_id: Optional[int] = None,
        use_knowledge_base: bool = True,
        prompt_id: Optional[int] = None,
        uploaded_images_base64: Optional[List[str]] = None,
        generate_playwright_script: bool = False,
        test_case_id: Optional[int] = None,
        use_pytest: bool = True,
    ):
        """
        创建 SSE 流式生成器（LangChain v1 重构版）

        使用 create_agent + astream 模式，替代旧的 AgentOrchestrator 循环。
        通过检测 updates 流中的工具调用来生成 step_start/step_complete 事件。
        """
        thread_id = f"{request.user.id}_{project_id}_{session_id}"

        # 1. 获取 LLM 配置
        active_config = await sync_to_async(
            LLMConfig.objects.filter(is_active=True).first
        )()
        if not active_config:
            yield create_sse_data(
                {"type": "error", "message": "No active LLM configuration found"}
            )
            return
        logger.info(f"AgentLoopStreamAPI: Using LLM config: {active_config.name}")
        context_limit = active_config.context_limit or 128000
        model_name = active_config.name or "gpt-4o"

        # 2. 验证多模态支持
        if uploaded_images_base64 and not active_config.supports_vision:
            yield create_sse_data(
                {
                    "type": "error",
                    "message": f"模型 {active_config.name} 不支持图片输入",
                }
            )
            return

        try:
            # 3. 初始化 LLM
            llm_temperature = 0.0 if test_case_id else 0.7
            llm = await sync_to_async(create_llm_instance)(
                active_config, temperature=llm_temperature
            )
            context_limit = resolve_runtime_context_limit(
                active_config.context_limit, llm, model_name
            )

            # 4. 加载 MCP 工具
            tools: List[Any] = []
            restrict_to_builtin_skills = bool(test_case_id)
            if restrict_to_builtin_skills:
                logger.info(
                    "AgentLoopStreamAPI: test_case_id=%s detected, skip MCP tools and use builtin skills only",
                    test_case_id,
                )
                yield create_sse_data(
                    {
                        "type": "info",
                        "message": "测试用例执行模式：已跳过 MCP 工具，仅保留内置执行技能",
                    }
                )
            else:
                try:
                    active_mcp_configs = await sync_to_async(list)(
                        RemoteMCPConfig.objects.filter(is_active=True)
                    )
                    if active_mcp_configs:
                        client_config = {}
                        for cfg in active_mcp_configs:
                            key = cfg.name or f"remote_{cfg.id}"
                            client_config[key] = {
                                "url": cfg.url,
                                "transport": (cfg.transport or "streamable_http").replace(
                                    "-", "_"
                                ),
                            }
                            if cfg.headers:
                                client_config[key]["headers"] = cfg.headers

                        if client_config:
                            mcp_tools = await mcp_session_manager.get_tools_for_config(
                                client_config,
                                user_id=str(request.user.id),
                                project_id=str(project_id),
                                session_id=session_id,
                            )
                            tools.extend(mcp_tools)
                            logger.info(
                                f"AgentLoopStreamAPI: Loaded {len(mcp_tools)} MCP tools"
                            )
                            yield create_sse_data(
                                {
                                    "type": "info",
                                    "message": f"已加载 {len(mcp_tools)} 个工具",
                                }
                            )
                except Exception as e:
                    logger.error(
                        f"AgentLoopStreamAPI: MCP tools loading failed: {e}", exc_info=True
                    )
                    yield create_sse_data(
                        {"type": "warning", "message": f"MCP 工具加载失败: {str(e)}"}
                    )

            # 5. 添加知识库工具
            logger.info(
                f"AgentLoopStreamAPI: 检查知识库工具 - knowledge_base_id={knowledge_base_id}, use_knowledge_base={use_knowledge_base}"
            )
            explicit_external_skill_request = _message_prefers_external_skill_docs(
                user_message
            )
            if knowledge_base_id and use_knowledge_base and not explicit_external_skill_request:
                try:
                    from knowledge.langgraph_integration import create_knowledge_tool

                    logger.info(f"AgentLoopStreamAPI: 正在创建知识库工具...")
                    kb_tool = await sync_to_async(create_knowledge_tool)(
                        knowledge_base_id=knowledge_base_id, user=request.user
                    )
                    tools.append(kb_tool)
                    logger.info(
                        f"AgentLoopStreamAPI: ✅ 知识库工具已添加: {kb_tool.name}"
                    )
                except Exception as e:
                    logger.warning(
                        f"AgentLoopStreamAPI: ❌ Knowledge tool creation failed: {e}",
                        exc_info=True,
                    )
            else:
                logger.info(
                    f"AgentLoopStreamAPI: ⚠️ 跳过知识库工具 (knowledge_base_id={knowledge_base_id}, use_knowledge_base={use_knowledge_base}, explicit_external_skill_request={explicit_external_skill_request})"
                )

            # 6. 添加内置工具（Playwright 脚本管理等）
            from orchestrator_integration.builtin_tools import get_builtin_tools

            builtin_tools = get_builtin_tools(
                user_id=request.user.id,
                project_id=int(project_id),
                test_case_id=test_case_id,
                chat_session_id=session_id,
            )
            tools.extend(builtin_tools)
            logger.info(f"AgentLoopStreamAPI: Added {len(builtin_tools)} builtin tools")

            # 7. 获取或创建 ChatSession（使用 get_or_create 避免竞态条件）
            prompt_obj = None
            if prompt_id:
                try:
                    prompt_obj = await sync_to_async(UserPrompt.objects.get)(
                        id=prompt_id, user=request.user, is_active=True
                    )
                except UserPrompt.DoesNotExist:
                    pass

            chat_session, created = await sync_to_async(
                ChatSession.objects.get_or_create
            )(
                session_id=session_id,
                defaults={
                    "user": request.user,
                    "project": project,
                    "prompt": prompt_obj,
                    "title": f"新对话 - {user_message[:30]}",
                },
            )
            if created:
                logger.info(
                    f"AgentLoopStreamAPI: Created new ChatSession: {session_id}"
                )

            # 8. 获取系统提示词
            effective_prompt, prompt_source = await get_effective_system_prompt_async(
                request.user, prompt_id, project
            )

            # 8.1 执行功能测试用例时，追加专用执行指令
            if test_case_id:
                effective_prompt = (
                    effective_prompt or ""
                ) + TEST_CASE_EXECUTION_INSTRUCTION
                logger.info(f"AgentLoopStreamAPI: 已追加测试用例执行指令")

            # 8.2 如果需要生成脚本，追加脚本生成指令
            if generate_playwright_script:
                effective_prompt = (
                    effective_prompt or ""
                ) + PLAYWRIGHT_SCRIPT_INSTRUCTION
                logger.info(f"AgentLoopStreamAPI: 已追加脚本生成指令")

            # 8.3 启用知识库时，明确要求优先检索后再回答
            if (
                knowledge_base_id
                and use_knowledge_base
                and not test_case_id
                and not explicit_external_skill_request
            ):
                effective_prompt = (
                    effective_prompt or ""
                ) + (
                    "\n\n【知识库使用要求】\n"
                    "本轮已启用知识库。如果用户问题与当前项目、平台文档、基线、流程、配置相关，"
                    "请优先调用 `knowledge_search` 检索后再回答；回答应尽量基于检索结果，"
                    "如果没有检索到有效结果，再明确说明。"
                )
                logger.info("AgentLoopStreamAPI: 已追加知识库优先检索指令")
            elif knowledge_base_id and use_knowledge_base and explicit_external_skill_request:
                effective_prompt = (
                    effective_prompt or ""
                ) + (
                    "\n\n【技能优先要求】\n"
                    "用户已明确指定使用外部技能（如 context7-mcp / firecrawl）。"
                    "本轮请优先调用用户点名的 Skill 获取外部文档或网页信息，"
                    "不要先调用知识库；只有当用户明确追问当前项目/平台资料时，才再考虑知识库。"
                    "注意：不能只调用 `read_skill_content` 后就结束，必须至少继续调用一次 `execute_skill_script`，"
                    "并基于脚本输出结果回答。"
                )
                logger.info("AgentLoopStreamAPI: 已追加技能优先指令并跳过知识库优先检索")

            # 9. 构建用户消息（支持多模态：上传图片 + 链接图片）
            linked_image_data_urls: List[str] = []
            linked_image_urls = _extract_linked_image_urls(user_message)
            if linked_image_urls:
                logger.info(
                    "AgentLoopStreamAPI: Extracted %s candidate image URLs from message",
                    len(linked_image_urls),
                )
                if active_config.supports_vision:
                    linked_image_data_urls = await _collect_linked_image_data_urls(
                        user_message,
                        linked_urls=linked_image_urls,
                    )
                    if linked_image_data_urls:
                        logger.info(
                            "AgentLoopStreamAPI: Loaded %s linked images for multimodal input",
                            len(linked_image_data_urls),
                        )
                else:
                    logger.warning(
                        "AgentLoopStreamAPI: Found %s linked image URLs but model %s does not support vision",
                        len(linked_image_urls),
                        active_config.name,
                    )
            elif (
                "http://" in user_message.lower() or "https://" in user_message.lower()
            ):
                logger.warning(
                    "AgentLoopStreamAPI: Message contains URL text but extractor found 0 valid URLs"
                )

            if uploaded_images_base64 or linked_image_data_urls:
                human_message_content = [{"type": "text", "text": user_message}]
                for data_url in linked_image_data_urls:
                    human_message_content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url},
                        }
                    )
                for image_base64 in uploaded_images_base64 or []:
                    human_message_content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            },
                        }
                    )
            else:
                human_message_content = user_message
            user_msg = HumanMessage(content=human_message_content)

            # 10. 获取工具名列表用于 HITL
            tool_names = [t.name for t in tools] if tools else None

            # 11. 发送开始信号
            yield create_sse_data(
                {
                    "type": "start",
                    "session_id": session_id,
                    "thread_id": thread_id,
                    "project_id": project_id,
                    "mode": "agent_loop",
                    "created_at": chat_session.created_at.isoformat()
                    if chat_session and chat_session.created_at
                    else None,
                }
            )

            explicit_skill_shortcut = (
                _build_explicit_skill_shortcut(user_message)
                if not test_case_id
                else None
            )
            if explicit_skill_shortcut:
                execute_skill_tool = next(
                    (t for t in builtin_tools if getattr(t, "name", "") == "execute_skill_script"),
                    None,
                )
                if execute_skill_tool is not None:
                    step_count = 1
                    yield create_sse_data(
                        {
                            "type": "step_start",
                            "step": step_count,
                            "max_steps": 1,
                            "tools": ["execute_skill_script"],
                        }
                    )
                    tool_result = await sync_to_async(execute_skill_tool.invoke)(
                        {
                            "skill_name": explicit_skill_shortcut["skill_name"],
                            "command": explicit_skill_shortcut["command"],
                        }
                    )
                    tool_result_text = str(tool_result)
                    if (
                        explicit_skill_shortcut["skill_name"] == "context7-mcp"
                        and "no_libraries_found" in tool_result_text
                        and explicit_skill_shortcut.get("fallback_skill_name")
                        and explicit_skill_shortcut.get("fallback_command")
                    ):
                        tool_result = await sync_to_async(execute_skill_tool.invoke)(
                            {
                                "skill_name": explicit_skill_shortcut["fallback_skill_name"],
                                "command": explicit_skill_shortcut["fallback_command"],
                            }
                        )
                        explicit_skill_shortcut["label"] = (
                            f"{explicit_skill_shortcut['label']}（未命中文档库，已回退 firecrawl）"
                        )
                    tool_content, tool_summary = process_mcp_tool_output(tool_result)
                    yield create_sse_data(
                        {
                            "type": "tool_result",
                            "tool_name": "execute_skill_script",
                            "tool_output": tool_content,
                            "summary": tool_summary,
                            "step": step_count,
                        }
                    )
                    yield create_sse_data({"type": "step_complete", "step": step_count})
                    response_text = await _summarize_explicit_skill_result(
                        llm=llm,
                        user_message=user_message,
                        skill_label=explicit_skill_shortcut["label"],
                        tool_content=tool_content or tool_summary or "",
                    )
                    yield create_sse_data(
                        {
                            "type": "stream",
                            "data": response_text,
                        }
                    )
                    yield create_sse_data({"type": "complete", "total_steps": step_count})
                    return

            if test_case_id:
                async for chunk in self._run_dedicated_test_case_execution(
                    llm=llm,
                    session_id=session_id,
                    project_id=project_id,
                    test_case_id=int(test_case_id),
                    user_message=user_message,
                    effective_prompt=effective_prompt,
                    context_limit=context_limit,
                    model_name=model_name,
                    builtin_tools=builtin_tools,
                    generate_playwright_script=generate_playwright_script,
                    creator_id=request.user.id,
                ):
                    yield chunk
                return

            # 12. 创建 Agent（LangChain v1 统一路径）
            async with get_async_checkpointer() as checkpointer:
                # 获取中间件（需要同步到异步，因为内部有 ORM 查询）
                middleware = await sync_to_async(get_middleware_from_config)(
                    active_config,
                    llm,
                    user=request.user,
                    session_id=session_id,
                    all_tool_names=tool_names,
                )

                agent = create_agent(
                    llm,
                    tools,
                    system_prompt=effective_prompt,
                    checkpointer=checkpointer,
                    middleware=middleware,
                )
                logger.info(
                    f"AgentLoopStreamAPI: Agent created with {len(tools)} tools"
                )

                # 13. 配置调用参数
                invoke_config = {
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 1000,  # 支持约500次工具调用
                }
                input_messages = {"messages": [user_msg]}

                # 13.1 发送前修复历史消息（配对错误 + 风险工具输出）
                await _sanitize_history_before_model_call(
                    agent=agent,
                    invoke_config=invoke_config,
                    log_prefix="AgentLoopStreamAPI",
                )

                # 14. 步骤跟踪状态
                step_count = 0
                current_tool_calls = []
                interrupt_detected = False
                user_stopped = False

                # 15. 流式执行
                stream_modes = ["updates", "messages"]

                try:
                    async for stream_mode, chunk in agent.astream(
                        input_messages, config=invoke_config, stream_mode=stream_modes
                    ):
                        # 检查用户停止信号
                        if should_stop(session_id):
                            user_stopped = True
                            clear_stop_signal(session_id)
                            logger.info(
                                f"AgentLoopStreamAPI: Stop signal received at step {step_count}"
                            )
                            yield create_sse_data(
                                {
                                    "type": "stopped",
                                    "message": "已停止生成",
                                    "step": step_count,
                                }
                            )
                            break

                        if stream_mode == "updates":
                            # 检查中断事件 (HITL)
                            if isinstance(chunk, dict) and "__interrupt__" in chunk:
                                interrupt_info = chunk["__interrupt__"]
                                logger.info(
                                    f"AgentLoopStreamAPI: HITL interrupt detected: {interrupt_info}"
                                )
                                logger.info(
                                    f"AgentLoopStreamAPI: interrupt_info type: {type(interrupt_info)}"
                                )

                                action_requests = []
                                interrupt_id = None
                                # 处理 tuple、list 或单个 Interrupt 对象
                                if isinstance(interrupt_info, (list, tuple)):
                                    interrupts_list = list(interrupt_info)
                                else:
                                    interrupts_list = [interrupt_info]

                                for intr in interrupts_list:
                                    logger.info(
                                        f"AgentLoopStreamAPI: Processing interrupt: type={type(intr)}, dir={dir(intr)}"
                                    )
                                    logger.info(
                                        f"AgentLoopStreamAPI: interrupt repr: {repr(intr)}"
                                    )

                                    if hasattr(intr, "id"):
                                        interrupt_id = intr.id
                                        logger.info(
                                            f"AgentLoopStreamAPI: interrupt_id from attr: {interrupt_id}"
                                        )
                                    elif isinstance(intr, dict) and "id" in intr:
                                        interrupt_id = intr["id"]
                                        logger.info(
                                            f"AgentLoopStreamAPI: interrupt_id from dict: {interrupt_id}"
                                        )

                                    intr_value = (
                                        getattr(intr, "value", intr)
                                        if hasattr(intr, "value")
                                        else intr
                                    )
                                    logger.info(
                                        f"AgentLoopStreamAPI: intr_value type={type(intr_value)}, value={intr_value}"
                                    )

                                    # 尝试多种方式获取 action_requests
                                    ars = []
                                    if isinstance(intr_value, dict):
                                        ars = intr_value.get("action_requests", [])
                                        logger.info(
                                            f"AgentLoopStreamAPI: action_requests from dict: {ars}"
                                        )
                                    elif hasattr(intr_value, "action_requests"):
                                        ars = intr_value.action_requests
                                        logger.info(
                                            f"AgentLoopStreamAPI: action_requests from attr: {ars}"
                                        )

                                    # 如果还是空的，尝试从 intr 本身获取
                                    if not ars and hasattr(intr, "action_requests"):
                                        ars = intr.action_requests
                                        logger.info(
                                            f"AgentLoopStreamAPI: action_requests from intr attr: {ars}"
                                        )

                                    logger.info(
                                        f"AgentLoopStreamAPI: Found {len(ars)} action_requests: {ars}"
                                    )

                                    for ar in ars:
                                        if isinstance(ar, dict):
                                            action_requests.append(
                                                {
                                                    "name": ar.get(
                                                        "name",
                                                        ar.get(
                                                            "action_name", "unknown"
                                                        ),
                                                    ),
                                                    "args": ar.get(
                                                        "arguments", ar.get("args", {})
                                                    ),
                                                    "description": ar.get(
                                                        "description", ""
                                                    ),
                                                }
                                            )
                                        else:
                                            action_requests.append(
                                                {
                                                    "name": getattr(
                                                        ar, "name", "unknown"
                                                    ),
                                                    "args": getattr(
                                                        ar,
                                                        "arguments",
                                                        getattr(ar, "args", {}),
                                                    ),
                                                    "description": getattr(
                                                        ar, "description", ""
                                                    ),
                                                }
                                            )

                                if action_requests:
                                    # 获取用户工具偏好，为 always_reject 的工具添加 auto_reject 标记
                                    user_approvals = await sync_to_async(
                                        get_user_tool_approvals
                                    )(request.user, session_id)
                                    for ar in action_requests:
                                        tool_name = ar.get("name", "")
                                        if (
                                            user_approvals.get(tool_name)
                                            == "always_reject"
                                        ):
                                            ar["auto_reject"] = True
                                            logger.info(
                                                f"AgentLoopStreamAPI: Tool {tool_name} marked as auto_reject"
                                            )

                                    interrupt_detected = True
                                    yield create_sse_data(
                                        {
                                            "type": "interrupt",
                                            "interrupt_id": interrupt_id
                                            or str(id(interrupt_info)),
                                            "action_requests": action_requests,
                                            "session_id": session_id,
                                            "thread_id": thread_id,
                                        }
                                    )
                                    logger.info(
                                        f"AgentLoopStreamAPI: Sent interrupt with {len(action_requests)} actions"
                                    )

                            # 检测工具调用开始（用于生成 step_start 事件）
                            elif isinstance(chunk, dict):
                                for node_name, node_output in chunk.items():
                                    if node_name == "agent" and isinstance(
                                        node_output, dict
                                    ):
                                        messages = node_output.get("messages", [])
                                        for msg in messages:
                                            if (
                                                hasattr(msg, "tool_calls")
                                                and msg.tool_calls
                                            ):
                                                # 新的工具调用 -> 新步骤开始
                                                step_count += 1
                                                current_tool_calls = msg.tool_calls
                                                tool_names_in_step = [
                                                    tc.get("name", "unknown")
                                                    if isinstance(tc, dict)
                                                    else getattr(tc, "name", "unknown")
                                                    for tc in current_tool_calls
                                                ]
                                                yield create_sse_data(
                                                    {
                                                        "type": "step_start",
                                                        "step": step_count,
                                                        "max_steps": self.MAX_STEPS,
                                                        "tools": tool_names_in_step,
                                                    }
                                                )
                                                logger.info(
                                                    f"AgentLoopStreamAPI: Step {step_count} started with tools: {tool_names_in_step}"
                                                )

                                    elif node_name == "tools" and isinstance(
                                        node_output, dict
                                    ):
                                        # 工具执行完成
                                        tool_messages = node_output.get("messages", [])
                                        for tool_msg in tool_messages:
                                            if hasattr(tool_msg, "content"):
                                                content = tool_msg.content
                                                tool_name = getattr(
                                                    tool_msg, "name", None
                                                ) or getattr(
                                                    tool_msg, "tool_name", "unknown"
                                                )

                                                # 使用辅助函数处理 MCP 工具输出
                                                content, summary = (
                                                    process_mcp_tool_output(content)
                                                )

                                                yield create_sse_data(
                                                    {
                                                        "type": "tool_result",
                                                        "tool_name": tool_name,
                                                        "tool_output": content,
                                                        "summary": summary,
                                                        "step": step_count,
                                                    }
                                                )
                                        if _tool_messages_need_sanitization(
                                            tool_messages
                                        ):
                                            await _sanitize_history_before_model_call(
                                                agent,
                                                invoke_config,
                                                "AgentLoopStreamAPI[post-tools]",
                                            )
                                        # 步骤完成
                                        if step_count > 0:
                                            yield create_sse_data(
                                                {
                                                    "type": "step_complete",
                                                    "step": step_count,
                                                }
                                            )

                        elif stream_mode == "messages":
                            # LLM Token 流式输出
                            # messages 模式返回元组 (token, metadata)
                            if isinstance(chunk, tuple) and len(chunk) >= 1:
                                token = chunk[0]
                                # 只发送 AI 消息，过滤掉 ToolMessage（工具结果已通过 tool_result 事件发送）
                                if hasattr(token, "content") and token.content:
                                    # 检查是否是 ToolMessage（通过类名或 type 属性）
                                    token_type = type(token).__name__
                                    if "ToolMessage" not in token_type:
                                        yield create_sse_data(
                                            {"type": "stream", "data": token.content}
                                        )
                            elif hasattr(chunk, "content") and chunk.content:
                                # 兼容旧版本可能直接返回 message 的情况
                                # 同样过滤掉 ToolMessage
                                chunk_type = type(chunk).__name__
                                if "ToolMessage" not in chunk_type:
                                    yield create_sse_data(
                                        {"type": "stream", "data": chunk.content}
                                    )

                except Exception as e:
                    friendly_error = get_user_friendly_llm_error(e)
                    if friendly_error:
                        logger.warning(
                            "AgentLoopStreamAPI: Friendly model error. session_id=%s, error_code=%s, message=%s",
                            session_id,
                            friendly_error.get("error_code"),
                            friendly_error.get("message"),
                        )
                        yield create_sse_data(_build_sse_error_event(e))
                    else:
                        logger.error(
                            "AgentLoopStreamAPI: Streaming error. session_id=%s, thread_id=%s, "
                            "model=%s, error_type=%s, error=%s",
                            session_id,
                            thread_id,
                            model_name,
                            type(e).__name__,
                            e,
                            exc_info=True,
                        )
                        yield create_sse_data(
                            {"type": "error", "message": f"Streaming error: {str(e)}"}
                        )

                # 16. 处理结束状态
                # 无论是否发生 interrupt，都需要计算和发送 context_update
                try:
                    current_state = await agent.aget_state(invoke_config)
                    all_messages = (
                        current_state.values.get("messages", [])
                        if current_state.values
                        else []
                    )

                    # 获取当前上下文 token 使用量（优先 usage_metadata，回退估算）
                    input_tokens, output_tokens, total_tokens = (
                        calculate_context_tokens(all_messages, model_name)
                    )

                    yield create_sse_data(
                        {
                            "type": "context_update",
                            "context_token_count": total_tokens,
                            "context_limit": context_limit,
                        }
                    )

                    # 记录 Token 使用量到 ChatSession
                    if input_tokens > 0 or output_tokens > 0:
                        await sync_to_async(self._update_session_token_usage)(
                            session_id, input_tokens, output_tokens
                        )
                        logger.info(
                            f"AgentLoopStreamAPI: Token usage recorded - input={input_tokens}, output={output_tokens}"
                        )
                except Exception as e:
                    logger.warning(
                        f"AgentLoopStreamAPI: Failed to calculate token count: {e}"
                    )

                if user_stopped:
                    yield create_sse_data(
                        {"type": "complete", "status": "stopped", "steps": step_count}
                    )
                elif interrupt_detected:
                    logger.info(
                        "AgentLoopStreamAPI: Interrupt detected, returning early"
                    )
                else:
                    complete_data = {"type": "complete", "total_steps": step_count}
                    if generate_playwright_script:
                        complete_data["script_generation"] = {
                            "enabled": True,
                            "message": "脚本管理工具已启用",
                        }
                    yield create_sse_data(complete_data)

                yield "data: [DONE]\n\n"

        except Exception as e:
            friendly_error = get_user_friendly_llm_error(e)
            if friendly_error:
                logger.warning(
                    "AgentLoopStreamAPI: Friendly model error. session_id=%s, error_code=%s, message=%s",
                    session_id,
                    friendly_error.get("error_code"),
                    friendly_error.get("message"),
                )
                yield create_sse_data(_build_sse_error_event(e))
            else:
                logger.error(
                    "AgentLoopStreamAPI: Error. session_id=%s, thread_id=%s, model=%s, "
                    "error_type=%s, error=%s",
                    session_id,
                    thread_id,
                    model_name if "model_name" in locals() else "unknown",
                    type(e).__name__,
                    e,
                    exc_info=True,
                )
                yield create_sse_data(
                    {"type": "error", "message": f"执行错误: {str(e)}"}
                )

    async def post(self, request, *args, **kwargs):
        """
        处理聊天请求

        支持 stream 参数：
        - stream=true (默认)：返回 SSE 流式响应
        - stream=false：返回普通 JSON 响应
        """
        # 1. 认证
        try:
            user = await self.authenticate_request(request)
            request.user = user
        except AuthenticationFailed as e:
            return api_error_response(str(e), 401)

        # 2. 解析请求
        try:
            body_data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as e:
            return api_error_response(f"Invalid JSON: {e}", 400)

        user_message = body_data.get("message")
        session_id = body_data.get("session_id")
        project_id = body_data.get("project_id")
        knowledge_base_id = body_data.get("knowledge_base_id")
        use_knowledge_base = body_data.get("use_knowledge_base", True)
        prompt_id = body_data.get("prompt_id")

        # 调试日志：知识库参数
        logger.info(
            f"AgentLoopStreamAPI: knowledge_base_id={knowledge_base_id}, use_knowledge_base={use_knowledge_base}"
        )
        uploaded_images_base64 = _normalize_uploaded_image_base64_list(
            body_data.get("images"),
            body_data.get("image"),
        )

        # stream 参数：控制流式/非流式输出（默认 true）
        stream_mode = body_data.get("stream", True)
        if isinstance(stream_mode, str):
            stream_mode = stream_mode.lower() in ("true", "1", "yes")

        # Playwright 脚本生成参数
        generate_playwright_script = body_data.get("generate_playwright_script", False)
        test_case_id = body_data.get("test_case_id")  # 用于关联生成的脚本
        use_pytest = body_data.get("use_pytest", True)  # 生成 pytest 格式还是简单格式

        # 兜底：如果前端没传 test_case_id，尝试从消息中解析
        if not test_case_id and user_message:
            import re

            # 匹配 "执行ID为 11 的测试用例" 或 "测试用例 ID：11" 等模式
            match = re.search(
                r"(?:执行\s*ID\s*为|测试用例\s*(?:ID|id)[：:]\s*|case[_-]?id[：:=]\s*)(\d+)",
                user_message,
            )
            if match:
                test_case_id = int(match.group(1))
                logger.info(
                    f"AgentLoopStreamAPI: Parsed test_case_id from message: {test_case_id}"
                )

        # 3. 参数验证
        if not project_id:
            return api_error_response("project_id is required", 400)

        if not user_message:
            return api_error_response("message is required", 400)

        # 4. 项目权限检查
        project = await sync_to_async(check_project_permission)(
            request.user, project_id
        )
        if not project:
            return api_error_response("Project access denied", 403)

        # 5. 生成 session_id
        if not session_id:
            session_id = uuid.uuid4().hex
            logger.info(f"AgentLoopStreamAPI: Generated new session_id: {session_id}")

        # 5.1 清理陈旧停止信号，避免上一次"停止"残留影响本轮首次发送
        # 场景：前端先断开 SSE，再调用 stop API，可能导致信号留存到下一次请求
        if clear_stop_signal(session_id):
            logger.info(
                f"AgentLoopStreamAPI: Cleared stale stop signal for session {session_id}"
            )

        # 6. 根据 stream 参数决定响应方式
        if stream_mode:
            # 流式响应 (SSE)
            async def async_generator():
                async for chunk in self._create_stream_generator(
                    request,
                    user_message,
                    session_id,
                    project_id,
                    project,
                    knowledge_base_id,
                    use_knowledge_base,
                    prompt_id,
                    uploaded_images_base64,
                    generate_playwright_script,
                    test_case_id,
                    use_pytest,
                ):
                    yield chunk

            response = StreamingHttpResponse(
                async_generator(), content_type="text/event-stream; charset=utf-8"
            )
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response
        else:
            # 非流式响应 (JSON)
            return await self._handle_non_stream_request(
                request,
                user_message,
                session_id,
                project_id,
                project,
                knowledge_base_id,
                use_knowledge_base,
                prompt_id,
                uploaded_images_base64,
                generate_playwright_script,
                test_case_id,
                use_pytest,
            )

    async def _handle_non_stream_request(
        self,
        request,
        user_message: str,
        session_id: str,
        project_id: str,
        project: Project,
        knowledge_base_id: Optional[int] = None,
        use_knowledge_base: bool = True,
        prompt_id: Optional[int] = None,
        uploaded_images_base64: Optional[List[str]] = None,
        generate_playwright_script: bool = False,
        test_case_id: Optional[int] = None,
        use_pytest: bool = True,
    ) -> JsonResponse:
        """
        处理非流式请求，收集所有流式事件后返回统一 JSON 响应
        """
        final_content = ""
        final_session_id = session_id
        tool_results = []
        total_steps = 0
        context_token_count = 0
        context_limit = 128000
        error_message = None
        error_status_code = 500
        error_details = None
        interrupt_info = None
        script_generation = None

        try:
            async for chunk in self._create_stream_generator(
                request,
                user_message,
                session_id,
                project_id,
                project,
                knowledge_base_id,
                use_knowledge_base,
                prompt_id,
                uploaded_images_base64,
                generate_playwright_script,
                test_case_id,
                use_pytest,
            ):
                # 解析 SSE 数据
                if isinstance(chunk, str) and chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        continue
                    try:
                        event = json.loads(data_str)
                        event_type = event.get("type")

                        if event_type == "start":
                            final_session_id = event.get("session_id", session_id)
                        elif event_type == "stream":
                            # 累积流式内容
                            final_content += event.get("data", "")
                        elif event_type == "tool_result":
                            tool_results.append(
                                {
                                    "summary": event.get("summary", ""),
                                    "tool_output": event.get("tool_output"),
                                    "tool_name": event.get("tool_name"),
                                    "step": event.get("step", 0),
                                }
                            )
                        elif event_type == "step_complete":
                            total_steps = max(total_steps, event.get("step", 0))
                        elif event_type == "context_update":
                            context_token_count = event.get("context_token_count", 0)
                            context_limit = event.get("context_limit", 128000)
                        elif event_type == "error":
                            error_message = event.get("message", "Unknown error")
                            error_status_code = event.get("code", 500)
                            error_details = event.get("errors")
                        elif event_type == "interrupt":
                            interrupt_info = {
                                "interrupt_id": event.get("interrupt_id"),
                                "action_requests": event.get("action_requests", []),
                            }
                        elif event_type == "complete":
                            if event.get("script_generation"):
                                script_generation = event.get("script_generation")
                    except json.JSONDecodeError:
                        continue

            # 构建响应
            if error_message:
                return api_error_response(
                    error_message, error_status_code, error_details
                )

            response_data = {
                "session_id": final_session_id,
                "content": final_content,
                "total_steps": total_steps,
                "tool_results": tool_results,
                "context_token_count": context_token_count,
                "context_limit": context_limit,
                "knowledge_base_used": any(
                    (tool_result.get("tool_name") == "knowledge_search")
                    for tool_result in tool_results
                ),
            }

            if interrupt_info:
                response_data["interrupt"] = interrupt_info

            if script_generation:
                response_data["script_generation"] = script_generation

            return api_success_response("Chat completed", response_data)

        except Exception as e:
            logger.error(
                "AgentLoopStreamAPI: Non-stream request error. session_id=%s, project_id=%s, "
                "error_type=%s, error=%s",
                session_id,
                project_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            friendly_error = get_user_friendly_llm_error(e)
            if friendly_error:
                return api_error_response(
                    friendly_error["message"],
                    friendly_error["status_code"],
                    friendly_error["errors"],
                )
            return api_error_response(f"执行错误: {str(e)}", 500)


@method_decorator(csrf_exempt, name="dispatch")
class AgentLoopStopAPIView(View):
    """
    Agent Loop 停止 API

    用于中断正在执行的 Agent Loop 任务。
    """

    async def authenticate_request(self, request):
        """JWT 认证（复用 AgentLoopStreamAPIView 的逻辑）"""
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Authentication credentials were not provided.")

        token = auth_header.split(" ")[1]
        jwt_auth = JWTAuthentication()

        try:
            validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
            user = await sync_to_async(jwt_auth.get_user)(validated_token)
            return user
        except Exception as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}")

    async def post(self, request, *args, **kwargs):
        """处理停止请求"""
        from .stop_signal import set_stop_signal

        # 1. 认证
        try:
            user = await self.authenticate_request(request)
            request.user = user
        except AuthenticationFailed as e:
            return api_error_response(str(e), 401)

        # 2. 解析请求
        try:
            body_data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as e:
            return api_error_response(f"Invalid JSON: {e}", 400)

        session_id = body_data.get("session_id")
        if not session_id:
            return api_error_response("session_id is required", 400)

        # 3. 设置停止信号
        success = set_stop_signal(session_id)

        logger.info(
            f"AgentLoopStopAPI: Stop signal set for session {session_id} by user {user.id}"
        )

        return api_success_response(
            "已发送停止信号", {"session_id": session_id, "success": success}
        )


@method_decorator(csrf_exempt, name="dispatch")
class AgentLoopResumeAPIView(View):
    """
    Agent Loop Resume API (SSE 流式版)

    用于恢复被 HITL 中断的 Agent Loop 任务。
    接收用户对工具调用的审批决策，然后通过 SSE 流式返回后续执行结果。

    这样前端可以像处理主流一样处理 resume 后的工具执行和 LLM 响应。
    """

    # 最大步骤数（与主流保持一致）
    MAX_STEPS = 500

    async def authenticate_request(self, request):
        """JWT 认证（复用 AgentLoopStreamAPIView 的逻辑）"""
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Authentication credentials were not provided.")

        token = auth_header.split(" ")[1]
        jwt_auth = JWTAuthentication()

        try:
            validated_token = await sync_to_async(jwt_auth.get_validated_token)(token)
            user = await sync_to_async(jwt_auth.get_user)(validated_token)
            return user
        except Exception as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}")

    async def _create_resume_stream_generator(
        self,
        user,
        session_id: str,
        project_id: str,
        resume_data: dict,
        knowledge_base_id: Optional[str] = None,
        use_knowledge_base: bool = False,
    ):
        """
        创建 Resume SSE 流式生成器

        与主流的 _create_stream_generator 类似，但使用 Command(resume=...) 来恢复执行。
        """
        from langgraph.types import Command

        # 1. 解析 resume 数据
        interrupt_id = list(resume_data.keys())[0] if resume_data else None
        if not interrupt_id:
            yield create_sse_data(
                {"type": "error", "message": "Invalid resume data format"}
            )
            return

        decision_info = resume_data[interrupt_id].get("decisions", [{}])[0]
        decision_type = decision_info.get("type", "reject")

        # 获取工具调用数量（前端传递）
        action_count = resume_data[interrupt_id].get("action_count", 1)

        # 构建 resume 值 - HITL middleware 需要 decisions 格式
        # 为每个 pending 工具调用生成相同的决策
        resume_value = {
            "decisions": [{"type": decision_type} for _ in range(action_count)]
        }

        # 2. 发送 resume 开始信号
        yield create_sse_data(
            {
                "type": "resume_start",
                "session_id": session_id,
                "decision": decision_type,
            }
        )

        try:
            async with get_async_checkpointer() as checkpointer:
                # 3. 获取 LLM 配置
                active_config = await sync_to_async(
                    LLMConfig.objects.filter(is_active=True).first
                )()

                if not active_config:
                    yield create_sse_data(
                        {"type": "error", "message": "没有可用的 LLM 配置"}
                    )
                    return

                context_limit = active_config.context_limit or 128000
                model_name = active_config.name or "gpt-4o"
                llm = await sync_to_async(create_llm_instance)(active_config)
                context_limit = resolve_runtime_context_limit(
                    active_config.context_limit, llm, model_name
                )

                # 4. 加载工具
                tools = []

                # 加载 MCP 工具
                try:
                    active_mcp_configs = await sync_to_async(list)(
                        RemoteMCPConfig.objects.filter(is_active=True)
                    )
                    if active_mcp_configs:
                        client_config = {}
                        for cfg in active_mcp_configs:
                            key = cfg.name or f"remote_{cfg.id}"
                            client_config[key] = {
                                "url": cfg.url,
                                "transport": (
                                    cfg.transport or "streamable_http"
                                ).replace("-", "_"),
                            }
                            if cfg.headers:
                                client_config[key]["headers"] = cfg.headers

                        if client_config:
                            mcp_tools = await mcp_session_manager.get_tools_for_config(
                                client_config,
                                user_id=str(user.id),
                                project_id=str(project_id) if project_id else "0",
                                session_id=session_id,
                            )
                            tools.extend(mcp_tools)
                            logger.info(
                                f"AgentLoopResumeAPI: Loaded {len(mcp_tools)} MCP tools"
                            )
                except Exception as e:
                    logger.warning(f"AgentLoopResumeAPI: MCP tools loading failed: {e}")

                # 加载知识库工具
                if knowledge_base_id and use_knowledge_base:
                    try:
                        from knowledge.langgraph_integration import (
                            create_knowledge_tool,
                        )

                        kb_tool = await sync_to_async(create_knowledge_tool)(
                            knowledge_base_id=knowledge_base_id, user=user
                        )
                        tools.append(kb_tool)
                        logger.info(
                            f"AgentLoopResumeAPI: ✅ 知识库工具已添加: {kb_tool.name}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"AgentLoopResumeAPI: ❌ Knowledge tool creation failed: {e}"
                        )

                # 加载内置工具
                try:
                    from orchestrator_integration.builtin_tools import get_builtin_tools

                    builtin_tools = get_builtin_tools(
                        user_id=user.id,
                        project_id=int(project_id) if project_id else 0,
                        test_case_id=None,
                        chat_session_id=session_id,
                    )
                    tools.extend(builtin_tools)
                    logger.info(
                        f"AgentLoopResumeAPI: Added {len(builtin_tools)} builtin tools"
                    )
                except Exception as e:
                    logger.warning(
                        f"AgentLoopResumeAPI: Builtin tools loading failed: {e}"
                    )

                # 5. 获取工具名列表和中间件配置
                tool_names = [t.name for t in tools] if tools else []
                middleware = await sync_to_async(get_middleware_from_config)(
                    active_config,
                    llm,
                    user=user,
                    session_id=session_id,
                    all_tool_names=tool_names,
                )

                # 6. 创建 agent
                agent = create_agent(
                    llm,
                    tools,
                    checkpointer=checkpointer,
                    middleware=middleware,
                )

                thread_id = (
                    f"{user.id}_{project_id}_{session_id}" if project_id else session_id
                )
                config = {
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": 1000,
                }

                # 6.1 恢复执行前，先修复历史消息（配对错误 + 风险工具输出）
                await _sanitize_history_before_model_call(
                    agent=agent,
                    invoke_config=config,
                    log_prefix="AgentLoopResumeAPI",
                )

                # 7. 构建 Command 来 resume
                command = Command(resume=resume_value)

                # 8. 步骤跟踪状态
                step_count = 0
                interrupt_detected = False

                # 9. 流式执行
                try:
                    async for stream_mode, chunk in agent.astream(
                        command, config=config, stream_mode=["updates", "messages"]
                    ):
                        if stream_mode == "updates":
                            # 检查中断事件 (HITL) - resume 后可能又触发新的中断
                            if isinstance(chunk, dict) and "__interrupt__" in chunk:
                                interrupt_info = chunk["__interrupt__"]
                                logger.info(
                                    f"AgentLoopResumeAPI: HITL interrupt detected after resume: {interrupt_info}"
                                )

                                action_requests = []
                                new_interrupt_id = None

                                if isinstance(interrupt_info, (list, tuple)):
                                    interrupts_list = list(interrupt_info)
                                else:
                                    interrupts_list = [interrupt_info]

                                for intr in interrupts_list:
                                    if hasattr(intr, "id"):
                                        new_interrupt_id = intr.id
                                    elif isinstance(intr, dict) and "id" in intr:
                                        new_interrupt_id = intr["id"]

                                    intr_value = (
                                        getattr(intr, "value", intr)
                                        if hasattr(intr, "value")
                                        else intr
                                    )
                                    if isinstance(intr_value, dict):
                                        ars = intr_value.get("action_requests", [])
                                    elif hasattr(intr_value, "action_requests"):
                                        ars = intr_value.action_requests
                                    else:
                                        ars = []

                                    for ar in ars:
                                        if isinstance(ar, dict):
                                            action_requests.append(
                                                {
                                                    "name": ar.get(
                                                        "name",
                                                        ar.get(
                                                            "action_name", "unknown"
                                                        ),
                                                    ),
                                                    "args": ar.get(
                                                        "arguments", ar.get("args", {})
                                                    ),
                                                    "description": ar.get(
                                                        "description", ""
                                                    ),
                                                }
                                            )
                                        else:
                                            action_requests.append(
                                                {
                                                    "name": getattr(
                                                        ar, "name", "unknown"
                                                    ),
                                                    "args": getattr(
                                                        ar,
                                                        "arguments",
                                                        getattr(ar, "args", {}),
                                                    ),
                                                    "description": getattr(
                                                        ar, "description", ""
                                                    ),
                                                }
                                            )

                                if action_requests:
                                    # 获取用户工具偏好，为 always_reject 的工具添加 auto_reject 标记
                                    user_approvals = await sync_to_async(
                                        get_user_tool_approvals
                                    )(user, session_id)
                                    for ar in action_requests:
                                        tool_name = ar.get("name", "")
                                        if (
                                            user_approvals.get(tool_name)
                                            == "always_reject"
                                        ):
                                            ar["auto_reject"] = True
                                            logger.info(
                                                f"AgentLoopResumeAPI: Tool {tool_name} marked as auto_reject"
                                            )

                                    interrupt_detected = True
                                    yield create_sse_data(
                                        {
                                            "type": "interrupt",
                                            "interrupt_id": new_interrupt_id
                                            or str(id(interrupt_info)),
                                            "action_requests": action_requests,
                                            "session_id": session_id,
                                            "thread_id": thread_id,
                                        }
                                    )

                            # 检测工具调用开始
                            elif isinstance(chunk, dict):
                                for node_name, node_output in chunk.items():
                                    if node_name == "agent" and isinstance(
                                        node_output, dict
                                    ):
                                        messages = node_output.get("messages", [])
                                        for msg in messages:
                                            if (
                                                hasattr(msg, "tool_calls")
                                                and msg.tool_calls
                                            ):
                                                step_count += 1
                                                tool_names_in_step = [
                                                    tc.get("name", "unknown")
                                                    if isinstance(tc, dict)
                                                    else getattr(tc, "name", "unknown")
                                                    for tc in msg.tool_calls
                                                ]
                                                yield create_sse_data(
                                                    {
                                                        "type": "step_start",
                                                        "step": step_count,
                                                        "max_steps": self.MAX_STEPS,
                                                        "tools": tool_names_in_step,
                                                    }
                                                )

                                    elif node_name == "tools" and isinstance(
                                        node_output, dict
                                    ):
                                        tool_messages = node_output.get("messages", [])
                                        for tool_msg in tool_messages:
                                            if hasattr(tool_msg, "content"):
                                                content = tool_msg.content
                                                tool_name = getattr(
                                                    tool_msg, "name", None
                                                ) or getattr(
                                                    tool_msg, "tool_name", "unknown"
                                                )

                                                # 使用辅助函数处理 MCP 工具输出
                                                content, summary = (
                                                    process_mcp_tool_output(content)
                                                )

                                                yield create_sse_data(
                                                    {
                                                        "type": "tool_result",
                                                        "tool_name": tool_name,
                                                        "tool_output": content,
                                                        "summary": summary,
                                                        "step": step_count,
                                                    }
                                                )
                                        if _tool_messages_need_sanitization(
                                            tool_messages
                                        ):
                                            await _sanitize_history_before_model_call(
                                                agent,
                                                config,
                                                "AgentLoopResumeAPI[post-tools]",
                                            )
                                        if step_count > 0:
                                            yield create_sse_data(
                                                {
                                                    "type": "step_complete",
                                                    "step": step_count,
                                                }
                                            )

                        elif stream_mode == "messages":
                            # LLM Token 流式输出
                            # messages 模式返回元组 (token, metadata)
                            if isinstance(chunk, tuple) and len(chunk) >= 1:
                                token = chunk[0]
                                # 只发送 AI 消息，过滤掉 ToolMessage（工具结果已通过 tool_result 事件发送）
                                if hasattr(token, "content") and token.content:
                                    # 检查是否是 ToolMessage（通过类名或 type 属性）
                                    token_type = type(token).__name__
                                    if "ToolMessage" not in token_type:
                                        yield create_sse_data(
                                            {"type": "stream", "data": token.content}
                                        )
                            elif hasattr(chunk, "content") and chunk.content:
                                # 兼容旧版本可能直接返回 message 的情况
                                # 同样过滤掉 ToolMessage
                                chunk_type = type(chunk).__name__
                                if "ToolMessage" not in chunk_type:
                                    yield create_sse_data(
                                        {"type": "stream", "data": chunk.content}
                                    )

                except Exception as e:
                    friendly_error = get_user_friendly_llm_error(e)
                    if friendly_error:
                        logger.warning(
                            "AgentLoopResumeAPI: Friendly model error. session_id=%s, error_code=%s, message=%s",
                            session_id,
                            friendly_error.get("error_code"),
                            friendly_error.get("message"),
                        )
                        yield create_sse_data(_build_sse_error_event(e))
                    else:
                        logger.error(
                            "AgentLoopResumeAPI: Streaming error: %s", e, exc_info=True
                        )
                        yield create_sse_data(
                            {"type": "error", "message": f"Streaming error: {str(e)}"}
                        )

                # 10. 处理结束状态
                # 无论是否发生 interrupt，都需要计算和发送 context_update
                try:
                    current_state = await agent.aget_state(config)
                    all_messages = (
                        current_state.values.get("messages", [])
                        if current_state.values
                        else []
                    )

                    # 获取当前上下文 token 使用量（优先 usage_metadata，回退估算）
                    input_tokens, output_tokens, total_tokens = (
                        calculate_context_tokens(all_messages, model_name)
                    )

                    yield create_sse_data(
                        {
                            "type": "context_update",
                            "context_token_count": total_tokens,
                            "context_limit": context_limit,
                        }
                    )

                    # 记录 Token 使用量到 ChatSession
                    if input_tokens > 0 or output_tokens > 0:
                        await sync_to_async(
                            AgentLoopStreamAPIView()._update_session_token_usage
                        )(session_id, input_tokens, output_tokens)
                        logger.info(
                            f"AgentLoopResumeAPI: Token usage recorded - input={input_tokens}, output={output_tokens}"
                        )
                except Exception as e:
                    logger.warning(
                        f"AgentLoopResumeAPI: Failed to calculate token count: {e}"
                    )

                if interrupt_detected:
                    logger.info(
                        "AgentLoopResumeAPI: New interrupt detected after resume"
                    )
                else:
                    yield create_sse_data(
                        {
                            "type": "complete",
                            "total_steps": step_count,
                            "decision": decision_type,
                        }
                    )

                yield "data: [DONE]\n\n"

        except Exception as e:
            friendly_error = get_user_friendly_llm_error(e)
            if friendly_error:
                logger.warning(
                    "AgentLoopResumeAPI: Friendly model error. session_id=%s, error_code=%s, message=%s",
                    session_id,
                    friendly_error.get("error_code"),
                    friendly_error.get("message"),
                )
                yield create_sse_data(_build_sse_error_event(e))
            else:
                logger.exception(
                    "AgentLoopResumeAPI: Error in resume stream for session %s",
                    session_id,
                )
                yield create_sse_data({"type": "error", "message": str(e)})

    async def post(self, request, *args, **kwargs):
        """处理 HITL resume 请求 - 返回 SSE 流式响应"""
        # 1. 认证
        try:
            user = await self.authenticate_request(request)
            request.user = user
        except AuthenticationFailed as e:
            return StreamingHttpResponse(
                iter(
                    [create_sse_data({"type": "error", "message": str(e), "code": 401})]
                ),
                content_type="text/event-stream; charset=utf-8",
                status=401,
            )

        # 2. 解析请求
        try:
            body_data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError as e:
            return StreamingHttpResponse(
                iter(
                    [
                        create_sse_data(
                            {
                                "type": "error",
                                "message": f"Invalid JSON: {e}",
                                "code": 400,
                            }
                        )
                    ]
                ),
                content_type="text/event-stream; charset=utf-8",
                status=400,
            )

        session_id = body_data.get("session_id")
        project_id = body_data.get("project_id")
        resume_data = body_data.get("resume", {})
        # 知识库参数（用于 resume 时重新加载知识库工具）
        knowledge_base_id = body_data.get("knowledge_base_id")
        use_knowledge_base = body_data.get("use_knowledge_base", False)

        if not session_id:
            return StreamingHttpResponse(
                iter(
                    [
                        create_sse_data(
                            {
                                "type": "error",
                                "message": "session_id is required",
                                "code": 400,
                            }
                        )
                    ]
                ),
                content_type="text/event-stream; charset=utf-8",
                status=400,
            )

        if not resume_data:
            return StreamingHttpResponse(
                iter(
                    [
                        create_sse_data(
                            {
                                "type": "error",
                                "message": "resume data is required",
                                "code": 400,
                            }
                        )
                    ]
                ),
                content_type="text/event-stream; charset=utf-8",
                status=400,
            )

        logger.info(
            f"AgentLoopResumeAPI: Resume request for session {session_id}, knowledge_base_id={knowledge_base_id}"
        )

        # 3. 返回 SSE 流式响应
        async def async_generator():
            async for chunk in self._create_resume_stream_generator(
                user,
                session_id,
                project_id,
                resume_data,
                knowledge_base_id,
                use_knowledge_base,
            ):
                yield chunk

        response = StreamingHttpResponse(
            async_generator(), content_type="text/event-stream; charset=utf-8"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

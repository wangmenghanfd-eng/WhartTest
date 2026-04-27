"""UI 自动化录制解析与落库服务。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from projects.models import Project

from .models import (
    UiCaseStepsDetailed,
    UiElement,
    UiModule,
    UiPage,
    UiPageSteps,
    UiPageStepsDetailed,
    UiPublicData,
    UiRecordingSession,
    UiTestCase,
)


_JS_STRING_PATTERN = r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
_GOTO_RE = re.compile(rf"await\s+page\.goto\(\s*(?P<url>{_JS_STRING_PATTERN})", re.IGNORECASE)
_WAIT_FOR_URL_RE = re.compile(rf"await\s+page\.waitForURL\(\s*(?P<url>{_JS_STRING_PATTERN})", re.IGNORECASE)
_WAIT_FOR_SELECTOR_RE = re.compile(
    rf"await\s+page\.waitForSelector\(\s*(?P<selector>{_JS_STRING_PATTERN})",
    re.IGNORECASE,
)
_TARGET_ACTION_RE = re.compile(
    r"await\s+(?P<target>.+?)\.(?P<op>dblclick|click|fill|press|selectOption|check|uncheck|hover|focus|clear)\((?P<args>.*)\)\s*;?$",
    re.IGNORECASE,
)
_EXPECT_PAGE_RE = re.compile(
    r"await\s+expect\(page\)\.(?P<assertion>toHaveURL|toHaveTitle)\((?P<args>.*)\)\s*;?$",
    re.IGNORECASE,
)
_EXPECT_TARGET_RE = re.compile(
    r"await\s+expect\((?P<target>.+?)\)\.(?P<assertion>toBeVisible|toBeHidden|toContainText|toHaveText|toHaveValue)\((?P<args>.*)\)\s*;?$",
    re.IGNORECASE,
)
_LOCATOR_RE = re.compile(rf"page\.locator\(\s*(?P<selector>{_JS_STRING_PATTERN})", re.IGNORECASE)
_LABEL_RE = re.compile(rf"page\.getByLabel\(\s*(?P<label>{_JS_STRING_PATTERN})", re.IGNORECASE)
_TEXT_RE = re.compile(rf"page\.getByText\(\s*(?P<text>{_JS_STRING_PATTERN})", re.IGNORECASE)
_PLACEHOLDER_RE = re.compile(
    rf"page\.getByPlaceholder\(\s*(?P<placeholder>{_JS_STRING_PATTERN})",
    re.IGNORECASE,
)
_TESTID_RE = re.compile(rf"page\.getByTestId\(\s*(?P<testid>{_JS_STRING_PATTERN})", re.IGNORECASE)
_ROLE_RE = re.compile(
    rf"page\.getByRole\(\s*(?P<role>{_JS_STRING_PATTERN})(?:\s*,\s*\{{(?P<options>.*?)\}}\s*)?\)",
    re.IGNORECASE,
)
_ROLE_NAME_RE = re.compile(rf"name\s*:\s*(?P<name>{_JS_STRING_PATTERN})", re.IGNORECASE)


@dataclass
class PageSegment:
    """按导航边界切分后的页面步骤候选。"""

    index: int
    url_hint: str = ""
    actions: List[Dict[str, Any]] = None

    def __post_init__(self):
        if self.actions is None:
            self.actions = []


def _decode_js_string(raw_value: str) -> str:
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return ""
    try:
        value = ast.literal_eval(raw_value)
        return value if isinstance(value, str) else str(value)
    except Exception:
        return raw_value.strip("'\"")


def _split_args(raw_args: str) -> List[str]:
    raw_args = (raw_args or "").strip()
    if not raw_args:
        return []
    parts: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    depth = 0
    escaped = False
    for char in raw_args:
        if escaped:
            buf.append(char)
            escaped = False
            continue
        if char == "\\":
            buf.append(char)
            escaped = True
            continue
        if quote:
            buf.append(char)
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            buf.append(char)
            continue
        if char in "([{":
            depth += 1
            buf.append(char)
            continue
        if char in ")]}":
            depth = max(depth - 1, 0)
            buf.append(char)
            continue
        if char == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue
        buf.append(char)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("**/"):
        return "/" + url[3:].lstrip("/")
    if url.startswith("*/"):
        return "/" + url[2:].lstrip("/")
    return url


def _join_base_url(base_url: str, path: str) -> str:
    base_url = (base_url or "").strip().rstrip("/")
    path = (path or "").strip()
    if not base_url or not path.startswith("/"):
        return ""
    return f"{base_url}{path}"


def _relative_to_base_url(url: str, base_url: str = "") -> str:
    """把与环境 base_url 同源的 URL 存成相对路径，便于切换环境。"""
    normalized = _normalize_url(url)
    if not normalized or normalized.startswith("/"):
        return normalized
    if not normalized.startswith(("http://", "https://")):
        return normalized

    parsed = urlparse(normalized)
    base = urlparse((base_url or "").strip())
    if base.scheme and base.netloc and parsed.scheme == base.scheme and parsed.netloc == base.netloc:
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        fragment = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{path}{query}{fragment}"
    return normalized


def _resolve_page_name(url: str, fallback_name: str = "") -> str:
    normalized = _normalize_url(url)
    path = ""
    if normalized.startswith("/"):
        path = normalized.split("?", 1)[0].split("#", 1)[0].strip("/") or "home"
    if normalized.startswith(("http://", "https://")):
        parsed = urlparse(normalized)
        path = parsed.path.strip("/") or "home"
    path_key = path.strip("/").lower()
    friendly_names = {
        "": "首页",
        "home": "首页",
        "login": "登录页",
        "secure": "安全区域页",
        "register": "注册页",
        "logout": "退出登录页",
    }
    if path_key in friendly_names:
        return friendly_names[path_key]
    if path:
        return path[:64]
    return fallback_name[:64] if fallback_name else f"录制页面-{timezone.now().strftime('%H%M%S')}"


def _should_update_page_name(existing_name: str, suggested_name: str) -> bool:
    if not suggested_name or existing_name == suggested_name:
        return False
    normalized = (existing_name or "").strip().lower()
    return normalized in {"login", "secure", "home", "index"} or "/" in normalized or "." in normalized


def _infer_locator(selector: str) -> Tuple[str, str]:
    selector = (selector or "").strip()
    if selector.startswith("#") and re.fullmatch(r"#[A-Za-z0-9_-]+", selector):
        return "id", selector[1:]
    name_match = re.fullmatch(r"\[name=['\"]([^'\"]+)['\"]\]", selector)
    if name_match:
        return "name", name_match.group(1)
    if selector.startswith("xpath="):
        return "xpath", selector[len("xpath=") :]
    if selector.startswith("//"):
        return "xpath", selector
    if selector.startswith("text="):
        return "text", selector[len("text=") :]
    return "css", selector


def _selector_display_name(locator_type: str, locator_value: str) -> str:
    locator_value_lower = (locator_value or "").lower()
    if "username" in locator_value_lower:
        return "用户名输入框"
    if "password" in locator_value_lower:
        return "密码输入框"
    if "submit" in locator_value_lower or "login" in locator_value_lower:
        return "登录按钮"
    if "logout" in locator_value_lower:
        return "退出登录入口"
    if locator_type == "label":
        return f"标签-{locator_value[:30]}"
    if locator_type == "placeholder":
        return f"占位符-{locator_value[:30]}"
    if locator_type == "text":
        return f"文本-{locator_value[:30]}"
    return f"元素-{locator_value[:30]}"


def _replace_with_public_data(project: Project, value: str) -> str:
    if not value:
        return value
    allowed_key = re.compile(r"(^|_)(username|password|account|email|phone|token)(_|$)", re.IGNORECASE)
    noisy_key = re.compile(r"(wrong|invalid|error|fail|negative|temp|random|auto|case)", re.IGNORECASE)
    public_data = UiPublicData.objects.filter(
        project=project,
        is_enabled=True,
        value=value,
    ).order_by("key").first()
    if public_data and allowed_key.search(public_data.key) and not noisy_key.search(public_data.key):
        return f"${{{{{public_data.key}}}}}"
    return value


def _parse_target_locator(target: str) -> Optional[Dict[str, Any]]:
    target = (target or "").strip()
    if not target:
        return None

    match = _LOCATOR_RE.search(target)
    if match:
        selector = _decode_js_string(match.group("selector"))
        locator_type, locator_value = _infer_locator(selector)
        return {
            "selector": selector,
            "locator_type": locator_type,
            "locator_value": locator_value,
            "source": "locator",
        }

    match = _LABEL_RE.search(target)
    if match:
        value = _decode_js_string(match.group("label"))
        return {"selector": value, "locator_type": "label", "locator_value": value, "source": "label"}

    match = _TEXT_RE.search(target)
    if match:
        value = _decode_js_string(match.group("text"))
        return {"selector": value, "locator_type": "text", "locator_value": value, "source": "text"}

    match = _PLACEHOLDER_RE.search(target)
    if match:
        value = _decode_js_string(match.group("placeholder"))
        return {
            "selector": value,
            "locator_type": "placeholder",
            "locator_value": value,
            "source": "placeholder",
        }

    match = _TESTID_RE.search(target)
    if match:
        value = _decode_js_string(match.group("testid"))
        return {"selector": value, "locator_type": "test_id", "locator_value": value, "source": "testid"}

    match = _ROLE_RE.search(target)
    if match:
        role = _decode_js_string(match.group("role"))
        options = match.group("options") or ""
        name_match = _ROLE_NAME_RE.search(options)
        name = _decode_js_string(name_match.group("name")) if name_match else ""
        if name:
            return {
                "selector": name,
                "locator_type": "text",
                "locator_value": name,
                "source": "role_name",
                "role": role,
            }
        return {
            "selector": role,
            "locator_type": "role",
            "locator_value": role,
            "source": "role",
        }

    return None


def _build_description(operation: str, locator: Optional[Dict[str, Any]] = None, value: str = "") -> str:
    selector_name = (
        _selector_display_name(locator["locator_type"], locator["locator_value"])
        if locator
        else ""
    )
    if operation == "goto":
        return f"打开页面: {value}"
    if operation in {"fill", "type"}:
        return f"输入 {selector_name}"
    if operation in {"click", "dblclick", "hover", "focus", "check", "uncheck"}:
        return f"{operation} {selector_name}"
    if operation == "press":
        return f"按键 {value} -> {selector_name}"
    if operation == "select":
        return f"选择 {selector_name}"
    if operation == "assert_visible":
        return f"断言 {selector_name} 可见"
    if operation == "assert_hidden":
        return f"断言 {selector_name} 隐藏"
    if operation == "assert_contain_text":
        return f"断言 {selector_name} 包含文本"
    if operation == "assert_text":
        return f"断言 {selector_name} 文本"
    if operation == "assert_url":
        return f"断言页面地址匹配 {value}"
    if operation == "assert_title":
        return f"断言页面标题匹配 {value}"
    return f"{operation} {selector_name or value}".strip()


def parse_playwright_recording(raw_script: str) -> Dict[str, Any]:
    """将 playwright codegen 产物解析为归一化动作。"""
    raw_lines: List[Dict[str, Any]] = []
    normalized_actions: List[Dict[str, Any]] = []
    unsupported_lines: List[str] = []

    for index, original_line in enumerate((raw_script or "").splitlines(), start=1):
        line = original_line.strip()
        if not line:
            continue
        raw_lines.append({"line_no": index, "content": line})

        if line.startswith(("import ", "const ", "async ", "});", "})", "await browser.close()", "const browser", "const page", "const context")):
            continue

        match = _GOTO_RE.search(line)
        if match:
            url = _decode_js_string(match.group("url"))
            normalized_actions.append(
                {
                    "line_no": index,
                    "operation": "goto",
                    "value": url,
                    "description": _build_description("goto", value=url),
                }
            )
            continue

        match = _WAIT_FOR_URL_RE.search(line)
        if match:
            url = _decode_js_string(match.group("url"))
            normalized_actions.append(
                {
                    "line_no": index,
                    "operation": "assert_url",
                    "value": _normalize_url(url),
                    "description": _build_description("assert_url", value=_normalize_url(url)),
                }
            )
            continue

        match = _WAIT_FOR_SELECTOR_RE.search(line)
        if match:
            selector = _decode_js_string(match.group("selector"))
            locator = _parse_target_locator(f"page.locator({selector!r})")
            normalized_actions.append(
                {
                    "line_no": index,
                    "operation": "assert_visible",
                    "selector": selector,
                    "locator_type": locator["locator_type"],
                    "locator_value": locator["locator_value"],
                    "description": _build_description("assert_visible", locator),
                }
            )
            continue

        match = _EXPECT_PAGE_RE.search(line)
        if match:
            assertion = match.group("assertion")
            args = _split_args(match.group("args"))
            value = _decode_js_string(args[0]) if args else ""
            op = "assert_url" if assertion.lower() == "tohaveurl" else "assert_title"
            normalized_actions.append(
                {
                    "line_no": index,
                    "operation": op,
                    "value": _normalize_url(value) if op == "assert_url" else value,
                    "description": _build_description(op, value=_normalize_url(value) if op == "assert_url" else value),
                }
            )
            continue

        match = _EXPECT_TARGET_RE.search(line)
        if match:
            locator = _parse_target_locator(match.group("target"))
            if not locator:
                unsupported_lines.append(line)
                continue
            args = _split_args(match.group("args"))
            value = _decode_js_string(args[0]) if args else ""
            assertion = match.group("assertion").lower()
            op_map = {
                "tobevisible": "assert_visible",
                "tobehidden": "assert_hidden",
                "tocontaintext": "assert_contain_text",
                "tohavetext": "assert_text",
                "tohavevalue": "assert_value",
            }
            operation = op_map.get(assertion)
            if not operation:
                unsupported_lines.append(line)
                continue
            payload: Dict[str, Any] = {
                "line_no": index,
                "operation": operation,
                "selector": locator["selector"],
                "locator_type": locator["locator_type"],
                "locator_value": locator["locator_value"],
                "description": _build_description(operation, locator, value=value),
            }
            if value:
                payload["value"] = value
            normalized_actions.append(payload)
            continue

        match = _TARGET_ACTION_RE.search(line)
        if match:
            locator = _parse_target_locator(match.group("target"))
            operation = match.group("op")
            args = _split_args(match.group("args"))
            value = _decode_js_string(args[0]) if args else ""
            if not locator:
                unsupported_lines.append(line)
                continue
            payload: Dict[str, Any] = {
                "line_no": index,
                "operation": "select" if operation == "selectOption" else operation,
                "selector": locator["selector"],
                "locator_type": locator["locator_type"],
                "locator_value": locator["locator_value"],
                "description": _build_description("select" if operation == "selectOption" else operation, locator, value=value),
            }
            if value:
                payload["value"] = value
            normalized_actions.append(payload)
            continue

        if line.startswith("await "):
            unsupported_lines.append(line)

    return {
        "raw_actions": raw_lines,
        "normalized_actions": normalized_actions,
        "unsupported_lines": unsupported_lines,
    }


def _build_segments(actions: Iterable[Dict[str, Any]]) -> List[PageSegment]:
    segments: List[PageSegment] = []
    current = PageSegment(index=1)
    boundary_ops = {"goto", "assert_url"}

    for action in actions:
        if action["operation"] in boundary_ops and current.actions:
            segments.append(current)
            current = PageSegment(index=len(segments) + 1)
        current.actions.append(action)
        if action["operation"] in {"goto", "assert_url"} and action.get("value"):
            current.url_hint = str(action["value"])

    if current.actions:
        segments.append(current)
    return segments


def _build_preview_payload(
    *,
    session: UiRecordingSession,
    normalized_actions: List[Dict[str, Any]],
    unsupported_lines: List[str],
    final_url: str = "",
) -> Dict[str, Any]:
    segments = _build_segments(normalized_actions) if session.target_type == "test_case" else [
        PageSegment(index=1, url_hint=final_url or session.base_url or (session.page.url if session.page_id and session.page else ""), actions=normalized_actions)
    ]

    preview_steps = []
    for segment in segments:
        resolved_url = _relative_to_base_url(
            segment.url_hint or final_url or session.base_url or "",
            session.base_url or "",
        )
        preview_steps.append(
            {
                "index": segment.index,
                "name": f"{session.name}-步骤{segment.index}" if session.target_type == "test_case" else session.name,
                "page_name": session.page.name if session.page_id and session.target_type == "page_step" else _resolve_page_name(resolved_url, session.name),
                "url": resolved_url,
                "action_count": len(segment.actions),
                "actions": segment.actions,
            }
        )

    return {
        "target_type": session.target_type,
        "unsupported_lines": unsupported_lines,
        "warnings": (
            [f"存在 {len(unsupported_lines)} 条暂不支持的录制语句，已保留在原始脚本中。"]
            if unsupported_lines
            else []
        ),
        "summary": {
            "raw_action_count": len(normalized_actions),
            "unsupported_count": len(unsupported_lines),
            "segment_count": len(preview_steps),
        },
        "page_steps": preview_steps,
        "test_case": (
            {
                "name": session.name,
                "step_count": len(preview_steps),
            }
            if session.target_type == "test_case"
            else None
        ),
    }


@transaction.atomic
def apply_recording_result(
    *,
    recording_id: int,
    raw_script: str,
    artifacts: Optional[Dict[str, Any]] = None,
    final_url: str = "",
    error_message: str = "",
    cancelled: bool = False,
) -> UiRecordingSession:
    session = UiRecordingSession.objects.select_related("page", "module", "project").get(id=recording_id)
    artifacts = artifacts or {}
    session.raw_script = raw_script or ""
    session.artifacts = artifacts
    session.ended_at = timezone.now()
    session.duration = max((session.ended_at - session.started_at).total_seconds(), 0.0) if session.started_at else None
    session.base_url = final_url or session.base_url

    if cancelled:
        session.status = "cancelled"
        session.error_message = error_message or None
        session.save(
            update_fields=[
                "raw_script",
                "artifacts",
                "ended_at",
                "duration",
                "base_url",
                "status",
                "error_message",
            ]
        )
        return session

    parsed = parse_playwright_recording(raw_script or "")
    session.raw_actions = parsed["raw_actions"]
    session.normalized_actions = parsed["normalized_actions"]
    session.preview_payload = _build_preview_payload(
        session=session,
        normalized_actions=parsed["normalized_actions"],
        unsupported_lines=parsed["unsupported_lines"],
        final_url=final_url,
    )
    if error_message:
        session.error_message = error_message
    elif not parsed["normalized_actions"]:
        session.error_message = "未能从录制脚本中提取到可保存的结构化动作"
    else:
        session.error_message = None
    session.status = "draft" if parsed["normalized_actions"] else "failed"
    session.save(
        update_fields=[
            "raw_script",
            "artifacts",
            "ended_at",
            "duration",
            "base_url",
            "raw_actions",
            "normalized_actions",
            "preview_payload",
            "error_message",
            "status",
        ]
    )
    return session


def _get_or_create_element(page: UiPage, action: Dict[str, Any], creator: Optional[User]) -> Optional[UiElement]:
    locator_type = action.get("locator_type")
    locator_value = action.get("locator_value")
    if not locator_type or not locator_value:
        return None
    existing = UiElement.objects.filter(
        page=page,
        locator_type=locator_type,
        locator_value=locator_value,
    ).first()
    if existing:
        return existing

    semantic_name = _selector_display_name(locator_type, locator_value)
    existing = UiElement.objects.filter(page=page, name=semantic_name).order_by("id").first()
    if existing:
        _merge_locator_into_element(existing, locator_type, locator_value)
        return existing

    return UiElement.objects.create(
        page=page,
        name=semantic_name,
        locator_type=locator_type,
        locator_value=locator_value,
        creator=creator,
        description=f"由录制自动生成，来源 selector: {action.get('selector') or locator_value}",
    )


def _locator_rank(locator_type: str) -> int:
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


def _merge_locator_into_element(element: UiElement, locator_type: str, locator_value: str):
    """同一语义元素只保留一条记录，新定位写入备用定位，优先稳定定位作为主定位。"""
    if not locator_type or not locator_value:
        return
    locators = [
        (element.locator_type, element.locator_value),
        (element.locator_type_2, element.locator_value_2),
        (element.locator_type_3, element.locator_value_3),
    ]
    if (locator_type, locator_value) in locators:
        return

    update_fields: List[str] = []
    if _locator_rank(locator_type) < _locator_rank(element.locator_type):
        old_type, old_value = element.locator_type, element.locator_value
        element.locator_type = locator_type
        element.locator_value = locator_value
        update_fields.extend(["locator_type", "locator_value"])
        locator_type, locator_value = old_type, old_value

    if not element.locator_type_2 or not element.locator_value_2:
        element.locator_type_2 = locator_type
        element.locator_value_2 = locator_value
        update_fields.extend(["locator_type_2", "locator_value_2"])
    elif not element.locator_type_3 or not element.locator_value_3:
        element.locator_type_3 = locator_type
        element.locator_value_3 = locator_value
        update_fields.extend(["locator_type_3", "locator_value_3"])

    if update_fields:
        element.save(update_fields=[*update_fields, "updated_at"])


def _resolve_page_for_segment(
    *,
    session: UiRecordingSession,
    segment: PageSegment,
    fallback_url: str,
    creator: Optional[User],
) -> UiPage:
    if session.target_type == "page_step" and session.page_id and session.page:
        url_candidate = segment.url_hint or fallback_url or session.base_url or session.page.url or ""
        normalized_url = _relative_to_base_url(url_candidate, session.base_url or "")
        page_name = _resolve_page_name(normalized_url, session.name)
        update_fields: List[str] = []
        if normalized_url and session.page.url != normalized_url:
            session.page.url = normalized_url
            update_fields.append("url")
        if _should_update_page_name(session.page.name, page_name):
            session.page.name = page_name
            update_fields.append("name")
        if update_fields:
            session.page.save(update_fields=[*update_fields, "updated_at"])
        return session.page

    url_candidate = segment.url_hint or fallback_url or session.base_url or ""
    normalized_url = _relative_to_base_url(url_candidate, session.base_url or "")
    page_name = _resolve_page_name(normalized_url, session.name)

    page = None
    url_candidates = [normalized_url]
    absolute_candidate = _join_base_url(session.base_url or "", normalized_url)
    if absolute_candidate:
        url_candidates.append(absolute_candidate)
    raw_candidate = _normalize_url(url_candidate)
    if raw_candidate:
        url_candidates.append(raw_candidate)
    url_candidates = [item for index, item in enumerate(url_candidates) if item and item not in url_candidates[:index]]
    if url_candidates:
        page = UiPage.objects.filter(
            project=session.project,
            module=session.module,
            url__in=url_candidates,
        ).first()
    if not page:
        page = UiPage.objects.filter(
            project=session.project,
            module=session.module,
            name=page_name,
        ).first()
    if page:
        update_fields: List[str] = []
        if normalized_url and page.url != normalized_url:
            page.url = normalized_url
            update_fields.append("url")
        if _should_update_page_name(page.name, page_name):
            page.name = page_name
            update_fields.append("name")
        if update_fields:
            page.save(update_fields=[*update_fields, "updated_at"])
        return page

    return UiPage.objects.create(
        project=session.project,
        module=session.module,
        name=page_name,
        url=normalized_url or None,
        description=f"由录制《{session.name}》自动生成",
        creator=creator,
    )


def _materialize_actions_to_page_step(
    *,
    session: UiRecordingSession,
    page: UiPage,
    actions: List[Dict[str, Any]],
    name: str,
    creator: Optional[User],
    project: Project,
) -> UiPageSteps:
    page_step = UiPageSteps.objects.create(
        project=session.project,
        page=page,
        module=session.module,
        name=name[:64],
        description=f"由录制《{session.name}》自动生成",
        creator=creator,
        run_flow="\n".join(
            f"{idx}. {item.get('description') or item.get('operation')}"
            for idx, item in enumerate(actions, start=1)
        ),
    )

    detailed_rows: List[UiPageStepsDetailed] = []
    for index, action in enumerate(actions, start=1):
        operation = action["operation"]
        element = _get_or_create_element(page, action, creator)
        value = str(action.get("value") or "")
        ope_value: Dict[str, Any] = {}
        step_type = 1 if operation.startswith("assert_") else 0

        if operation == "goto":
            ope_value = {"url": _relative_to_base_url(value, session.base_url or "")}
        elif operation in {"fill", "type"}:
            ope_value = {"text": _replace_with_public_data(project, value)}
        elif operation == "press":
            ope_value = {"key": value}
        elif operation == "select":
            ope_value = {"value": value}
        elif operation in {"assert_text", "assert_value", "assert_contain_text", "assert_url", "assert_title"}:
            ope_value = {"expected": value}

        detailed_rows.append(
            UiPageStepsDetailed(
                page_step=page_step,
                step_type=step_type,
                element=element,
                step_sort=index,
                ope_key=operation,
                ope_value=ope_value,
                description=action.get("description") or operation,
            )
        )

    UiPageStepsDetailed.objects.bulk_create(detailed_rows)
    return page_step


def _clean_edited_actions(actions: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for index, action in enumerate(actions or [], start=1):
        if not isinstance(action, dict):
            continue
        operation = str(action.get("operation") or "").strip()
        if not operation:
            continue
        payload = {
            "line_no": action.get("line_no") or index,
            "operation": operation,
            "description": str(action.get("description") or operation).strip(),
        }
        for key in ["selector", "locator_type", "locator_value", "value"]:
            value = action.get(key)
            if value is not None and str(value).strip() != "":
                payload[key] = str(value).strip()
        cleaned.append(payload)
    return cleaned


@transaction.atomic
def materialize_recording_session(
    recording_id: int,
    *,
    normalized_actions: Optional[List[Dict[str, Any]]] = None,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    session = UiRecordingSession.objects.select_related(
        "project",
        "module",
        "page",
        "executor",
    ).get(id=recording_id)

    if session.status == "materialized":
        return {
            "generated_page_step_ids": session.generated_page_step_ids or [],
            "generated_test_case_id": session.generated_test_case_id,
            "created_pages": [],
            "warnings": session.preview_payload.get("warnings", []),
        }

    if session.status not in {"draft", "failed"}:
        raise ValueError("当前录制会话还未生成可保存草稿")
    if session.status == "failed" and normalized_actions is None:
        raise ValueError("当前录制会话未生成稳定草稿，请先编辑并保留至少一个动作")

    if name is not None and name.strip():
        session.name = name.strip()[:255]

    if normalized_actions is not None:
        cleaned_actions = _clean_edited_actions(normalized_actions)
        if not cleaned_actions:
            raise ValueError("编辑后的录制草稿中没有可保存的结构化动作")
        session.normalized_actions = cleaned_actions
        session.status = "draft"
        session.preview_payload = _build_preview_payload(
            session=session,
            normalized_actions=cleaned_actions,
            unsupported_lines=session.preview_payload.get("unsupported_lines", []),
            final_url=session.artifacts.get("final_url", ""),
        )
        session.save(update_fields=["name", "status", "normalized_actions", "preview_payload"])
    elif name is not None:
        session.save(update_fields=["name"])

    actions = list(session.normalized_actions or [])
    if not actions:
        raise ValueError("录制草稿中没有可保存的结构化动作")

    creator = session.executor
    project = session.project
    created_pages: List[Dict[str, Any]] = []
    created_page_step_ids: List[int] = []

    if session.target_type == "page_step":
        segment = PageSegment(
            index=1,
            url_hint=session.base_url or (session.page.url if session.page_id and session.page else ""),
            actions=actions,
        )
        page = _resolve_page_for_segment(
            session=session,
            segment=segment,
            fallback_url=session.artifacts.get("final_url", ""),
            creator=creator,
        )
        if page.id not in [item.get("id") for item in created_pages]:
            created_pages.append({"id": page.id, "name": page.name})
        page_step = _materialize_actions_to_page_step(
            session=session,
            page=page,
            actions=actions,
            name=session.name,
            creator=creator,
            project=project,
        )
        created_page_step_ids.append(page_step.id)
        generated_case_id = None
    else:
        segments = _build_segments(actions)
        page_steps: List[UiPageSteps] = []
        for segment in segments:
            page = _resolve_page_for_segment(
                session=session,
                segment=segment,
                fallback_url=session.artifacts.get("final_url", ""),
                creator=creator,
            )
            if page.id not in [item.get("id") for item in created_pages]:
                created_pages.append({"id": page.id, "name": page.name})
            page_step = _materialize_actions_to_page_step(
                session=session,
                page=page,
                actions=segment.actions,
                name=(f"{session.name}-步骤{segment.index}")[:64],
                creator=creator,
                project=project,
            )
            page_steps.append(page_step)
            created_page_step_ids.append(page_step.id)

        ui_case = UiTestCase.objects.create(
            project=project,
            module=session.module,
            name=session.name[:255],
            description=f"由录制《{session.name}》自动生成",
            creator=creator,
            case_flow="\n".join(
                f"{idx}. {page_step.name}"
                for idx, page_step in enumerate(page_steps, start=1)
            ),
        )
        for index, page_step in enumerate(page_steps, start=1):
            UiCaseStepsDetailed.objects.create(
                test_case=ui_case,
                page_step=page_step,
                case_sort=index,
                switch_step_open_url=False,
            )
        generated_case_id = ui_case.id

    session.generated_page_step_ids = created_page_step_ids
    session.generated_test_case_id = generated_case_id
    session.status = "materialized"
    session.save(update_fields=["generated_page_step_ids", "generated_test_case_id", "status"])

    return {
        "generated_page_step_ids": created_page_step_ids,
        "generated_test_case_id": generated_case_id,
        "created_pages": created_pages,
        "warnings": session.preview_payload.get("warnings", []),
    }

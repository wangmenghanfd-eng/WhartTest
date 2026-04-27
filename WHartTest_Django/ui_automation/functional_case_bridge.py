"""功能测试执行结果转 UI 自动化用例。"""

from __future__ import annotations

import ast
import json
import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.db import transaction

from projects.models import Project

from .models import (
    UiCaseStepsDetailed,
    UiElement,
    UiModule,
    UiPage,
    UiPageSteps,
    UiPageStepsDetailed,
    UiPublicData,
    UiTestCase,
)


_JS_STRING_PATTERN = r"(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')"
_GOTO_RE = re.compile(rf"page\.goto\(\s*(?P<url>{_JS_STRING_PATTERN})", re.IGNORECASE)
_FILL_RE = re.compile(
    rf"page\.fill\(\s*(?P<selector>{_JS_STRING_PATTERN})\s*,\s*(?P<value>{_JS_STRING_PATTERN})",
    re.IGNORECASE,
)
_CLICK_RE = re.compile(
    rf"page\.(?P<op>click|dblclick|hover|check|uncheck|focus)\(\s*(?P<selector>{_JS_STRING_PATTERN})",
    re.IGNORECASE,
)
_PRESS_RE = re.compile(
    rf"page\.press\(\s*(?P<selector>{_JS_STRING_PATTERN})\s*,\s*(?P<key>{_JS_STRING_PATTERN})",
    re.IGNORECASE,
)
_SELECT_RE = re.compile(
    rf"page\.select_option\(\s*(?P<selector>{_JS_STRING_PATTERN})\s*,\s*(?P<value>{_JS_STRING_PATTERN})",
    re.IGNORECASE,
)


def _decode_js_string(raw_value: str) -> str:
    """解析 run.js 中的 JS 字符串字面量。"""
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return ""
    try:
        value = ast.literal_eval(raw_value)
        return value if isinstance(value, str) else str(value)
    except Exception:
        return raw_value.strip("'\"")


def _parse_test_case_detail(test_case_detail: Any) -> Dict[str, Any]:
    if isinstance(test_case_detail, dict):
        return test_case_detail
    if isinstance(test_case_detail, str):
        try:
            return json.loads(test_case_detail)
        except Exception:
            match = re.search(r"(\{.*\})", test_case_detail, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    return {}
    return {}


def _split_js_statements(command: str) -> Iterable[str]:
    for segment in (command or "").split(";"):
        segment = segment.strip()
        if segment:
            yield segment


def _infer_locator(selector: str) -> tuple[str, str]:
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


def _infer_element_name(selector: str, operation: str) -> str:
    selector_lower = (selector or "").lower()
    if "username" in selector_lower:
        return "用户名输入框"
    if "password" in selector_lower:
        return "密码输入框"
    if "submit" in selector_lower or ("login" in selector_lower and operation in {"click", "dblclick"}):
        return "登录按钮"
    if "logout" in selector_lower:
        return "退出登录入口"
    if selector_lower in {"body", "css=body"}:
        return "页面主体"
    if selector_lower == "h1":
        return "一级标题"
    return f"元素-{selector[:40]}"


def _build_action_description(operation: str, selector: str = "", value: str = "") -> str:
    if operation == "goto":
        return f"打开页面: {value}"
    if operation == "fill":
        return f"填充 {_infer_element_name(selector, operation)}"
    if operation == "click":
        return f"点击 {_infer_element_name(selector, operation)}"
    if operation == "dblclick":
        return f"双击 {_infer_element_name(selector, operation)}"
    if operation == "press":
        return f"按键操作 {_infer_element_name(selector, operation)}"
    if operation == "select":
        return f"选择 {_infer_element_name(selector, operation)}"
    if operation == "assert_visible":
        return f"断言 {_infer_element_name(selector, operation)} 可见"
    if operation == "assert_contain_text":
        return f"断言 {_infer_element_name(selector, operation)} 包含文本"
    return f"{operation}: {selector or value}"


def _extract_actions_from_commands(command_records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    for record in command_records:
        command = str(record.get("command") or "")
        for segment in _split_js_statements(command):
            match = _GOTO_RE.search(segment)
            if match:
                url = _decode_js_string(match.group("url"))
                key = ("goto", url)
                if url and key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "operation": "goto",
                            "value": url,
                            "description": _build_action_description("goto", value=url),
                        }
                    )
                continue

            match = _FILL_RE.search(segment)
            if match:
                selector = _decode_js_string(match.group("selector"))
                value = _decode_js_string(match.group("value"))
                key = ("fill", selector, value)
                if selector and key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "operation": "fill",
                            "selector": selector,
                            "value": value,
                            "description": _build_action_description("fill", selector, value),
                        }
                    )
                continue

            match = _CLICK_RE.search(segment)
            if match:
                selector = _decode_js_string(match.group("selector"))
                operation = match.group("op").lower()
                key = (operation, selector)
                if selector and key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "operation": operation,
                            "selector": selector,
                            "description": _build_action_description(operation, selector),
                        }
                    )
                continue

            match = _PRESS_RE.search(segment)
            if match:
                selector = _decode_js_string(match.group("selector"))
                value = _decode_js_string(match.group("key"))
                key = ("press", selector, value)
                if selector and key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "operation": "press",
                            "selector": selector,
                            "value": value,
                            "description": _build_action_description("press", selector, value),
                        }
                    )
                continue

            match = _SELECT_RE.search(segment)
            if match:
                selector = _decode_js_string(match.group("selector"))
                value = _decode_js_string(match.group("value"))
                key = ("select", selector, value)
                if selector and key not in seen:
                    seen.add(key)
                    actions.append(
                        {
                            "operation": "select",
                            "selector": selector,
                            "value": value,
                            "description": _build_action_description("select", selector, value),
                        }
                    )
                continue

    return actions


def _extract_assertions(
    command_records: Iterable[Dict[str, Any]], observed_signals: Iterable[str]
) -> List[Dict[str, Any]]:
    outputs = "\n".join(str(record.get("output") or "") for record in command_records)
    assertions: List[Dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()

    candidates = [
        ("body", "assert_contain_text", "You logged into a secure area!"),
        ("body", "assert_contain_text", "Welcome to the Secure Area"),
        ("body", "assert_contain_text", "Your username is invalid!"),
        ("body", "assert_contain_text", "Your password is invalid!"),
    ]
    for selector, operation, expected_text in candidates:
        if expected_text in outputs:
            key = (operation, selector, expected_text)
            if key not in seen:
                seen.add(key)
                assertions.append(
                    {
                        "operation": operation,
                        "selector": selector,
                        "value": expected_text,
                        "description": _build_action_description(operation, selector, expected_text),
                    }
                )

    if (
        "Logout link found" in outputs
        or "退出登录入口存在" in outputs
        or "logout_found" in set(observed_signals)
    ):
        key = ("assert_visible", "a[href='/logout']")
        if key not in seen:
            seen.add(key)
            assertions.append(
                {
                    "operation": "assert_visible",
                    "selector": "a[href='/logout']",
                    "description": _build_action_description("assert_visible", "a[href='/logout']"),
                }
            )

    if "Secure Area" in outputs:
        key = ("assert_contain_text", "h1", "Secure Area")
        if key not in seen:
            seen.add(key)
            assertions.append(
                {
                    "operation": "assert_contain_text",
                    "selector": "h1",
                    "value": "Secure Area",
                    "description": _build_action_description("assert_contain_text", "h1", "Secure Area"),
                }
            )

    return assertions


def _replace_with_public_data(project: Project, value: str) -> str:
    if not value:
        return value
    allowed_key = re.compile(r"(^|_)(username|password|account|email|phone|token)(_|$)", re.IGNORECASE)
    noisy_key = re.compile(r"(wrong|invalid|error|fail|negative|temp|random|auto|case)", re.IGNORECASE)
    public_data = UiPublicData.objects.filter(
        project=project, is_enabled=True, value=value
    ).order_by("key").first()
    if public_data and allowed_key.search(public_data.key) and not noisy_key.search(public_data.key):
        return f"${{{{{public_data.key}}}}}"
    return value


def _relative_to_base_url(url: str, base_url: str = "") -> str:
    url = (url or "").strip()
    if not url or url.startswith("/"):
        return url
    if not url.startswith(("http://", "https://")):
        return url
    parsed = urlparse(url)
    base = urlparse((base_url or "").strip())
    if base.scheme and base.netloc and parsed.scheme == base.scheme and parsed.netloc == base.netloc:
        return parsed.path or "/"
    return url


def _resolve_page_name(target_url: str, testcase_name: str) -> str:
    if target_url:
        parsed = urlparse(target_url)
        path = (parsed.path if parsed.scheme else target_url).split("?", 1)[0].strip("/") or "home"
        friendly_names = {
            "home": "首页",
            "login": "登录页",
            "secure": "安全区域页",
            "register": "注册页",
            "logout": "退出登录页",
        }
        return friendly_names.get(path.lower(), path[:64])
    return f"{testcase_name[:40]} 页面"


def _should_update_page_name(existing_name: str, suggested_name: str) -> bool:
    if not suggested_name or existing_name == suggested_name:
        return False
    normalized = (existing_name or "").strip().lower()
    return normalized in {"login", "secure", "home", "index"} or "/" in normalized or "." in normalized


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


def _get_or_create_element(
    page: UiPage, selector: str, operation: str, creator: Optional[User]
) -> UiElement:
    locator_type, locator_value = _infer_locator(selector)
    existing = UiElement.objects.filter(
        page=page,
        locator_type=locator_type,
        locator_value=locator_value,
    ).first()
    if existing:
        return existing
    semantic_name = _infer_element_name(selector, operation)
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
        description=f"由功能测试执行自动生成，原始 selector: {selector}",
    )


@transaction.atomic
def generate_ui_case_from_functional_execution(
    *,
    project_id: int,
    creator_id: Optional[int],
    test_case_detail: Any,
    command_records: List[Dict[str, Any]],
    observed_signals: Iterable[str],
    target_url_hint: str = "",
) -> Dict[str, Any]:
    """根据功能测试执行步骤，生成可落库的 UI 自动化用例。"""
    detail = _parse_test_case_detail(test_case_detail)
    if not detail:
        raise ValueError("无法解析功能测试用例详情")

    project = Project.objects.get(id=project_id)
    creator = User.objects.filter(id=creator_id).first() if creator_id else None

    actions = _extract_actions_from_commands(command_records)
    assertions = _extract_assertions(command_records, observed_signals)
    if not actions:
        raise ValueError("未能从实际执行步骤中提取可保存的 UI 自动化动作")

    test_case_name = str(detail.get("name") or f"功能用例-{detail.get('id')}")
    module_name = str(detail.get("module_detail") or "功能用例转换")
    target_url = target_url_hint or next(
        (str(action.get("value") or "") for action in actions if action["operation"] == "goto"),
        "",
    )
    base_url = ""
    if target_url.startswith(("http://", "https://")):
        parsed_target = urlparse(target_url)
        base_url = f"{parsed_target.scheme}://{parsed_target.netloc}"
    relative_target_url = _relative_to_base_url(target_url, base_url)

    root_module, _ = UiModule.objects.get_or_create(
        project=project,
        parent=None,
        name="AI生成用例",
        defaults={"creator": creator},
    )
    leaf_module, _ = UiModule.objects.get_or_create(
        project=project,
        parent=root_module,
        name=module_name,
        defaults={"creator": creator},
    )

    page_name = _resolve_page_name(relative_target_url or target_url, test_case_name)
    page = (
        UiPage.objects.filter(project=project, module=leaf_module, url=relative_target_url).first()
        or UiPage.objects.filter(project=project, module=leaf_module, url=target_url).first()
        or UiPage.objects.filter(project=project, module=leaf_module, name=page_name).first()
    )
    page_created = False
    if not page:
        page = UiPage.objects.create(
            project=project,
            module=leaf_module,
            name=page_name,
            url=relative_target_url or target_url,
            description=f"由功能测试用例 #{detail.get('id')} 自动生成",
            creator=creator,
        )
        page_created = True
    page.module = leaf_module
    if _should_update_page_name(page.name, page_name):
        page.name = page_name or page.name
    page.url = relative_target_url or target_url or page.url
    page.description = f"由功能测试用例 #{detail.get('id')} 自动生成"
    if creator and page.creator_id is None:
        page.creator = creator
    page.save()

    page_step_name = f"AI生成步骤-{test_case_name[:48]}"
    page_step, step_created = UiPageSteps.objects.get_or_create(
        project=project,
        page=page,
        module=leaf_module,
        name=page_step_name,
        defaults={
            "creator": creator,
            "description": f"由功能测试用例 #{detail.get('id')} 自动生成",
        },
    )
    page_step.description = f"由功能测试用例 #{detail.get('id')} 自动生成"
    if creator and page_step.creator_id is None:
        page_step.creator = creator
    page_step.run_flow = "\n".join(
        f"{idx}. {item['description']}"
        for idx, item in enumerate(actions + assertions, start=1)
    )
    page_step.save()
    page_step.step_details.all().delete()

    generated_steps = []
    for index, item in enumerate(actions + assertions, start=1):
        operation = item["operation"]
        selector = item.get("selector") or ""
        value = item.get("value") or ""
        step_type = 1 if operation.startswith("assert_") else 0
        element = None
        ope_value: Dict[str, Any] | None = None

        if operation == "goto":
            ope_value = {"url": _relative_to_base_url(value, base_url)}
        elif selector:
            element = _get_or_create_element(page, selector, operation, creator)
            if operation in {"fill", "type"}:
                ope_value = {"text": _replace_with_public_data(project, value)}
            elif operation == "press":
                ope_value = {"key": value}
            elif operation == "select":
                ope_value = {"value": value}
            elif operation == "assert_contain_text":
                ope_value = {"text": value}
            else:
                ope_value = {}
        else:
            ope_value = {"value": value} if value else {}

        generated_steps.append(
            UiPageStepsDetailed(
                page_step=page_step,
                step_type=step_type,
                element=element,
                step_sort=index,
                ope_key=operation,
                ope_value=ope_value,
                description=item["description"],
            )
        )

    UiPageStepsDetailed.objects.bulk_create(generated_steps)

    ui_case_name = f"AI生成-{test_case_name[:64]}"
    ui_case, case_created = UiTestCase.objects.get_or_create(
        project=project,
        module=leaf_module,
        name=ui_case_name,
        defaults={
            "creator": creator,
            "level": str(detail.get("level") or "P2"),
            "description": f"由功能测试用例 #{detail.get('id')} 自动转换",
        },
    )
    ui_case.module = leaf_module
    ui_case.level = str(detail.get("level") or ui_case.level or "P2")
    ui_case.description = f"由功能测试用例 #{detail.get('id')} 自动转换"
    ui_case.case_flow = "\n".join(
        f"{idx}. {item['description']}"
        for idx, item in enumerate(actions + assertions, start=1)
    )
    if creator and ui_case.creator_id is None:
        ui_case.creator = creator
    ui_case.save()
    ui_case.case_steps.all().delete()
    UiCaseStepsDetailed.objects.create(
        test_case=ui_case,
        page_step=page_step,
        case_sort=1,
        switch_step_open_url=False,
    )

    return {
        "ui_testcase_id": ui_case.id,
        "ui_testcase_name": ui_case.name,
        "ui_module_id": leaf_module.id,
        "ui_module_name": leaf_module.name,
        "page_id": page.id,
        "page_step_id": page_step.id,
        "page_name": page.name,
        "action_count": len(actions),
        "assertion_count": len(assertions),
        "created_page": page_created,
        "created_page_step": step_created,
        "created_case": case_created,
    }

# -*- coding: utf-8 -*-
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import argparse
import json
import os
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


BASE_URL = (os.getenv("WHARTTEST_BACKEND_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("WHARTTEST_API_KEY") or "wharttest-default-mcp-key-2025"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}


def _handle_response(resp):
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def _parse_json_list(raw: str, field_name: str):
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{field_name} 不是合法 JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValueError(f"{field_name} 必须是 JSON 数组")
    return data


def get_module_tree(project_id: int):
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/modules/tree/",
        headers=HEADERS,
        params={"project": project_id},
        timeout=30,
    )
    return _handle_response(resp)


def list_pages(project_id: int = None, module_id: int = None):
    params = {}
    if project_id is not None:
        params["project"] = project_id
    if module_id is not None:
        params["module"] = module_id
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/pages/",
        headers=HEADERS,
        params=params,
        timeout=30,
    )
    return _handle_response(resp)


def list_elements(page_id: int):
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/elements/",
        headers=HEADERS,
        params={"page": page_id},
        timeout=30,
    )
    return _handle_response(resp)


def list_page_steps(project_id: int = None, module_id: int = None, page_id: int = None):
    params = {}
    if project_id is not None:
        params["project"] = project_id
    if module_id is not None:
        params["module"] = module_id
    if page_id is not None:
        params["page"] = page_id
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/page-steps/",
        headers=HEADERS,
        params=params,
        timeout=30,
    )
    return _handle_response(resp)


def get_page_step_detail(page_step_id: int):
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/page-steps/{page_step_id}/",
        headers=HEADERS,
        timeout=30,
    )
    return _handle_response(resp)


def list_testcases(project_id: int = None, module_id: int = None):
    params = {}
    if project_id is not None:
        params["project"] = project_id
    if module_id is not None:
        params["module"] = module_id
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/testcases/",
        headers=HEADERS,
        params=params,
        timeout=30,
    )
    return _handle_response(resp)


def get_testcase_detail(case_id: int):
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/testcases/{case_id}/",
        headers=HEADERS,
        timeout=30,
    )
    return _handle_response(resp)


def list_public_data(project_id: int):
    resp = requests.get(
        f"{BASE_URL}/api/ui-automation/public-data/by-project/{project_id}/",
        headers=HEADERS,
        timeout=30,
    )
    return _handle_response(resp)


def create_module(project_id: int, name: str, parent_id: int = None):
    payload = {"project": project_id, "name": name}
    if parent_id is not None:
        payload["parent"] = parent_id
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/modules/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def create_page(project_id: int, module_id: int, name: str, url: str = "", description: str = ""):
    payload = {
        "project": project_id,
        "module": module_id,
        "name": name,
        "url": url,
        "description": description,
    }
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/pages/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def create_element(
    page_id: int,
    name: str,
    locator_type: str,
    locator_value: str,
    wait_time: int = 0,
    description: str = "",
):
    payload = {
        "page": page_id,
        "name": name,
        "locator_type": locator_type,
        "locator_value": locator_value,
        "wait_time": wait_time,
        "description": description,
    }
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/elements/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def create_page_step(project_id: int, module_id: int, page_id: int, name: str, description: str = ""):
    payload = {
        "project": project_id,
        "module": module_id,
        "page": page_id,
        "name": name,
        "description": description,
    }
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/page-steps/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def update_page_step_details(page_step_id: int, steps_raw: str):
    steps = _parse_json_list(steps_raw, "steps")
    payload = {"page_step": page_step_id, "steps": steps}
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/page-steps-detailed/batch_update/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def create_testcase(project_id: int, module_id: int, name: str, level: str = "P2", description: str = ""):
    payload = {
        "project": project_id,
        "module": module_id,
        "name": name,
        "level": level,
        "description": description,
    }
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/testcases/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def update_case_steps(test_case_id: int, steps_raw: str):
    steps = _parse_json_list(steps_raw, "steps")
    payload = {"test_case": test_case_id, "steps": steps}
    resp = requests.post(
        f"{BASE_URL}/api/ui-automation/case-steps/batch_update/",
        headers=HEADERS,
        data=json.dumps(payload, ensure_ascii=False),
        timeout=30,
    )
    return _handle_response(resp)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--project_id", type=int)
    parser.add_argument("--module_id", type=int)
    parser.add_argument("--page_id", type=int)
    parser.add_argument("--page_step_id", type=int)
    parser.add_argument("--test_case_id", type=int)
    parser.add_argument("--case_id", type=int)
    parser.add_argument("--parent_id", type=int)
    parser.add_argument("--name")
    parser.add_argument("--url")
    parser.add_argument("--description")
    parser.add_argument("--level", default="P2")
    parser.add_argument("--locator_type")
    parser.add_argument("--locator_value")
    parser.add_argument("--wait_time", type=int, default=0)
    parser.add_argument("--steps")
    args = parser.parse_args()

    action_map = {
        "get_module_tree": lambda: get_module_tree(args.project_id),
        "list_pages": lambda: list_pages(args.project_id, args.module_id),
        "list_elements": lambda: list_elements(args.page_id),
        "list_page_steps": lambda: list_page_steps(args.project_id, args.module_id, args.page_id),
        "get_page_step_detail": lambda: get_page_step_detail(args.page_step_id),
        "list_testcases": lambda: list_testcases(args.project_id, args.module_id),
        "get_testcase_detail": lambda: get_testcase_detail(args.case_id or args.test_case_id),
        "list_public_data": lambda: list_public_data(args.project_id),
        "create_module": lambda: create_module(args.project_id, args.name, args.parent_id),
        "create_page": lambda: create_page(args.project_id, args.module_id, args.name, args.url or "", args.description or ""),
        "create_element": lambda: create_element(args.page_id, args.name, args.locator_type, args.locator_value, args.wait_time, args.description or ""),
        "create_page_step": lambda: create_page_step(args.project_id, args.module_id, args.page_id, args.name, args.description or ""),
        "update_page_step_details": lambda: update_page_step_details(args.page_step_id, args.steps),
        "create_testcase": lambda: create_testcase(args.project_id, args.module_id, args.name, args.level, args.description or ""),
        "update_case_steps": lambda: update_case_steps(args.test_case_id, args.steps),
    }

    if args.action not in action_map:
        print(json.dumps({"error": f"未知 action: {args.action}"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        result = action_map[args.action]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()

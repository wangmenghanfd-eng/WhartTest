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
LOG_DIR = os.getenv("WHARTTEST_LOG_DIR") or "/app/data/logs"


def _handle_response(resp):
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def _tail_file(file_path: str, lines: int = 50):
    if not os.path.exists(file_path):
        return {"error": f"文件不存在: {file_path}"}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.readlines()
    return {
        "file": file_path,
        "lines": min(lines, len(content)),
        "content": "".join(content[-lines:]),
    }


def list_actuators():
    return _handle_response(requests.get(f"{BASE_URL}/api/ui-automation/actuators/list_actuators/", headers=HEADERS, timeout=30))


def get_status():
    return _handle_response(requests.get(f"{BASE_URL}/api/ui-automation/actuators/status/", headers=HEADERS, timeout=30))


def toggle_open(actuator_id: str, is_open: bool):
    payload = {"actuator_id": actuator_id, "is_open": is_open}
    return _handle_response(
        requests.post(
            f"{BASE_URL}/api/ui-automation/actuators/toggle_open/",
            headers=HEADERS,
            data=json.dumps(payload, ensure_ascii=False),
            timeout=30,
        )
    )


def list_recent_ui_execution_records(project_id: int = None, limit: int = 10):
    params = {}
    if project_id is not None:
        params["project"] = project_id
    resp = _handle_response(
        requests.get(
            f"{BASE_URL}/api/ui-automation/execution-records/",
            headers=HEADERS,
            params=params,
            timeout=30,
        )
    )
    if isinstance(resp, list):
        return resp[:limit]
    if isinstance(resp, dict) and isinstance(resp.get("results"), list):
        resp["results"] = resp["results"][:limit]
    return resp


def get_ui_execution_record(record_id: int):
    return _handle_response(
        requests.get(
            f"{BASE_URL}/api/ui-automation/execution-records/{record_id}/",
            headers=HEADERS,
            timeout=30,
        )
    )


def tail_actuator_log(log_file: str = "err", lines: int = 50):
    mapping = {
        "err": "actuator-launchd.err.log",
        "out": "actuator-launchd.out.log",
    }
    file_name = mapping.get(log_file, log_file)
    return _tail_file(os.path.join(LOG_DIR, file_name), lines)


def tail_platform_log(lines: int = 50, file_name: str = "app.log"):
    return _tail_file(os.path.join(LOG_DIR, file_name), lines)


def _parse_bool(value: str) -> bool:
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError("is_open 必须是 true/false")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--actuator_id")
    parser.add_argument("--is_open")
    parser.add_argument("--project_id", type=int)
    parser.add_argument("--record_id", type=int)
    parser.add_argument("--lines", type=int, default=50)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--log_file", default="err")
    parser.add_argument("--file_name", default="app.log")
    args = parser.parse_args()

    actions = {
        "list_actuators": lambda: list_actuators(),
        "get_status": lambda: get_status(),
        "toggle_open": lambda: toggle_open(args.actuator_id, _parse_bool(args.is_open)),
        "list_recent_ui_execution_records": lambda: list_recent_ui_execution_records(args.project_id, args.limit),
        "get_ui_execution_record": lambda: get_ui_execution_record(args.record_id),
        "tail_actuator_log": lambda: tail_actuator_log(args.log_file, args.lines),
        "tail_platform_log": lambda: tail_platform_log(args.lines, args.file_name),
    }

    if args.action not in actions:
        print(json.dumps({"error": f"未知 action: {args.action}"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        result = actions[args.action]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()

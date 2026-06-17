# -*- coding: utf-8 -*-
import sys
import io

# Windows 终端 UTF-8 输出
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import argparse
import json
import os
import time
try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover - runtime fallback for skill container
    import mimetypes
    import uuid
    import urllib.error
    import urllib.request

    class _CompatResponse:
        def __init__(self, response):
            self._response = response
            self.status_code = getattr(response, "status_code", None) or response.getcode()
            raw = response.read()
            self.text = raw.decode("utf-8", errors="replace")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}: {self.text}")

        def json(self):
            return __import__("json").loads(self.text)

    class _CompatRequests:
        @staticmethod
        def _encode_multipart(data=None, files=None):
            boundary = f"----WHartTestSkill{uuid.uuid4().hex}"
            chunks = []
            for key, value in (data or {}).items():
                chunks.extend([
                    f"--{boundary}\r\n".encode(),
                    f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                    str(value).encode(),
                    b"\r\n",
                ])
            for key, file_info in (files or {}).items():
                filename = getattr(file_info, "name", f"{key}.bin").split("/")[-1]
                content = file_info.read()
                if hasattr(file_info, "seek"):
                    file_info.seek(0)
                content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                chunks.extend([
                    f"--{boundary}\r\n".encode(),
                    (
                        f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
                        f"Content-Type: {content_type}\r\n\r\n"
                    ).encode(),
                    content,
                    b"\r\n",
                ])
            chunks.append(f"--{boundary}--\r\n".encode())
            return boundary, b"".join(chunks)

        @staticmethod
        def _request(method, url, headers=None, params=None, json=None, data=None, files=None):
            req_headers = dict(headers or {})
            if params:
                from urllib.parse import urlencode
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urlencode(params)}"
            body = None
            if files:
                boundary, body = _CompatRequests._encode_multipart(data=data, files=files)
                req_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
            elif json is not None:
                body = __import__("json").dumps(json).encode("utf-8")
                req_headers["Content-Type"] = "application/json"
            elif data is not None:
                from urllib.parse import urlencode
                body = urlencode(data).encode("utf-8")
                req_headers["Content-Type"] = "application/x-www-form-urlencoded"
            req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as response:
                    return _CompatResponse(response)
            except urllib.error.HTTPError as exc:
                return _CompatResponse(exc)

        @staticmethod
        def get(url, headers=None, params=None):
            return _CompatRequests._request("GET", url, headers=headers, params=params)

        @staticmethod
        def post(url, headers=None, json=None, data=None, files=None):
            return _CompatRequests._request(
                "POST", url, headers=headers, json=json, data=data, files=files
            )

        @staticmethod
        def patch(url, headers=None, json=None, data=None):
            return _CompatRequests._request("PATCH", url, headers=headers, json=json, data=data)

    requests = _CompatRequests()
from pathlib import Path

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / '.env')
except ImportError:
    pass

# 配置
BASE_URL = (os.getenv("WHARTTEST_BACKEND_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("WHARTTEST_API_KEY") or "wharttest-default-mcp-key-2025"
HEADERS = {
    "accept": "application/json, text/plain,*/*",
    "X-API-Key": API_KEY
}


def _resolve_screenshot_path(file_path: str) -> str:
    if not file_path:
        return file_path

    if os.path.exists(file_path):
        return file_path

    screenshot_dir = os.environ.get('SCREENSHOT_DIR', '')
    if not screenshot_dir:
        return file_path

    basename = os.path.basename(file_path)
    if not basename:
        return file_path

    fallback_path = os.path.join(screenshot_dir, basename)
    if os.path.exists(fallback_path):
        return fallback_path

    return file_path


def _extract_tree(nodes_list, id_key, name_key):
    """递归提取树形结构"""
    result = []
    if not isinstance(nodes_list, list):
        return result
    for node in nodes_list:
        if isinstance(node, dict):
            result.append({id_key: node.get("id"), name_key: node.get("name")})
            children = node.get("children")
            if isinstance(children, list):
                result.extend(_extract_tree(children, id_key, name_key))
    return result


def get_projects():
    """获取项目列表"""
    url = f"{BASE_URL}/api/projects/"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return _extract_tree(data, "project_id", "project_name")
    except Exception as e:
        return {"error": str(e)}


def get_modules(project_id: int):
    """获取项目下的模块"""
    url = f"{BASE_URL}/api/projects/{project_id}/testcase-modules/"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return _extract_tree(data, "module_id", "module_name")
    except Exception as e:
        return {"error": str(e)}


def get_module_id(project_id: int, module_name: str):
    """根据模块名称获取模块ID，优先精确匹配，其次包含匹配"""
    modules = get_modules(project_id)
    if isinstance(modules, dict) and "error" in modules:
        return modules

    if not module_name:
        return {"error": "module_name 不能为空"}

    normalized_target = "".join(str(module_name).strip().lower().split())
    exact_match = None
    fuzzy_match = None

    for item in modules:
        name = item.get("module_name", "")
        normalized_name = "".join(str(name).strip().lower().split())
        if normalized_name == normalized_target:
            exact_match = item
            break
        if normalized_target in normalized_name or normalized_name in normalized_target:
            fuzzy_match = item

    matched = exact_match or fuzzy_match
    if matched:
        return matched

    return {
        "error": f"未找到模块: {module_name}",
        "available_modules": modules,
    }


def get_levels():
    """获取用例等级"""
    return ["P0", "P1", "P2", "P3"]


def get_testcases(project_id: int, module_id: int):
    """获取用例列表"""
    url = f"{BASE_URL}/api/projects/{project_id}/testcases/?page=1&page_size=1000&module_id={module_id}"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return [{"case_id": i.get("id"), "case_name": i.get("name")} for i in data]
    except Exception as e:
        return {"error": str(e)}


def get_testcase_detail(project_id: int, case_id: int):
    """获取用例详情"""
    url = f"{BASE_URL}/api/projects/{project_id}/testcases/{case_id}/"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        return resp.json().get("data", {})
    except Exception as e:
        return {"error": str(e)}


def get_case_details(project_id: int, case_id: int):
    """兼容旧动作名，等价于 get_testcase_detail"""
    return get_testcase_detail(project_id, case_id)


def get_test_result(project_id: int, case_id: int):
    """获取指定用例最近一次执行结果"""
    url = f"{BASE_URL}/api/projects/{project_id}/test-executions/?page=1&page_size=50"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        executions = resp.json().get("data", [])
        for execution in executions:
            for result in execution.get("results", []) or []:
                if result.get("testcase") == case_id:
                    return {
                        "execution_id": execution.get("id"),
                        "execution_status": execution.get("status"),
                        "case_id": case_id,
                        "result_id": result.get("id"),
                        "result_status": result.get("status"),
                        "error_message": result.get("error_message"),
                        "screenshots": result.get("screenshots", []),
                        "started_at": result.get("started_at"),
                        "completed_at": result.get("completed_at"),
                        "execution_time": result.get("execution_time"),
                        "execution_log": result.get("execution_log"),
                    }
        return {
            "message": f"未找到用例 {case_id} 的历史执行结果",
            "case_id": case_id,
        }
    except Exception as e:
        return {"error": str(e)}


def execute_test_case(project_id: int, case_id: int, module_id: int = None):
    """
    兼容旧动作名，返回正确执行链路指引，避免模型把浏览器执行错误地交给 whart_tools.py。
    """
    testcase = get_testcase_detail(project_id, case_id)
    return {
        "success": False,
        "warning": "whart_tools.py 不负责浏览器执行。请改用 playwright-skill 执行页面操作，再用 upload_screenshot 或 upload_screenshots 上传真实截图。",
        "recommended_sequence": [
            "1. 使用 get_testcase_detail 获取测试步骤",
            "2. 使用 playwright-skill 执行浏览器操作，命令格式为 node run.js \"...\"",
            "3. 截图必须保存到 SCREENSHOT_DIR，再通过 upload_screenshot 或 upload_screenshots 上传",
            "4. 如需查询历史执行结果，再调用 get_test_result",
        ],
        "project_id": project_id,
        "case_id": case_id,
        "module_id": module_id,
        "testcase": testcase,
    }


def add_testcase(project_id: int, module_id: int, name: str, level: str = "P1",
                 precondition: str = "无", steps: list = None, notes: str = "",
                 review_status: str = "pending_review", test_type: str = "functional"):
    """新增测试用例"""
    url = f"{BASE_URL}/api/projects/{project_id}/testcases/"
    data = {
        "name": name,
        "precondition": precondition,
        "level": level,
        "module_id": module_id,
        "steps": steps or [],
        "notes": notes,
        "review_status": review_status,
        "test_type": test_type
    }
    try:
        resp = requests.post(url, headers=HEADERS, json=data)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 201:
            return {"message": "保存成功", "testcase": {"id": result.get("data", {}).get("id"),"name": result.get("data", {}).get("name", name)}}
        return {"message": "保存失败", "response": result}
    except Exception as e:
        return {"error": str(e)}


def edit_testcase(project_id: int, case_id: int, name: str = None, level: str = None,
                  module_id: int = None, precondition: str = None, steps: list = None, notes: str = None,
                  review_status: str = None, test_type: str = None, is_optimization: bool = False):
    """编辑测试用例"""
    url = f"{BASE_URL}/api/projects/{project_id}/testcases/{case_id}/"
    data = {}
    if name is not None: data["name"] = name
    if level is not None: data["level"] = level
    if module_id is not None: data["module_id"] = module_id
    if precondition is not None: data["precondition"] = precondition
    if steps is not None: data["steps"] = steps
    if notes is not None: data["notes"] = notes
    if test_type is not None: data["test_type"] = test_type

    # 处理优化工作流
    if is_optimization:
        data["review_status"] = "optimization_pending_review"
    elif review_status is not None:
        data["review_status"] = review_status

    try:
        resp = requests.patch(url, headers=HEADERS, json=data)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 200:
            status_msg = ""
            if is_optimization:
                status_msg = "，状态已自动设为「优化待审核」"
            elif review_status:
                status_msg = f"，状态已设为「{review_status}」"
            return {
                "success": True,
                "message": f"用例ID {case_id} 编辑成功{status_msg}。任务已完成，无需再次编辑或查询。"
            }
        return {"success": False, "message": "编辑失败", "response": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


def upload_screenshot(project_id: int, case_id: int, file_path: str, title: str,
                      description: str = "", step_number: int = None, page_url: str = ""):
    """上传单张截图"""
    title = title or os.path.basename(file_path or "") or "自动上传截图"
    # 如果是文件名（无目录分隔符），自动从 SCREENSHOT_DIR 查找
    if os.sep not in file_path and '/' not in file_path:
        screenshot_dir = os.environ.get('SCREENSHOT_DIR', '')
        if screenshot_dir:
            file_path = os.path.join(screenshot_dir, file_path)
    else:
        file_path = _resolve_screenshot_path(file_path)

    if not os.path.exists(file_path):
        screenshot_dir = os.environ.get('SCREENSHOT_DIR', '')
        available_files = []
        if screenshot_dir and os.path.isdir(screenshot_dir):
            try:
                available_files = sorted(
                    name for name in os.listdir(screenshot_dir)
                    if not name.startswith('.')
                )[:20]
            except OSError:
                available_files = []
        return {
            "error": f"文件不存在: {file_path}",
            "screenshot_dir": screenshot_dir,
            "available_files": available_files,
        }

    url = f"{BASE_URL}/api/projects/{project_id}/testcases/{case_id}/upload-screenshots/"
    mime_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif'}
    ext = os.path.splitext(file_path)[1].lower()
    content_type = mime_types.get(ext, 'image/png')

    try:
        with open(file_path, 'rb') as f:
            files = {'screenshots': (os.path.basename(file_path), f, content_type)}
            data = {'title': title}
            if description: data['description'] = description
            if step_number is not None: data['step_number'] = str(step_number)
            if page_url: data['page_url'] = page_url

            resp = requests.post(url, headers=HEADERS, files=files, data=data)
            resp.raise_for_status()
            return {"message": f"截图 '{title}' 上传成功"}
    except Exception as e:
        return {"error": str(e)}


def upload_screenshots(project_id: int, case_id: int, file_paths: str, title: str,
                       description: str = "", step_number: int = None, page_url: str = ""):
    """批量上传截图（最多10张）"""
    paths = [p.strip() for p in file_paths.split(',') if p.strip()]
    if not paths:
        return {"error": "未提供文件路径"}
    if len(paths) > 10:
        return {"error": "一次最多上传10张图片"}

    screenshot_dir = os.environ.get('SCREENSHOT_DIR', '')
    resolved_paths = []
    for fp in paths:
        if os.sep not in fp and '/' not in fp and screenshot_dir:
            fp = os.path.join(screenshot_dir, fp)
        else:
            fp = _resolve_screenshot_path(fp)
        if not os.path.exists(fp):
            available_files = []
            if screenshot_dir and os.path.isdir(screenshot_dir):
                try:
                    available_files = sorted(
                        name for name in os.listdir(screenshot_dir)
                        if not name.startswith('.')
                    )[:20]
                except OSError:
                    available_files = []
            return {
                "error": f"文件不存在: {fp}",
                "screenshot_dir": screenshot_dir,
                "available_files": available_files,
            }
        resolved_paths.append(fp)

    url = f"{BASE_URL}/api/projects/{project_id}/testcases/{case_id}/upload-screenshots/"
    mime_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif'}

    try:
        files = []
        file_handles = []
        for fp in resolved_paths:
            ext = os.path.splitext(fp)[1].lower()
            content_type = mime_types.get(ext, 'image/png')
            f = open(fp, 'rb')
            file_handles.append(f)
            files.append(('screenshots', (os.path.basename(fp), f, content_type)))

        data = {'title': title or '批量上传截图'}
        if description: data['description'] = description
        if step_number is not None: data['step_number'] = str(step_number)
        if page_url: data['page_url'] = page_url

        resp = requests.post(url, headers=HEADERS, files=files, data=data)
        resp.raise_for_status()

        for f in file_handles:
            f.close()

        return {"message": f"成功上传 {len(resolved_paths)} 张截图"}
    except Exception as e:
        for f in file_handles:
            try: f.close()
            except: pass
        return {"error": str(e)}


def _parse_steps(steps_str):
    """解析 steps JSON，支持容错，自动修复常见格式问题"""
    if not steps_str:
        return []

    # 先尝试直接解析
    try:
        parsed = json.loads(steps_str)
        if isinstance(parsed, list):
            return parsed
        return [parsed] if isinstance(parsed, dict) else []
    except json.JSONDecodeError:
        pass

    # 尝试修复：给没有引号的键名加上引号
    import re
    fixed = steps_str
    # 匹配 {key: 或 ,key: 形式的未加引号键名
    fixed = re.sub(r'([{,])\s*(\w+)\s*:', r'\1"\2":', fixed)
    # 匹配未加引号的字符串值（排除数字、布尔值、null）
    def quote_value(m):
        val = m.group(1).strip()
        suffix = m.group(2)
        if re.match(r'^-?\d+\.?\d*$', val) or val in ('true', 'false', 'null'):
            return f':{val}{suffix}'
        return f':"{val}"{suffix}'
    fixed = re.sub(r':\s*([^",\[\]{}][^,\[\]{}]*?)([,}\]])', quote_value, fixed)

    try:
        parsed = json.loads(fixed)
        if isinstance(parsed, list):
            return parsed
        return [parsed] if isinstance(parsed, dict) else []
    except json.JSONDecodeError as e:
        return {"error": f"steps JSON 格式错误，无法解析: {str(e)}。正确格式: [{{\"step_number\":1,\"description\":\"...\",\"expected_result\":\"...\"}}]"}


# Action 路由
ACTIONS = {
    "get_projects": lambda args: get_projects(),
    "get_modules": lambda args: get_modules(args.project_id),
    "get_module_id": lambda args: get_module_id(args.project_id, args.module_name),
    "get_levels": lambda args: get_levels(),
    "get_testcases": lambda args: get_testcases(args.project_id, args.module_id),
    "get_testcase_detail": lambda args: get_testcase_detail(args.project_id, args.case_id),
    "get_case_details": lambda args: get_case_details(args.project_id, args.case_id),
    "get_test_result": lambda args: get_test_result(args.project_id, args.case_id),
    "execute_test_case": lambda args: execute_test_case(args.project_id, args.case_id, args.module_id),
    "add_testcase": lambda args: (
        _parse_steps(args.steps) if isinstance(_parse_steps(args.steps), dict) else
        add_testcase(
            args.project_id, args.module_id, args.name, args.level,
            args.precondition or "", _parse_steps(args.steps), args.notes or "",
            args.review_status or "pending_review", args.test_type or "functional"
        )
    ),
    "edit_testcase": lambda args: (
        _parse_steps(args.steps) if args.steps and isinstance(_parse_steps(args.steps), dict) else
        edit_testcase(
            args.project_id, args.case_id, args.name, args.level, args.module_id,
            args.precondition, _parse_steps(args.steps) if args.steps else None, args.notes,
            args.review_status, args.test_type, args.is_optimization
        )
    ),
    "upload_screenshot": lambda args: upload_screenshot(
        args.project_id, args.case_id, args.file_path or args.screenshot_path, args.title,
        args.description or "", args.step_number, args.page_url or ""
    ),
    "upload_screenshots": lambda args: upload_screenshots(
        args.project_id, args.case_id, args.file_paths or args.screenshot_paths, args.title,
        args.description or "", args.step_number, args.page_url or ""
    ),
}


def main():
    parser = argparse.ArgumentParser(description="WHartTest 测试管理平台工具", allow_abbrev=False)
    parser.add_argument("--action", required=True, choices=ACTIONS.keys(), help="要执行的操作")
    parser.add_argument("--project_id", type=int, help="项目ID")
    parser.add_argument("--module_id", type=int, help="模块ID")
    parser.add_argument("--module_name", help="模块名称")
    parser.add_argument("--case_id", type=int, help="用例ID")
    parser.add_argument("--name", help="用例名称")
    parser.add_argument("--level", help="用例等级 (P0/P1/P2/P3)")
    parser.add_argument("--precondition", help="前置条件")
    parser.add_argument("--steps", help="用例步骤 (JSON格式)")
    parser.add_argument("--notes", help="备注")
    parser.add_argument("--file_path", help="文件路径（单张上传）")
    parser.add_argument("--screenshot_path", help="兼容旧参数名，等价于 --file_path")
    parser.add_argument("--file_paths", help="文件路径列表（批量上传，逗号分隔）")
    parser.add_argument("--screenshot_paths", help="兼容旧参数名，等价于 --file_paths")
    parser.add_argument("--title", help="标题")
    parser.add_argument("--description", help="描述")
    parser.add_argument("--step", type=int, help="兼容旧参数名，等价于 --step_number")
    parser.add_argument("--step_number", type=int, help="步骤编号")
    parser.add_argument("--page_url", help="页面URL")
    parser.add_argument("--review_status", help="审核状态 (pending_review/approved/needs_optimization/optimization_pending_review/unavailable)")
    parser.add_argument("--test_type", help="测试类型 (smoke/functional/boundary/exception/permission/security/compatibility)", default="functional")
    parser.add_argument("--is_optimization", action="store_true", help="是否为优化操作（自动设置状态为optimization_pending_review）")

    args = parser.parse_args()
    if args.step_number is None and args.step is not None:
        args.step_number = args.step

    result = ACTIONS[args.action](args)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 如果结果包含 error 字段，返回非零退出码
    if isinstance(result, dict) and "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()

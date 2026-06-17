import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from api_automation.models import (
    ApiDefinition,
    ApiEnvironmentConfig,
    ApiExecutionRecord,
    ApiModule,
    ApiScenario,
    ApiScenarioStep,
    ApiTestCase,
)
from api_automation.services import _execute_api_record, execute_api_scenario
from projects.models import Project


BASE_URL = "https://mss-admin-dev.marchbu.com"
COMMON_IGNORE_PATTERNS = [
    "/api/v1/auth/",
    "/api/v1/admin/portals/",
    "/api/v1/admin/portals?",
    "/api/v1/admin/import-tasks/active",
    "/api/v1/admin/export-tasks/active",
    "/api/v1/help-center/upload-tasks/active",
    "/api/v1/admin/task-assignments/pending-count",
    "/api/v1/im/conversations",
    "/api/v1/im/contacts",
]
MODULE_RULES = {
    "profile": ["/api/v1/im/me"],
    "notifications": ["/api/v1/admin/notifications"],
    "dashboard": ["/api/v1/admin/dashboard/tactical-overview"],
    "reports": ["/api/v1/admin/reports", "/api/v1/admin/crises/snapshots"],
    "crises": ["/api/v1/admin/crises?page", "/api/v1/admin/crises?", "/api/v1/admin/crises/"],
    "users": ["/api/v1/admin/admin-users", "/api/v1/admin/portal-users", "/api/v1/admin/users"],
    "roles": ["/api/v1/admin/roles"],
    "departments": ["/api/v1/admin/departments"],
    "permission-grants": ["/api/v1/admin/permission-grants"],
    "audit-logs": ["/api/v1/admin/audit-logs"],
    "settings": ["/api/v1/admin/settings", "/api/v1/admin/system-settings"],
    "file-verification": ["/api/v1/admin/evidence-verifications/outbox", "/api/v1/admin/file-verification"],
    "evidence-verification": ["/api/v1/admin/evidence-verifications/outbox", "/api/v1/admin/evidence-verification"],
    "evidence-inbox": ["/api/v1/admin/evidence-inbox"],
    "internal-direct-inbox": ["/api/v1/admin/internal-direct-inbox"],
    "my-tasks": ["/api/v1/admin/my-tasks"],
    "incidents": ["/api/v1/admin/incidents/"],
    "early-feedback": ["/api/v1/admin/early-review/"],
    "portal-administration": ["/api/v1/admin/portal-"],
    "admin-tools": ["/api/v1/admin/admin-tools"],
    "showcase": ["/api/v1/admin/showcase"],
}
DISPLAY_NAMES = {
    "profile": "Current User Profile",
    "notifications": "Notifications",
    "dashboard": "Dashboard Tactical Overview",
    "reports": "Reports Summary",
    "crises": "Crises List",
    "users": "Users List",
    "roles": "Roles List",
    "departments": "Departments List",
    "permission-grants": "Permission Grants",
    "audit-logs": "Audit Logs",
    "settings": "Settings Overview",
    "file-verification": "Evidence Verification Outbox",
    "evidence-verification": "Evidence Verification Outbox",
    "evidence-inbox": "Evidence Inbox",
    "internal-direct-inbox": "Internal Direct Inbox",
    "my-tasks": "My Tasks",
    "incidents": "Incidents Overview",
    "early-feedback": "Early Feedback Badge",
    "portal-administration": "Portal Administration",
    "admin-tools": "Admin Tools",
    "showcase": "Showcase",
}
MODULE_ORDER = [
    "profile",
    "notifications",
    "dashboard",
    "reports",
    "crises",
    "incidents",
    "users",
    "roles",
    "departments",
    "permission-grants",
    "settings",
    "file-verification",
    "evidence-verification",
    "evidence-inbox",
    "internal-direct-inbox",
    "my-tasks",
    "early-feedback",
    "portal-administration",
    "admin-tools",
    "showcase",
]
TYPE_NAMES = {
    type(None): "null",
    bool: "boolean",
    int: "number",
    float: "number",
    str: "string",
    list: "array",
    dict: "object",
}


def normalize_path(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path


def tab_to_module_name(tab: str) -> str | None:
    if not tab:
        return None
    path = urlparse(tab).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return None
    last = segments[-1]
    return {
        "admin-users": "users",
        "portal-users": "users",
        "portal-roles": "roles",
    }.get(last, last)


def cookie_map(cookie_items):
    return {item["name"]: item["value"] for item in cookie_items or [] if item.get("name")}


def env_headers_from_cookies(cookie_items):
    cookies = cookie_map(cookie_items)
    cookie_header = "; ".join(f"{name}={value}" for name, value in cookies.items())
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{BASE_URL}/",
    }
    access_token = cookies.get("SAFAR_ACCESS_TOKEN")
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    xsrf = cookies.get("XSRF_TOKEN")
    if xsrf:
        headers["X-XSRF-Token"] = xsrf
        headers["X-CSRF-Token"] = xsrf
    if cookie_header:
        headers["Cookie"] = cookie_header
    return headers


def is_common_noise(path: str) -> bool:
    return any(pattern in path for pattern in COMMON_IGNORE_PATTERNS)


def dedupe_apis(raw_apis):
    seen = set()
    cleaned = []
    for item in raw_apis or []:
        method = (item.get("method") or "GET").upper()
        path = normalize_path(item.get("url") or "")
        if not path.startswith("/api/v1/"):
            continue
        key = (method, path, item.get("tab") or "")
        if key in seen:
            continue
        seen.add(key)
        cleaned.append({
            "method": method,
            "path": path,
            "tab": item.get("tab") or "",
            "status": item.get("status") or 0,
        })
    return cleaned


def module_display_name(module_name: str, path: str) -> str:
    if module_name == "reports" and "/snapshots" in path:
        return "Crisis Snapshots"
    if module_name == "crises" and path.startswith("/api/v1/admin/crises?page"):
        return "Crises List"
    if module_name == "users" and "admin-users" in path:
        return "Admin Users List"
    if module_name == "incidents" and "/facets/" in path:
        return "Incident Facet Overview"
    if module_name == "early-feedback" and "/badge" in path:
        return "Early Feedback Badge"
    return DISPLAY_NAMES.get(module_name, module_name.replace("-", " ").title())


def pick_core_api(module_name: str, apis: list[dict]) -> dict | None:
    candidates = []
    for item in apis:
        path = item["path"]
        if is_common_noise(path):
            if module_name not in {"profile", "notifications", "dashboard", "file-verification", "evidence-verification", "early-feedback"}:
                continue
            if module_name == "profile" and path != "/api/v1/im/me":
                continue
            if module_name == "notifications" and path != "/api/v1/admin/notifications":
                continue
            if module_name == "dashboard" and "/api/v1/admin/dashboard/tactical-overview" not in path:
                continue
            if module_name in {"file-verification", "evidence-verification"} and "/api/v1/admin/evidence-verifications/outbox" not in path:
                continue
            if module_name == "early-feedback" and "/api/v1/admin/early-review/" not in path:
                continue
        score = 0
        mapped_tab = tab_to_module_name(item["tab"])
        if mapped_tab == module_name:
            score += 40
        rule_hit = False
        for index, rule in enumerate(MODULE_RULES.get(module_name, [])):
            if rule in path:
                rule_hit = True
                score += 100 - index * 10
        if module_name in path:
            score += 5
        if module_name == "reports" and ("/reports" in path or "/snapshots" in path):
            score += 15
        if module_name == "crises" and "/crises/snapshots" in path:
            score -= 20
        if module_name == "portal-administration" and any(key in path for key in ["/users", "/roles", "/departments", "/permission-grants"]):
            score += 10
        if module_name == "dashboard" and "portal=" in path:
            score += 8
        if score > 0 and (rule_hit or module_name not in MODULE_RULES):
            candidates.append((score, item))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (-row[0], row[1]["path"]))
    return candidates[0][1]


def infer_type_name(value):
    if value is None:
        return "null"
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
    return type(value).__name__.lower()


def build_stable_assertions(response_data):
    assertions = [{"type": "status_code", "operator": "eq", "expected": 200}]
    payload = response_data or {}
    body = payload.get("json")
    if body is None and payload.get("text"):
        try:
            body = json.loads(payload.get("text") or "null")
        except Exception:
            body = None
    header_content_type = str((payload.get("headers") or {}).get("content-type") or "")
    if "application/json" in header_content_type:
        assertions.append({"type": "header_value", "path": "content-type", "operator": "contains", "expected": "application/json"})
    if isinstance(body, dict):
        if isinstance(body.get("items"), list):
            assertions.append({"type": "json_path_type", "path": "items", "operator": "eq", "expected": "array"})
            if body["items"] and isinstance(body["items"][0], dict):
                for key in ("id", "crisisNo", "status", "title", "name", "type"):
                    if key in body["items"][0] and body["items"][0][key] not in (None, ""):
                        assertions.append({
                            "type": "json_path_type",
                            "path": f"items[0].{key}",
                            "operator": "eq",
                            "expected": infer_type_name(body["items"][0][key]),
                        })
                        break
            return assertions
        if isinstance(body.get("content"), list):
            assertions.append({"type": "json_path_type", "path": "content", "operator": "eq", "expected": "array"})
            return assertions
        if "data" in body and body["data"] is not None:
            assertions.append({
                "type": "json_path_type",
                "path": "data",
                "operator": "eq",
                "expected": infer_type_name(body["data"]),
            })
            return assertions
        if {"forReviewer", "forAuthor"} & set(body.keys()):
            for key in ("forReviewer", "forAuthor"):
                if key in body:
                    assertions.append({
                        "type": "json_path_type",
                        "path": key,
                        "operator": "eq",
                        "expected": infer_type_name(body[key]),
                    })
            return assertions
        if "stats" in body and isinstance(body.get("stats"), dict):
            assertions.append({"type": "json_path_type", "path": "portal", "operator": "eq", "expected": infer_type_name(body.get("portal"))})
            assertions.append({"type": "json_path_type", "path": "stats", "operator": "eq", "expected": "object"})
            return assertions
        for key in ("id", "name", "status", "portal", "agency", "teamCode"):
            if key in body and body[key] not in (None, ""):
                assertions.append({
                    "type": "json_path_type",
                    "path": key,
                    "operator": "eq",
                    "expected": infer_type_name(body[key]),
                })
                if len(assertions) >= 3:
                    break
        return assertions
    if isinstance(body, list):
        assertions.append({"type": "json_path_type", "path": "", "operator": "eq", "expected": "array"})
        if body and isinstance(body[0], dict):
            for key in ("id", "type", "title", "status", "link"):
                if key in body[0] and body[0][key] not in (None, ""):
                    assertions.append({
                        "type": "json_path_type",
                        "path": f"[0].{key}",
                        "operator": "eq",
                        "expected": infer_type_name(body[0][key]),
                    })
                    break
    return assertions


def build_extractors(module_name: str, response_data):
    payload = response_data or {}
    body = payload.get("json")
    if body is None and payload.get("text"):
        try:
            body = json.loads(payload.get("text") or "null")
        except Exception:
            body = None
    extractors = []
    if isinstance(body, dict):
        if module_name == "profile":
            for key in ("id", "agency", "dept"):
                if key in body and body[key] not in (None, ""):
                    extractors.append({
                        "name": f"profile_{key}",
                        "source": "json_path",
                        "path": key,
                    })
        elif isinstance(body.get("items"), list) and body["items"] and isinstance(body["items"][0], dict):
            first = body["items"][0]
            for key in ("id", "crisisNo", "status"):
                if key in first and first[key] not in (None, ""):
                    extractors.append({
                        "name": f"first_{module_name.replace('-', '_')}_{key}",
                        "source": "json_path",
                        "path": f"items[0].{key}",
                    })
        elif "id" in body and body["id"] not in (None, ""):
            extractors.append({"name": f"{module_name.replace('-', '_')}_id", "source": "json_path", "path": "id"})
    elif isinstance(body, list) and body and isinstance(body[0], dict):
        for key in ("id", "link"):
            if key in body[0] and body[0][key] not in (None, ""):
                extractors.append({
                    "name": f"first_{module_name.replace('-', '_')}_{key}",
                    "source": "json_path",
                    "path": f"[0].{key}",
                })
    return extractors[:2]


class Command(BaseCommand):
    help = "将浏览器抓取的 MSS 角色接口按 角色 -> tab -> 接口 导入接口自动化，并可同步验证。"

    def add_arguments(self, parser):
        parser.add_argument("--capture", default="/tmp/mss_role_capture.json")
        parser.add_argument("--project", default="MSS")
        parser.add_argument("--username", default="admin")
        parser.add_argument("--verify", action="store_true")
        parser.add_argument("--roles", nargs="*")

    def handle(self, *args, **options):
        capture_path = Path(options["capture"])
        if not capture_path.exists():
            raise CommandError(f"抓取文件不存在: {capture_path}")

        data = json.loads(capture_path.read_text())
        if not isinstance(data, dict):
            raise CommandError("抓取文件格式不正确，预期为 role->payload 的字典。")

        project = Project.objects.filter(name=options["project"]).first()
        if not project:
            raise CommandError(f"项目不存在: {options['project']}")
        user = get_user_model().objects.filter(username=options["username"]).first()
        if not user:
            raise CommandError(f"用户不存在: {options['username']}")

        role_names = options["roles"] or list(data.keys())
        role_case_map: dict[str, list[int]] = defaultdict(list)

        self._migrate_admin_baseline(project, user)
        ApiScenario.objects.filter(project=project, name__regex=r"^01 .* Core Flow$").delete()

        for role_name in role_names:
            if role_name not in data:
                self.stdout.write(self.style.WARNING(f"跳过未抓取角色: {role_name}"))
                continue
            self.stdout.write(f"[import] {role_name}")
            case_ids = self._import_role(project, user, role_name, data[role_name])
            role_case_map[role_name].extend(case_ids)

        self._dedupe_cases_by_module_and_path(project)
        if options["verify"]:
            role_case_map = self._verify_cases(project, role_case_map)
        self._sync_role_scenarios(project, user, role_case_map)
        self._prune_stale_role_cases(project, role_names, role_case_map)
        if options["verify"]:
            self._verify_scenarios(project, role_case_map)

        self.stdout.write(self.style.SUCCESS("MSS 角色接口导入完成"))

    def _import_role(self, project, user, role_name: str, payload: dict) -> list[int]:
        top_module = ApiModule.objects.filter(project=project, name=role_name, parent__isnull=True).first()
        if not top_module:
            self.stdout.write(self.style.WARNING(f"未找到角色模块，跳过: {role_name}"))
            return []
        env = self._upsert_environment(project, user, role_name, payload.get("cookies") or [])
        children = {item.name: item for item in ApiModule.objects.filter(parent=top_module)}
        apis = dedupe_apis(payload.get("apis") or [])

        first_tab_modules = []
        for link in payload.get("links") or []:
            module_name = tab_to_module_name(link.get("href") or "")
            if module_name and module_name in children and module_name not in first_tab_modules:
                first_tab_modules.append(module_name)
            if len(first_tab_modules) >= 3:
                break
        target_modules = []
        for module_name in ["profile", "notifications", "dashboard", *first_tab_modules]:
            if module_name in children and module_name not in target_modules:
                target_modules.append(module_name)
        for module_name in MODULE_ORDER:
            if module_name in children and module_name not in target_modules:
                candidate = pick_core_api(module_name, apis)
                if candidate:
                    target_modules.append(module_name)

        case_ids = []
        seq = 1
        used_paths = set()
        for module_name in target_modules:
            candidate = pick_core_api(module_name, apis)
            if not candidate:
                continue
            if module_name == "crises" and "/snapshots" in candidate["path"]:
                continue
            if candidate["path"] in used_paths:
                continue
            display_name = module_display_name(module_name, candidate["path"])
            case_name = f"{seq:02d} {display_name}"
            definition, _ = ApiDefinition.objects.update_or_create(
                project=project,
                module=children[module_name],
                method=candidate["method"],
                path=candidate["path"],
                defaults={
                    "name": display_name,
                    "summary": display_name,
                    "description": f"{role_name} / {module_name} 页面抓取到的核心接口",
                    "tags": [role_name, module_name, "mss-capture"],
                    "source": "mss_capture",
                    "creator": user,
                },
            )
            case, _ = ApiTestCase.objects.update_or_create(
                project=project,
                module=children[module_name],
                name=case_name,
                defaults={
                    "definition": definition,
                    "environment": env,
                    "method": candidate["method"],
                    "path": candidate["path"],
                    "headers": {},
                    "query_params": {},
                    "body": {},
                    "pre_script": "",
                    "post_script": "",
                    "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
                    "extractors": [],
                    "source": "mss_capture",
                    "creator": user,
                },
            )
            case_ids.append(case.id)
            used_paths.add(candidate["path"])
            seq += 1
        return case_ids

    def _upsert_environment(self, project, user, role_name: str, cookie_items: list[dict]):
        env_name = f"MSS {role_name} Dev"
        defaults = {
            "base_url": BASE_URL,
            "headers": env_headers_from_cookies(cookie_items),
            "variables": {"role": role_name},
            "creator": user,
        }
        env, _ = ApiEnvironmentConfig.objects.update_or_create(project=project, name=env_name, defaults=defaults)
        return env

    def _sync_role_scenarios(self, project, user, role_case_map: dict[str, list[int]]):
        for role_name, case_ids in role_case_map.items():
            if len(case_ids) < 2:
                continue
            top_module = ApiModule.objects.filter(project=project, name=role_name, parent__isnull=True).first()
            if not top_module:
                continue
            scenario, _ = ApiScenario.objects.update_or_create(
                project=project,
                module=top_module,
                name=f"01 {role_name} Core Flow",
                defaults={
                    "description": f"{role_name} 角色的核心接口串联冒烟场景",
                    "creator": user,
                },
            )
            scenario.steps.all().delete()
            steps = []
            for index, case in enumerate(ApiTestCase.objects.filter(id__in=case_ids).order_by("name"), start=1):
                steps.append(ApiScenarioStep(
                    scenario=scenario,
                    order=index,
                    test_case=case,
                    name=case.name,
                    is_enabled=True,
                    stop_on_failure=True,
                ))
            ApiScenarioStep.objects.bulk_create(steps)

    def _verify_cases(self, project, role_case_map: dict[str, list[int]]):
        passed_case_map: dict[str, list[int]] = defaultdict(list)
        all_case_ids = [case_id for case_ids in role_case_map.values() for case_id in case_ids]
        cases_by_id = {
            case.id: case
            for case in ApiTestCase.objects.filter(project=project, id__in=all_case_ids).select_related("environment", "module__parent")
        }
        for role_name, case_ids in role_case_map.items():
            for case_id in case_ids:
                case = cases_by_id.get(case_id)
                if not case:
                    continue
                if not self._verify_single_case(project, case):
                    self.stdout.write(self.style.WARNING(f"[skip] {role_name} / {case.name}"))
                    if case.source == "mss_capture":
                        case.delete()
                    continue
                passed_case_map[role_name].append(case.id)
        return passed_case_map

    def _verify_single_case(self, project, case):
        record = ApiExecutionRecord.objects.create(
            project=project,
            test_case=case,
            environment=case.environment,
            status=0,
            trigger_type="manual",
        )
        result = _execute_api_record(record)
        if result.get("status") != "success":
            return False
        record.refresh_from_db()
        response_data = deepcopy(record.response_data or {})
        response_data["json"] = self._safe_json(response_data.get("text"))
        case.assertions = build_stable_assertions(response_data)
        case.extractors = build_extractors(case.module.name, response_data)
        case.save(update_fields=["assertions", "extractors", "updated_at"])
        verify_record = ApiExecutionRecord.objects.create(
            project=project,
            test_case=case,
            environment=case.environment,
            status=0,
            trigger_type="manual",
        )
        verify_result = _execute_api_record(verify_record)
        if verify_result.get("status") != "success":
            return False
        return True

    def _verify_scenarios(self, project, role_case_map: dict[str, list[int]]):
        for scenario in ApiScenario.objects.filter(project=project, name__regex=r"^01 .* Core Flow$").select_related("module"):
            env = ApiEnvironmentConfig.objects.filter(project=project, name=f"MSS {scenario.module.name} Dev").first()
            record = scenario.execution_records.create(
                project=project,
                environment=env,
                status=0,
                trigger_type="manual",
            )
            result = execute_api_scenario(record.id)
            if result.get("status") != "success":
                raise CommandError(f"场景验证失败: {scenario.name}")

    def _migrate_admin_baseline(self, project, user):
        admin_module = ApiModule.objects.filter(project=project, name="admin", parent__isnull=True).first()
        if not admin_module:
            return
        children = {item.name: item for item in ApiModule.objects.filter(parent=admin_module)}
        mappings = {
            "Create Crisis - real MSS": ("crises", "05 Create Crisis"),
            "List Crises - real MSS": ("crises", "04 Crises List"),
            "Dashboard Tactical Overview - real MSS": ("dashboard", "03 Dashboard Tactical Overview"),
            "Notifications - real MSS": ("notifications", "02 Notifications"),
            "Current User Profile - real MSS": ("profile", "01 Current User Profile"),
        }
        for case in ApiTestCase.objects.filter(project=project, name__in=mappings.keys()):
            module_name, new_name = mappings[case.name]
            if module_name in children:
                case.module = children[module_name]
                case.name = new_name
                case.save(update_fields=["module", "name"])
        scenario = ApiScenario.objects.filter(project=project, name="01 Admin Crisis Flow").first()
        if scenario and "crises" in children:
            scenario.module = children["crises"]
            scenario.save(update_fields=["module"])
        for module_name, case_name in [
            ("profile", "01 Current User Profile"),
            ("notifications", "02 Notifications"),
            ("dashboard", "03 Dashboard Tactical Overview"),
            ("crises", "04 Crises List"),
            ("crises", "05 Create Crisis"),
        ]:
            module = children.get(module_name)
            if not module:
                continue
            duplicates = list(ApiTestCase.objects.filter(project=project, module=module, name=case_name).order_by("id"))
            if len(duplicates) > 1:
                keeper = duplicates[0]
                for extra in duplicates[1:]:
                    extra.delete()
        legacy_module = ApiModule.objects.filter(project=project, name="Crisis Management", parent__isnull=True).first()
        if legacy_module and not legacy_module.children.exists() and not legacy_module.definitions.exists() and not legacy_module.testcases.exists() and not legacy_module.scenarios.exists():
            legacy_module.delete()

    def _dedupe_cases_by_module_and_path(self, project):
        grouped = defaultdict(list)
        for case in ApiTestCase.objects.filter(project=project).select_related("module").order_by("id"):
            grouped[(case.module_id, case.path)].append(case)
        for (_module_id, _path), items in grouped.items():
            if len(items) <= 1:
                continue
            items.sort(key=lambda obj: (obj.name, obj.id))
            keeper = items[0]
            for extra in items[1:]:
                if extra.source == "mss_capture" and not extra.scenario_steps.exists():
                    extra.delete()

    def _prune_stale_role_cases(self, project, role_names, role_case_map):
        allowed_ids = {case_id for case_ids in role_case_map.values() for case_id in case_ids}
        stale_cases = ApiTestCase.objects.filter(
            project=project,
            source="mss_capture",
            module__parent__name__in=role_names,
        ).exclude(id__in=allowed_ids)
        for case in stale_cases:
            if not case.scenario_steps.exists():
                case.delete()

    def _safe_json(self, text):
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return None

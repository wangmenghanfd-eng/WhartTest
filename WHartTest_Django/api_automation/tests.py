import json
from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from projects.models import Project, ProjectMember

from .models import ApiBatchExecutionRecord, ApiDefinition, ApiEnvironmentConfig, ApiExecutionRecord, ApiModule, ApiPublicData, ApiScenario, ApiScenarioExecutionRecord, ApiScenarioStep, ApiScript, ApiTestCase
from .services import execute_api_case, execute_api_scenario, import_openapi_spec, load_openapi_spec, update_batch_summary


User = get_user_model()


OPENAPI_SAMPLE = """
openapi: 3.0.0
info:
  title: Demo API
  version: 1.0.0
servers:
  - url: https://api.example.com
paths:
  /users:
    get:
      operationId: listUsers
      summary: 查询用户列表
      tags: [用户管理]
      responses:
        '200':
          description: ok
"""


class ApiAutomationServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api_tester", password="test123456")
        self.project = Project.objects.create(name="api-project", creator=self.user)

    def test_import_openapi_spec_creates_definition_and_case(self):
        spec = load_openapi_spec(OPENAPI_SAMPLE)
        result = import_openapi_spec(self.project, self.user, spec, create_cases=True)

        self.assertEqual(result["created_definitions"], 1)
        self.assertEqual(result["created_cases"], 1)
        definition = ApiDefinition.objects.get(project=self.project, method="GET", path="/users")
        self.assertEqual(definition.name, "查询用户列表")
        self.assertEqual(definition.module.name, "用户管理")
        case = ApiTestCase.objects.get(project=self.project, definition=definition)
        self.assertEqual(case.method, "GET")
        self.assertEqual(case.path, "/users")

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_case_uses_environment_and_updates_record(self, client_cls):
        module = ApiModule.objects.create(project=self.project, name="用户管理", creator=self.user)
        env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="测试环境",
            base_url="https://api.example.com",
            is_default=True,
            creator=self.user,
        )
        ApiPublicData.objects.create(project=self.project, key="token", value="abc123", is_enabled=True, creator=self.user)
        case = ApiTestCase.objects.create(
            project=self.project,
            module=module,
            environment=env,
            name="获取用户列表",
            method="GET",
            path="/users",
            headers={"Authorization": "Bearer ${{token}}"},
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            creator=self.user,
        )
        record = ApiExecutionRecord.objects.create(
            project=self.project,
            test_case=case,
            environment=env,
            status=0,
            trigger_type="manual",
            executor=self.user,
        )

        response = httpx.Response(200, text='{"ok": true}', request=httpx.Request("GET", "https://api.example.com/users"))
        client_cls.return_value.__enter__.return_value.request.return_value = response

        result = execute_api_case(record.id)

        self.assertEqual(result["status"], "success")
        record.refresh_from_db()
        case.refresh_from_db()
        self.assertEqual(record.status, 2)
        self.assertEqual(case.status, 2)
        self.assertIn("status_code", record.response_data["assertions"][0]["type"])
        self.assertEqual(record.request_data["headers"]["Authorization"], "Bearer abc123")

    def test_update_batch_summary_marks_partial_failure(self):
        module = ApiModule.objects.create(project=self.project, name="用户管理", creator=self.user)
        case = ApiTestCase.objects.create(project=self.project, module=module, name="接口1", method="GET", path="/users", creator=self.user)
        batch = ApiBatchExecutionRecord.objects.create(project=self.project, name="批次1", total_cases=2, executor=self.user)
        ApiExecutionRecord.objects.create(project=self.project, test_case=case, batch=batch, status=2, trigger_type="manual", executor=self.user)
        ApiExecutionRecord.objects.create(project=self.project, test_case=case, batch=batch, status=3, trigger_type="manual", executor=self.user)

        update_batch_summary(batch.id)

        batch.refresh_from_db()
        self.assertEqual(batch.status, 3)
        self.assertEqual(batch.passed_cases, 1)
        self.assertEqual(batch.failed_cases, 1)

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_scenario_shares_extracted_variables(self, client_cls):
        module = ApiModule.objects.create(project=self.project, name="流程模块", creator=self.user)
        env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="测试环境",
            base_url="https://api.example.com",
            creator=self.user,
        )
        login_case = ApiTestCase.objects.create(
            project=self.project,
            module=module,
            environment=env,
            name="01 登录",
            method="POST",
            path="/login",
            extractors=[{"name": "token", "source": "json_path", "path": "token"}],
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            creator=self.user,
        )
        profile_case = ApiTestCase.objects.create(
            project=self.project,
            module=module,
            environment=env,
            name="02 用户信息",
            method="GET",
            path="/me",
            headers={"Authorization": "Bearer ${{token}}"},
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            creator=self.user,
        )
        scenario = ApiScenario.objects.create(project=self.project, module=module, name="登录流程", creator=self.user)
        ApiScenarioStep.objects.create(scenario=scenario, order=1, test_case=login_case, name="登录")
        ApiScenarioStep.objects.create(scenario=scenario, order=2, test_case=profile_case, name="查询用户")
        scenario_record = ApiScenarioExecutionRecord.objects.create(
            project=self.project,
            scenario=scenario,
            environment=env,
            status=0,
            trigger_type="manual",
            executor=self.user,
        )

        responses = [
            httpx.Response(200, json={"token": "abc123"}, request=httpx.Request("POST", "https://api.example.com/login")),
            httpx.Response(200, json={"name": "Alice"}, request=httpx.Request("GET", "https://api.example.com/me")),
        ]
        client_cls.return_value.__enter__.return_value.request.side_effect = responses

        result = execute_api_scenario(scenario_record.id)

        self.assertEqual(result["status"], "success")
        scenario_record.refresh_from_db()
        self.assertEqual(scenario_record.status, 2)
        second_record = ApiExecutionRecord.objects.filter(test_case=profile_case).latest("id")
        self.assertEqual(second_record.request_data["headers"]["Authorization"], "Bearer abc123")


class ApiAutomationViewSetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="api_view_tester",
            password="test123456",
            email="api_view_tester@example.com",
        )
        self.project = Project.objects.create(name="api-view-project", creator=self.user)
        ProjectMember.objects.create(project=self.project, user=self.user, role="owner")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.module = ApiModule.objects.create(project=self.project, name="用户管理", creator=self.user)
        self.env_a = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="环境A",
            base_url="https://api.example.com",
            creator=self.user,
        )
        self.env_b = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="环境B",
            base_url="https://api.example.com",
            creator=self.user,
        )

    def test_definition_list_supports_search(self):
        ApiDefinition.objects.create(
            project=self.project,
            module=self.module,
            name="创建危机",
            method="POST",
            path="/api/v1/admin/crises",
            creator=self.user,
        )
        ApiDefinition.objects.create(
            project=self.project,
            module=self.module,
            name="查询报告",
            method="GET",
            path="/api/v1/reports",
            creator=self.user,
        )

        response = self.client.get("/api/api-automation/definitions/", {"project": self.project.id, "search": "crises"})
        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["path"], "/api/v1/admin/crises")

    def test_case_list_supports_environment_filter(self):
        ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env_a,
            name="环境A用例",
            method="GET",
            path="/a",
            creator=self.user,
        )
        ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env_b,
            name="环境B用例",
            method="GET",
            path="/b",
            creator=self.user,
        )

        response = self.client.get("/api/api-automation/testcases/", {"project": self.project.id, "environment": self.env_b.id})
        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "环境B用例")

    def test_case_list_supports_parent_module_filter(self):
        child = ApiModule.objects.create(project=self.project, name="子模块", parent=self.module, creator=self.user)
        ApiTestCase.objects.create(
            project=self.project,
            module=child,
            environment=self.env_a,
            name="子模块用例",
            method="GET",
            path="/child",
            creator=self.user,
        )
        response = self.client.get("/api/api-automation/testcases/", {"project": self.project.id, "module": self.module.id})
        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "子模块用例")

    def test_scenario_create_and_execute_endpoint(self):
        case = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env_a,
            name="接口1",
            method="GET",
            path="/users",
            creator=self.user,
        )
        create_resp = self.client.post("/api/api-automation/scenarios/", {
            "project": self.project.id,
            "module": self.module.id,
            "name": "用户场景",
            "description": "冒烟流程",
            "steps": [{"order": 1, "test_case": case.id, "is_enabled": True, "stop_on_failure": True}],
        }, format="json")
        self.assertEqual(create_resp.status_code, 201)
        scenario_id = create_resp.json()["data"]["id"]

        with patch("api_automation.views.execute_api_scenario_task.delay") as delay:
            execute_resp = self.client.post(f"/api/api-automation/scenarios/{scenario_id}/execute/", {}, format="json")
        self.assertEqual(execute_resp.status_code, 200)
        delay.assert_called_once()

    def test_scenario_list_supports_parent_module_filter(self):
        child = ApiModule.objects.create(project=self.project, name="场景子模块", parent=self.module, creator=self.user)
        ApiScenario.objects.create(project=self.project, module=child, name="子模块场景", creator=self.user)
        response = self.client.get("/api/api-automation/scenarios/", {"project": self.project.id, "module": self.module.id})
        self.assertEqual(response.status_code, 200)
        results = response.json()["data"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "子模块场景")

    def test_import_openapi_endpoint_smoke(self):
        response = self.client.post(
            "/api/api-automation/definitions/import-openapi/",
            {
                "project": self.project.id,
                "content": OPENAPI_SAMPLE,
                "create_cases": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["created_definitions"], 1)
        self.assertEqual(response.data["created_cases"], 1)


class ApiServiceHelperTests(TestCase):
    """services 模块内部辅助函数（变量替换、断言、URL 拼接）"""

    def test_render_value_substitutes_strings_dicts_lists(self):
        from .services import _render_value

        variables = {"token": "abc", "user": "Alice"}
        self.assertEqual(_render_value("Bearer ${{token}}", variables), "Bearer abc")
        self.assertEqual(
            _render_value(
                {"Authorization": "Bearer ${{token}}", "X-User": "${{user}}"},
                variables,
            ),
            {"Authorization": "Bearer abc", "X-User": "Alice"},
        )
        self.assertEqual(
            _render_value(["${{user}}", {"k": "${{token}}"}], variables),
            ["Alice", {"k": "abc"}],
        )

    def test_render_value_keeps_unknown_placeholder(self):
        from .services import _render_value
        self.assertEqual(_render_value("hi ${{missing}}", {"x": "1"}), "hi ${{missing}}")

    def test_render_value_passes_through_non_string_primitives(self):
        from .services import _render_value
        self.assertEqual(_render_value(42, {"a": "b"}), 42)
        self.assertIsNone(_render_value(None, {}))

    def test_assert_response_status_code_operators(self):
        from .services import _assert_response

        resp = httpx.Response(
            200,
            text='{"ok": true}',
            request=httpx.Request("GET", "https://x"),
        )
        ok, results = _assert_response(resp, [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "status_code", "operator": "lt", "expected": 500},
            {"type": "status_code", "operator": "in", "expected": [200, 201]},
        ])
        self.assertTrue(ok)
        self.assertTrue(all(r["passed"] for r in results))

    def test_assert_response_body_contains_and_header_exists(self):
        from .services import _assert_response

        resp = httpx.Response(
            200,
            text='{"ok": true}',
            headers={"X-Custom": "1"},
            request=httpx.Request("GET", "https://x"),
        )
        ok, _results = _assert_response(resp, [
            {"type": "body_contains", "expected": "ok"},
            {"type": "header_exists", "expected": "X-Custom"},
        ])
        self.assertTrue(ok)

    def test_assert_response_partial_failure(self):
        from .services import _assert_response

        resp = httpx.Response(
            404,
            text='not found',
            request=httpx.Request("GET", "https://x"),
        )
        ok, results = _assert_response(resp, [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "body_contains", "expected": "not"},
        ])
        self.assertFalse(ok)
        self.assertFalse(results[0]["passed"])
        self.assertTrue(results[1]["passed"])

    def test_assert_response_default_when_no_assertions(self):
        from .services import _assert_response

        resp = httpx.Response(200, text="ok", request=httpx.Request("GET", "https://x"))
        ok, results = _assert_response(resp, [])
        self.assertTrue(ok)
        self.assertEqual(results[0]["type"], "status_code")
        self.assertEqual(results[0]["operator"], "lt")

    def test_build_url_supports_absolute_and_relative(self):
        from .services import _build_url

        env = ApiEnvironmentConfig(base_url="https://api.example.com/v1/")
        self.assertEqual(
            _build_url(None, "https://api.example.com/v1/x"),
            "https://api.example.com/v1/x",
        )
        self.assertEqual(_build_url(env, "/users"), "https://api.example.com/v1/users")
        self.assertEqual(_build_url(env, "users"), "https://api.example.com/v1/users")

    def test_build_url_raises_when_relative_without_base(self):
        from .services import _build_url
        with self.assertRaises(ValueError):
            _build_url(None, "/users")


class ApiPathAccessTests(TestCase):
    """_get_by_path 点路径访问"""

    def test_dot_path_walks_dict(self):
        from .services import _get_by_path
        data = {"data": {"user": {"id": 7, "name": "Alice"}}}
        self.assertEqual(_get_by_path(data, "data.user.name"), "Alice")
        self.assertEqual(_get_by_path(data, "$.data.user.id"), 7)

    def test_index_walks_list(self):
        from .services import _get_by_path
        data = {"items": [{"id": 1}, {"id": 2}]}
        self.assertEqual(_get_by_path(data, "items[1].id"), 2)

    def test_returns_none_for_missing_path(self):
        from .services import _get_by_path
        self.assertIsNone(_get_by_path({"a": 1}, "b.c"))
        self.assertIsNone(_get_by_path([1, 2], "[5]"))
        self.assertIsNone(_get_by_path(None, "a"))


class ApiCompareOperatorTests(TestCase):
    """_compare 各种运算符"""

    def test_equality_operators(self):
        from .services import _compare
        self.assertTrue(_compare("abc", "eq", "abc"))
        self.assertTrue(_compare(7, "eq", "7"))
        self.assertTrue(_compare("abc", "neq", "xyz"))
        self.assertFalse(_compare("abc", "neq", "abc"))

    def test_numeric_operators(self):
        from .services import _compare
        self.assertTrue(_compare(5, "lt", 10))
        self.assertTrue(_compare(10, "lte", 10))
        self.assertTrue(_compare(11, "gt", 10))
        self.assertTrue(_compare(10, "gte", 10))
        self.assertFalse(_compare(10, "gt", 10))

    def test_contains_and_regex(self):
        from .services import _compare
        self.assertTrue(_compare("hello world", "contains", "world"))
        self.assertTrue(_compare("hello world", "not_contains", "xyz"))
        self.assertTrue(_compare("abc123", "regex", r"\d+"))
        self.assertFalse(_compare("abc", "regex", r"\d+"))

    def test_emptiness_operators(self):
        from .services import _compare
        self.assertTrue(_compare(None, "is_empty", None))
        self.assertTrue(_compare("", "is_empty", None))
        self.assertTrue(_compare("x", "is_not_empty", None))
        self.assertFalse(_compare(None, "is_not_empty", None))

    def test_in_and_not_in(self):
        from .services import _compare
        self.assertTrue(_compare("a", "in", ["a", "b"]))
        self.assertFalse(_compare("z", "in", ["a", "b"]))
        self.assertTrue(_compare("z", "not_in", ["a", "b"]))


class ApiJsonPathAssertionTests(TestCase):
    """_assert_response 的 json_path / body_not_contains / header_value"""

    def test_json_path_eq(self):
        from .services import _assert_response

        resp = httpx.Response(
            200,
            text='{"data": {"token": "abc", "user": {"id": 7}}}',
            request=httpx.Request("GET", "https://x"),
        )
        ok, results = _assert_response(resp, [
            {"type": "json_path", "path": "data.token", "operator": "eq", "expected": "abc"},
            {"type": "json_path", "path": "data.user.id", "operator": "gte", "expected": 1},
        ])
        self.assertTrue(ok)
        self.assertTrue(all(r["passed"] for r in results))

    def test_json_path_missing_returns_none_actual(self):
        from .services import _assert_response

        resp = httpx.Response(
            200,
            text='{"data": {}}',
            request=httpx.Request("GET", "https://x"),
        )
        ok, results = _assert_response(resp, [
            {"type": "json_path", "path": "data.missing", "operator": "eq", "expected": "x"},
            {"type": "json_path", "path": "data.missing", "operator": "is_empty", "expected": None},
        ])
        self.assertFalse(ok)
        self.assertFalse(results[0]["passed"])
        self.assertIsNone(results[0]["actual"])
        self.assertTrue(results[1]["passed"])  # is_empty 通过

    def test_body_not_contains(self):
        from .services import _assert_response

        resp = httpx.Response(
            200,
            text='success',
            request=httpx.Request("GET", "https://x"),
        )
        ok, _r = _assert_response(resp, [
            {"type": "body_not_contains", "expected": "error"},
        ])
        self.assertTrue(ok)

    def test_header_value(self):
        from .services import _assert_response

        resp = httpx.Response(
            200,
            text='ok',
            headers={"X-Total": "42"},
            request=httpx.Request("GET", "https://x"),
        )
        ok, _r = _assert_response(resp, [
            {"type": "header_value", "path": "X-Total", "operator": "eq", "expected": "42"},
            {"type": "header_value", "path": "X-Total", "operator": "gt", "expected": 10},
        ])
        self.assertTrue(ok)

    def test_unknown_type_passes_silently(self):
        """未知断言类型不应导致失败（向后兼容）。"""
        from .services import _assert_response
        resp = httpx.Response(200, text="x", request=httpx.Request("GET", "https://x"))
        ok, _r = _assert_response(resp, [
            {"type": "future_unknown", "expected": "x"},
        ])
        self.assertTrue(ok)


class ApiExtractorTests(TestCase):
    """_extract_variables 三种来源 + execute_api_case 集成"""

    def test_extract_json_path(self):
        from .services import _extract_variables
        resp = httpx.Response(
            200,
            text='{"data": {"token": "abc-123", "items": [{"id": 9}]}}',
            request=httpx.Request("GET", "https://x"),
        )
        result = _extract_variables(resp, [
            {"name": "token", "source": "json_path", "path": "data.token"},
            {"name": "first_id", "source": "json_path", "path": "data.items[0].id"},
            {"name": "missing", "source": "json_path", "path": "data.no.such.field"},
        ])
        self.assertEqual(result["token"], "abc-123")
        self.assertEqual(result["first_id"], 9)
        self.assertIsNone(result["missing"])

    def test_extract_header(self):
        from .services import _extract_variables
        resp = httpx.Response(
            200, text="x",
            headers={"X-Request-Id": "rid-7"},
            request=httpx.Request("GET", "https://x"),
        )
        result = _extract_variables(resp, [
            {"name": "rid", "source": "header", "path": "X-Request-Id"},
        ])
        self.assertEqual(result["rid"], "rid-7")

    def test_extract_regex_with_group_and_without(self):
        from .services import _extract_variables
        resp = httpx.Response(
            200, text="user_id=42&token=abc",
            request=httpx.Request("GET", "https://x"),
        )
        result = _extract_variables(resp, [
            {"name": "uid", "source": "regex", "path": r"user_id=(\d+)"},
            {"name": "raw", "source": "regex", "path": r"token=\w+"},
            {"name": "miss", "source": "regex", "path": r"missing-(\d+)"},
            {"name": "skip_no_name", "source": "regex", "path": r"x"},  # name=skip_no_name still works
        ])
        self.assertEqual(result["uid"], "42")
        self.assertEqual(result["raw"], "token=abc")
        self.assertIsNone(result["miss"])

    def test_extract_skips_invalid_entries(self):
        from .services import _extract_variables
        resp = httpx.Response(200, text="x", request=httpx.Request("GET", "https://x"))
        result = _extract_variables(resp, [
            "not_a_dict",
            {"name": "", "source": "json_path", "path": "x"},
            None,
        ])
        self.assertEqual(result, {})

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_case_persists_extracted(self, client_cls):
        user = User.objects.create_user(username="extract_user", password="test123456")
        project = Project.objects.create(name="extract-project", creator=user)
        module = ApiModule.objects.create(project=project, name="m", creator=user)
        env = ApiEnvironmentConfig.objects.create(
            project=project,
            name="E",
            base_url="https://api.example.com",
            is_default=True,
            creator=user,
        )
        case = ApiTestCase.objects.create(
            project=project,
            module=module,
            environment=env,
            name="case",
            method="GET",
            path="/x",
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            extractors=[{"name": "token", "source": "json_path", "path": "data.token"}],
            creator=user,
        )
        record = ApiExecutionRecord.objects.create(
            project=project,
            test_case=case,
            environment=env,
            status=0,
            trigger_type="manual",
            executor=user,
        )
        response = httpx.Response(
            200,
            text='{"data": {"token": "T-123"}}',
            request=httpx.Request("GET", "https://api.example.com/x"),
        )
        client_cls.return_value.__enter__.return_value.request.return_value = response

        execute_api_case(record.id)

        record.refresh_from_db()
        self.assertEqual(record.response_data["extracted"], {"token": "T-123"})


class ExecuteApiCaseExtraTests(TestCase):
    """execute_api_case 边界场景：失败断言、httpx 异常"""

    def setUp(self):
        self.user = User.objects.create_user(username="exec_extra", password="test123456")
        self.project = Project.objects.create(name="exec-extra-project", creator=self.user)
        self.module = ApiModule.objects.create(project=self.project, name="m", creator=self.user)
        self.env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="E",
            base_url="https://api.example.com",
            is_default=True,
            creator=self.user,
        )

    def _make_case_record(self, assertions, path="/x"):
        case = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env,
            name="case",
            method="GET",
            path=path,
            assertions=assertions,
            creator=self.user,
        )
        record = ApiExecutionRecord.objects.create(
            project=self.project,
            test_case=case,
            environment=self.env,
            status=0,
            trigger_type="manual",
            executor=self.user,
        )
        return case, record

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_case_marks_record_failed_on_assertion_failure(self, client_cls):
        case, record = self._make_case_record(
            [{"type": "status_code", "operator": "eq", "expected": 200}],
        )
        response = httpx.Response(
            500,
            text='boom',
            request=httpx.Request("GET", "https://api.example.com/x"),
        )
        client_cls.return_value.__enter__.return_value.request.return_value = response

        result = execute_api_case(record.id)

        self.assertEqual(result["status"], "failed")
        record.refresh_from_db()
        case.refresh_from_db()
        self.assertEqual(record.status, 3)
        self.assertEqual(case.status, 3)
        self.assertEqual(record.error_message, "接口断言未通过")

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_case_marks_record_failed_when_httpx_raises(self, client_cls):
        _case, record = self._make_case_record(
            [{"type": "status_code", "operator": "eq", "expected": 200}],
        )
        client_cls.return_value.__enter__.return_value.request.side_effect = (
            httpx.ConnectError("network down")
        )

        result = execute_api_case(record.id)

        self.assertEqual(result["status"], "failed")
        record.refresh_from_db()
        self.assertEqual(record.status, 3)
        self.assertIn("network down", record.error_message)


class ApiBatchTaskTests(TestCase):
    """execute_api_batch_task 端到端：批次状态汇总和结果统计"""

    def setUp(self):
        self.user = User.objects.create_user(username="batch_tester", password="test123456")
        self.project = Project.objects.create(name="batch-project", creator=self.user)
        self.module = ApiModule.objects.create(project=self.project, name="M", creator=self.user)
        self.env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="E",
            base_url="https://api.example.com",
            is_default=True,
            creator=self.user,
        )

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_batch_task_updates_summary_partial(self, client_cls):
        case_pass = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env,
            name="pass",
            method="GET",
            path="/ok",
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            creator=self.user,
        )
        case_fail = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env,
            name="fail",
            method="GET",
            path="/notfound",
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            creator=self.user,
        )
        batch = ApiBatchExecutionRecord.objects.create(
            project=self.project,
            name="batch",
            total_cases=2,
            executor=self.user,
        )
        ApiExecutionRecord.objects.create(
            project=self.project,
            test_case=case_pass,
            batch=batch,
            environment=self.env,
            status=0,
            trigger_type="manual",
            executor=self.user,
        )
        ApiExecutionRecord.objects.create(
            project=self.project,
            test_case=case_fail,
            batch=batch,
            environment=self.env,
            status=0,
            trigger_type="manual",
            executor=self.user,
        )

        responses = [
            httpx.Response(
                200,
                text='{"ok": true}',
                request=httpx.Request("GET", "https://api.example.com/ok"),
            ),
            httpx.Response(
                404,
                text='not found',
                request=httpx.Request("GET", "https://api.example.com/notfound"),
            ),
        ]
        client_cls.return_value.__enter__.return_value.request.side_effect = responses

        from .tasks import execute_api_batch_task

        result = execute_api_batch_task.apply(args=[batch.id]).get()

        self.assertEqual(result["status"], "done")
        batch.refresh_from_db()
        self.assertEqual(batch.passed_cases, 1)
        self.assertEqual(batch.failed_cases, 1)
        self.assertEqual(batch.status, 3)  # 部分失败
        self.assertIsNotNone(batch.end_time)


class ApiModelBehaviorTests(TestCase):
    """ApiModule.save、ApiEnvironmentConfig 默认环境唯一性、批次成功率"""

    def setUp(self):
        self.user = User.objects.create_user(username="model_tester", password="test123456")
        self.project = Project.objects.create(name="m-project", creator=self.user)

    def test_environment_default_is_unique_within_project(self):
        env1 = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="E1",
            base_url="https://a",
            is_default=True,
            creator=self.user,
        )
        env2 = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="E2",
            base_url="https://b",
            is_default=True,
            creator=self.user,
        )
        env1.refresh_from_db()
        env2.refresh_from_db()
        self.assertFalse(env1.is_default)
        self.assertTrue(env2.is_default)

    def test_module_save_cascades_level_from_parent(self):
        parent = ApiModule.objects.create(project=self.project, name="P", creator=self.user)
        child = ApiModule.objects.create(
            project=self.project, name="C", parent=parent, creator=self.user,
        )
        self.assertEqual(parent.level, 1)
        self.assertEqual(child.level, 2)

    def test_batch_success_rate(self):
        batch = ApiBatchExecutionRecord.objects.create(
            project=self.project,
            name="b",
            total_cases=4,
            passed_cases=3,
            failed_cases=1,
            executor=self.user,
        )
        self.assertEqual(batch.success_rate, 75.0)

        empty = ApiBatchExecutionRecord.objects.create(
            project=self.project,
            name="e",
            total_cases=0,
            executor=self.user,
        )
        self.assertEqual(empty.success_rate, 0)


class OpenApiImportExtraTests(TestCase):
    """OpenAPI 导入的幂等性与默认环境创建"""

    def setUp(self):
        self.user = User.objects.create_user(username="openapi", password="test123456")
        self.project = Project.objects.create(name="openapi-project", creator=self.user)

    def test_import_creates_default_environment(self):
        spec = load_openapi_spec(OPENAPI_SAMPLE)
        import_openapi_spec(self.project, self.user, spec, create_cases=False)
        env = ApiEnvironmentConfig.objects.get(project=self.project)
        self.assertEqual(env.base_url, "https://api.example.com")
        self.assertTrue(env.is_default)

    def test_import_is_idempotent_for_definitions(self):
        spec = load_openapi_spec(OPENAPI_SAMPLE)
        first = import_openapi_spec(self.project, self.user, spec, create_cases=True)
        second = import_openapi_spec(self.project, self.user, spec, create_cases=True)

        self.assertEqual(first["created_definitions"], 1)
        self.assertEqual(first["created_cases"], 1)
        # 第二次导入：定义复用更新，不再重复创建用例
        self.assertEqual(second["created_definitions"], 0)
        self.assertEqual(second["updated_definitions"], 1)
        self.assertEqual(second["created_cases"], 0)
        self.assertEqual(ApiDefinition.objects.filter(project=self.project).count(), 1)
        self.assertEqual(ApiTestCase.objects.filter(project=self.project, source="openapi").count(), 1)


# ----------------------------------------------------------------------------
# Item 1: UI Trace 网络请求 → 接口用例
# ----------------------------------------------------------------------------


def _build_trace_data(network_requests):
    """简易构造 trace_parser 风格的解析结果，用于测试。"""
    return {
        "title": "test trace",
        "start_time": 0,
        "end_time": 100,
        "duration": 100,
        "page_url": "https://example.com",
        "actions": [],
        "network_requests": network_requests,
        "console_messages": [],
        "snapshots": [],
        "summary": {},
    }


SAMPLE_NETWORK_REQUESTS = [
    {  # index 0: xhr POST 登录
        "url": "https://api.example.com/v1/login?from=home",
        "method": "POST",
        "status": 200,
        "mime_type": "application/json",
        "request_headers": {
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
            "Cookie": "sid=abc",
            "Accept": "application/json",
        },
        "response_headers": {"X-Trace-Id": "rid-123"},
        "request_body": '{"username": "alice", "password": "p"}',
        "response_body": '{"token": "T"}',
        "duration": 88,
        "response_size": 100,
    },
    {  # index 1: xhr GET 列表
        "url": "https://api.example.com/v1/items?page=1&size=20",
        "method": "GET",
        "status": 200,
        "mime_type": "application/json",
        "request_headers": {"Accept": "application/json"},
        "response_headers": {},
        "request_body": None,
        "response_body": '[{"id": 1}]',
        "duration": 10,
        "response_size": 30,
    },
    {  # index 2: 静态 js
        "url": "https://cdn.example.com/static/app.js",
        "method": "GET",
        "status": 200,
        "mime_type": "application/javascript",
        "request_headers": {},
        "response_headers": {},
        "duration": 1,
        "response_size": 10000,
    },
    {  # index 3: 静态 png
        "url": "https://cdn.example.com/static/logo.png",
        "method": "GET",
        "status": 200,
        "mime_type": "image/png",
        "request_headers": {},
        "response_headers": {},
        "duration": 1,
    },
    {  # index 4: OPTIONS 预检
        "url": "https://api.example.com/v1/items",
        "method": "OPTIONS",
        "status": 204,
        "mime_type": "",
        "request_headers": {},
        "response_headers": {},
    },
    {  # index 5: 非 http url
        "url": "data:image/png;base64,xxx",
        "method": "GET",
        "status": 200,
        "mime_type": "image/png",
        "request_headers": {},
        "response_headers": {},
    },
]


class TraceCandidateExtractorTests(TestCase):
    """trace_to_api_cases 纯函数行为"""

    def test_extract_filters_static_options_and_invalid_urls(self):
        from .trace_to_api_cases import extract_candidate_requests

        candidates = extract_candidate_requests(_build_trace_data(SAMPLE_NETWORK_REQUESTS))
        self.assertEqual([c["index"] for c in candidates], [0, 1])
        self.assertEqual(candidates[0]["method"], "POST")
        self.assertEqual(candidates[0]["base_url"], "https://api.example.com")
        self.assertEqual(candidates[0]["path"], "/v1/login")
        self.assertEqual(candidates[0]["query_params"], {"from": "home"})

    def test_extract_keeps_static_when_skip_disabled(self):
        from .trace_to_api_cases import extract_candidate_requests

        candidates = extract_candidate_requests(
            _build_trace_data(SAMPLE_NETWORK_REQUESTS),
            skip_static=False,
        )
        # 关掉过滤后，js 和 png 也保留；OPTIONS / 非 http 仍然剔除
        kept_indexes = [c["index"] for c in candidates]
        self.assertIn(2, kept_indexes)
        self.assertIn(3, kept_indexes)
        self.assertNotIn(4, kept_indexes)
        self.assertNotIn(5, kept_indexes)

    def test_sanitize_strips_sensitive_headers(self):
        from .trace_to_api_cases import extract_candidate_requests

        candidates = extract_candidate_requests(_build_trace_data(SAMPLE_NETWORK_REQUESTS))
        login = candidates[0]
        keys = {k.lower() for k in login["request_headers"].keys()}
        self.assertNotIn("authorization", keys)
        self.assertNotIn("cookie", keys)
        self.assertIn("content-type", keys)

    def test_request_body_parsed_into_dict_when_json(self):
        from .trace_to_api_cases import extract_candidate_requests

        candidates = extract_candidate_requests(_build_trace_data(SAMPLE_NETWORK_REQUESTS))
        login = candidates[0]
        self.assertEqual(login["request_body"], {"username": "alice", "password": "p"})

    def test_request_body_invalid_json_keeps_raw(self):
        from .trace_to_api_cases import extract_candidate_requests

        trace = _build_trace_data([
            {
                "url": "https://api.example.com/x",
                "method": "POST",
                "status": 200,
                "mime_type": "application/json",
                "request_headers": {},
                "response_headers": {},
                "request_body": "<not-json>",
            },
        ])
        candidate = extract_candidate_requests(trace)[0]
        self.assertEqual(candidate["request_body"], {"_raw": "<not-json>"})

    def test_split_url_root_path(self):
        from .trace_to_api_cases import _split_url

        self.assertEqual(_split_url("https://api.example.com"), ("https://api.example.com", "/", {}))


class TraceToApiCasesMaterializeTests(TestCase):
    """materialize_from_execution 真正落库"""

    def setUp(self):
        from ui_automation.models import UiExecutionRecord, UiModule, UiTestCase

        self.user = User.objects.create_user(username="trace_tester", password="test123456")
        self.project = Project.objects.create(name="trace-project", creator=self.user)
        self.api_module = ApiModule.objects.create(
            project=self.project, name="导入接口", creator=self.user,
        )

        # UI 自动化端的 case + execution record
        ui_module = UiModule.objects.create(
            project=self.project, name="UI 模块", creator=self.user,
        )
        ui_case = UiTestCase.objects.create(
            project=self.project, module=ui_module, name="登录用例", creator=self.user,
        )
        self.execution_record = UiExecutionRecord.objects.create(
            test_case=ui_case,
            status=2,
            trigger_type="manual",
            trace_data=_build_trace_data(SAMPLE_NETWORK_REQUESTS),
        )

    def test_materialize_creates_cases_for_all_candidates(self):
        from .trace_to_api_cases import materialize_from_execution

        result = materialize_from_execution(
            self.execution_record,
            project=self.project,
            module=self.api_module,
            creator=self.user,
        )
        self.assertEqual(result["created_count"], 2)
        cases = list(ApiTestCase.objects.filter(module=self.api_module).order_by("id"))
        self.assertEqual(len(cases), 2)
        login = cases[0]
        self.assertEqual(login.method, "POST")
        self.assertEqual(login.path, "/v1/login")
        self.assertEqual(login.query_params, {"from": "home"})
        self.assertEqual(login.body, {"username": "alice", "password": "p"})
        self.assertEqual(login.source, "ui_trace")
        # 默认断言根据原始 status_code 生成
        self.assertEqual(login.assertions, [{"type": "status_code", "operator": "eq", "expected": 200}])

    def test_materialize_creates_environment_per_base_url(self):
        from .trace_to_api_cases import materialize_from_execution

        materialize_from_execution(
            self.execution_record,
            project=self.project,
            module=self.api_module,
            creator=self.user,
        )
        envs = list(ApiEnvironmentConfig.objects.filter(project=self.project))
        self.assertEqual(len(envs), 1)
        self.assertEqual(envs[0].base_url, "https://api.example.com")
        self.assertTrue(envs[0].is_default)

    def test_materialize_with_selected_indexes(self):
        from .trace_to_api_cases import materialize_from_execution

        result = materialize_from_execution(
            self.execution_record,
            project=self.project,
            module=self.api_module,
            creator=self.user,
            selected_indexes=[1],  # 只选第二个候选
        )
        self.assertEqual(result["created_count"], 1)
        case = ApiTestCase.objects.get(id=result["created_case_ids"][0])
        self.assertEqual(case.method, "GET")
        self.assertEqual(case.path, "/v1/items")

    def test_materialize_uses_explicit_environment(self):
        from .trace_to_api_cases import materialize_from_execution

        explicit_env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="explicit",
            base_url="https://other.example.com",
            is_default=False,
            creator=self.user,
        )
        materialize_from_execution(
            self.execution_record,
            project=self.project,
            module=self.api_module,
            creator=self.user,
            environment=explicit_env,
        )
        cases = list(ApiTestCase.objects.filter(module=self.api_module))
        # 全部用例都使用显式 env，不再创建新环境
        self.assertTrue(all(c.environment_id == explicit_env.id for c in cases))
        self.assertEqual(ApiEnvironmentConfig.objects.filter(project=self.project).count(), 1)


class GenerateFromUiTraceViewTests(TestCase):
    """POST /api/api-automation/cases/generate-from-ui-trace/ 端到端"""

    def setUp(self):
        from rest_framework.test import APIClient
        from ui_automation.models import UiExecutionRecord, UiModule, UiTestCase

        self.user = User.objects.create_user(username="trace_view", password="test123456")
        self.project = Project.objects.create(name="trace-view-project", creator=self.user)
        self.api_module = ApiModule.objects.create(
            project=self.project, name="导入", creator=self.user,
        )
        ui_module = UiModule.objects.create(project=self.project, name="ui", creator=self.user)
        ui_case = UiTestCase.objects.create(
            project=self.project, module=ui_module, name="ui case", creator=self.user,
        )
        self.execution_record = UiExecutionRecord.objects.create(
            test_case=ui_case,
            status=2,
            trigger_type="manual",
            trace_data=_build_trace_data(SAMPLE_NETWORK_REQUESTS),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self):
        return "/api/api-automation/testcases/generate-from-ui-trace/"

    def test_returns_400_when_execution_record_id_missing(self):
        resp = self.client.post(self._url(), {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_returns_404_when_execution_record_not_found(self):
        resp = self.client.post(
            self._url(),
            {"execution_record_id": 9999999},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_dry_run_returns_candidates_without_persisting(self):
        resp = self.client.post(
            self._url(),
            {"execution_record_id": self.execution_record.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["candidate_count"], 2)
        self.assertEqual(ApiTestCase.objects.count(), 0)

    def test_create_requires_project_and_module_when_not_dry_run(self):
        resp = self.client.post(
            self._url(),
            {"execution_record_id": self.execution_record.id, "dry_run": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_create_persists_selected_cases(self):
        resp = self.client.post(
            self._url(),
            {
                "execution_record_id": self.execution_record.id,
                "dry_run": False,
                "project": self.project.id,
                "module": self.api_module.id,
                "selected_indexes": [0],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["created_count"], 1)
        case = ApiTestCase.objects.get(module=self.api_module)
        self.assertEqual(case.method, "POST")
        self.assertEqual(case.path, "/v1/login")


class FunctionalCaseToApiCaseTests(TestCase):
    """Item 2: 功能用例 → 接口用例 AI 辅助生成。

    LLM 调用全部 mock，避免依赖外部模型。
    """

    def setUp(self):
        from testcases.models import TestCase as FunctionalTestCase, TestCaseModule, TestCaseStep
        self.user = User.objects.create_user(username="ai_user", password="test123456")
        self.project = Project.objects.create(name="ai-project", creator=self.user)

        self.api_module = ApiModule.objects.create(project=self.project, name="登录", creator=self.user)
        # 已有定义供 LLM 参考
        ApiDefinition.objects.create(
            project=self.project,
            module=self.api_module,
            name="登录",
            method="POST",
            path="/v1/login",
            summary="账号登录",
            tags=["auth"],
            creator=self.user,
        )

        # 功能用例
        self.fn_module = TestCaseModule.objects.create(project=self.project, name="auth-fn", creator=self.user)
        self.functional_case = FunctionalTestCase.objects.create(
            project=self.project,
            module=self.fn_module,
            name="登录功能-正常账号密码登录成功",
            level="P0",
            test_type="smoke",
            precondition="账号已注册",
            creator=self.user,
        )
        TestCaseStep.objects.create(
            test_case=self.functional_case,
            step_number=1,
            description="用合法账号密码请求登录接口",
            expected_result="返回 200 + token",
            creator=self.user,
        )
        TestCaseStep.objects.create(
            test_case=self.functional_case,
            step_number=2,
            description="用错误密码再次请求",
            expected_result="返回 401",
            creator=self.user,
        )

    def _stub_llm_response(self, content: str):
        class _Resp:
            def __init__(self, c):
                self.content = c
        return _Resp(content)

    def test_normalize_case_drops_invalid(self):
        from .ai_from_functional import _normalize_case
        self.assertIsNone(_normalize_case({"name": "x"}))  # 缺 method/path
        self.assertIsNone(_normalize_case({"name": "x", "method": "INVALID", "path": "/p"}))
        ok = _normalize_case({"name": "n", "method": "post", "path": "/p", "headers": "bad", "body": "x"})
        self.assertEqual(ok["method"], "POST")  # 自动大写
        self.assertEqual(ok["headers"], {})  # bad 类型被替换为 {}
        self.assertEqual(ok["body"], {})

    @patch("api_automation.ai_from_functional.safe_llm_invoke")
    @patch("api_automation.ai_from_functional.create_llm_instance")
    @patch("api_automation.ai_from_functional.LLMConfig")
    def test_preview_returns_candidates(self, llm_config_cls, create_llm, safe_invoke):
        from .ai_from_functional import preview_from_functional_case
        llm_config_cls.objects.filter.return_value.first.return_value = object()
        create_llm.return_value = object()
        safe_invoke.return_value = self._stub_llm_response(json.dumps({
            "cases": [
                {
                    "name": "登录-成功",
                    "method": "POST",
                    "path": "/v1/login",
                    "headers": {"Content-Type": "application/json"},
                    "query_params": {},
                    "body": {"username": "demo", "password": "pwd"},
                    "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
                    "extractors": [],
                    "matched_definition_id": None,
                    "rationale": "正向用例",
                },
                {
                    "name": "登录-密码错",
                    "method": "POST",
                    "path": "/v1/login",
                    "headers": {},
                    "query_params": {},
                    "body": {"username": "demo", "password": "wrong"},
                    "assertions": [{"type": "status_code", "operator": "eq", "expected": 401}],
                    "extractors": [],
                    "matched_definition_id": None,
                    "rationale": "异常用例",
                },
            ]
        }))

        result = preview_from_functional_case(self.functional_case.id)
        self.assertEqual(result["testcase_id"], self.functional_case.id)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["candidates"][0]["index"], 0)
        self.assertEqual(result["candidates"][1]["assertions"][0]["expected"], 401)

    @patch("api_automation.ai_from_functional.safe_llm_invoke")
    @patch("api_automation.ai_from_functional.create_llm_instance")
    @patch("api_automation.ai_from_functional.LLMConfig")
    def test_preview_returns_empty_when_llm_returns_garbage(self, llm_config_cls, create_llm, safe_invoke):
        from .ai_from_functional import preview_from_functional_case
        llm_config_cls.objects.filter.return_value.first.return_value = object()
        create_llm.return_value = object()
        safe_invoke.return_value = self._stub_llm_response("这不是 JSON")

        result = preview_from_functional_case(self.functional_case.id)
        self.assertEqual(result["candidates"], [])

    @patch("api_automation.ai_from_functional.LLMConfig")
    def test_preview_returns_error_when_no_llm_config(self, llm_config_cls):
        from .ai_from_functional import preview_from_functional_case
        llm_config_cls.objects.filter.return_value.first.return_value = None

        result = preview_from_functional_case(self.functional_case.id)
        self.assertIn("LLM", result["error"])
        self.assertEqual(result["candidates"], [])

    @patch("api_automation.ai_from_functional.safe_llm_invoke")
    @patch("api_automation.ai_from_functional.create_llm_instance")
    @patch("api_automation.ai_from_functional.LLMConfig")
    def test_materialize_creates_selected_cases(self, llm_config_cls, create_llm, safe_invoke):
        from .ai_from_functional import materialize_from_functional_case
        llm_config_cls.objects.filter.return_value.first.return_value = object()
        create_llm.return_value = object()
        safe_invoke.return_value = self._stub_llm_response(json.dumps({
            "cases": [
                {"name": "case1", "method": "POST", "path": "/v1/login",
                 "headers": {}, "query_params": {}, "body": {},
                 "assertions": [], "extractors": [], "matched_definition_id": None, "rationale": ""},
                {"name": "case2", "method": "GET", "path": "/v1/me",
                 "headers": {}, "query_params": {}, "body": {},
                 "assertions": [], "extractors": [], "matched_definition_id": None, "rationale": ""},
            ]
        }))

        result = materialize_from_functional_case(
            testcase_id=self.functional_case.id,
            module_id=self.api_module.id,
            selected_indexes=[1],
            environment_id=None,
            creator=self.user,
        )
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(ApiTestCase.objects.filter(module=self.api_module).count(), 1)
        api_case = ApiTestCase.objects.get(module=self.api_module)
        self.assertEqual(api_case.name, "case2")
        self.assertEqual(api_case.path, "/v1/me")
        self.assertEqual(api_case.source, "ai_from_functional")


class GenerateFromFunctionalCaseViewTests(TestCase):
    """View: POST /api/api-automation/testcases/generate-from-functional-case/"""

    def setUp(self):
        from rest_framework.test import APIClient
        from testcases.models import TestCase as FunctionalTestCase, TestCaseModule
        self.user = User.objects.create_user(username="view_user", password="test123456")
        self.project = Project.objects.create(name="view-project", creator=self.user)
        self.api_module = ApiModule.objects.create(project=self.project, name="m", creator=self.user)
        fn_module = TestCaseModule.objects.create(project=self.project, name="fn", creator=self.user)
        self.functional_case = FunctionalTestCase.objects.create(
            project=self.project,
            module=fn_module,
            name="登录功能",
            creator=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _url(self):
        return "/api/api-automation/testcases/generate-from-functional-case/"

    def test_returns_400_when_testcase_id_missing(self):
        resp = self.client.post(self._url(), {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_returns_404_when_testcase_not_found(self):
        resp = self.client.post(self._url(), {"testcase_id": 9999999}, format="json")
        self.assertEqual(resp.status_code, 404)

    @patch("api_automation.ai_from_functional.preview_from_functional_case")
    def test_dry_run_calls_preview(self, preview_mock):
        preview_mock.return_value = {"candidates": [{"index": 0, "name": "n"}]}
        resp = self.client.post(
            self._url(),
            {"testcase_id": self.functional_case.id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        preview_mock.assert_called_once_with(self.functional_case.id)

    def test_create_requires_module(self):
        resp = self.client.post(
            self._url(),
            {"testcase_id": self.functional_case.id, "dry_run": False},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)


class GenerateCaseFromDefinitionTests(TestCase):
    """ApiDefinitionViewSet.generate-case：根据接口定义一键生成用例。"""

    def setUp(self):
        from rest_framework.test import APIClient
        self.user = User.objects.create_user(username="defgen_user", password="test123456")
        self.project = Project.objects.create(name="defgen-project", creator=self.user)
        self.module = ApiModule.objects.create(project=self.project, name="m", creator=self.user)
        self.env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="default",
            base_url="https://api.example.com",
            is_default=True,
            creator=self.user,
        )
        self.definition = ApiDefinition.objects.create(
            project=self.project,
            module=self.module,
            name="获取用户",
            method="GET",
            path="/users/{id}",
            responses={"200": {"description": "OK"}},
            source="manual",
            creator=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_generate_case_creates_with_default_env(self):
        resp = self.client.post(
            f"/api/api-automation/definitions/{self.definition.id}/generate-case/", {}, format="json"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        case = ApiTestCase.objects.get(id=resp.data["case_id"])
        self.assertEqual(case.method, "GET")
        self.assertEqual(case.path, "/users/{id}")
        self.assertEqual(case.module_id, self.module.id)
        self.assertEqual(case.environment_id, self.env.id)
        self.assertEqual(case.source, "definition")
        self.assertTrue(case.assertions, "应该自带默认断言")

    def test_generate_case_returns_404_for_invalid_module(self):
        resp = self.client.post(
            f"/api/api-automation/definitions/{self.definition.id}/generate-case/",
            {"module": 99999},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_generate_case_reuses_existing_generated_case(self):
        existing = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            definition=self.definition,
            environment=None,
            name="旧生成用例",
            method="POST",
            path="/stale",
            assertions=[],
            source="definition",
            creator=self.user,
        )
        duplicate = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            definition=self.definition,
            environment=None,
            name="重复生成用例",
            method="POST",
            path="/duplicate",
            assertions=[],
            source="definition",
            creator=self.user,
        )

        resp = self.client.post(
            f"/api/api-automation/definitions/{self.definition.id}/generate-case/",
            {},
            format="json",
        )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertTrue(resp.data["replaced"])
        self.assertFalse(ApiTestCase.objects.filter(id=existing.id).exists())
        self.assertFalse(ApiTestCase.objects.filter(id=duplicate.id).exists())
        remaining = ApiTestCase.objects.get(id=resp.data["case_id"])
        self.assertEqual(
            ApiTestCase.objects.filter(
                project=self.project,
                module=self.module,
                definition=self.definition,
                source="definition",
            ).count(),
            1,
        )
        self.assertEqual(remaining.method, "GET")
        self.assertEqual(remaining.path, "/users/{id}")
        self.assertEqual(remaining.environment_id, self.env.id)
        self.assertTrue(remaining.assertions)


class AiEnhanceCaseTests(TestCase):
    """ai-enhance：mock LLM，验证 dedup + apply 逻辑。"""

    def setUp(self):
        from rest_framework.test import APIClient
        self.user = User.objects.create_user(username="ai_enh", password="test123456")
        self.project = Project.objects.create(name="ai-enh-project", creator=self.user)
        self.module = ApiModule.objects.create(project=self.project, name="m", creator=self.user)
        self.case = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            name="登录",
            method="POST",
            path="/v1/login",
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            extractors=[],
            creator=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _stub_llm_response(self, content: str):
        class _Resp:
            def __init__(self, c):
                self.content = c
        return _Resp(content)

    @patch("api_automation.ai_enhance.LLMConfig")
    def test_returns_message_when_no_llm_config(self, llm_config_cls):
        from api_automation.ai_enhance import enhance_api_case
        llm_config_cls.objects.filter.return_value.first.return_value = None
        result = enhance_api_case(self.case.id)
        self.assertTrue(all(item["type"] in ["status_code", "header_value"] for item in result["suggested"]["assertions"]))
        self.assertEqual(result["suggested"]["extractors"], [])
        self.assertFalse(result["applied"])

    @patch("api_automation.ai_enhance.safe_llm_invoke")
    @patch("api_automation.ai_enhance.create_llm_instance")
    @patch("api_automation.ai_enhance.LLMConfig")
    def test_apply_merges_and_dedups(self, llm_config_cls, create_llm, safe_invoke):
        from api_automation.ai_enhance import enhance_api_case
        llm_config_cls.objects.filter.return_value.first.return_value = object()
        create_llm.return_value = object()
        safe_invoke.return_value = self._stub_llm_response(json.dumps({
            "assertions": [
                {"type": "status_code", "operator": "eq", "expected": 200},
                {"type": "json_path", "operator": "is_not_empty", "expected": None, "target": "data.token"},
            ],
            "extractors": [
                {"name": "auth_token", "source": "json_path", "expression": "data.token"}
            ],
            "rationale": "补全字段提取与断言"
        }))

        result = enhance_api_case(self.case.id, apply=True)
        self.assertTrue(result["applied"])
        self.case.refresh_from_db()
        self.assertGreaterEqual(len(self.case.assertions), 2)
        sc_assertions = [a for a in self.case.assertions if a["type"] == "status_code"]
        self.assertEqual(len(sc_assertions), 1)
        self.assertIn(sc_assertions[0]["expected"], [200, 201])
        self.assertEqual(self.case.extractors[0]["name"], "auth_token")
        self.assertTrue(result["rationale"])

    @patch("api_automation.ai_enhance.safe_llm_invoke")
    @patch("api_automation.ai_enhance.create_llm_instance")
    @patch("api_automation.ai_enhance.LLMConfig")
    def test_status_code_uses_last_execution_when_available(self, llm_config_cls, create_llm, safe_invoke):
        from api_automation.ai_enhance import enhance_api_case
        # 准备一条最近执行记录（真实 status_code=202）
        ApiExecutionRecord.objects.create(
            project=self.project,
            test_case=self.case,
            status=2,
            response_data={"status_code": 202, "text": "ok", "headers": {}},
        )
        llm_config_cls.objects.filter.return_value.first.return_value = object()
        create_llm.return_value = object()
        safe_invoke.return_value = self._stub_llm_response(json.dumps({
            "assertions": [{"type": "status_code", "operator": "eq", "expected": 200}],
            "extractors": [],
            "rationale": "",
        }))
        result = enhance_api_case(self.case.id, apply=False)
        merged_sc = [a for a in result["merged"]["assertions"] if a["type"] == "status_code"]
        self.assertEqual(merged_sc[0]["expected"], 202)

    @patch("api_automation.ai_enhance.safe_llm_invoke")
    @patch("api_automation.ai_enhance.create_llm_instance")
    @patch("api_automation.ai_enhance.LLMConfig")
    def test_view_dry_run_does_not_modify(self, llm_config_cls, create_llm, safe_invoke):
        llm_config_cls.objects.filter.return_value.first.return_value = object()
        create_llm.return_value = object()
        safe_invoke.return_value = self._stub_llm_response(json.dumps({
            "assertions": [{"type": "json_path", "operator": "eq", "expected": True, "target": "ok"}],
            "extractors": [],
            "rationale": "x",
        }))
        resp = self.client.post(f"/api/api-automation/testcases/{self.case.id}/ai-enhance/", {}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["applied"])
        self.case.refresh_from_db()
        self.assertEqual(len(self.case.assertions), 1)  # 保持不变


class ApiScriptAndPublicDataExecutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api_script_user", password="test123456")
        self.project = Project.objects.create(name="api-script-project", creator=self.user)
        self.module = ApiModule.objects.create(project=self.project, name="scripts", creator=self.user)
        self.env = ApiEnvironmentConfig.objects.create(
            project=self.project,
            name="Script Env",
            base_url="https://api.example.com",
            is_default=True,
            creator=self.user,
        )

    @patch("api_automation.services.httpx.Client")
    def test_execute_api_case_runs_project_and_case_scripts(self, client_cls):
        ApiPublicData.objects.create(
            project=self.project,
            key="default_page_size",
            value="20",
            creator=self.user,
        )
        ApiScript.objects.create(
            project=self.project,
            module=None,
            name="pre-default-header",
            script_type="pre",
            content="""
request.headers['X-From-Project-Script'] = 'yes';
request.query_params.size = variables.default_page_size;
""",
            creator=self.user,
        )
        ApiScript.objects.create(
            project=self.project,
            module=self.module,
            name="post-extract-runtime",
            script_type="post",
            content="""
if (response.status_code === 200 && response.json && response.json.data) {
  extracted.script_token = response.json.data.token;
  variables.last_status = response.status_code;
}
""",
            creator=self.user,
        )
        case = ApiTestCase.objects.create(
            project=self.project,
            module=self.module,
            environment=self.env,
            name="script-case",
            method="GET",
            path="/items",
            query_params={"page": 0},
            pre_script="request.headers['X-From-Case-Script'] = 'ok';",
            assertions=[{"type": "status_code", "operator": "eq", "expected": 200}],
            creator=self.user,
        )
        record = ApiExecutionRecord.objects.create(
            project=self.project,
            test_case=case,
            environment=self.env,
            status=0,
            trigger_type="manual",
            executor=self.user,
        )

        response = httpx.Response(
            200,
            text='{"data":{"token":"T-123"}}',
            request=httpx.Request("GET", "https://api.example.com/items"),
        )
        client_cls.return_value.__enter__.return_value.request.return_value = response

        execute_api_case(record.id)

        record.refresh_from_db()
        self.assertEqual(record.request_data["headers"]["X-From-Project-Script"], "yes")
        self.assertEqual(record.request_data["headers"]["X-From-Case-Script"], "ok")
        self.assertEqual(record.request_data["query_params"]["size"], "20")
        self.assertEqual(record.response_data["extracted"]["script_token"], "T-123")
        self.assertEqual(record.response_data["runtime_variables"]["last_status"], 200)

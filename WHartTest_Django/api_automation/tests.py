from unittest.mock import patch

import httpx
from django.contrib.auth import get_user_model
from django.test import TestCase

from projects.models import Project

from .models import ApiBatchExecutionRecord, ApiDefinition, ApiEnvironmentConfig, ApiExecutionRecord, ApiModule, ApiPublicData, ApiTestCase
from .services import execute_api_case, import_openapi_spec, load_openapi_spec, update_batch_summary


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

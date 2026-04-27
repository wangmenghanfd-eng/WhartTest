from unittest.mock import AsyncMock, MagicMock

from asgiref.sync import async_to_sync
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from projects.models import Project

from .consumers import SocketUserManager, UiAutomationConsumer
from .functional_case_bridge import generate_ui_case_from_functional_execution
from .models import (
    UiBatchExecutionRecord,
    UiElement,
    UiExecutionRecord,
    UiModule,
    UiPage,
    UiPageSteps,
    UiPageStepsDetailed,
    UiCaseStepsDetailed,
    UiPublicData,
    UiRecordingSession,
    UiTestCase,
)
from .recording_service import materialize_recording_session, parse_playwright_recording


class FunctionalCaseBridgeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bridge_tester", password="test123456")
        self.project = Project.objects.create(
            name="bridge-project",
            description="test",
            creator=self.user,
        )
        UiPublicData.objects.create(
            project=self.project,
            key="login_username",
            value="practice",
            creator=self.user,
        )
        UiPublicData.objects.create(
            project=self.project,
            key="login_password",
            value="SuperSecretPassword!",
            creator=self.user,
        )
        self.test_case_detail = {
            "id": 5,
            "name": "用户登录-有效用户名和密码-正常流程",
            "module_detail": "用户登录模块",
            "level": "P0",
        }
        self.command_records = [
            {
                "command": (
                    'node run.js "await page.goto(\'https://practice.expandtesting.com/login\'); '
                    'const desc = await helpers.describePageForAI(page); console.log(desc);"'
                ),
                "output": "## Page: Login\nURL: https://practice.expandtesting.com/login",
            },
            {
                "command": (
                    'node run.js "await page.fill(\'#username\', \'practice\'); '
                    'await page.fill(\'#password\', \'SuperSecretPassword!\'); '
                    'await page.click(\'#submit-login\');"'
                ),
                "output": "(无输出)",
            },
            {
                "command": (
                    'node run.js "await page.waitForSelector(\'h1\'); '
                    'const h1Text = await page.textContent(\'h1\'); console.log(h1Text);"'
                ),
                "output": "Secure Area",
            },
            {
                "command": (
                    'node run.js "await page.waitForSelector(\'a\'); '
                    'console.log(\'Logout link found\');"'
                ),
                "output": "Logout link found\nWelcome to the Secure Area",
            },
        ]

    def test_generate_ui_case_from_functional_execution_creates_structured_ui_case(self):
        result = generate_ui_case_from_functional_execution(
            project_id=self.project.id,
            creator_id=self.user.id,
            test_case_detail=self.test_case_detail,
            command_records=self.command_records,
            observed_signals=["secure_area_text", "logout_found"],
            target_url_hint="https://practice.expandtesting.com/login",
        )

        ui_case = UiTestCase.objects.get(id=result["ui_testcase_id"])
        self.assertEqual(ui_case.module.name, "用户登录模块")
        self.assertEqual(ui_case.case_steps.count(), 1)
        self.assertTrue(ui_case.name.startswith("AI生成-"))

        page_step = UiPageSteps.objects.get(id=result["page_step_id"])
        step_details = list(page_step.step_details.order_by("step_sort"))
        self.assertGreaterEqual(len(step_details), 6)
        self.assertEqual(step_details[0].ope_key, "goto")
        self.assertEqual(step_details[1].ope_key, "fill")
        self.assertEqual(step_details[1].ope_value["text"], "${{login_username}}")
        self.assertEqual(step_details[2].ope_value["text"], "${{login_password}}")
        self.assertEqual(step_details[3].ope_key, "click")
        self.assertIn(step_details[-1].ope_key, {"assert_visible", "assert_contain_text"})

    def test_generate_ui_case_from_functional_execution_is_idempotent_for_case_name(self):
        first = generate_ui_case_from_functional_execution(
            project_id=self.project.id,
            creator_id=self.user.id,
            test_case_detail=self.test_case_detail,
            command_records=self.command_records,
            observed_signals=["secure_area_text", "logout_found"],
            target_url_hint="https://practice.expandtesting.com/login",
        )
        second = generate_ui_case_from_functional_execution(
            project_id=self.project.id,
            creator_id=self.user.id,
            test_case_detail=self.test_case_detail,
            command_records=self.command_records,
            observed_signals=["secure_area_text", "logout_found"],
            target_url_hint="https://practice.expandtesting.com/login",
        )

        self.assertEqual(first["ui_testcase_id"], second["ui_testcase_id"])
        self.assertEqual(
            UiModule.objects.filter(project=self.project, name="AI生成用例").count(),
            1,
        )
        self.assertEqual(UiTestCase.objects.filter(project=self.project).count(), 1)


class TestUiAutomationConsumerExecutionSync(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="consumer_tester", password="test123456")
        self.project = Project.objects.create(
            name="consumer-project",
            description="test",
            creator=self.user,
        )
        self.module = UiModule.objects.create(
            project=self.project,
            name="登录模块",
            creator=self.user,
        )
        self.page = UiPage.objects.create(
            project=self.project,
            module=self.module,
            name="登录页",
            url="https://example.com/login",
            creator=self.user,
        )
        self.page_step_success = UiPageSteps.objects.create(
            project=self.project,
            page=self.page,
            module=self.module,
            name="登录成功步骤",
            creator=self.user,
        )
        self.step_success_1 = UiPageStepsDetailed.objects.create(
            page_step=self.page_step_success,
            step_sort=1,
            ope_key="fill",
            description="填写用户名",
        )
        self.step_success_2 = UiPageStepsDetailed.objects.create(
            page_step=self.page_step_success,
            step_sort=2,
            ope_key="click",
            description="点击登录",
        )
        self.page_step_pending = UiPageSteps.objects.create(
            project=self.project,
            page=self.page,
            module=self.module,
            name="未执行步骤",
            creator=self.user,
        )
        self.pending_detail = UiPageStepsDetailed.objects.create(
            page_step=self.page_step_pending,
            step_sort=1,
            ope_key="assert_visible",
            description="校验错误提示",
        )
        self.test_case = UiTestCase.objects.create(
            project=self.project,
            module=self.module,
            name="登录用例",
            creator=self.user,
        )
        self.case_step_success = UiCaseStepsDetailed.objects.create(
            test_case=self.test_case,
            page_step=self.page_step_success,
            case_sort=1,
        )
        self.case_step_pending = UiCaseStepsDetailed.objects.create(
            test_case=self.test_case,
            page_step=self.page_step_pending,
            case_sort=2,
        )

    def test_save_execution_result_syncs_case_step_and_page_step_statuses(self):
        consumer = UiAutomationConsumer()

        async_to_sync(consumer.save_execution_result)({
            'case_id': self.test_case.id,
            'status': 'success',
            'message': '执行成功',
            'duration': 3,
            'steps': [
                {
                    'step_id': self.step_success_1.id,
                    'status': 'success',
                    'message': '',
                },
                {
                    'step_id': self.step_success_2.id,
                    'status': 'success',
                    'message': '',
                },
            ],
        })

        self.test_case.refresh_from_db()
        self.case_step_success.refresh_from_db()
        self.case_step_pending.refresh_from_db()
        self.page_step_success.refresh_from_db()
        self.page_step_pending.refresh_from_db()

        self.assertEqual(self.test_case.status, 2)
        self.assertEqual(self.case_step_success.status, 2)
        self.assertEqual(self.page_step_success.status, 2)
        self.assertEqual(self.case_step_pending.status, 0)
        self.assertEqual(self.page_step_pending.status, 0)

    def test_save_execution_result_preserves_scheduled_trigger_and_executor(self):
        consumer = UiAutomationConsumer()
        async_to_sync(consumer.save_execution_result)({
            'case_id': self.test_case.id,
            'status': 'success',
            'message': '定时执行成功',
            'duration': 1,
            'trigger_type': 'scheduled',
            'executor_id': self.user.id,
            'steps': [],
        })

        record = self.test_case.execution_records.latest('id')
        self.assertEqual(record.trigger_type, 'scheduled')
        self.assertEqual(record.executor_id, self.user.id)


class RecordingServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="recording_tester", password="test123456")
        self.project = Project.objects.create(
            name="recording-project",
            description="test",
            creator=self.user,
        )
        self.module = UiModule.objects.create(
            project=self.project,
            name="登录模块",
            creator=self.user,
        )
        self.login_page = UiPage.objects.create(
            project=self.project,
            module=self.module,
            name="login",
            url="https://practice.expandtesting.com/login",
            creator=self.user,
        )
        self.secure_page = UiPage.objects.create(
            project=self.project,
            module=self.module,
            name="secure",
            url="/secure",
            creator=self.user,
        )
        UiPublicData.objects.create(
            project=self.project,
            key="login_username",
            value="practice",
            creator=self.user,
        )

    def test_parse_playwright_recording_extracts_supported_actions_and_unsupported_lines(self):
        parsed = parse_playwright_recording(
            """
            import { test, expect } from '@playwright/test';
            await page.goto('https://practice.expandtesting.com/login');
            await page.locator('#username').fill('practice');
            await page.locator('#submit-login').click();
            await page.waitForURL('**/secure');
            await expect(page.getByText('Welcome')).toContainText('Welcome');
            await page.keyboard.insertText('unsupported');
            """
        )

        operations = [action["operation"] for action in parsed["normalized_actions"]]
        self.assertEqual(
            operations,
            ["goto", "fill", "click", "assert_url", "assert_contain_text"],
        )
        self.assertEqual(len(parsed["unsupported_lines"]), 1)
        self.assertIn("keyboard.insertText", parsed["unsupported_lines"][0])

    def test_materialize_recording_session_creates_page_step_for_page_step_mode(self):
        UiElement.objects.create(
            page=self.login_page,
            name="登录按钮",
            locator_type="text",
            locator_value="Login",
            creator=self.user,
        )
        session = UiRecordingSession.objects.create(
            project=self.project,
            module=self.module,
            page=self.login_page,
            target_type="page_step",
            name="录制登录步骤",
            status="draft",
            actuator_id="WHartTest-001",
            executor=self.user,
            base_url="https://practice.expandtesting.com/login",
            normalized_actions=[
                {
                    "line_no": 1,
                    "operation": "goto",
                    "value": "https://practice.expandtesting.com/login",
                    "description": "打开页面: https://practice.expandtesting.com/login",
                },
                {
                    "line_no": 2,
                    "operation": "fill",
                    "selector": "#username",
                    "locator_type": "id",
                    "locator_value": "username",
                    "value": "practice",
                    "description": "输入 用户名输入框",
                },
                {
                    "line_no": 3,
                    "operation": "click",
                    "selector": "#submit-login",
                    "locator_type": "id",
                    "locator_value": "submit-login",
                    "description": "click 登录按钮",
                },
            ],
            preview_payload={"warnings": []},
        )

        result = materialize_recording_session(session.id)

        session.refresh_from_db()
        self.assertEqual(session.status, "materialized")
        self.assertEqual(len(result["generated_page_step_ids"]), 1)
        self.assertIsNone(result["generated_test_case_id"])

        page_step = UiPageSteps.objects.get(id=result["generated_page_step_ids"][0])
        details = list(page_step.step_details.order_by("step_sort"))
        self.assertEqual(page_step.page_id, self.login_page.id)
        self.assertEqual([detail.ope_key for detail in details], ["goto", "fill", "click"])
        self.assertEqual(details[0].ope_value["url"], "/login")
        self.assertEqual(details[1].ope_value["text"], "${{login_username}}")
        self.login_page.refresh_from_db()
        self.assertEqual(self.login_page.url, "/login")
        self.assertEqual(self.login_page.name, "登录页")
        login_button = UiElement.objects.get(page=self.login_page, name="登录按钮")
        self.assertEqual(login_button.locator_type, "id")
        self.assertEqual(login_button.locator_value, "submit-login")
        self.assertEqual(login_button.locator_type_2, "text")
        self.assertEqual(login_button.locator_value_2, "Login")
        self.assertEqual(UiElement.objects.filter(page=self.login_page, name="登录按钮").count(), 1)

    def test_materialize_recording_session_accepts_edited_actions(self):
        session = UiRecordingSession.objects.create(
            project=self.project,
            module=self.module,
            page=self.login_page,
            target_type="page_step",
            name="原始名称",
            status="draft",
            actuator_id="WHartTest-001",
            executor=self.user,
            base_url="https://practice.expandtesting.com",
            normalized_actions=[
                {
                    "line_no": 1,
                    "operation": "goto",
                    "value": "https://practice.expandtesting.com/login",
                    "description": "打开页面",
                },
                {
                    "line_no": 2,
                    "operation": "click",
                    "selector": "#unused",
                    "locator_type": "id",
                    "locator_value": "unused",
                    "description": "待删除动作",
                },
            ],
            preview_payload={"warnings": [], "unsupported_lines": []},
        )

        result = materialize_recording_session(
            session.id,
            name="编辑后的登录步骤",
            normalized_actions=[
                {
                    "operation": "goto",
                    "value": "https://practice.expandtesting.com/login",
                    "description": "打开登录页",
                },
            ],
        )

        page_step = UiPageSteps.objects.get(id=result["generated_page_step_ids"][0])
        details = list(page_step.step_details.order_by("step_sort"))
        self.assertEqual(page_step.name, "编辑后的登录步骤")
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].ope_key, "goto")
        self.assertEqual(details[0].description, "打开登录页")

    def test_materialize_recording_session_creates_test_case_and_reuses_pages(self):
        session = UiRecordingSession.objects.create(
            project=self.project,
            module=self.module,
            target_type="test_case",
            name="录制登录成功",
            status="draft",
            actuator_id="WHartTest-001",
            executor=self.user,
            base_url="https://practice.expandtesting.com/login",
            normalized_actions=[
                {
                    "line_no": 1,
                    "operation": "goto",
                    "value": "https://practice.expandtesting.com/login",
                    "description": "打开页面: https://practice.expandtesting.com/login",
                },
                {
                    "line_no": 2,
                    "operation": "fill",
                    "selector": "#username",
                    "locator_type": "id",
                    "locator_value": "username",
                    "value": "practice",
                    "description": "输入 用户名输入框",
                },
                {
                    "line_no": 3,
                    "operation": "click",
                    "selector": "#submit-login",
                    "locator_type": "id",
                    "locator_value": "submit-login",
                    "description": "click 登录按钮",
                },
                {
                    "line_no": 4,
                    "operation": "assert_url",
                    "value": "/secure",
                    "description": "断言页面地址匹配 /secure",
                },
                {
                    "line_no": 5,
                    "operation": "assert_visible",
                    "selector": "text=Logout",
                    "locator_type": "text",
                    "locator_value": "Logout",
                    "description": "断言 退出登录入口 可见",
                },
            ],
            preview_payload={"warnings": []},
            artifacts={"final_url": "/secure"},
        )

        result = materialize_recording_session(session.id)

        session.refresh_from_db()
        self.assertEqual(session.status, "materialized")
        self.assertEqual(len(result["generated_page_step_ids"]), 2)
        self.assertIsNotNone(result["generated_test_case_id"])

        ui_case = UiTestCase.objects.get(id=result["generated_test_case_id"])
        case_steps = list(ui_case.case_steps.order_by("case_sort"))
        self.assertEqual(len(case_steps), 2)
        self.assertEqual(case_steps[0].page_step.page_id, self.login_page.id)
        self.assertEqual(case_steps[1].page_step.page_id, self.secure_page.id)


class SocketUserManagerActuatorTests(TestCase):
    """SocketUserManager.get_actuator 应该按 is_open 过滤掉暂停接单的执行器。"""

    def setUp(self):
        SocketUserManager._actuator_users.clear()

    def tearDown(self):
        SocketUserManager._actuator_users.clear()

    def _make_actuator(self, actuator_id, is_open=True):
        consumer = MagicMock(spec=UiAutomationConsumer)
        consumer.actuator_info = {"id": actuator_id, "is_open": is_open}
        return consumer

    def test_get_actuator_returns_open_actuator_by_id(self):
        SocketUserManager._actuator_users["A1"] = self._make_actuator("A1", is_open=True)
        self.assertIsNotNone(SocketUserManager.get_actuator("A1"))

    def test_get_actuator_returns_none_when_target_paused(self):
        SocketUserManager._actuator_users["A1"] = self._make_actuator("A1", is_open=False)
        self.assertIsNone(SocketUserManager.get_actuator("A1"))

    def test_get_actuator_default_skips_paused_and_picks_open(self):
        SocketUserManager._actuator_users["A1"] = self._make_actuator("A1", is_open=False)
        SocketUserManager._actuator_users["A2"] = self._make_actuator("A2", is_open=True)
        consumer = SocketUserManager.get_actuator()
        self.assertIsNotNone(consumer)
        self.assertEqual(consumer.actuator_info["id"], "A2")

    def test_get_actuator_default_returns_none_when_all_paused(self):
        SocketUserManager._actuator_users["A1"] = self._make_actuator("A1", is_open=False)
        SocketUserManager._actuator_users["A2"] = self._make_actuator("A2", is_open=False)
        self.assertIsNone(SocketUserManager.get_actuator())

    def test_get_actuator_by_id_ignores_open_flag(self):
        """get_actuator_by_id 用于设置/查询 OPEN 状态本身，不能按 is_open 过滤。"""
        SocketUserManager._actuator_users["A1"] = self._make_actuator("A1", is_open=False)
        self.assertIsNotNone(SocketUserManager.get_actuator_by_id("A1"))


class TriggerBatchExecutionViewTests(TestCase):
    """POST /api/ui-automation/trigger-batch/ 入口（定时任务调用路径）。"""

    def setUp(self):
        SocketUserManager._actuator_users.clear()
        self.user = User.objects.create_user(username="trigger_tester", password="test123456")
        self.project = Project.objects.create(
            name="trigger-project", description="test", creator=self.user,
        )
        self.module = UiModule.objects.create(
            project=self.project, name="登录模块", creator=self.user,
        )
        self.test_case = UiTestCase.objects.create(
            project=self.project, module=self.module, name="登录用例", creator=self.user,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def tearDown(self):
        SocketUserManager._actuator_users.clear()

    def _register_actuator(self, actuator_id, is_open=True):
        consumer = MagicMock(spec=UiAutomationConsumer)
        consumer.actuator_info = {"id": actuator_id, "is_open": is_open}
        consumer.send_json = AsyncMock(return_value=None)
        SocketUserManager._actuator_users[actuator_id] = consumer
        return consumer

    def test_returns_400_when_no_case_ids(self):
        resp = self.client.post(
            "/api/ui-automation/trigger-batch/",
            {"actuator_id": "A1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_returns_503_when_actuator_offline(self):
        resp = self.client.post(
            "/api/ui-automation/trigger-batch/",
            {"case_ids": [self.test_case.id], "actuator_id": "missing"},
            format="json",
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("不在线", resp.data.get("error", ""))

    def test_returns_503_when_actuator_paused(self):
        self._register_actuator("A1", is_open=False)
        resp = self.client.post(
            "/api/ui-automation/trigger-batch/",
            {"case_ids": [self.test_case.id], "actuator_id": "A1"},
            format="json",
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("暂停接单", resp.data.get("error", ""))

    def test_returns_503_when_no_actuator_specified_and_none_open(self):
        self._register_actuator("A1", is_open=False)
        resp = self.client.post(
            "/api/ui-automation/trigger-batch/",
            {"case_ids": [self.test_case.id]},
            format="json",
        )
        self.assertEqual(resp.status_code, 503)
        self.assertIn("没有可用的执行器", resp.data.get("error", ""))

    def test_creates_batch_and_dispatches_to_actuator(self):
        consumer = self._register_actuator("A1", is_open=True)
        resp = self.client.post(
            "/api/ui-automation/trigger-batch/",
            {
                "case_ids": [self.test_case.id],
                "actuator_id": "A1",
                "trigger_type": "scheduled",
                "batch_name": "定时任务-冒烟",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        batch_id = resp.data["data"]["batch_id"]
        batch = UiBatchExecutionRecord.objects.get(id=batch_id)
        self.assertEqual(batch.trigger_type, "scheduled")
        self.assertEqual(batch.total_cases, 1)
        self.assertEqual(batch.status, 1)  # 执行中
        self.assertEqual(batch.name, "定时任务-冒烟")
        consumer.send_json.assert_awaited_once()


class UiBatchExecutionStatisticsTests(TestCase):
    """UiBatchExecutionRecord.update_statistics 的状态计算"""

    def setUp(self):
        self.user = User.objects.create_user(username="stat_tester", password="test123456")
        self.project = Project.objects.create(
            name="stat-project", description="test", creator=self.user,
        )
        self.module = UiModule.objects.create(
            project=self.project, name="m", creator=self.user,
        )
        self.case = UiTestCase.objects.create(
            project=self.project, module=self.module, name="c", creator=self.user,
        )

    def _add_record(self, batch, status):
        return UiExecutionRecord.objects.create(
            batch=batch,
            test_case=self.case,
            status=status,
            trigger_type='manual',
            executor=self.user,
        )

    def _make_batch(self, total):
        from django.utils import timezone as tz
        return UiBatchExecutionRecord.objects.create(
            name="b",
            total_cases=total,
            status=1,
            trigger_type='manual',
            executor=self.user,
            start_time=tz.now(),
        )

    def test_update_statistics_all_success(self):
        batch = self._make_batch(total=2)
        self._add_record(batch, status=2)
        self._add_record(batch, status=2)
        batch.update_statistics()
        self.assertEqual(batch.passed_cases, 2)
        self.assertEqual(batch.failed_cases, 0)
        self.assertEqual(batch.status, 2)
        self.assertIsNotNone(batch.end_time)

    def test_update_statistics_all_failed(self):
        batch = self._make_batch(total=2)
        self._add_record(batch, status=3)
        self._add_record(batch, status=3)
        batch.update_statistics()
        self.assertEqual(batch.failed_cases, 2)
        self.assertEqual(batch.status, 4)

    def test_update_statistics_partial_failure(self):
        batch = self._make_batch(total=2)
        self._add_record(batch, status=2)
        self._add_record(batch, status=3)
        batch.update_statistics()
        self.assertEqual(batch.passed_cases, 1)
        self.assertEqual(batch.failed_cases, 1)
        self.assertEqual(batch.status, 3)

    def test_update_statistics_keeps_running_when_not_complete(self):
        """部分用例还在执行时，status 不应被改写为终态。"""
        batch = self._make_batch(total=3)
        self._add_record(batch, status=2)
        self._add_record(batch, status=0)  # 未执行
        self._add_record(batch, status=1)  # 执行中
        batch.update_statistics()
        self.assertEqual(batch.passed_cases, 1)
        self.assertEqual(batch.failed_cases, 0)
        self.assertEqual(batch.status, 1)
        self.assertIsNone(batch.end_time)


class UiModuleLevelTests(TestCase):
    """UiModule.clean 应该自动级联 level，并阻止超过 5 级。"""

    def setUp(self):
        self.user = User.objects.create_user(username="level_tester", password="test123456")
        self.project = Project.objects.create(
            name="level-project", description="test", creator=self.user,
        )

    def test_level_cascades_from_parent(self):
        m1 = UiModule.objects.create(project=self.project, name="m1", creator=self.user)
        m2 = UiModule.objects.create(project=self.project, name="m2", parent=m1, creator=self.user)
        m3 = UiModule.objects.create(project=self.project, name="m3", parent=m2, creator=self.user)
        self.assertEqual(m1.level, 1)
        self.assertEqual(m2.level, 2)
        self.assertEqual(m3.level, 3)

    def test_level_validation_rejects_explicit_overlevel(self):
        """直接构造 level>5 的实例时，clean() 应该报错。"""
        from django.core.exceptions import ValidationError
        bad = UiModule(project=self.project, name="bad", creator=self.user, level=6)
        with self.assertRaises(ValidationError):
            bad.save()

    def test_parent_must_be_in_same_project(self):
        from django.core.exceptions import ValidationError
        other_project = Project.objects.create(
            name="other", description="t", creator=self.user,
        )
        outside_parent = UiModule.objects.create(
            project=other_project, name="outside", creator=self.user,
        )
        with self.assertRaises(ValidationError):
            UiModule.objects.create(
                project=self.project, name="bad", parent=outside_parent, creator=self.user,
            )

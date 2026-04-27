from datetime import time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django_celery_beat.models import PeriodicTask

from projects.models import Project
from ui_automation.models import UiBatchExecutionRecord, UiModule, UiTestCase
from api_automation.models import ApiBatchExecutionRecord, ApiModule, ApiTestCase
from .models import ScheduledTask, TaskExecution
from .scheduler import _beat_name, register_periodic_task, unregister_periodic_task
from .serializers import ScheduledTaskSerializer, TaskExecutionSerializer
from .utils import (
    extract_api_batch_id,
    extract_suite_execution_id,
    extract_ui_batch_id,
    format_duration_value,
)


User = get_user_model()


class TaskExecutionSerializerTests(TestCase):
    def test_ui_automation_task_execution_links_batch_result(self):
        user = User.objects.create_user(username="scheduler", password="test123456")
        project = Project.objects.create(name="task-project", creator=user)
        module = UiModule.objects.create(project=project, name="用户登录模块", creator=user)
        ui_case = UiTestCase.objects.create(
            project=project,
            module=module,
            name="登录成功",
            creator=user,
        )
        task = ScheduledTask.objects.create(
            name="UI 登录定时任务",
            project=project,
            module=ScheduledTask.TaskModule.UI_AUTOMATION,
            execution_target=ScheduledTask.ExecutionTarget.ACTUATOR,
            actuator_id="WHartTest-001",
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=timezone.now() + timedelta(minutes=5),
            status=ScheduledTask.TaskStatus.RUNNING,
            creator=user,
        )
        task.ui_testcases.add(ui_case)
        batch = UiBatchExecutionRecord.objects.create(
            name="定时任务-UI 登录定时任务",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            status=2,
            trigger_type="scheduled",
            executor=user,
            start_time=timezone.now() - timedelta(seconds=2),
            end_time=timezone.now(),
            duration=2,
        )
        execution = TaskExecution.objects.create(
            task=task,
            trigger_type=TaskExecution.TriggerType.SCHEDULED,
            status=TaskExecution.ExecutionStatus.SUCCESS,
            finished_at=timezone.now(),
            log=f"[2026-04-23 12:00:00] 批量执行已触发: batch_id={batch.id}",
        )

        data = TaskExecutionSerializer(execution).data

        self.assertEqual(data["actual_execution_id"], batch.id)
        self.assertEqual(data["actual_result_status"], "passed")
        self.assertEqual(data["actual_result_text"], "通过")
        self.assertEqual(data["actual_duration"], "2s")
        self.assertEqual(data["actual_summary"], "总 1 / 通过 1 / 失败 0")

    def test_api_automation_task_execution_links_batch_result(self):
        user = User.objects.create_user(username="api_scheduler", password="test123456")
        project = Project.objects.create(name="api-task-project", creator=user)
        module = ApiModule.objects.create(project=project, name="用户接口模块", creator=user)
        api_case = ApiTestCase.objects.create(
            project=project,
            module=module,
            name="查询用户列表",
            method="GET",
            path="/users",
            creator=user,
        )
        task = ScheduledTask.objects.create(
            name="接口登录定时任务",
            project=project,
            module=ScheduledTask.TaskModule.API_AUTOMATION,
            execution_target=ScheduledTask.ExecutionTarget.BACKEND,
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=timezone.now() + timedelta(minutes=5),
            status=ScheduledTask.TaskStatus.RUNNING,
            creator=user,
        )
        task.api_testcases.add(api_case)
        batch = ApiBatchExecutionRecord.objects.create(
            project=project,
            name="定时任务-接口登录定时任务",
            total_cases=1,
            passed_cases=1,
            failed_cases=0,
            status=2,
            trigger_type="scheduled",
            executor=user,
            start_time=timezone.now() - timedelta(seconds=1),
            end_time=timezone.now(),
            duration=1,
        )
        execution = TaskExecution.objects.create(
            task=task,
            trigger_type=TaskExecution.TriggerType.SCHEDULED,
            status=TaskExecution.ExecutionStatus.SUCCESS,
            finished_at=timezone.now(),
            log=f"[2026-04-23 12:00:00] 接口批量执行已触发: batch_id={batch.id}",
        )

        data = TaskExecutionSerializer(execution).data

        self.assertEqual(data["actual_execution_id"], batch.id)
        self.assertEqual(data["actual_result_status"], "passed")
        self.assertEqual(data["actual_result_text"], "通过")
        self.assertEqual(data["actual_duration"], "1s")
        self.assertEqual(data["actual_summary"], "总 1 / 通过 1 / 失败 0")


class TaskCenterUtilsTests(TestCase):
    """日志解析与时长格式化"""

    def test_extract_ui_batch_id(self):
        log = "[2026-04-23 12:00:00] 批量执行已触发: batch_id=42"
        self.assertEqual(extract_ui_batch_id(log), 42)
        self.assertIsNone(extract_ui_batch_id(""))
        self.assertIsNone(extract_ui_batch_id("无关日志"))

    def test_extract_api_batch_id_does_not_match_ui_log(self):
        ui_log = "[2026-04-23 12:00:00] 批量执行已触发: batch_id=42"
        api_log = "[2026-04-23 12:00:00] 接口批量执行已触发: batch_id=99"
        self.assertIsNone(extract_api_batch_id(ui_log))
        self.assertEqual(extract_api_batch_id(api_log), 99)

    def test_extract_suite_execution_id_supports_both_phrases(self):
        log_a = "[2026-04-23 12:00:00] 套件执行已提交: execution_id=1"
        log_b = "[2026-04-23 12:00:00] 套件执行已触发: execution_id=2"
        self.assertEqual(extract_suite_execution_id(log_a), 1)
        self.assertEqual(extract_suite_execution_id(log_b), 2)

    def test_format_duration_value(self):
        self.assertEqual(format_duration_value(None), "—")
        self.assertEqual(format_duration_value(-1), "—")
        self.assertEqual(format_duration_value(0.5), "<1s")
        self.assertEqual(format_duration_value(45), "45s")
        self.assertEqual(format_duration_value(125), "2m 5s")
        self.assertEqual(format_duration_value(3725), "1h 2m 5s")
        self.assertEqual(format_duration_value("not-a-number"), "—")


class SchedulerRegistrationTests(TestCase):
    """register_periodic_task / unregister_periodic_task 应正确注册到 django-celery-beat。"""

    def setUp(self):
        self.user = User.objects.create_user(username="sched_tester", password="test123456")
        self.project = Project.objects.create(name="sched-project", creator=self.user)
        self.module = UiModule.objects.create(project=self.project, name="登录", creator=self.user)
        self.case = UiTestCase.objects.create(
            project=self.project, module=self.module, name="登录用例", creator=self.user,
        )

    def _make_task(self, **overrides):
        defaults = dict(
            name="测试调度任务",
            project=self.project,
            module=ScheduledTask.TaskModule.UI_AUTOMATION,
            execution_target=ScheduledTask.ExecutionTarget.ACTUATOR,
            actuator_id="WHartTest-001",
            schedule_type=ScheduledTask.ScheduleType.DAILY,
            daily_time=time(9, 30),
            task_timezone="Asia/Dubai",
            status=ScheduledTask.TaskStatus.RUNNING,
            creator=self.user,
        )
        defaults.update(overrides)
        task = ScheduledTask.objects.create(**defaults)
        task.ui_testcases.add(self.case)
        return task

    def test_register_daily_uses_task_timezone(self):
        task = self._make_task(daily_time=time(9, 30), task_timezone="Asia/Dubai")
        register_periodic_task(task)

        pt = PeriodicTask.objects.get(name=_beat_name(task))
        crontab = pt.crontab
        self.assertEqual(crontab.hour, "9")
        self.assertEqual(crontab.minute, "30")
        self.assertEqual(crontab.day_of_week, "*")
        self.assertEqual(str(crontab.timezone), "Asia/Dubai")

    def test_register_weekly_maps_days_correctly(self):
        # weekly_days: 0=周一, 6=周日；cron: 0=Sunday..6=Saturday
        task = self._make_task(
            schedule_type=ScheduledTask.ScheduleType.WEEKLY,
            daily_time=None,
            weekly_days=[0, 6],
            weekly_time=time(8, 0),
        )
        register_periodic_task(task)
        pt = PeriodicTask.objects.get(name=_beat_name(task))
        crontab = pt.crontab
        self.assertEqual(set(crontab.day_of_week.split(",")), {"0", "1"})
        self.assertEqual(crontab.hour, "8")
        self.assertEqual(crontab.minute, "0")

    def test_register_hourly_uses_minute(self):
        task = self._make_task(
            schedule_type=ScheduledTask.ScheduleType.HOURLY,
            daily_time=None,
            hourly_minute=15,
        )
        register_periodic_task(task)
        pt = PeriodicTask.objects.get(name=_beat_name(task))
        crontab = pt.crontab
        self.assertEqual(crontab.minute, "15")
        self.assertEqual(crontab.hour, "*")

    def test_register_once_creates_clocked_schedule(self):
        future = timezone.now() + timedelta(minutes=5)
        task = self._make_task(
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=future,
            daily_time=None,
        )
        register_periodic_task(task)
        pt = PeriodicTask.objects.get(name=_beat_name(task))
        self.assertIsNotNone(pt.clocked)
        self.assertIsNone(pt.crontab)
        self.assertTrue(pt.one_off)

    def test_register_once_skipped_for_past_time(self):
        past = timezone.now() - timedelta(minutes=5)
        task = self._make_task(
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=past,
            daily_time=None,
        )
        register_periodic_task(task)
        self.assertFalse(PeriodicTask.objects.filter(name=_beat_name(task)).exists())

    def test_unregister_removes_periodic_task(self):
        task = self._make_task()
        register_periodic_task(task)
        self.assertTrue(PeriodicTask.objects.filter(name=_beat_name(task)).exists())

        unregister_periodic_task(task)
        self.assertFalse(PeriodicTask.objects.filter(name=_beat_name(task)).exists())


class ScheduledTaskValidationTests(TestCase):
    """ScheduledTaskSerializer.validate 各模块/各调度类型规则"""

    def setUp(self):
        self.user = User.objects.create_user(username="validator", password="test123456")
        self.project = Project.objects.create(name="validator-project", creator=self.user)
        self.ui_module = UiModule.objects.create(project=self.project, name="m", creator=self.user)
        self.ui_case = UiTestCase.objects.create(
            project=self.project, module=self.ui_module, name="c", creator=self.user,
        )
        self.api_module = ApiModule.objects.create(project=self.project, name="m", creator=self.user)
        self.api_case = ApiTestCase.objects.create(
            project=self.project,
            module=self.api_module,
            name="c",
            method="GET",
            path="/x",
            creator=self.user,
        )

    def _base_payload(self, **extra):
        payload = {
            "name": "T1",
            "module": ScheduledTask.TaskModule.UI_AUTOMATION,
            "execution_target": ScheduledTask.ExecutionTarget.ACTUATOR,
            "schedule_type": ScheduledTask.ScheduleType.DAILY,
            "daily_time": "09:00:00",
            "ui_testcase_ids": [self.ui_case.id],
            "actuator_id": "WHartTest-001",
        }
        payload.update(extra)
        return payload

    def test_valid_ui_payload_passes(self):
        ser = ScheduledTaskSerializer(data=self._base_payload())
        self.assertTrue(ser.is_valid(), msg=ser.errors)

    def test_ui_module_requires_actuator_id(self):
        ser = ScheduledTaskSerializer(data=self._base_payload(actuator_id=""))
        self.assertFalse(ser.is_valid())
        self.assertIn("actuator_id", ser.errors)

    def test_ui_module_requires_at_least_one_case(self):
        ser = ScheduledTaskSerializer(data=self._base_payload(ui_testcase_ids=[]))
        self.assertFalse(ser.is_valid())
        self.assertIn("ui_testcase_ids", ser.errors)

    def test_api_module_requires_at_least_one_case(self):
        payload = self._base_payload(
            module=ScheduledTask.TaskModule.API_AUTOMATION,
            actuator_id="",
            ui_testcase_ids=[],
        )
        ser = ScheduledTaskSerializer(data=payload)
        self.assertFalse(ser.is_valid())
        self.assertIn("api_testcase_ids", ser.errors)

    def test_once_requires_future_datetime(self):
        past = (timezone.now() - timedelta(minutes=10)).isoformat()
        payload = self._base_payload(
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=past,
            daily_time=None,
        )
        ser = ScheduledTaskSerializer(data=payload)
        self.assertFalse(ser.is_valid())
        self.assertIn("once_datetime", ser.errors)

    def test_weekly_requires_days(self):
        payload = self._base_payload(
            schedule_type=ScheduledTask.ScheduleType.WEEKLY,
            daily_time=None,
            weekly_days=[],
            weekly_time="10:00:00",
        )
        ser = ScheduledTaskSerializer(data=payload)
        self.assertFalse(ser.is_valid())
        self.assertIn("weekly_days", ser.errors)

    def test_hourly_requires_minute(self):
        payload = self._base_payload(
            schedule_type=ScheduledTask.ScheduleType.HOURLY,
            daily_time=None,
        )
        ser = ScheduledTaskSerializer(data=payload)
        self.assertFalse(ser.is_valid())
        self.assertIn("hourly_minute", ser.errors)


class ScheduledTaskExecutionTests(TestCase):
    """execute_scheduled_task celery 入口的关键分支"""

    def setUp(self):
        self.user = User.objects.create_user(username="executor", password="test123456")
        self.project = Project.objects.create(name="executor-project", creator=self.user)
        self.api_module = ApiModule.objects.create(
            project=self.project, name="API 模块", creator=self.user,
        )
        self.api_case = ApiTestCase.objects.create(
            project=self.project,
            module=self.api_module,
            name="case",
            method="GET",
            path="/x",
            creator=self.user,
        )

    def _make_api_task(self, **overrides):
        defaults = dict(
            name="API 定时任务",
            project=self.project,
            module=ScheduledTask.TaskModule.API_AUTOMATION,
            execution_target=ScheduledTask.ExecutionTarget.BACKEND,
            schedule_type=ScheduledTask.ScheduleType.HOURLY,
            hourly_minute=15,
            status=ScheduledTask.TaskStatus.RUNNING,
            creator=self.user,
        )
        defaults.update(overrides)
        task = ScheduledTask.objects.create(**defaults)
        task.api_testcases.add(self.api_case)
        return task

    def test_skips_disabled_task_when_scheduled(self):
        from .tasks import execute_scheduled_task

        task = self._make_api_task(status=ScheduledTask.TaskStatus.DISABLED)
        result = execute_scheduled_task.apply(args=[task.id, 'scheduled']).get()
        self.assertEqual(result, {'status': 'skipped', 'message': '任务已禁用'})
        self.assertEqual(task.executions.count(), 0)

    def test_returns_error_when_task_missing(self):
        from .tasks import execute_scheduled_task

        result = execute_scheduled_task.apply(args=[9999999, 'manual']).get()
        self.assertEqual(result['status'], 'error')

    @patch("api_automation.tasks.execute_api_batch_task.delay")
    def test_api_module_creates_batch_and_dispatches(self, delay_mock):
        from .tasks import execute_scheduled_task

        task = self._make_api_task()
        result = execute_scheduled_task.apply(args=[task.id, 'scheduled']).get()

        self.assertEqual(result['status'], 'success')
        batch = ApiBatchExecutionRecord.objects.get(name=f"定时任务-{task.name}")
        self.assertEqual(batch.total_cases, 1)
        self.assertEqual(batch.execution_records.count(), 1)
        delay_mock.assert_called_once_with(batch.id)

        execution = task.executions.latest('id')
        self.assertEqual(execution.status, TaskExecution.ExecutionStatus.SUCCESS)
        self.assertIn(f"接口批量执行已触发: batch_id={batch.id}", execution.log)

    def test_api_module_fails_when_no_cases(self):
        from .tasks import execute_scheduled_task

        task = self._make_api_task()
        task.api_testcases.clear()
        result = execute_scheduled_task.apply(args=[task.id, 'manual']).get()

        self.assertEqual(result['status'], 'failed')
        execution = task.executions.latest('id')
        self.assertEqual(execution.status, TaskExecution.ExecutionStatus.FAILED)
        self.assertIn("未关联任何接口自动化用例", execution.error_message)

    @patch("api_automation.tasks.execute_api_batch_task.delay")
    def test_once_task_disabled_after_success(self, _delay_mock):
        from .tasks import execute_scheduled_task

        task = self._make_api_task(
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=timezone.now() + timedelta(minutes=5),
            hourly_minute=None,
        )
        execute_scheduled_task.apply(args=[task.id, 'manual']).get()
        task.refresh_from_db()
        self.assertEqual(task.status, ScheduledTask.TaskStatus.DISABLED)


class ScheduledTaskModelTests(TestCase):
    """ScheduledTask.get_schedule_display_text 与 TaskExecution 字段行为"""

    def setUp(self):
        self.user = User.objects.create_user(username="model_tester", password="test123456")
        self.project = Project.objects.create(name="model-project", creator=self.user)

    def _make(self, **overrides):
        defaults = dict(
            name="t",
            project=self.project,
            module=ScheduledTask.TaskModule.TEST_SUITE,
            schedule_type=ScheduledTask.ScheduleType.DAILY,
            daily_time=time(8, 0),
            creator=self.user,
        )
        defaults.update(overrides)
        return ScheduledTask.objects.create(**defaults)

    def test_schedule_display_text_daily(self):
        task = self._make(daily_time=time(9, 5))
        self.assertEqual(task.get_schedule_display_text(), "每天 09:05")

    def test_schedule_display_text_weekly(self):
        task = self._make(
            schedule_type=ScheduledTask.ScheduleType.WEEKLY,
            daily_time=None,
            weekly_days=[0, 2, 6],
            weekly_time=time(20, 0),
        )
        text = task.get_schedule_display_text()
        self.assertIn("周一", text)
        self.assertIn("周三", text)
        self.assertIn("周日", text)
        self.assertIn("20:00", text)

    def test_schedule_display_text_hourly(self):
        task = self._make(
            schedule_type=ScheduledTask.ScheduleType.HOURLY,
            daily_time=None,
            hourly_minute=15,
        )
        self.assertEqual(task.get_schedule_display_text(), "每小时第 15 分钟")

    def test_task_execution_id_auto_generated(self):
        task = self._make()
        execution = TaskExecution.objects.create(
            task=task,
            trigger_type=TaskExecution.TriggerType.MANUAL,
        )
        self.assertTrue(execution.execution_id.startswith("run_"))
        self.assertGreater(len(execution.execution_id), 10)

    def test_duration_display_returns_dash_when_unfinished(self):
        task = self._make()
        execution = TaskExecution.objects.create(
            task=task,
            trigger_type=TaskExecution.TriggerType.MANUAL,
        )
        self.assertEqual(execution.duration_display, "—")

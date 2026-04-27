from django.utils import timezone
from rest_framework import serializers
from .models import ScheduledTask, TaskExecution
from ui_automation.models import UiTestCase
from ui_automation.models import UiBatchExecutionRecord
from api_automation.models import ApiTestCase
from api_automation.models import ApiBatchExecutionRecord as ApiBatchRecord
from testcases.models import TestExecution as SuiteExecution
from .utils import extract_suite_execution_id, extract_ui_batch_id, extract_api_batch_id, format_duration_value


class ScheduledTaskSerializer(serializers.ModelSerializer):
    schedule_display = serializers.SerializerMethodField()
    creator_name = serializers.SerializerMethodField()
    test_suite_name = serializers.SerializerMethodField()
    scheduler_timezone = serializers.SerializerMethodField()
    ui_testcase_ids = serializers.PrimaryKeyRelatedField(
        source='ui_testcases', many=True,
        queryset=UiTestCase.objects.all(), required=False
    )
    api_testcase_ids = serializers.PrimaryKeyRelatedField(
        source='api_testcases', many=True,
        queryset=ApiTestCase.objects.all(), required=False
    )

    class Meta:
        model = ScheduledTask
        fields = [
            'id', 'name', 'description', 'project', 'module',
            'execution_target', 'schedule_type', 'once_datetime',
            'daily_time', 'weekly_days', 'weekly_time', 'hourly_minute',
            'task_timezone', 'retry_enabled', 'retry_count', 'retry_interval',
            'status', 'last_run_at', 'creator', 'creator_name',
            'schedule_display', 'created_at', 'updated_at',
            'test_suite', 'test_suite_name', 'ui_testcase_ids', 'api_testcase_ids',
            'actuator_id', 'scheduler_timezone',
        ]
        read_only_fields = [
            'project', 'status', 'last_run_at', 'creator', 'creator_name',
            'schedule_display', 'created_at', 'updated_at',
            'test_suite_name', 'scheduler_timezone',
        ]
        extra_kwargs = {
            'task_timezone': {'required': False},
        }

    def get_schedule_display(self, obj):
        return obj.get_schedule_display_text()

    def get_creator_name(self, obj):
        if obj.creator:
            return obj.creator.get_full_name() or obj.creator.username
        return None

    def get_test_suite_name(self, obj):
        if obj.test_suite:
            return obj.test_suite.name
        return None

    def get_scheduler_timezone(self, obj):
        return timezone.get_current_timezone_name()

    def validate_name(self, value):
        if len(value) > 50:
            raise serializers.ValidationError('任务名称最大长度为50字符')
        return value

    def validate(self, attrs):
        schedule_type = attrs.get('schedule_type', getattr(self.instance, 'schedule_type', None))
        module = attrs.get('module', getattr(self.instance, 'module', None))

        # 模块关联验证
        if module == ScheduledTask.TaskModule.TEST_SUITE:
            if not attrs.get('test_suite') and not getattr(self.instance, 'test_suite', None):
                raise serializers.ValidationError({'test_suite': '测试套件模块必须关联一个测试套件'})
        elif module == ScheduledTask.TaskModule.UI_AUTOMATION:
            ui_testcases = attrs.get('ui_testcases')
            if ui_testcases is None and self.instance is not None:
                ui_testcases = self.instance.ui_testcases.all()
            if not ui_testcases:
                raise serializers.ValidationError({'ui_testcase_ids': 'UI 自动化模块必须至少关联一个 UI 用例'})
            actuator_id = attrs.get('actuator_id', getattr(self.instance, 'actuator_id', ''))
            if not actuator_id:
                raise serializers.ValidationError({'actuator_id': 'UI 自动化模块必须选择一个执行器'})
        elif module == ScheduledTask.TaskModule.API_AUTOMATION:
            api_testcases = attrs.get('api_testcases')
            if api_testcases is None and self.instance is not None:
                api_testcases = self.instance.api_testcases.all()
            if not api_testcases:
                raise serializers.ValidationError({'api_testcase_ids': '接口自动化模块必须至少关联一个接口用例'})

        if schedule_type == ScheduledTask.ScheduleType.ONCE:
            once_datetime = attrs.get('once_datetime', getattr(self.instance, 'once_datetime', None))
            if not once_datetime:
                raise serializers.ValidationError({'once_datetime': '仅执行一次时必须指定执行时间'})
            if once_datetime <= timezone.now():
                raise serializers.ValidationError({'once_datetime': '仅执行一次时必须选择未来时间'})
        elif schedule_type == ScheduledTask.ScheduleType.DAILY:
            if not attrs.get('daily_time') and not getattr(self.instance, 'daily_time', None):
                raise serializers.ValidationError({'daily_time': '每天执行时必须指定时间'})
        elif schedule_type == ScheduledTask.ScheduleType.WEEKLY:
            weekly_days = attrs.get('weekly_days', getattr(self.instance, 'weekly_days', None))
            if not weekly_days:
                raise serializers.ValidationError({'weekly_days': '每周执行时必须选择至少一天'})
            if not attrs.get('weekly_time') and not getattr(self.instance, 'weekly_time', None):
                raise serializers.ValidationError({'weekly_time': '每周执行时必须指定时间'})
        elif schedule_type == ScheduledTask.ScheduleType.HOURLY:
            hourly_minute = attrs.get('hourly_minute', getattr(self.instance, 'hourly_minute', None))
            if hourly_minute is None:
                raise serializers.ValidationError({'hourly_minute': '每小时执行时必须指定分钟数'})

        return attrs


class TaskExecutionSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    display_status = serializers.SerializerMethodField()
    display_status_text = serializers.SerializerMethodField()
    actual_execution_id = serializers.SerializerMethodField()
    actual_result_status = serializers.SerializerMethodField()
    actual_result_text = serializers.SerializerMethodField()
    actual_duration = serializers.SerializerMethodField()
    actual_summary = serializers.SerializerMethodField()

    class Meta:
        model = TaskExecution
        fields = [
            'id', 'execution_id', 'task', 'trigger_type', 'status',
            'started_at', 'finished_at', 'duration', 'log', 'error_message',
            'display_status', 'display_status_text',
            'actual_execution_id', 'actual_result_status', 'actual_result_text',
            'actual_duration', 'actual_summary',
        ]
        read_only_fields = fields

    def get_duration(self, obj):
        return obj.duration_display

    def _get_related_suite_execution(self, obj):
        cached = getattr(obj, '_related_suite_execution_cache', None)
        if cached is not None:
            return cached

        suite_execution = None
        if obj.task.module == ScheduledTask.TaskModule.TEST_SUITE:
            suite_execution_id = extract_suite_execution_id(obj.log)
            if suite_execution_id:
                suite_execution = (
                    SuiteExecution.objects
                    .filter(id=suite_execution_id)
                    .select_related('suite')
                    .first()
                )

        setattr(obj, '_related_suite_execution_cache', suite_execution or False)
        return suite_execution

    def _get_related_ui_batch(self, obj):
        cached = getattr(obj, '_related_ui_batch_cache', None)
        if cached is not None:
            return cached

        ui_batch = None
        if obj.task.module == ScheduledTask.TaskModule.UI_AUTOMATION:
            batch_id = extract_ui_batch_id(obj.log)
            if batch_id:
                ui_batch = UiBatchExecutionRecord.objects.filter(id=batch_id).first()

        setattr(obj, '_related_ui_batch_cache', ui_batch or False)
        return ui_batch

    def _get_related_api_batch(self, obj):
        cached = getattr(obj, '_related_api_batch_cache', None)
        if cached is not None:
            return cached

        api_batch = None
        if obj.task.module == ScheduledTask.TaskModule.API_AUTOMATION:
            batch_id = extract_api_batch_id(obj.log)
            if batch_id:
                api_batch = ApiBatchRecord.objects.filter(id=batch_id).first()

        setattr(obj, '_related_api_batch_cache', api_batch or False)
        return api_batch

    def _get_actual_result_tuple(self, obj):
        api_batch = self._get_related_api_batch(obj)
        if api_batch:
            mapping = {
                0: ('pending', '待执行'),
                1: ('running', '执行中'),
                2: ('passed', '通过'),
                3: ('failed', '部分失败'),
                4: ('failed', '失败'),
            }
            return mapping.get(api_batch.status, (str(api_batch.status), api_batch.get_status_display()))

        ui_batch = self._get_related_ui_batch(obj)
        if ui_batch:
            mapping = {
                0: ('pending', '待执行'),
                1: ('running', '执行中'),
                2: ('passed', '通过'),
                3: ('failed', '部分失败'),
                4: ('failed', '失败'),
            }
            return mapping.get(ui_batch.status, (str(ui_batch.status), ui_batch.get_status_display()))

        suite_execution = self._get_related_suite_execution(obj)
        if not suite_execution:
            return None, None

        if suite_execution.status == 'pending':
            return 'pending', '等待中'
        if suite_execution.status == 'running':
            return 'running', '执行中'
        if suite_execution.status == 'cancelled':
            return 'cancelled', '已取消'
        if suite_execution.status == 'failed':
            return 'failed', '失败'
        if suite_execution.status == 'completed':
            if suite_execution.failed_count > 0 or suite_execution.error_count > 0:
                return 'failed', '失败'
            if suite_execution.passed_count > 0 and suite_execution.failed_count == 0 and suite_execution.error_count == 0:
                return 'passed', '通过'
            return 'completed', '已完成'

        return suite_execution.status, suite_execution.get_status_display()

    def get_display_status(self, obj):
        mapping = {
            TaskExecution.ExecutionStatus.RUNNING: 'submitting',
            TaskExecution.ExecutionStatus.SUCCESS: 'triggered',
            TaskExecution.ExecutionStatus.FAILED: 'failed',
        }
        return mapping.get(obj.status, obj.status)

    def get_display_status_text(self, obj):
        mapping = {
            'submitting': '提交中',
            'triggered': '已触发',
            'failed': '触发失败',
        }
        return mapping.get(self.get_display_status(obj), obj.get_status_display())

    def get_actual_execution_id(self, obj):
        api_batch = self._get_related_api_batch(obj)
        if api_batch:
            return api_batch.id
        ui_batch = self._get_related_ui_batch(obj)
        if ui_batch:
            return ui_batch.id
        suite_execution = self._get_related_suite_execution(obj)
        return suite_execution.id if suite_execution else None

    def get_actual_result_status(self, obj):
        status_code, _ = self._get_actual_result_tuple(obj)
        return status_code

    def get_actual_result_text(self, obj):
        _, text = self._get_actual_result_tuple(obj)
        return text

    def get_actual_duration(self, obj):
        api_batch = self._get_related_api_batch(obj)
        if api_batch:
            return format_duration_value(api_batch.duration)
        ui_batch = self._get_related_ui_batch(obj)
        if ui_batch:
            return format_duration_value(ui_batch.duration)
        suite_execution = self._get_related_suite_execution(obj)
        if not suite_execution:
            return None
        return format_duration_value(suite_execution.duration)

    def get_actual_summary(self, obj):
        api_batch = self._get_related_api_batch(obj)
        if api_batch:
            return (
                f"总 {api_batch.total_cases} / 通过 {api_batch.passed_cases} / "
                f"失败 {api_batch.failed_cases}"
            )
        ui_batch = self._get_related_ui_batch(obj)
        if ui_batch:
            return (
                f"总 {ui_batch.total_cases} / 通过 {ui_batch.passed_cases} / "
                f"失败 {ui_batch.failed_cases}"
            )
        suite_execution = self._get_related_suite_execution(obj)
        if not suite_execution:
            return None
        return (
            f"总 {suite_execution.total_count} / 通过 {suite_execution.passed_count} / "
            f"失败 {suite_execution.failed_count} / 错误 {suite_execution.error_count} / "
            f"跳过 {suite_execution.skipped_count}"
        )

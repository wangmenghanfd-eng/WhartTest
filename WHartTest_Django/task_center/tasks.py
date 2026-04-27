"""
Celery 任务定义 - 定时任务执行入口
"""
import logging
from celery import shared_task
from django.utils import timezone
from .utils import append_log

logger = logging.getLogger(__name__)


@shared_task(bind=True, name='task_center.tasks.execute_scheduled_task')
def execute_scheduled_task(self, task_id: int, trigger_type: str = 'scheduled'):
    """执行定时任务的 Celery 入口"""
    from .models import ScheduledTask, TaskExecution

    try:
        task = ScheduledTask.objects.get(id=task_id)
    except ScheduledTask.DoesNotExist:
        logger.error(f"任务 ID={task_id} 不存在")
        return {'status': 'error', 'message': f'任务 {task_id} 不存在'}

    # 一次性任务若已被禁用且非手动触发，跳过执行
    if task.status == ScheduledTask.TaskStatus.DISABLED and trigger_type == 'scheduled':
        logger.info(f"任务 [{task.name}] 已禁用，跳过定时执行")
        return {'status': 'skipped', 'message': '任务已禁用'}

    # 创建执行记录
    execution = TaskExecution.objects.create(
        task=task,
        trigger_type=trigger_type,
        status=TaskExecution.ExecutionStatus.RUNNING,
        celery_task_id=self.request.id or '',
    )

    task.last_run_at = timezone.now()
    task.save(update_fields=['last_run_at'])

    log_lines = []
    try:
        append_log(log_lines, f"开始执行任务: {task.name}")
        append_log(log_lines, f"模块: {task.get_module_display()}")
        append_log(log_lines, f"执行目标: {task.get_execution_target_display()}")

        # 根据模块类型执行不同逻辑
        if task.module == ScheduledTask.TaskModule.UI_AUTOMATION:
            append_log(log_lines, "触发 UI 自动化执行...")
            ui_case_ids = list(task.ui_testcases.values_list('id', flat=True))
            if not ui_case_ids:
                raise ValueError("未关联任何 UI 自动化用例")
            append_log(log_lines, f"关联用例数: {len(ui_case_ids)}")
            logger.info(
                "定时任务触发 UI 自动化批量执行: task_id=%s, name=%s, cases=%s, actuator_id=%s",
                task.id,
                task.name,
                ui_case_ids,
                task.actuator_id,
            )

            # 通过内部 API 触发批量执行（API 会创建记录并通过 WebSocket 通知执行器）
            import requests
            from rest_framework_simplejwt.tokens import RefreshToken
            from django.conf import settings as django_settings

            # 使用任务创建者身份获取 token
            token = str(RefreshToken.for_user(task.creator).access_token)
            resp = requests.post(
                f"{django_settings.BASE_URL}/api/ui-automation/trigger-batch/",
                json={
                    'case_ids': ui_case_ids,
                    'actuator_id': task.actuator_id,
                    'batch_name': f"定时任务-{task.name}",
                    'trigger_type': 'scheduled',
                },
                headers={'Authorization': f'Bearer {token}'},
                timeout=30,
            )
            if resp.status_code >= 400:
                error_msg = resp.json().get('error', resp.text)
                raise ValueError(f"触发批量执行失败: {error_msg}")

            batch_data = resp.json().get('data', {})
            append_log(log_lines, f"批量执行已触发: batch_id={batch_data.get('batch_id')}")
            append_log(log_lines, "任务已触发完成，等待 UI 自动化批量执行结束")
            logger.info(
                "UI 自动化批量执行已触发: task_id=%s, task_execution=%s, batch_id=%s",
                task.id,
                execution.execution_id,
                batch_data.get('batch_id'),
            )

        elif task.module == ScheduledTask.TaskModule.API_AUTOMATION:
            append_log(log_lines, "触发接口自动化执行...")
            api_case_ids = list(task.api_testcases.values_list('id', flat=True))
            if not api_case_ids:
                raise ValueError("未关联任何接口自动化用例")
            append_log(log_lines, f"关联接口用例数: {len(api_case_ids)}")

            from api_automation.models import ApiBatchExecutionRecord, ApiExecutionRecord
            from api_automation.tasks import execute_api_batch_task

            batch = ApiBatchExecutionRecord.objects.create(
                project=task.project,
                name=f"定时任务-{task.name}",
                status=0,
                trigger_type='scheduled',
                total_cases=len(api_case_ids),
                executor=task.creator,
                start_time=timezone.now(),
            )
            for case in task.api_testcases.all():
                ApiExecutionRecord.objects.create(
                    project=task.project,
                    test_case=case,
                    batch=batch,
                    environment=case.environment,
                    status=0,
                    trigger_type='scheduled',
                    executor=task.creator,
                )
            execute_api_batch_task.delay(batch.id)
            append_log(log_lines, f"接口批量执行已触发: batch_id={batch.id}")
            append_log(log_lines, "任务已触发完成，等待接口自动化批量执行结束")
            logger.info(
                "接口自动化批量执行已触发: task_id=%s, task_execution=%s, batch_id=%s",
                task.id,
                execution.execution_id,
                batch.id,
            )

        elif task.module == ScheduledTask.TaskModule.TEST_SUITE:
            append_log(log_lines, "触发测试套件执行...")
            if not task.test_suite:
                raise ValueError("未关联测试套件")
            append_log(log_lines, f"套件: {task.test_suite.name}")
            # 创建执行记录并启动 Celery 任务
            from testcases.models import TestExecution
            from testcases.tasks import execute_test_suite as run_suite
            suite_execution = TestExecution.objects.create(
                suite=task.test_suite,
                executor=task.creator,
                status='pending',
            )
            run_suite.delay(suite_execution.id)
            append_log(log_lines, f"套件执行已触发: execution_id={suite_execution.id}")
            append_log(log_lines, "任务已触发完成，等待测试套件执行结束")

        append_log(log_lines, "任务触发完成")

        execution.status = TaskExecution.ExecutionStatus.SUCCESS
        execution.finished_at = timezone.now()
        execution.log = '\n'.join(log_lines)
        execution.save()

        # 一次性任务执行后自动禁用
        if task.schedule_type == ScheduledTask.ScheduleType.ONCE:
            task.status = ScheduledTask.TaskStatus.DISABLED
            task.save(update_fields=['status'])

        return {'status': 'success', 'execution_id': execution.execution_id}

    except Exception as e:
        logger.exception(f"任务 [{task.name}] 执行失败")
        append_log(log_lines, f"执行失败: {str(e)}")

        execution.status = TaskExecution.ExecutionStatus.FAILED
        execution.finished_at = timezone.now()
        execution.log = '\n'.join(log_lines)
        execution.error_message = str(e)
        execution.save()

        # 一次性任务失败后自动禁用
        if task.schedule_type == ScheduledTask.ScheduleType.ONCE:
            task.status = ScheduledTask.TaskStatus.DISABLED
            task.save(update_fields=['status'])

        # 重试逻辑
        if task.retry_enabled and self.request.retries < task.retry_count:
            raise self.retry(
                exc=e,
                countdown=task.retry_interval * 60,
                max_retries=task.retry_count,
            )

        return {'status': 'failed', 'execution_id': execution.execution_id, 'error': str(e)}

from celery import shared_task

from .models import ApiBatchExecutionRecord, ApiExecutionRecord
from .services import execute_api_case, update_batch_summary


@shared_task(name="api_automation.tasks.execute_api_case_task")
def execute_api_case_task(record_id: int):
    return execute_api_case(record_id)


@shared_task(name="api_automation.tasks.execute_api_batch_task")
def execute_api_batch_task(batch_id: int):
    batch = ApiBatchExecutionRecord.objects.get(id=batch_id)
    batch.status = 1
    batch.save(update_fields=["status"])
    for record in ApiExecutionRecord.objects.filter(batch=batch).order_by("id"):
        execute_api_case(record.id)
    update_batch_summary(batch_id)
    return {"status": "done", "batch_id": batch_id}


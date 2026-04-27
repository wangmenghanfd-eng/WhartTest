import re
from datetime import datetime

from django.utils import timezone


LOG_LINE_PATTERN = re.compile(r"^\[(?P<timestamp>[^\]]+)\]\s*(?P<message>.*)$")
SUITE_EXECUTION_ID_PATTERN = re.compile(r"套件执行已(?:提交|触发): execution_id=(?P<execution_id>\d+)")
UI_BATCH_ID_PATTERN = re.compile(r"批量执行已触发: batch_id=(?P<batch_id>\d+)")
API_BATCH_ID_PATTERN = re.compile(r"接口批量执行已触发: batch_id=(?P<batch_id>\d+)")


def format_local_timestamp(dt=None) -> str:
    value = timezone.localtime(dt or timezone.now())
    return value.strftime("%Y-%m-%d %H:%M:%S")


def append_log(log_lines: list[str], message: str, dt=None) -> None:
    log_lines.append(f"[{format_local_timestamp(dt)}] {message}")


def parse_log_timestamp(value: str):
    if not value:
        return None

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None

    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    return timezone.localtime(dt)


def format_log_for_display(log_text: str) -> str:
    if not log_text:
        return ""

    formatted_lines: list[str] = []
    for line in log_text.splitlines():
        match = LOG_LINE_PATTERN.match(line)
        if not match:
            formatted_lines.append(line)
            continue

        local_dt = parse_log_timestamp(match.group("timestamp"))
        if not local_dt:
            formatted_lines.append(line)
            continue

        formatted_lines.append(f"[{local_dt.strftime('%Y-%m-%d %H:%M:%S')}] {match.group('message')}")

    return "\n".join(formatted_lines)


def extract_suite_execution_id(log_text: str):
    if not log_text:
        return None

    match = SUITE_EXECUTION_ID_PATTERN.search(log_text)
    if not match:
        return None

    try:
        return int(match.group("execution_id"))
    except (TypeError, ValueError):
        return None


def extract_ui_batch_id(log_text: str):
    if not log_text:
        return None

    match = UI_BATCH_ID_PATTERN.search(log_text)
    if not match:
        return None

    try:
        return int(match.group("batch_id"))
    except (TypeError, ValueError):
        return None


def extract_api_batch_id(log_text: str):
    if not log_text:
        return None

    match = API_BATCH_ID_PATTERN.search(log_text)
    if not match:
        return None

    try:
        return int(match.group("batch_id"))
    except (TypeError, ValueError):
        return None


def format_duration_value(seconds) -> str:
    if seconds is None:
        return "—"

    try:
        total_seconds = float(seconds)
    except (TypeError, ValueError):
        return "—"

    if total_seconds < 0:
        return "—"
    if 0 < total_seconds < 1:
        return "<1s"

    total_seconds_int = int(total_seconds)
    if total_seconds_int < 60:
        return f"{total_seconds_int}s"

    minutes, seconds_remainder = divmod(total_seconds_int, 60)
    if minutes < 60:
        return f"{minutes}m {seconds_remainder}s"

    hours, minutes_remainder = divmod(minutes, 60)
    return f"{hours}h {minutes_remainder}m {seconds_remainder}s"

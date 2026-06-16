# -*- coding: utf-8 -*-
"""
为接口自动化模块种入演示数据，方便用户快速点测。

用法：
    python manage.py seed_api_automation --project 1
    python manage.py seed_api_automation --project 1 --reset

数据来源选择 https://jsonplaceholder.typicode.com，公开免费可调用，
点击「执行」按钮即可看到真实响应。

种入内容：
- 1 个环境（默认）：JSONPlaceholder
- 3 个模块：用户管理 / 帖子管理 / 评论管理
- 11 个接口用例：覆盖 GET / POST / PUT / DELETE
- 2 条公共数据
- 3 个历史批次执行（不同状态 + 时间）
"""

import random
from datetime import timedelta

from datetime import time as time_cls

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from projects.models import Project

from api_automation.models import (
    ApiBatchExecutionRecord,
    ApiDefinition,
    ApiEnvironmentConfig,
    ApiExecutionRecord,
    ApiModule,
    ApiPublicData,
    ApiScript,
    ApiTestCase,
)

User = get_user_model()


CASES = [
    # 用户管理
    {
        "module": "用户管理",
        "name": "GET 用户列表",
        "method": "GET",
        "path": "/users",
        "headers": {"Accept": "application/json"},
        "query_params": {},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "json_path", "path": "0.id", "operator": "eq", "expected": 1},
        ],
        "extractors": [
            {"name": "first_user_id", "source": "json_path", "expression": "0.id"},
        ],
    },
    {
        "module": "用户管理",
        "name": "GET 单个用户详情",
        "method": "GET",
        "path": "/users/1",
        "headers": {"Accept": "application/json"},
        "query_params": {},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "json_path", "path": "username", "operator": "eq", "expected": "Bret"},
        ],
        "extractors": [],
    },
    {
        "module": "用户管理",
        "name": "GET 用户的待办事项",
        "method": "GET",
        "path": "/users/1/todos",
        "headers": {"Accept": "application/json"},
        "query_params": {},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
        ],
        "extractors": [],
    },
    # 帖子管理
    {
        "module": "帖子管理",
        "name": "GET 帖子列表",
        "method": "GET",
        "path": "/posts",
        "headers": {"Accept": "application/json"},
        "query_params": {"_limit": "10"},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
        ],
        "extractors": [],
    },
    {
        "module": "帖子管理",
        "name": "GET 单个帖子",
        "method": "GET",
        "path": "/posts/1",
        "headers": {"Accept": "application/json"},
        "query_params": {},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "json_path", "path": "userId", "operator": "eq", "expected": 1},
        ],
        "extractors": [],
    },
    {
        "module": "帖子管理",
        "name": "POST 创建帖子",
        "method": "POST",
        "path": "/posts",
        "headers": {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json"},
        "query_params": {},
        "body": {"title": "WHartTest demo", "body": "Hello from seed", "userId": 1},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 201},
            {"type": "json_path", "path": "title", "operator": "eq", "expected": "WHartTest demo"},
        ],
        "extractors": [
            {"name": "new_post_id", "source": "json_path", "expression": "id"},
        ],
    },
    {
        "module": "帖子管理",
        "name": "PUT 更新帖子",
        "method": "PUT",
        "path": "/posts/1",
        "headers": {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json"},
        "query_params": {},
        "body": {"id": 1, "title": "updated title", "body": "updated body", "userId": 1},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "json_path", "path": "title", "operator": "eq", "expected": "updated title"},
        ],
        "extractors": [],
    },
    {
        "module": "帖子管理",
        "name": "DELETE 删除帖子",
        "method": "DELETE",
        "path": "/posts/1",
        "headers": {"Accept": "application/json"},
        "query_params": {},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
        ],
        "extractors": [],
    },
    # 评论管理
    {
        "module": "评论管理",
        "name": "GET 评论列表",
        "method": "GET",
        "path": "/comments",
        "headers": {"Accept": "application/json"},
        "query_params": {"_limit": "20"},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
        ],
        "extractors": [],
    },
    {
        "module": "评论管理",
        "name": "GET 帖子的评论",
        "method": "GET",
        "path": "/posts/1/comments",
        "headers": {"Accept": "application/json"},
        "query_params": {},
        "body": {},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 200},
            {"type": "json_path", "path": "0.postId", "operator": "eq", "expected": 1},
        ],
        "extractors": [],
    },
    {
        "module": "评论管理",
        "name": "POST 创建评论",
        "method": "POST",
        "path": "/comments",
        "headers": {"Content-Type": "application/json; charset=UTF-8", "Accept": "application/json"},
        "query_params": {},
        "body": {"name": "WHartTest", "email": "demo@example.com", "body": "looks great", "postId": 1},
        "assertions": [
            {"type": "status_code", "operator": "eq", "expected": 201},
        ],
        "extractors": [],
    },
]


PUBLIC_DATA = [
    {"key": "default_user_id", "value": "1", "description": "用例里常用的演示 userId"},
    {"key": "demo_token", "value": "Bearer demo-token-XYZ", "description": "公共示例 token"},
]


class Command(BaseCommand):
    help = "为指定项目种入接口自动化演示数据（使用 jsonplaceholder.typicode.com）"

    def add_arguments(self, parser):
        parser.add_argument("--project", type=int, required=False, help="目标项目 ID（与 --all-projects 二选一）")
        parser.add_argument("--all-projects", action="store_true", help="为所有项目都种入示例数据")
        parser.add_argument("--user", type=str, default=None, help="用户名作为 creator，缺省取项目 creator 或第一个 superuser")
        parser.add_argument(
            "--reset",
            action="store_true",
            help="先清除该项目下的接口自动化数据再种入",
        )
        parser.add_argument(
            "--run-real",
            action="store_true",
            help="额外起一个真实批次，调用 jsonplaceholder.typicode.com 的真实请求（需外网）",
        )

    def handle(self, *args, **options):
        if options.get("all_projects"):
            projects = list(Project.objects.all().order_by("id"))
            if not projects:
                raise CommandError("系统中没有任何项目")
            for project in projects:
                self.stdout.write(self.style.NOTICE(f"\n========== 项目 #{project.id} {project.name} =========="))
                self._handle_one(project, options)
            return

        project_id = options.get("project")
        if not project_id:
            raise CommandError("请指定 --project <id> 或 --all-projects")
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            raise CommandError(f"项目 {project_id} 不存在")
        self._handle_one(project, options)

    def _handle_one(self, project, options):
        if options["user"]:
            try:
                creator = User.objects.get(username=options["user"])
            except User.DoesNotExist:
                raise CommandError(f"用户 {options['user']} 不存在")
        else:
            creator = (
                project.creator
                or User.objects.filter(is_superuser=True).first()
                or User.objects.first()
            )
        if not creator:
            raise CommandError("找不到可用的 creator 用户")

        self.stdout.write(self.style.NOTICE(f"creator: {creator.username}"))

        with transaction.atomic():
            if options["reset"]:
                self._reset(project)
            envs = self._ensure_envs(project, creator)
            modules = self._ensure_modules(project, creator)
            cases = self._ensure_cases(project, creator, envs["default"], modules)
            self._ensure_public_data(project, creator)
            self._ensure_definitions(project, creator, modules)
            self._ensure_scripts(project, creator, modules)
            self._seed_history_batches(project, creator, cases)
            self._ensure_scheduled_tasks(project, creator, cases)

        if options["run_real"]:
            self._run_real_batch(project, creator, cases)

        self.stdout.write(self.style.SUCCESS(
            f"完成：环境 {len(envs)}，模块 {len(modules)}，用例 {len(cases)}，批次 3 + (真实执行 {1 if options['run_real'] else 0})"
        ))

    # ------------------------------------------------------------------
    def _reset(self, project):
        from task_center.models import ScheduledTask
        ScheduledTask.objects.filter(project=project).delete()
        ApiScript.objects.filter(project=project).delete()
        ApiDefinition.objects.filter(project=project).delete()
        deleted = ApiBatchExecutionRecord.objects.filter(project=project).delete()
        self.stdout.write(f"  - 删除批次：{deleted[0]}")
        ApiExecutionRecord.objects.filter(project=project).delete()
        ApiTestCase.objects.filter(project=project).delete()
        ApiModule.objects.filter(project=project).delete()
        ApiEnvironmentConfig.objects.filter(project=project).delete()
        ApiPublicData.objects.filter(project=project).delete()

    def _ensure_envs(self, project, creator) -> dict[str, ApiEnvironmentConfig]:
        """创建两个环境：默认 prod + staging（同域名，只是 Header / variables 不同）。"""
        default_env, created = ApiEnvironmentConfig.objects.get_or_create(
            project=project,
            base_url="https://jsonplaceholder.typicode.com",
            defaults={
                "name": "JSONPlaceholder",
                "headers": {"User-Agent": "WHartTest-demo", "X-Env": "prod"},
                "variables": {"site": "jsonplaceholder", "env": "prod"},
                "is_default": not ApiEnvironmentConfig.objects.filter(project=project).exists(),
                "creator": creator,
            },
        )
        verb = "创建" if created else "复用"
        self.stdout.write(f"  - 环境：{verb} {default_env.name}")

        staging_env, created = ApiEnvironmentConfig.objects.get_or_create(
            project=project,
            name="JSONPlaceholder-Staging",
            defaults={
                "base_url": "https://jsonplaceholder.typicode.com",
                "headers": {"User-Agent": "WHartTest-staging", "X-Env": "staging"},
                "variables": {"site": "jsonplaceholder", "env": "staging"},
                "is_default": False,
                "creator": creator,
            },
        )
        verb = "创建" if created else "复用"
        self.stdout.write(f"  - 环境：{verb} {staging_env.name}")
        return {"default": default_env, "staging": staging_env}

    def _ensure_modules(self, project, creator) -> dict[str, ApiModule]:
        names = ["用户管理", "帖子管理", "评论管理"]
        result: dict[str, ApiModule] = {}
        for name in names:
            module, created = ApiModule.objects.get_or_create(
                project=project, parent=None, name=name, defaults={"creator": creator}
            )
            result[name] = module
            if created:
                self.stdout.write(f"  - 模块：创建 {name}")
        return result

    def _ensure_cases(self, project, creator, env, modules) -> list[ApiTestCase]:
        existing = {(c.module_id, c.name): c for c in ApiTestCase.objects.filter(project=project)}
        result: list[ApiTestCase] = []
        for spec in CASES:
            module = modules[spec["module"]]
            key = (module.id, spec["name"])
            if key in existing:
                result.append(existing[key])
                continue
            case = ApiTestCase.objects.create(
                project=project,
                module=module,
                environment=env,
                name=spec["name"],
                method=spec["method"],
                path=spec["path"],
                headers=spec["headers"],
                query_params=spec["query_params"],
                body=spec["body"],
                assertions=spec["assertions"],
                extractors=spec["extractors"],
                source="seed",
                creator=creator,
            )
            result.append(case)
        self.stdout.write(f"  - 用例：当前共 {len(result)} 条")
        return result

    def _ensure_public_data(self, project, creator):
        for spec in PUBLIC_DATA:
            ApiPublicData.objects.get_or_create(
                project=project,
                key=spec["key"],
                defaults={
                    "value": spec["value"],
                    "description": spec["description"],
                    "is_enabled": True,
                    "creator": creator,
                },
            )

    def _ensure_definitions(self, project, creator, modules):
        """为常用接口生成文档定义，Item 2 (AI 辅助) 需要以这些作为参考。"""
        defs = [
            ("用户管理", "GET", "/users", "获取用户列表", []),
            ("用户管理", "GET", "/users/{id}", "获取单个用户", [
                {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}
            ]),
            ("帖子管理", "GET", "/posts", "获取帖子列表", [
                {"name": "_limit", "in": "query", "required": False, "schema": {"type": "integer"}}
            ]),
            ("帖子管理", "POST", "/posts", "创建帖子", []),
            ("帖子管理", "PUT", "/posts/{id}", "更新帖子", []),
            ("帖子管理", "DELETE", "/posts/{id}", "删除帖子", []),
            ("评论管理", "GET", "/comments", "获取评论列表", []),
            ("评论管理", "GET", "/posts/{postId}/comments", "某帖子的评论", []),
            ("评论管理", "POST", "/comments", "创建评论", []),
        ]
        created = 0
        for module_name, method, path, summary, params in defs:
            module = modules[module_name]
            obj, was_created = ApiDefinition.objects.update_or_create(
                project=project,
                method=method,
                path=path,
                defaults={
                    "module": module,
                    "name": summary,
                    "summary": summary,
                    "description": f"{summary}。演示数据来自 jsonplaceholder.typicode.com。",
                    "tags": [module_name],
                    "parameters": params,
                    "responses": {"200": {"description": "OK"}},
                    "source": "seed",
                    "creator": creator,
                },
            )
            created += int(was_created)
        self.stdout.write(f"  - 接口定义：新增 {created} / 合计 {len(defs)} 个")

    def _ensure_scripts(self, project, creator, modules):
        scripts = [
            {
                "module": "用户管理",
                "name": "设置公共 token",
                "script_type": "pre",
                "content": (
                    "# 示例前置脚本，在所有请求前注入 Authorization 头\n"
                    "# 实际运行时框架会提供 request 上下文\n"
                    "request.headers['Authorization'] = '${{ demo_token }}'\n"
                ),
            },
            {
                "module": "帖子管理",
                "name": "记录响应耗时",
                "script_type": "post",
                "content": (
                    "# 示例后置脚本：记录响应耗时 + 提取 id\n"
                    "if response.status_code < 400:\n"
                    "    log(f\"耗时 {response.elapsed_ms} ms\")\n"
                    "    if 'id' in response.json():\n"
                    "        ctx.set('latest_post_id', response.json()['id'])\n"
                ),
            },
            {
                "module": "评论管理",
                "name": "生成随机邮箱",
                "script_type": "pre",
                "content": (
                    "import uuid\n"
                    "# 给请求体动态填充邮箱\n"
                    "if isinstance(request.body, dict):\n"
                    "    request.body.setdefault('email', f'demo-{uuid.uuid4().hex[:6]}@example.com')\n"
                ),
            },
        ]
        created = 0
        for spec in scripts:
            module = modules[spec["module"]]
            _obj, was_created = ApiScript.objects.get_or_create(
                project=project,
                module=module,
                name=spec["name"],
                script_type=spec["script_type"],
                defaults={
                    "content": spec["content"],
                    "creator": creator,
                },
            )
            created += int(was_created)
        self.stdout.write(f"  - 脚本：新增 {created} / 合计 {len(scripts)} 个")

    def _ensure_scheduled_tasks(self, project, creator, cases):
        """创建 1 个上线的定时任务 + 1 个未启用的一次性任务。"""
        from task_center.models import ScheduledTask
        if ScheduledTask.objects.filter(project=project, name__startswith="演示定时").exists():
            self.stdout.write("  - 定时任务：已存在演示任务，跳过")
            return
        if not cases:
            return

        daily = ScheduledTask.objects.create(
            name="演示定时 - 每日凌晨接口巡检",
            description="每天凌晨 1:30 跑一轮接口冗余检测。演示使用，未交付 Celery beat。",
            project=project,
            module=ScheduledTask.TaskModule.API_AUTOMATION,
            execution_target=ScheduledTask.ExecutionTarget.BACKEND,
            schedule_type=ScheduledTask.ScheduleType.DAILY,
            daily_time=time_cls(1, 30),
            status=ScheduledTask.TaskStatus.DISABLED,
            creator=creator,
        )
        daily.api_testcases.set(cases[:5])

        once = ScheduledTask.objects.create(
            name="演示定时 - 一次性冲击测试",
            description="仅作演示，未启用。",
            project=project,
            module=ScheduledTask.TaskModule.API_AUTOMATION,
            execution_target=ScheduledTask.ExecutionTarget.BACKEND,
            schedule_type=ScheduledTask.ScheduleType.ONCE,
            once_datetime=timezone.now() + timedelta(days=1),
            status=ScheduledTask.TaskStatus.DISABLED,
            creator=creator,
        )
        once.api_testcases.set(cases[5:8])
        self.stdout.write("  - 定时任务：创建 2 个（默认未启用，免得意外外网调用）")

    def _seed_history_batches(self, project, creator, cases):
        if ApiBatchExecutionRecord.objects.filter(project=project, name__startswith="演示批次").exists():
            self.stdout.write("  - 批次：已存在演示批次，跳过")
            return
        if not cases:
            return
        now = timezone.now()
        scenarios = [
            # name, days_ago, fail_ratio
            ("演示批次 #1（全部成功）", 5, 0.0),
            ("演示批次 #2（部分失败）", 3, 0.4),
            ("演示批次 #3（最近一次）", 1, 0.1),
        ]
        for name, days_ago, fail_ratio in scenarios:
            start = now - timedelta(days=days_ago, hours=random.randint(0, 8))
            end = start + timedelta(seconds=random.randint(20, 120))
            failed = sum(1 for _ in cases if random.random() < fail_ratio)
            passed = len(cases) - failed
            status = 2 if failed == 0 else (4 if passed == 0 else 3)
            batch = ApiBatchExecutionRecord.objects.create(
                project=project,
                name=name,
                status=status,
                trigger_type="manual",
                total_cases=len(cases),
                passed_cases=passed,
                failed_cases=failed,
                duration=(end - start).total_seconds(),
                executor=creator,
                start_time=start,
                end_time=end,
            )
            # 改 created_at 这种 auto_now_add 字段需要手动 update
            ApiBatchExecutionRecord.objects.filter(id=batch.id).update(created_at=start)
            for case in cases:
                rec_status = 3 if (failed and random.random() < fail_ratio) else 2
                ApiExecutionRecord.objects.create(
                    project=project,
                    test_case=case,
                    batch=batch,
                    environment=case.environment,
                    status=rec_status,
                    trigger_type="manual",
                    request_data={
                        "method": case.method,
                        "url": f"{case.environment.base_url if case.environment else ''}{case.path}",
                    },
                    response_data={"status_code": 200 if rec_status == 2 else 500},
                    error_message="" if rec_status == 2 else "演示数据：模拟失败",
                    duration=round(random.uniform(0.05, 0.6), 3),
                    executor=creator,
                    start_time=start,
                    end_time=end,
                )
            self.stdout.write(f"  - 批次：{name} (passed={passed}, failed={failed})")

    def _run_real_batch(self, project, creator, cases):
        """起动一次真实批次：调用 jsonplaceholder.typicode.com。"""
        from api_automation.services import execute_api_case, update_batch_summary
        if not cases:
            return
        now = timezone.now()
        batch = ApiBatchExecutionRecord.objects.create(
            project=project,
            name=f"真实演示运行 {now.strftime('%m-%d %H:%M')}",
            status=1,
            trigger_type="manual",
            total_cases=len(cases),
            executor=creator,
            start_time=now,
        )
        record_ids = []
        for case in cases:
            rec = ApiExecutionRecord.objects.create(
                project=project,
                test_case=case,
                batch=batch,
                environment=case.environment,
                status=0,
                trigger_type="manual",
                executor=creator,
            )
            record_ids.append(rec.id)
        self.stdout.write(self.style.NOTICE(f"  - 真实执行：创建批次 #{batch.id}，并发递调 {len(record_ids)} 个用例中..."))
        for rec_id in record_ids:
            execute_api_case(rec_id)
        update_batch_summary(batch.id)
        batch.refresh_from_db()
        self.stdout.write(self.style.SUCCESS(
            f"  - 真实执行完成：passed={batch.passed_cases}, failed={batch.failed_cases}, success_rate={batch.success_rate}%"
        ))

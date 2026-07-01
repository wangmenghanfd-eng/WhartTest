import httpx
from collections import defaultdict, deque
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from projects.models import Project

from .models import (
    ApiBatchExecutionRecord,
    ApiDefinition,
    ApiEnvironmentConfig,
    ApiExecutionRecord,
    ApiModule,
    ApiPublicData,
    ApiScenario,
    ApiScenarioExecutionRecord,
    ApiScenarioStep,
    ApiScript,
    ApiTestCase,
)
from .serializers import (
    ApiBatchExecutionRecordListSerializer,
    ApiBatchExecutionRecordSerializer,
    ApiDefinitionSerializer,
    ApiEnvironmentConfigSerializer,
    ApiExecutionRecordSerializer,
    ApiExecutionRecordListSerializer,
    ApiModuleSerializer,
    ApiPublicDataSerializer,
    ApiScenarioExecutionRecordListSerializer,
    ApiScenarioExecutionRecordSerializer,
    ApiScenarioSerializer,
    ApiScriptSerializer,
    ApiTestCaseSerializer,
)
from .services import import_openapi_spec, load_openapi_spec
from .tasks import execute_api_batch_task, execute_api_case_task, execute_api_scenario_task
from .trace_to_api_cases import (
    materialize_from_execution,
    preview_from_execution,
)

from ui_automation.models import UiExecutionRecord


class CreatorMixin:
    def perform_create(self, serializer):
        serializer.save(creator=self.request.user)


class ApiModuleViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiModule.objects.select_related("project", "parent", "creator")
    serializer_class = ApiModuleSerializer
    filterset_fields = ["project", "parent", "level"]
    search_fields = ["name"]
    ordering = ["level", "name"]

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = (self.request.query_params.get("search") or "").strip()
        if keyword:
            queryset = queryset.filter(name__icontains=keyword)
        return queryset

    @action(detail=False, methods=["get"])
    def tree(self, request):
        project_id = request.query_params.get("project")
        if not project_id:
            return Response({"error": "project 参数必填"}, status=status.HTTP_400_BAD_REQUEST)
        visible_ids = _visible_module_ids(int(project_id))
        modules = self.get_queryset().filter(project_id=project_id, parent__isnull=True)
        if visible_ids:
            modules = modules.filter(id__in=visible_ids)
        else:
            modules = modules.none()
        return Response(self.get_serializer(modules, many=True, context={"visible_ids": visible_ids}).data)


class ApiEnvironmentConfigViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiEnvironmentConfig.objects.select_related("project", "creator")
    serializer_class = ApiEnvironmentConfigSerializer
    filterset_fields = ["project", "is_default"]

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = (self.request.query_params.get("search") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(name__icontains=keyword) | Q(base_url__icontains=keyword))
        return queryset


class ApiDefinitionViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiDefinition.objects.select_related("project", "module", "creator")
    serializer_class = ApiDefinitionSerializer
    filterset_fields = ["project", "method", "source"]

    def get_queryset(self):
        queryset = super().get_queryset()
        module_id = self.request.query_params.get("module")
        project_id = self.request.query_params.get("project")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            queryset = queryset.filter(module_id__in=module_ids or [-1])
        keyword = (self.request.query_params.get("search") or "").strip()
        if keyword:
            queryset = queryset.filter(
                Q(name__icontains=keyword) |
                Q(path__icontains=keyword) |
                Q(operation_id__icontains=keyword)
            )
        return queryset

    @action(detail=True, methods=["post"], url_path="generate-case", permission_classes=[IsAuthenticated])
    def generate_case(self, request, pk=None):
        """根据接口定义一键生成一条基础用例。

        Body 可选：- module: 不传则使用 definition.module
          - environment: 不传则取项目默认环境
        """
        from .services import _default_assertions  # type: ignore

        definition: ApiDefinition = self.get_object()
        module_id = request.data.get("module") or definition.module_id
        if not module_id:
            return Response(
                {"error": "该接口定义未绑定模块，请传 module"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            module = ApiModule.objects.get(id=module_id, project=definition.project)
        except ApiModule.DoesNotExist:
            return Response(
                {"error": f"接口模块 {module_id} 不存在或不属于该项目"},
                status=status.HTTP_404_NOT_FOUND,
            )
        env_id = request.data.get("environment")
        env = None
        if env_id:
            env = ApiEnvironmentConfig.objects.filter(id=env_id, project=definition.project).first()
        if env is None:
            env = ApiEnvironmentConfig.objects.filter(project=definition.project, is_default=True).first()

        defaults = {
            "project": definition.project,
            "module": module,
            "definition": definition,
            "environment": env,
            "name": f"{definition.method}-{definition.name or definition.path}"[:255],
            "method": definition.method,
            "path": definition.path,
            "assertions": _default_assertions(definition.responses or {}),
            "source": "definition",
        }
        existing_cases = ApiTestCase.objects.filter(
            project=definition.project,
            module=module,
            definition=definition,
            source="definition",
        )
        replaced = existing_cases.exists()
        if replaced:
            existing_cases.delete()
        case = ApiTestCase.objects.create(creator=request.user, **defaults)
        return Response({
            "case_id": case.id,
            "name": case.name,
            "method": case.method,
            "path": case.path,
            "replaced": replaced,
        })

    @action(detail=False, methods=["post"], url_path="import-openapi")
    def import_openapi(self, request):
        project_id = request.data.get("project")
        if not project_id:
            return Response({"error": "project 参数必填"}, status=status.HTTP_400_BAD_REQUEST)
        project = Project.objects.get(id=project_id)
        create_cases = bool(request.data.get("create_cases", True))
        raw = request.data.get("content") or ""
        url = request.data.get("url") or ""
        upload = request.FILES.get("file")

        if upload:
            raw = upload.read().decode("utf-8")
        elif url:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                raw = client.get(url).text
        if not raw:
            return Response({"error": "请上传 OpenAPI 文件、填写 URL 或粘贴内容"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            spec = load_openapi_spec(raw)
            result = import_openapi_spec(project, request.user, spec, create_cases=create_cases)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class ApiTestCaseViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiTestCase.objects.select_related("project", "module", "definition", "environment", "creator")
    serializer_class = ApiTestCaseSerializer
    filterset_fields = ["project", "definition", "environment", "status", "source"]

    def get_queryset(self):
        queryset = super().get_queryset()
        module_id = self.request.query_params.get("module")
        project_id = self.request.query_params.get("project")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            queryset = queryset.filter(module_id__in=module_ids or [-1])
        keyword = (self.request.query_params.get("search") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(name__icontains=keyword) | Q(path__icontains=keyword))
        return queryset

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        case = self.get_object()
        env_id = request.data.get("environment") or case.environment_id
        record = ApiExecutionRecord.objects.create(
            project=case.project,
            test_case=case,
            environment_id=env_id,
            status=0,
            trigger_type="manual",
            executor=request.user,
        )
        execute_api_case_task.delay(record.id)
        return Response({"record_id": record.id, "message": "接口用例已提交执行"})

    @action(detail=False, methods=["post"], url_path="batch-execute")
    def batch_execute(self, request):
        case_ids = request.data.get("case_ids") or []
        project_id = request.data.get("project")
        if not case_ids:
            return Response({"error": "请选择接口用例"}, status=status.HTTP_400_BAD_REQUEST)
        cases = list(ApiTestCase.objects.filter(id__in=case_ids).select_related("project"))
        if not cases:
            return Response({"error": "未找到接口用例"}, status=status.HTTP_400_BAD_REQUEST)
        project = Project.objects.get(id=project_id or cases[0].project_id)
        env_id = request.data.get("environment")
        with transaction.atomic():
            batch = ApiBatchExecutionRecord.objects.create(
                project=project,
                name=request.data.get("name") or f"接口批量执行-{timezone.now().strftime('%Y%m%d%H%M%S')}",
                status=0,
                trigger_type=request.data.get("trigger_type") or "manual",
                total_cases=len(cases),
                executor=request.user if request.user.is_authenticated else None,
                start_time=timezone.now(),
            )
            for case in cases:
                ApiExecutionRecord.objects.create(
                    project=case.project,
                    test_case=case,
                    batch=batch,
                    environment_id=env_id or case.environment_id,
                    status=0,
                    trigger_type=batch.trigger_type,
                    executor=batch.executor,
                )
        execute_api_batch_task.delay(batch.id)
        return Response({"batch_id": batch.id, "message": "接口批量执行已提交"})

    @action(
        detail=False,
        methods=["post"],
        url_path="generate-from-functional-case",
        permission_classes=[IsAuthenticated],
    )
    def generate_from_functional_case(self, request):
        """
        把功能用例（testcases.TestCase）通过 LLM 翻译为接口用例草稿。

        Body:
          - testcase_id (int, required)
          - dry_run (bool, default true)
          - module (int, required when dry_run=false): 接收新建用例的接口模块
          - environment (int, optional)
          - selected_indexes (list[int], optional)
        """
        from .ai_from_functional import (
            materialize_from_functional_case,
            preview_from_functional_case,
        )
        from testcases.models import TestCase

        testcase_id = request.data.get("testcase_id")
        if not testcase_id:
            return Response({"error": "testcase_id 必填"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            TestCase.objects.get(id=testcase_id)
        except TestCase.DoesNotExist:
            return Response(
                {"error": f"功能用例 {testcase_id} 不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )

        dry_run = request.data.get("dry_run", True)
        if dry_run:
            return Response(preview_from_functional_case(int(testcase_id)))

        module_id = request.data.get("module")
        if not module_id:
            return Response(
                {"error": "创建用例时 module 必填"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        environment_id = request.data.get("environment")
        selected_indexes = request.data.get("selected_indexes")
        try:
            payload = materialize_from_functional_case(
                testcase_id=int(testcase_id),
                module_id=int(module_id),
                selected_indexes=selected_indexes,
                environment_id=int(environment_id) if environment_id else None,
                creator=request.user,
            )
        except ApiModule.DoesNotExist:
            return Response(
                {"error": f"接口模块 {module_id} 不存在或不属于该用例的项目"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="generate-from-ui-trace", permission_classes=[IsAuthenticated])
    def generate_from_ui_trace(self, request):
        """
        从 UI 执行记录的 Playwright trace 中提取网络请求，转为接口用例。

        Body:
          - execution_record_id (required, int): UI 执行记录 ID
          - dry_run (bool, default true): 只预览不入库
          - project (int, required when dry_run=false): 目标项目
          - module (int, required when dry_run=false): 目标接口模块
          - environment (int, optional): 指定环境；不传则按 base_url 自动查找/创建
          - selected_indexes (list[int], optional): 选中的候选下标；不传全部创建
          - skip_static (bool, default true): 过滤静态资源
        """
        execution_record_id = request.data.get("execution_record_id")
        if not execution_record_id:
            return Response(
                {"error": "execution_record_id 必填"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            record = UiExecutionRecord.objects.get(id=execution_record_id)
        except UiExecutionRecord.DoesNotExist:
            return Response(
                {"error": f"UI 执行记录 {execution_record_id} 不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )

        skip_static = request.data.get("skip_static", True)
        dry_run = request.data.get("dry_run", True)

        if dry_run:
            payload = preview_from_execution(record, skip_static=bool(skip_static))
            return Response(payload)

        project_id = request.data.get("project")
        module_id = request.data.get("module")
        if not project_id or not module_id:
            return Response(
                {"error": "创建用例时 project 与 module 必填"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response(
                {"error": f"项目 {project_id} 不存在"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            module = ApiModule.objects.get(id=module_id, project_id=project.id)
        except ApiModule.DoesNotExist:
            return Response(
                {"error": f"接口模块 {module_id} 不存在或不属于该项目"},
                status=status.HTTP_404_NOT_FOUND,
            )
        environment = None
        env_id = request.data.get("environment")
        if env_id:
            environment = ApiEnvironmentConfig.objects.filter(
                id=env_id, project=project,
            ).first()
        result = materialize_from_execution(
            record,
            project=project,
            module=module,
            creator=request.user if request.user.is_authenticated else None,
            selected_indexes=request.data.get("selected_indexes"),
            environment=environment,
            skip_static=bool(skip_static),
        )
        return Response(result)

    @action(detail=True, methods=["post"], url_path="ai-enhance", permission_classes=[IsAuthenticated])
    def ai_enhance(self, request, pk=None):
        """调用 LLM 为当前用例补全 assertions / extractors。

        Body:
          - apply (bool, default false): 为 true 时将建议合并到用例
        """
        from .ai_enhance import enhance_api_case

        case = self.get_object()
        apply = bool(request.data.get("apply", False))
        suggested_override = request.data.get("suggested")
        try:
            payload = enhance_api_case(case.id, apply=apply, suggested_override=suggested_override)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="batch-ai-enhance", permission_classes=[IsAuthenticated])
    def batch_ai_enhance(self, request):
        """批量为多个用例补全 assertions / extractors。

        Body:
          - case_ids (list[int], required)
          - apply (bool, default false): true 时把(预览给出的或新生成的)建议写回各用例
          - mode ('accurate'|'fast', default accurate): fast 跳过 LLM
          - items (list, optional): 预览阶段的结果,apply 时按 case_id 复用其 suggested
        """
        from .ai_enhance import enhance_api_case
        from concurrent.futures import ThreadPoolExecutor, as_completed

        case_ids = request.data.get("case_ids") or []
        apply = bool(request.data.get("apply", False))
        mode = str(request.data.get("mode") or "accurate").strip().lower()
        preview_items = request.data.get("items") or []
        if not case_ids:
            return Response({"error": "请选择接口用例"}, status=status.HTTP_400_BAD_REQUEST)

        cases = {case.id: case for case in ApiTestCase.objects.filter(id__in=case_ids)}
        override_map = {}
        if isinstance(preview_items, list):
            for item in preview_items:
                if not isinstance(item, dict):
                    continue
                case_id = item.get("case_id")
                suggested = item.get("suggested")
                if case_id in cases and isinstance(suggested, dict):
                    override_map[int(case_id)] = suggested

        def _build_missing_item(raw_case_id):
            return {"case_id": raw_case_id, "case_name": f"#{raw_case_id}", "error": "用例不存在"}

        def _run_case_enhance(case):
            payload = enhance_api_case(
                case.id,
                apply=apply,
                suggested_override=override_map.get(case.id) if apply else None,
                fast_mode=(not apply and mode == "fast"),
            )
            suggested = payload.get("suggested") or {}
            return {
                "case_id": case.id,
                "case_name": case.name,
                "method": case.method,
                "path": case.path,
                "current": payload.get("current") or {"assertions": [], "extractors": []},
                "merged": payload.get("merged") or {"assertions": [], "extractors": []},
                "rationale": payload.get("rationale") or "",
                "suggested": suggested,
                "added_assertions": len(suggested.get("assertions") or []),
                "added_extractors": len(suggested.get("extractors") or []),
                "applied": bool(payload.get("applied")),
            }

        def _run_case_enhance_threaded(case):
            # 仅线程预览路径用：每个 worker 用完关闭其线程本地连接,避免连接泄漏;不碰主连接。
            from django.db import connection as _conn
            try:
                return _run_case_enhance(case)
            finally:
                _conn.close()

        items_map = {}
        error_count = 0
        missing_case_ids = []
        valid_cases = []
        for raw_case_id in case_ids:
            case = cases.get(int(raw_case_id))
            if not case:
                missing_case_ids.append(raw_case_id)
                error_count += 1
                continue
            valid_cases.append(case)

        if apply:
            for case in valid_cases:
                try:
                    items_map[case.id] = _run_case_enhance(case)
                except Exception as exc:
                    error_count += 1
                    items_map[case.id] = {"case_id": case.id, "case_name": case.name, "error": str(exc)}
        else:
            max_workers = min(max(len(valid_cases), 1), 4)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {executor.submit(_run_case_enhance_threaded, case): case for case in valid_cases}
                for future in as_completed(future_map):
                    case = future_map[future]
                    try:
                        items_map[case.id] = future.result()
                    except Exception as exc:
                        error_count += 1
                        items_map[case.id] = {"case_id": case.id, "case_name": case.name, "error": str(exc)}

        for missing_case_id in missing_case_ids:
            items_map[int(missing_case_id)] = _build_missing_item(missing_case_id)

        items = []
        enhanced_count = 0
        for raw_case_id in case_ids:
            item = items_map.get(int(raw_case_id)) or _build_missing_item(raw_case_id)
            if (item.get("added_assertions") or 0) + (item.get("added_extractors") or 0) > 0 and not item.get("error"):
                enhanced_count += 1
            items.append(item)

        return Response({
            "items": items,
            "total": len(case_ids),
            "enhanced_count": enhanced_count,
            "error_count": error_count,
            "applied": apply,
        })


class ApiPublicDataViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiPublicData.objects.select_related("project", "creator")
    serializer_class = ApiPublicDataSerializer
    filterset_fields = ["project", "is_enabled"]

    def get_queryset(self):
        queryset = super().get_queryset()
        keyword = (self.request.query_params.get("search") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(key__icontains=keyword) | Q(value__icontains=keyword))
        return queryset


class ApiScriptViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiScript.objects.select_related("project", "module", "creator")
    serializer_class = ApiScriptSerializer
    filterset_fields = ["project", "script_type"]

    def get_queryset(self):
        queryset = super().get_queryset()
        module_id = self.request.query_params.get("module")
        project_id = self.request.query_params.get("project")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            queryset = queryset.filter(Q(module__isnull=True) | Q(module_id__in=module_ids or [-1]))
        return queryset


class ApiExecutionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiExecutionRecord.objects.select_related("project", "test_case", "environment", "executor")
    serializer_class = ApiExecutionRecordSerializer
    filterset_fields = ["project", "test_case", "batch", "status", "trigger_type"]

    def get_serializer_class(self):
        # 列表用轻量序列化器(不含 request_data/response_data),详情仍返回完整数据
        if self.action == "list":
            return ApiExecutionRecordListSerializer
        return ApiExecutionRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        module_id = self.request.query_params.get("module")
        project_id = self.request.query_params.get("project")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            queryset = queryset.filter(test_case__module_id__in=module_ids or [-1])
        return queryset

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """报告页统计:汇总数 + 按接口聚合 Top10,全部走 DB 聚合,
        避免把上万条执行记录拉到前端再算(曾达 16.8s)。"""
        project_id = request.query_params.get("project")
        qs = ApiExecutionRecord.objects.all()
        if project_id:
            qs = qs.filter(project_id=project_id)
        module_id = request.query_params.get("module")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            qs = qs.filter(test_case__module_id__in=module_ids or [-1])
        total = qs.count()
        passed = qs.filter(status=2).count()
        failed = qs.filter(status=3).count()
        by_case = list(
            qs.values("test_case__name", "test_case__method", "test_case__path")
            .annotate(
                total=Count("id"),
                passed=Count("id", filter=Q(status=2)),
                failed=Count("id", filter=Q(status=3)),
            )
            .order_by("-total")[:10]
        )
        for item in by_case:
            item["name"] = item.pop("test_case__name") or "-"
            item["method"] = item.pop("test_case__method") or "-"
            item["path"] = item.pop("test_case__path") or "-"
            item["passRate"] = round((item["passed"] / item["total"]) * 100, 1) if item["total"] else 0
        pass_rate = round((passed / total) * 100, 1) if total else 0
        return Response({
            "total": total, "passed": passed, "failed": failed, "passRate": pass_rate,
            "by_case": by_case,
        })


class ApiBatchExecutionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiBatchExecutionRecord.objects.select_related("project", "executor").prefetch_related("execution_records")
    serializer_class = ApiBatchExecutionRecordSerializer
    filterset_fields = ["project", "status", "trigger_type"]

    def get_queryset(self):
        # 列表不需要内嵌 execution_records，避免 prefetch 拉大字段
        if self.action == "list":
            return ApiBatchExecutionRecord.objects.select_related("project", "executor")
        return super().get_queryset()

    def get_serializer_class(self):
        if self.action == "list":
            return ApiBatchExecutionRecordListSerializer
        return ApiBatchExecutionRecordSerializer



def _expand_module_ids(module_id, project_id=None):
    try:
        root_id = int(module_id)
    except (TypeError, ValueError):
        return []
    modules = ApiModule.objects.all()
    if project_id:
        modules = modules.filter(project_id=project_id)
    children_map = defaultdict(list)
    for item in modules.values("id", "parent_id"):
        children_map[item["parent_id"]].append(item["id"])
    collected = []
    queue = deque([root_id])
    seen = set()
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        collected.append(current)
        queue.extend(children_map.get(current, []))
    return collected


def _visible_module_ids(project_id: int) -> set[int]:
    modules = list(ApiModule.objects.filter(project_id=project_id).values("id", "parent_id"))
    children_map = defaultdict(list)
    for item in modules:
        children_map[item["parent_id"]].append(item["id"])

    content_ids = set(ApiDefinition.objects.filter(project_id=project_id).values_list("module_id", flat=True))
    content_ids.update(ApiTestCase.objects.filter(project_id=project_id).values_list("module_id", flat=True))
    content_ids.update(ApiScenario.objects.filter(project_id=project_id).values_list("module_id", flat=True))
    content_ids.update(ApiScript.objects.filter(project_id=project_id).values_list("module_id", flat=True))

    visible = set(content_ids)
    if not visible:
        return visible

    parent_map = {item["id"]: item["parent_id"] for item in modules}
    queue = deque(visible)
    while queue:
        current = queue.popleft()
        parent_id = parent_map.get(current)
        if parent_id and parent_id not in visible:
            visible.add(parent_id)
            queue.append(parent_id)
    return visible

class ApiScenarioViewSet(CreatorMixin, viewsets.ModelViewSet):
    queryset = ApiScenario.objects.select_related("project", "module", "creator").prefetch_related("steps__test_case")
    serializer_class = ApiScenarioSerializer
    filterset_fields = ["project", "status"]

    def get_queryset(self):
        queryset = super().get_queryset()
        module_id = self.request.query_params.get("module")
        project_id = self.request.query_params.get("project")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            queryset = queryset.filter(module_id__in=module_ids or [-1])
        keyword = (self.request.query_params.get("search") or "").strip()
        if keyword:
            queryset = queryset.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
        return queryset

    def create(self, request, *args, **kwargs):
        payload = dict(request.data)
        steps = payload.pop("steps", [])
        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        scenario = serializer.save(creator=request.user)
        self._sync_steps(scenario, steps)
        return Response(self.get_serializer(scenario).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        scenario = self.get_object()
        payload = dict(request.data)
        steps = payload.pop("steps", None)
        serializer = self.get_serializer(scenario, data=payload, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        if steps is not None:
            self._sync_steps(scenario, steps)
        return Response(self.get_serializer(scenario).data)

    def _sync_steps(self, scenario: ApiScenario, steps):
        scenario.steps.all().delete()
        normalized = []
        for index, step in enumerate(steps or [], start=1):
            test_case_id = step.get("test_case") or step.get("test_case_id")
            if not test_case_id:
                continue
            normalized.append(ApiScenarioStep(
                scenario=scenario,
                order=int(step.get("order") or index),
                test_case_id=int(test_case_id),
                name=(step.get("name") or "").strip(),
                is_enabled=bool(step.get("is_enabled", True)),
                stop_on_failure=bool(step.get("stop_on_failure", True)),
            ))
        if normalized:
            ApiScenarioStep.objects.bulk_create(normalized)

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):
        scenario = self.get_object()
        env_id = request.data.get("environment")
        record = ApiScenarioExecutionRecord.objects.create(
            project=scenario.project,
            scenario=scenario,
            environment_id=env_id,
            status=0,
            trigger_type=request.data.get("trigger_type") or "manual",
            executor=request.user if request.user.is_authenticated else None,
        )
        execute_api_scenario_task.delay(record.id)
        return Response({"record_id": record.id, "message": "接口场景已提交执行"})

    @action(detail=False, methods=["post"], url_path="batch-execute")
    def batch_execute(self, request):
        """批量执行多个接口场景：为每个场景各创建一条执行记录并异步提交。"""
        scenario_ids = request.data.get("scenario_ids") or []
        if not scenario_ids:
            return Response({"error": "请选择接口场景"}, status=status.HTTP_400_BAD_REQUEST)
        scenarios = list(ApiScenario.objects.filter(id__in=scenario_ids).select_related("project"))
        if not scenarios:
            return Response({"error": "未找到接口场景"}, status=status.HTTP_400_BAD_REQUEST)
        env_id = request.data.get("environment")
        trigger_type = request.data.get("trigger_type") or "manual"
        executor = request.user if request.user.is_authenticated else None
        results = []
        for scenario in scenarios:
            record = ApiScenarioExecutionRecord.objects.create(
                project=scenario.project,
                scenario=scenario,
                environment_id=env_id,
                status=0,
                trigger_type=trigger_type,
                executor=executor,
            )
            execute_api_scenario_task.delay(record.id)
            results.append({"scenario_id": scenario.id, "record_id": record.id})
        return Response({"submitted": len(results), "records": results, "message": f"已提交 {len(results)} 个接口场景执行"})


class ApiScenarioExecutionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiScenarioExecutionRecord.objects.select_related("project", "scenario", "environment", "executor").prefetch_related("step_records__test_case", "step_records__step")
    serializer_class = ApiScenarioExecutionRecordSerializer
    filterset_fields = ["project", "scenario", "status", "trigger_type"]

    def get_serializer_class(self):
        if self.action == "list":
            return ApiScenarioExecutionRecordListSerializer
        return ApiScenarioExecutionRecordSerializer

    def get_queryset(self):
        if self.action == "list":
            queryset = ApiScenarioExecutionRecord.objects.select_related("project", "scenario", "environment", "executor")
        else:
            queryset = super().get_queryset()
        module_id = self.request.query_params.get("module")
        project_id = self.request.query_params.get("project")
        if module_id:
            module_ids = _expand_module_ids(module_id, project_id)
            queryset = queryset.filter(scenario__module_id__in=module_ids or [-1])
        return queryset


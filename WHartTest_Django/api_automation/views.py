import httpx
from django.db import transaction
from django.db.models import Q
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
    ApiScript,
    ApiTestCase,
)
from .serializers import (
    ApiBatchExecutionRecordSerializer,
    ApiDefinitionSerializer,
    ApiEnvironmentConfigSerializer,
    ApiExecutionRecordSerializer,
    ApiModuleSerializer,
    ApiPublicDataSerializer,
    ApiScriptSerializer,
    ApiTestCaseSerializer,
)
from .services import import_openapi_spec, load_openapi_spec
from .tasks import execute_api_batch_task, execute_api_case_task
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
        modules = self.get_queryset().filter(project_id=project_id, parent__isnull=True)
        return Response(self.get_serializer(modules, many=True).data)


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
    filterset_fields = ["project", "module", "method", "source"]

    def get_queryset(self):
        queryset = super().get_queryset()
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

        case = ApiTestCase.objects.create(
            project=definition.project,
            module=module,
            definition=definition,
            environment=env,
            name=f"{definition.method}-{definition.name or definition.path}"[:255],
            method=definition.method,
            path=definition.path,
            assertions=_default_assertions(definition.responses or {}),
            source="definition",
            creator=request.user,
        )
        return Response({
            "case_id": case.id,
            "name": case.name,
            "method": case.method,
            "path": case.path,
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
    filterset_fields = ["project", "module", "definition", "environment", "status", "source"]

    def get_queryset(self):
        queryset = super().get_queryset()
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
        try:
            payload = enhance_api_case(case.id, apply=apply)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload)


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
    filterset_fields = ["project", "module", "script_type"]


class ApiExecutionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiExecutionRecord.objects.select_related("project", "test_case", "environment", "executor")
    serializer_class = ApiExecutionRecordSerializer
    filterset_fields = ["project", "test_case", "batch", "status", "trigger_type"]


class ApiBatchExecutionRecordViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ApiBatchExecutionRecord.objects.select_related("project", "executor").prefetch_related("execution_records")
    serializer_class = ApiBatchExecutionRecordSerializer
    filterset_fields = ["project", "status", "trigger_type"]


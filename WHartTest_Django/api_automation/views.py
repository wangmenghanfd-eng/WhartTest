import httpx
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
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

    @action(detail=False, methods=["post"], url_path="generate-from-functional-case")
    def generate_from_functional_case(self, request):
        return Response(
            {
                "message": "已预留功能用例转接口用例入口。建议先通过 OpenAPI 或 UI Trace 导入真实接口，再由 AI 补全断言与参数化。",
                "status": "planned",
            }
        )

    @action(detail=False, methods=["post"], url_path="generate-from-ui-trace")
    def generate_from_ui_trace(self, request):
        return Response(
            {
                "message": "已预留 UI Trace 网络请求转接口用例入口。下一步会从 UI 执行 trace/network 产物提取请求并生成候选接口用例。",
                "status": "planned",
            }
        )

    @action(detail=True, methods=["post"], url_path="ai-enhance")
    def ai_enhance(self, request, pk=None):
        return Response(
            {
                "message": "已预留 AI 增强入口。V1 优先保持 OpenAPI 事实来源，AI 后续用于补全断言、提取器与参数化。",
                "status": "planned",
            }
        )


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


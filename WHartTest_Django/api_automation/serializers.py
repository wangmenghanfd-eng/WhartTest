from rest_framework import serializers

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
    ApiScenarioStepRecord,
    ApiScript,
    ApiTestCase,
)


class ApiModuleSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiModule
        fields = "__all__"
        read_only_fields = ["level", "creator", "created_at", "updated_at"]

    def get_children(self, obj):
        visible_ids = set(self.context.get("visible_ids") or [])
        children = obj.children.all()
        if visible_ids:
            children = children.filter(id__in=visible_ids)
        return ApiModuleSerializer(children, many=True, context=self.context).data if children else []


class ApiEnvironmentConfigSerializer(serializers.ModelSerializer):
    creator_name = serializers.CharField(source="creator.username", read_only=True)
    env_type_display = serializers.CharField(source="get_env_type_display", read_only=True)

    class Meta:
        model = ApiEnvironmentConfig
        fields = "__all__"
        read_only_fields = ["creator", "created_at", "updated_at"]


class ApiDefinitionSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True)
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiDefinition
        fields = "__all__"
        read_only_fields = ["creator", "created_at", "updated_at"]


class ApiTestCaseListSerializer(serializers.ModelSerializer):
    """列表用轻量序列化器:排除 body/headers/query_params/assertions/extractors/
    脚本/result_data 等大字段(result_data 含上次执行的完整响应体,列表全量拉曾达 6.7MB)。"""

    module_name = serializers.CharField(source="module.name", read_only=True)
    definition_name = serializers.CharField(source="definition.name", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiTestCase
        exclude = ["body", "headers", "query_params", "assertions", "extractors",
                   "pre_script", "post_script", "result_data"]
        read_only_fields = ["status", "error_message", "creator", "created_at", "updated_at"]


class ApiTestCaseSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True)
    definition_name = serializers.CharField(source="definition.name", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiTestCase
        fields = "__all__"
        read_only_fields = ["status", "result_data", "error_message", "creator", "created_at", "updated_at"]


class ApiPublicDataSerializer(serializers.ModelSerializer):
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiPublicData
        fields = "__all__"
        read_only_fields = ["creator", "created_at", "updated_at"]


class ApiScriptSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True)
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiScript
        fields = "__all__"
        read_only_fields = ["creator", "created_at", "updated_at"]


class ApiExecutionRecordSerializer(serializers.ModelSerializer):
    test_case_name = serializers.CharField(source="test_case.name", read_only=True)
    test_case_module = serializers.IntegerField(source="test_case.module_id", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    executor_name = serializers.CharField(source="executor.username", read_only=True)

    class Meta:
        model = ApiExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time"]


class ApiExecutionRecordListSerializer(serializers.ModelSerializer):
    """列表用轻量序列化器：排除 request_data/response_data 等大字段，
    避免一次拉全部记录时响应体过大（报告页/执行记录页只需汇总字段）。"""

    test_case_name = serializers.CharField(source="test_case.name", read_only=True)
    test_case_module = serializers.IntegerField(source="test_case.module_id", read_only=True)
    test_case_method = serializers.CharField(source="test_case.method", read_only=True)
    test_case_path = serializers.CharField(source="test_case.path", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    executor_name = serializers.CharField(source="executor.username", read_only=True)

    class Meta:
        model = ApiExecutionRecord
        exclude = ["request_data", "response_data"]
        read_only_fields = ["created_at", "start_time", "end_time"]


class ApiBatchExecutionRecordListSerializer(serializers.ModelSerializer):
    """列表用轻量序列化器：不内嵌 execution_records，避免报告页一次拉全部
    批次时把每条执行记录的 request_data/response_data 也带出来(曾达 32MB→502)。"""

    executor_name = serializers.CharField(source="executor.username", read_only=True)
    success_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = ApiBatchExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time", "success_rate"]


class ApiBatchExecutionRecordSerializer(serializers.ModelSerializer):
    executor_name = serializers.CharField(source="executor.username", read_only=True)
    success_rate = serializers.FloatField(read_only=True)
    # 详情内嵌执行记录也用轻量序列化器(不含 request/response 大字段);
    # 查看单条记录详情时前端再单独拉 execution-records/{id}/。
    execution_records = ApiExecutionRecordListSerializer(many=True, read_only=True)

    class Meta:
        model = ApiBatchExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time", "success_rate"]



class ApiScenarioStepSerializer(serializers.ModelSerializer):
    test_case_name = serializers.CharField(source="test_case.name", read_only=True)
    test_case_method = serializers.CharField(source="test_case.method", read_only=True)
    test_case_path = serializers.CharField(source="test_case.path", read_only=True)

    class Meta:
        model = ApiScenarioStep
        fields = "__all__"
        read_only_fields = ["created_at", "updated_at"]


class ApiScenarioSerializer(serializers.ModelSerializer):
    module_name = serializers.CharField(source="module.name", read_only=True)
    creator_name = serializers.CharField(source="creator.username", read_only=True)
    steps = ApiScenarioStepSerializer(many=True, read_only=True)
    step_count = serializers.IntegerField(source="steps.count", read_only=True)

    class Meta:
        model = ApiScenario
        fields = "__all__"
        read_only_fields = ["status", "last_result", "error_message", "creator", "created_at", "updated_at"]


class ApiScenarioStepRecordSerializer(serializers.ModelSerializer):
    step_name = serializers.SerializerMethodField()
    test_case_name = serializers.CharField(source="test_case.name", read_only=True)

    class Meta:
        model = ApiScenarioStepRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time"]

    def get_step_name(self, obj):
        return obj.step.name or obj.test_case_name or ""


class ApiScenarioExecutionRecordListSerializer(serializers.ModelSerializer):
    """列表用轻量序列化器：不内嵌 step_records,列表只需汇总字段。"""

    scenario_name = serializers.CharField(source="scenario.name", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    executor_name = serializers.CharField(source="executor.username", read_only=True)

    class Meta:
        model = ApiScenarioExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time"]


class ApiScenarioExecutionRecordSerializer(serializers.ModelSerializer):
    scenario_name = serializers.CharField(source="scenario.name", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    executor_name = serializers.CharField(source="executor.username", read_only=True)
    step_records = ApiScenarioStepRecordSerializer(many=True, read_only=True)

    class Meta:
        model = ApiScenarioExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time"]


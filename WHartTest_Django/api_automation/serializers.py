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


class ApiScenarioStepRecordSerializer(serializers.ModelSerializer):
    step_name = serializers.SerializerMethodField()
    test_case_name = serializers.CharField(source="test_case.name", read_only=True)

    class Meta:
        model = ApiScenarioStepRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time"]

    def get_step_name(self, obj):
        return obj.step.name or obj.test_case_name or ""


class ApiScenarioExecutionRecordSerializer(serializers.ModelSerializer):
    scenario_name = serializers.CharField(source="scenario.name", read_only=True)
    environment_name = serializers.CharField(source="environment.name", read_only=True)
    executor_name = serializers.CharField(source="executor.username", read_only=True)
    step_records = ApiScenarioStepRecordSerializer(many=True, read_only=True)

    class Meta:
        model = ApiScenarioExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time"]


class ApiBatchExecutionRecordSerializer(serializers.ModelSerializer):
    executor_name = serializers.CharField(source="executor.username", read_only=True)
    success_rate = serializers.FloatField(read_only=True)
    execution_records = ApiExecutionRecordSerializer(many=True, read_only=True)

    class Meta:
        model = ApiBatchExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time", "success_rate"]

from rest_framework import serializers

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


class ApiModuleSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    creator_name = serializers.CharField(source="creator.username", read_only=True)

    class Meta:
        model = ApiModule
        fields = "__all__"
        read_only_fields = ["level", "creator", "created_at", "updated_at"]

    def get_children(self, obj):
        children = obj.children.all()
        return ApiModuleSerializer(children, many=True).data if children else []


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


class ApiBatchExecutionRecordSerializer(serializers.ModelSerializer):
    executor_name = serializers.CharField(source="executor.username", read_only=True)
    success_rate = serializers.FloatField(read_only=True)
    execution_records = ApiExecutionRecordSerializer(many=True, read_only=True)

    class Meta:
        model = ApiBatchExecutionRecord
        fields = "__all__"
        read_only_fields = ["created_at", "start_time", "end_time", "success_rate"]


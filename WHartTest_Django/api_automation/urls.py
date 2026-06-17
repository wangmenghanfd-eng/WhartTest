from rest_framework.routers import DefaultRouter

from .views import (
    ApiBatchExecutionRecordViewSet,
    ApiDefinitionViewSet,
    ApiEnvironmentConfigViewSet,
    ApiExecutionRecordViewSet,
    ApiModuleViewSet,
    ApiPublicDataViewSet,
    ApiScenarioExecutionRecordViewSet,
    ApiScenarioViewSet,
    ApiScriptViewSet,
    ApiTestCaseViewSet,
)

router = DefaultRouter()
router.register("modules", ApiModuleViewSet, basename="api-modules")
router.register("env-configs", ApiEnvironmentConfigViewSet, basename="api-env-configs")
router.register("definitions", ApiDefinitionViewSet, basename="api-definitions")
router.register("testcases", ApiTestCaseViewSet, basename="api-testcases")
router.register("scripts", ApiScriptViewSet, basename="api-scripts")
router.register("public-data", ApiPublicDataViewSet, basename="api-public-data")
router.register("scenarios", ApiScenarioViewSet, basename="api-scenarios")
router.register("scenario-records", ApiScenarioExecutionRecordViewSet, basename="api-scenario-records")
router.register("execution-records", ApiExecutionRecordViewSet, basename="api-execution-records")
router.register("batch-records", ApiBatchExecutionRecordViewSet, basename="api-batch-records")

urlpatterns = router.urls

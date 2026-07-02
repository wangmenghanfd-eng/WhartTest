from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from projects.models import Project


class ApiModule(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_modules", verbose_name=_("所属项目"))
    name = models.CharField(_("模块名称"), max_length=100)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="children", verbose_name=_("父模块"))
    level = models.PositiveSmallIntegerField(_("模块级别"), default=1)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_modules", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_module"
        ordering = ["project", "level", "name"]
        unique_together = ("project", "parent", "name")
        verbose_name = _("接口模块")
        verbose_name_plural = _("接口模块")

    def save(self, *args, **kwargs):
        self.level = self.parent.level + 1 if self.parent else 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ApiEnvironmentConfig(models.Model):
    ENV_TYPE_CHOICES = [
        ("dev", _("开发")),
        ("test", _("测试")),
        ("staging", _("预发布")),
        ("prod", _("生产")),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_env_configs", verbose_name=_("所属项目"))
    name = models.CharField(_("环境名称"), max_length=80)
    env_type = models.CharField(_("环境类型"), max_length=16, choices=ENV_TYPE_CHOICES, default="dev")
    base_url = models.URLField(_("基础 URL"), max_length=500, blank=True, default="")
    headers = models.JSONField(_("公共请求头"), default=dict, blank=True)
    variables = models.JSONField(_("环境变量"), default=dict, blank=True)
    is_default = models.BooleanField(_("默认环境"), default=False)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_env_configs", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_environment_config"
        ordering = ["-is_default", "-id"]
        verbose_name = _("接口环境配置")
        verbose_name_plural = _("接口环境配置")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_default:
            ApiEnvironmentConfig.objects.filter(project=self.project).exclude(id=self.id).update(is_default=False)


class ApiDefinition(models.Model):
    METHOD_CHOICES = [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("PATCH", "PATCH"),
        ("DELETE", "DELETE"),
        ("HEAD", "HEAD"),
        ("OPTIONS", "OPTIONS"),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_definitions", verbose_name=_("所属项目"))
    module = models.ForeignKey(ApiModule, on_delete=models.PROTECT, related_name="definitions", verbose_name=_("所属模块"))
    name = models.CharField(_("接口名称"), max_length=200)
    method = models.CharField(_("请求方法"), max_length=10, choices=METHOD_CHOICES)
    path = models.CharField(_("接口路径"), max_length=500)
    operation_id = models.CharField(_("Operation ID"), max_length=200, blank=True, default="")
    summary = models.CharField(_("摘要"), max_length=300, blank=True, default="")
    description = models.TextField(_("描述"), blank=True, default="")
    tags = models.JSONField(_("标签"), default=list, blank=True)
    parameters = models.JSONField(_("参数定义"), default=list, blank=True)
    request_body = models.JSONField(_("请求体定义"), default=dict, blank=True)
    responses = models.JSONField(_("响应定义"), default=dict, blank=True)
    source = models.CharField(_("来源"), max_length=40, default="manual")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_definitions", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_definition"
        ordering = ["-id"]
        unique_together = ("project", "module", "method", "path")
        verbose_name = _("接口定义")
        verbose_name_plural = _("接口定义")

    def __str__(self):
        return f"{self.method} {self.path}"


class ApiPublicData(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_public_data", verbose_name=_("所属项目"))
    key = models.CharField(_("变量名"), max_length=100)
    value = models.TextField(_("变量值"), blank=True, default="")
    description = models.TextField(_("描述"), blank=True, default="")
    is_enabled = models.BooleanField(_("启用"), default=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_public_data", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_public_data"
        ordering = ["-id"]
        unique_together = ("project", "key")
        verbose_name = _("接口公共数据")
        verbose_name_plural = _("接口公共数据")


class ApiTestCase(models.Model):
    STATUS_CHOICES = [(0, _("未执行")), (1, _("执行中")), (2, _("成功")), (3, _("失败"))]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_testcases", verbose_name=_("所属项目"))
    module = models.ForeignKey(ApiModule, on_delete=models.PROTECT, related_name="testcases", verbose_name=_("所属模块"))
    definition = models.ForeignKey(ApiDefinition, on_delete=models.SET_NULL, null=True, blank=True, related_name="testcases", verbose_name=_("接口定义"))
    environment = models.ForeignKey(ApiEnvironmentConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name="testcases", verbose_name=_("默认环境"))
    name = models.CharField(_("用例名称"), max_length=255)
    method = models.CharField(_("请求方法"), max_length=10, default="GET")
    path = models.CharField(_("接口路径"), max_length=500)
    headers = models.JSONField(_("请求头"), default=dict, blank=True)
    query_params = models.JSONField(_("Query 参数"), default=dict, blank=True)
    body = models.JSONField(_("请求体"), default=dict, blank=True)
    pre_script = models.TextField(_("前置脚本"), blank=True, default="")
    post_script = models.TextField(_("后置脚本"), blank=True, default="")
    assertions = models.JSONField(_("断言"), default=list, blank=True)
    extractors = models.JSONField(_("变量提取"), default=list, blank=True)
    parameters = models.JSONField(
        _("参数化数据"),
        default=dict,
        blank=True,
        help_text=_('数据驱动：{"ver":["v1","v2"], "user-pwd":[["u1","p1"],["u2","p2"]]}，多参数取笛卡尔积'),
    )
    status = models.SmallIntegerField(_("状态"), choices=STATUS_CHOICES, default=0)
    result_data = models.JSONField(_("最近执行结果"), default=dict, blank=True)
    error_message = models.TextField(_("错误信息"), blank=True, default="")
    source = models.CharField(_("来源"), max_length=40, default="manual")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_testcases", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_testcase"
        ordering = ["-id"]
        verbose_name = _("接口测试用例")
        verbose_name_plural = _("接口测试用例")


class ApiScenario(models.Model):
    STATUS_CHOICES = [(0, _("未执行")), (1, _("执行中")), (2, _("成功")), (3, _("失败"))]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_scenarios", verbose_name=_("所属项目"))
    module = models.ForeignKey(ApiModule, on_delete=models.PROTECT, related_name="scenarios", verbose_name=_("所属模块"))
    name = models.CharField(_("场景名称"), max_length=255)
    description = models.TextField(_("场景描述"), blank=True, default="")
    status = models.SmallIntegerField(_("状态"), choices=STATUS_CHOICES, default=0)
    last_result = models.JSONField(_("最近执行结果"), default=dict, blank=True)
    error_message = models.TextField(_("错误信息"), blank=True, default="")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_scenarios", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_scenario"
        ordering = ["module_id", "name", "id"]
        verbose_name = _("接口场景")
        verbose_name_plural = _("接口场景")


class ApiScenarioStep(models.Model):
    scenario = models.ForeignKey(ApiScenario, on_delete=models.CASCADE, related_name="steps", verbose_name=_("所属场景"))
    order = models.PositiveIntegerField(_("顺序"), default=1)
    test_case = models.ForeignKey(ApiTestCase, on_delete=models.PROTECT, related_name="scenario_steps", verbose_name=_("接口用例"))
    name = models.CharField(_("步骤名称"), max_length=255, blank=True, default="")
    is_enabled = models.BooleanField(_("启用"), default=True)
    stop_on_failure = models.BooleanField(_("失败即停止"), default=True)
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_scenario_step"
        ordering = ["order", "id"]
        unique_together = ("scenario", "order")
        verbose_name = _("接口场景步骤")
        verbose_name_plural = _("接口场景步骤")


class ApiScript(models.Model):
    SCRIPT_TYPE_CHOICES = [("pre", _("前置脚本")), ("post", _("后置脚本"))]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_scripts", verbose_name=_("所属项目"))
    module = models.ForeignKey(ApiModule, on_delete=models.SET_NULL, null=True, blank=True, related_name="scripts", verbose_name=_("所属模块"))
    name = models.CharField(_("脚本名称"), max_length=120)
    script_type = models.CharField(_("脚本类型"), max_length=10, choices=SCRIPT_TYPE_CHOICES)
    content = models.TextField(_("脚本内容"), blank=True, default="")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_scripts", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_script"
        ordering = ["-id"]
        verbose_name = _("接口脚本")
        verbose_name_plural = _("接口脚本")


class ApiBatchExecutionRecord(models.Model):
    STATUS_CHOICES = [(0, _("待执行")), (1, _("执行中")), (2, _("全部成功")), (3, _("部分失败")), (4, _("全部失败"))]
    TRIGGER_TYPE_CHOICES = [("manual", _("手动执行")), ("scheduled", _("定时执行"))]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_batch_records", verbose_name=_("所属项目"))
    name = models.CharField(_("批次名称"), max_length=255)
    status = models.SmallIntegerField(_("状态"), choices=STATUS_CHOICES, default=0)
    trigger_type = models.CharField(_("触发类型"), max_length=20, choices=TRIGGER_TYPE_CHOICES, default="manual")
    total_cases = models.PositiveIntegerField(_("总用例数"), default=0)
    passed_cases = models.PositiveIntegerField(_("成功数"), default=0)
    failed_cases = models.PositiveIntegerField(_("失败数"), default=0)
    duration = models.FloatField(_("耗时秒"), null=True, blank=True)
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="api_batch_records", verbose_name=_("执行人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    start_time = models.DateTimeField(_("开始时间"), null=True, blank=True)
    end_time = models.DateTimeField(_("结束时间"), null=True, blank=True)

    class Meta:
        db_table = "api_batch_execution_record"
        ordering = ["-id"]

    @property
    def success_rate(self):
        return round((self.passed_cases / self.total_cases) * 100, 2) if self.total_cases else 0


class ApiExecutionRecord(models.Model):
    STATUS_CHOICES = [(0, _("未执行")), (1, _("执行中")), (2, _("成功")), (3, _("失败"))]
    TRIGGER_TYPE_CHOICES = [("manual", _("手动执行")), ("scheduled", _("定时执行"))]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_execution_records", verbose_name=_("所属项目"))
    test_case = models.ForeignKey(ApiTestCase, on_delete=models.CASCADE, related_name="execution_records", verbose_name=_("接口用例"))
    batch = models.ForeignKey(ApiBatchExecutionRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="execution_records", verbose_name=_("批次"))
    environment = models.ForeignKey(ApiEnvironmentConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name="execution_records", verbose_name=_("环境"))
    status = models.SmallIntegerField(_("状态"), choices=STATUS_CHOICES, default=0)
    trigger_type = models.CharField(_("触发类型"), max_length=20, choices=TRIGGER_TYPE_CHOICES, default="manual")
    request_data = models.JSONField(_("请求数据"), default=dict, blank=True)
    response_data = models.JSONField(_("响应数据"), default=dict, blank=True)
    error_message = models.TextField(_("错误信息"), blank=True, default="")
    duration = models.FloatField(_("耗时秒"), null=True, blank=True)
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="api_execution_records", verbose_name=_("执行人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    start_time = models.DateTimeField(_("开始时间"), null=True, blank=True)
    end_time = models.DateTimeField(_("结束时间"), null=True, blank=True)

    class Meta:
        db_table = "api_execution_record"
        ordering = ["-id"]


class ApiScenarioExecutionRecord(models.Model):
    STATUS_CHOICES = [(0, _("待执行")), (1, _("执行中")), (2, _("成功")), (3, _("失败"))]
    TRIGGER_TYPE_CHOICES = [("manual", _("手动执行")), ("scheduled", _("定时执行"))]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_scenario_execution_records", verbose_name=_("所属项目"))
    scenario = models.ForeignKey(ApiScenario, on_delete=models.CASCADE, related_name="execution_records", verbose_name=_("接口场景"))
    environment = models.ForeignKey(ApiEnvironmentConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name="scenario_execution_records", verbose_name=_("环境"))
    status = models.SmallIntegerField(_("状态"), choices=STATUS_CHOICES, default=0)
    trigger_type = models.CharField(_("触发类型"), max_length=20, choices=TRIGGER_TYPE_CHOICES, default="manual")
    variables_snapshot = models.JSONField(_("变量快照"), default=dict, blank=True)
    result_summary = models.JSONField(_("结果摘要"), default=dict, blank=True)
    error_message = models.TextField(_("错误信息"), blank=True, default="")
    duration = models.FloatField(_("耗时秒"), null=True, blank=True)
    executor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="api_scenario_execution_records", verbose_name=_("执行人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    start_time = models.DateTimeField(_("开始时间"), null=True, blank=True)
    end_time = models.DateTimeField(_("结束时间"), null=True, blank=True)

    class Meta:
        db_table = "api_scenario_execution_record"
        ordering = ["-id"]
        verbose_name = _("接口场景执行记录")
        verbose_name_plural = _("接口场景执行记录")


class ApiScenarioStepRecord(models.Model):
    STATUS_CHOICES = [(0, _("待执行")), (1, _("执行中")), (2, _("成功")), (3, _("失败")), (4, _("跳过"))]

    scenario_execution = models.ForeignKey(ApiScenarioExecutionRecord, on_delete=models.CASCADE, related_name="step_records", verbose_name=_("所属场景执行"))
    step = models.ForeignKey(ApiScenarioStep, on_delete=models.CASCADE, related_name="step_records", verbose_name=_("场景步骤"))
    test_case = models.ForeignKey(ApiTestCase, on_delete=models.SET_NULL, null=True, blank=True, related_name="scenario_step_records", verbose_name=_("接口用例"))
    execution_record = models.ForeignKey(ApiExecutionRecord, on_delete=models.SET_NULL, null=True, blank=True, related_name="scenario_step_records", verbose_name=_("接口执行记录"))
    order = models.PositiveIntegerField(_("顺序"), default=1)
    status = models.SmallIntegerField(_("状态"), choices=STATUS_CHOICES, default=0)
    extracted_variables = models.JSONField(_("提取变量"), default=dict, blank=True)
    error_message = models.TextField(_("错误信息"), blank=True, default="")
    duration = models.FloatField(_("耗时秒"), null=True, blank=True)
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    start_time = models.DateTimeField(_("开始时间"), null=True, blank=True)
    end_time = models.DateTimeField(_("结束时间"), null=True, blank=True)

    class Meta:
        db_table = "api_scenario_step_record"
        ordering = ["order", "id"]
        verbose_name = _("接口场景步骤执行记录")
        verbose_name_plural = _("接口场景步骤执行记录")


class ApiCustomFunction(models.Model):
    """项目级自定义 Python 函数库。函数体在执行时编译，供接口用例的
    ${{func(args)}} 表达式在渲染阶段调用（如动态加签、时间戳、随机数）。"""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="api_custom_functions", verbose_name=_("所属项目"))
    name = models.CharField(_("函数名"), max_length=100)
    code = models.TextField(_("Python 代码"), help_text=_("使用 def 定义函数；模块内所有函数均会被注册，函数名即调用名"))
    description = models.TextField(_("描述"), blank=True, default="")
    is_active = models.BooleanField(_("启用"), default=True)
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_api_custom_functions", verbose_name=_("创建人"))
    created_at = models.DateTimeField(_("创建时间"), auto_now_add=True)
    updated_at = models.DateTimeField(_("更新时间"), auto_now=True)

    class Meta:
        db_table = "api_custom_function"
        ordering = ["-id"]
        unique_together = ("project", "name")
        verbose_name = _("接口自定义函数")
        verbose_name_plural = _("接口自定义函数")

    def __str__(self) -> str:
        return f"{self.name} (project={self.project_id})"

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from prompts.models import UserPrompt, PromptType


class Command(BaseCommand):
    help = 'Initializes the database with default prompts for the system.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=int,
            help='User ID to assign the prompts to (default: first superuser)',
        )

    def handle(self, *args, **kwargs):
        self.stdout.write('Initializing default prompts...')

        # 获取用户
        user_id = kwargs.get('user')
        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'User with ID {user_id} not found'))
                return
        else:
            # 默认使用第一个超级用户
            user = User.objects.filter(is_superuser=True).first()
            if not user:
                self.stdout.write(self.style.ERROR('No superuser found. Please create a superuser first or specify a user ID.'))
                return

        self.stdout.write(f'Using user: {user.username} (ID: {user.id})')

        # 提示词内容
        prompts_to_create = [
            {
                "name": "测试用例执行提示词",
                "prompt_type": PromptType.TEST_CASE_EXECUTION,
                "content": """# 角色
你是一个专业的软件测试执行引擎。

# 任务
根据下面提供的测试用例信息，使用当前系统真正可用的 builtin skills 执行功能测试，不要混用 MCP 名称、旧工具名或占位路径。

# 测试用例信息
- **项目ID**: $project_id
- **用例ID**: $testcase_id
- **用例名称**: $testcase_name
- **前置条件**: $precondition

# 执行步骤
$steps

# 强制工具分工
1. 平台数据查询、截图上传，只能使用 `whart-test` skill。
2. 浏览器动作，只能使用 `playwright-skill`，命令格式必须是 `node run.js "..."`。
3. 同一个用例执行过程中，`session_id` 必须始终保持为 `case_$testcase_id`。
4. 截图必须保存在 `process.env.SCREENSHOT_DIR`，上传时只能传真实文件名，不能传 `/path/to/...` 这种占位路径。

# 推荐执行顺序
1. 先读取用例详情：
   `python whart_tools.py --action get_testcase_detail --project_id $project_id --case_id $testcase_id`
2. 如需查模块：
   `python whart_tools.py --action get_modules --project_id $project_id`
   或
   `python whart_tools.py --action get_module_id --project_id $project_id --module_name "<模块名>"`
3. 用 `playwright-skill` 执行浏览器步骤。打开页面后必须先调用 `helpers.describePageForAI(page)`，再使用返回的选择器操作。
4. 每个关键步骤后截图，文件名建议为 `case_$testcase_id_step1.png`、`case_$testcase_id_step2.png`。
5. 用 `whart-test` 上传截图，例如：
   `python whart_tools.py --action upload_screenshot --project_id $project_id --case_id $testcase_id --file_path "case_$testcase_id_step1.png" --title "步骤1截图" --step_number 1`
6. 如需查看最近一次历史结果，可调用：
   `python whart_tools.py --action get_test_result --project_id $project_id --case_id $testcase_id`
7. 默认不要在 `page.goto()` 中使用 `waitUntil: 'networkidle'`；优先 `page.goto()` 后配合 `waitForSelector` / `waitForURL`。
8. 负向场景先检查真实 `page.url()` 和页面文本，再写断言；不要先猜固定错误文案直接等待 30 秒。

# 严禁使用
- `browser_navigate`
- `browser_snapshot`
- `browser_take_screenshot`
- `save_operation_screenshots_to_the_application_case`
- `python playwright_script.py --action execute_test_case`
- 将 `get_case_details` 当成主流程动作名

# 输出格式
在所有步骤执行完毕后，你**必须**返回一个JSON对象，格式如下:
```json
{
  "testcase_id": $testcase_id,
  "status": "pass" | "fail",
  "summary": "对执行过程的简短总结。",
  "steps": [
    {
      "step_number": 1,
      "description": "步骤的描述",
      "status": "pass" | "fail",
      "screenshot": "case_$testcase_id_step1.png" | null,
      "error": "如果失败,记录错误信息" | null
    },
    ...
  ]
}
```""",
                "description": "用于驱动测试用例自动执行的系统提示词",
                "is_active": True,
            }
        ]

        for prompt_data in prompts_to_create:
            # 使用 get_or_create 来避免重复创建
            # 注意：程序调用类型的提示词每个用户只能有一个
            prompt, created = UserPrompt.objects.get_or_create(
                user=user,
                prompt_type=prompt_data["prompt_type"],
                defaults={
                    'name': prompt_data["name"],
                    'content': prompt_data["content"].strip(),
                    'description': prompt_data.get("description", ""),
                    'is_active': prompt_data.get("is_active", True),
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created prompt: "{prompt.name}" for user {user.username}'))
            else:
                # 如果已存在,更新内容
                prompt.name = prompt_data["name"]
                prompt.content = prompt_data["content"].strip()
                prompt.description = prompt_data.get("description", "")
                prompt.is_active = prompt_data.get("is_active", True)
                prompt.save()
                self.stdout.write(self.style.WARNING(f'Prompt "{prompt.name}" already exists for user {user.username}. Updated it.'))

        self.stdout.write(self.style.SUCCESS('Default prompts initialization complete.'))

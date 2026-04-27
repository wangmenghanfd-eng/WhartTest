"""
Agent Loop 补充指令

用于 Agent Loop 模式下的功能测试执行与 UI 自动化生成任务。
"""

TEST_CASE_EXECUTION_INSTRUCTION = """

## 【强制要求】功能测试用例执行

当请求中带有 `test_case_id` 时，说明你正在执行 WHartTest 的功能测试用例。必须遵守以下工具分工：

1. 平台数据读取、模块查询、截图上传使用 `whart-test` skill。
2. 浏览器操作使用 `playwright-skill`，命令只能是 `node run.js "..."`。
3. 同一个用例的浏览器步骤必须复用同一个 `session_id`，建议格式为 `case_当前用例ID`。
4. 打开页面后，先调用 `helpers.describePageForAI(page)`，再根据真实返回的选择器执行操作。
5. 截图必须先保存在 `process.env.SCREENSHOT_DIR`，上传时只能传真实文件名。
6. `run.js` 双引号内必须是可执行 JavaScript 语句，例如 `await page.goto('https://example.com');`，绝对不能写成“输入用户名和密码”这种自然语言。
7. 验证页面跳转/登录成功时，优先用 URL 检查，禁止用 `text=` 正则匹配跳转目标：
   - 推荐：`await page.waitForURL('**/secure');` 或 `console.log(page.url());`
   - 必须用文本匹配时，正则须加 `/i` 标志忽略大小写，例如 `text=/secure area/i`，禁止写 `text=/secure/`。
8. 默认不要在 `page.goto()` 中使用 `waitUntil: 'networkidle'`。很多站点会持续发请求，容易造成无意义的导航超时。优先 `page.goto()` 后配合 `waitForSelector` / `waitForURL`。
9. 负向场景（如用户名错误、密码错误）先检查 `page.url()` 和页面实际文本，再写断言；禁止先凭空猜测完整报错文案后直接 `waitForSelector('text=...')` 30 秒。

推荐动作：
- `python whart_tools.py --action get_testcase_detail --project_id <项目ID> --case_id <用例ID>`
- `python whart_tools.py --action get_modules --project_id <项目ID>`
- `python whart_tools.py --action get_module_id --project_id <项目ID> --module_name "<模块名>"`
- `python whart_tools.py --action upload_screenshot ...`
- `python whart_tools.py --action upload_screenshots ...`

严禁使用以下错误名称或错误方式：
- `get_case_details` 作为主流程动作名
- `execute_test_case`
- `browser_navigate`
- `browser_snapshot`
- `browser_take_screenshot`
- `save_operation_screenshots_to_the_application_case`
- `python playwright_script.py --action execute_test_case`
- `/path/to/screenshot1.png`

如果工具返回兼容提示或纠错信息，不要误判为测试已执行完成，应该继续切换到正确的 skill 和命令完成测试。
"""

PLAYWRIGHT_SCRIPT_INSTRUCTION = """

## 【强制要求】UI自动化用例生成

## 主要流程
1.判断之前是否生成过UI自动化用例，有则基于存在的用例进行修改和完善，没有则生成新的用例。
2.具体怎么保存用例查看 ui-automation 工具的操作方法和描述。
3.记得执行一下，确定保存的用例是可执行的。

**重要 本次任务必须在执行完所有功能测试步骤后，生成并调用相应工具保存UI自动化用例。**

### 断言规则（非常重要）
1. **禁止猜测 URL**：断言中的 URL 必须使用执行步骤时**实际观察到的 URL**，不要自己编造或猜测
2. **禁止使用通配符模式**：不要使用 `**/dashboard` 这样的模式，必须使用完整的实际 URL
3. **断言必须来源于实际结果**所有断言值 URL、标题、文本等必须是执行过程中**实际看到的值**
4. **当无法确定元素的具体文本时，优先使用可见性断言
"""

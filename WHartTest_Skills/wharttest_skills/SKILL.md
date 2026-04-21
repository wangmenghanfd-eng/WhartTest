---
name: whart-test
description: WHartTest测试管理平台工具集。用于管理项目、模块、测试用例的增删改查，以及测试截图上传。当用户需要操作测试用例、查询项目信息或上传截图时使用。
---

# WHartTest 测试管理平台

## 快速开始

```bash
# 设置环境变量
export WHARTTEST_BACKEND_URL="http://your-backend:8000"
export WHARTTEST_API_KEY="your-api-key"

# 执行操作
python whart_tools.py --action <action_name> [--参数名 参数值]
```

## 可用操作

### 项目管理

| Action | 描述 | 参数 |
|--------|------|------|
| `get_projects` | 获取所有项目列表 | 无 |
| `get_modules` | 获取项目下的模块列表 | `--project_id` |
| `get_module_id` | 根据模块名称获取模块ID | `--project_id`, `--module_name` |

### 用例管理

| Action | 描述 | 参数 |
|--------|------|------|
| `get_levels` | 获取用例等级列表 | 无 |
| `get_testcases` | 获取模块下的用例列表 | `--project_id`, `--module_id` |
| `get_testcase_detail` | 获取用例详情 | `--project_id`, `--case_id` |
| `get_test_result` | 获取该用例最近一次执行结果 | `--project_id`, `--case_id` |
| `add_testcase` | 新增测试用例 | `--project_id`, `--module_id`, `--name`, `--level`, `--precondition`, `--steps`, `--notes`, `--review_status`, `--test_type` |
| `edit_testcase` | 编辑测试用例 | `--project_id`, `--case_id`, `--name`, `--level`, `--module_id`, `--precondition`, `--steps`, `--notes`, `--review_status`, `--test_type`, `--is_optimization` |

### 兼容动作（仅用于容错，不是主流程）

| Action | 描述 | 说明 |
|--------|------|------|
| `get_case_details` | `get_testcase_detail` 的兼容别名 | 优先仍使用 `get_testcase_detail` |
| `execute_test_case` | 返回正确执行链路指引 | 不会直接驱动浏览器执行 |

### 截图管理

| Action | 描述 | 参数 |
|--------|------|------|
| `upload_screenshot` | 上传单张截图 | `--project_id`, `--case_id`, `--file_path`, `--title`, `--description`, `--step_number`, `--page_url` |
| `upload_screenshots` | 批量上传截图 | `--project_id`, `--case_id`, `--file_paths`(逗号分隔), `--title`, `--description`, `--step_number`, `--page_url` |

**截图路径约定**：playwright-skill 保存的截图位于 `SCREENSHOT_DIR` 环境变量指定的目录。上传时只需传入文件名（无需路径），系统会自动从 `SCREENSHOT_DIR` 查找。

**单张上传**：`--file_path "case_11_step1.png"`
**批量上传**：`--file_paths "step1.png,step2.png,step3.png"`（最多10张，逗号分隔）

## 功能测试执行时的职责边界

`whart-test` 只负责平台数据读写，不负责浏览器自动化执行。

推荐顺序：
1. 用 `get_testcase_detail` 读取用例步骤。
2. 如需模块ID，用 `get_module_id` 或 `get_modules`。
3. 浏览器操作必须切换到 `playwright-skill`，并使用 `node run.js "..."`。
4. 截图必须先保存到 `SCREENSHOT_DIR`，再用 `upload_screenshot` 或 `upload_screenshots` 上传。
5. 如需回看最近一次执行结果，再调用 `get_test_result`。

## 避免混用其他工具层的名称

下面这些名字容易和 MCP / 旧链路混淆，在 `whart-test` 里不要当成主流程动作使用：

- `get_case_details`
- `execute_test_case`
- `browser_navigate`
- `browser_snapshot`
- `browser_take_screenshot`
- `save_operation_screenshots_to_the_application_case`
- `python playwright_script.py`

正确做法是：

- 平台数据：`python whart_tools.py --action get_testcase_detail ...`
- 浏览器执行：`node run.js "..."`（在 `playwright-skill` 中）
- 截图上传：`python whart_tools.py --action upload_screenshot --file_path "case_11_step1.png" ...`

### 审核状态

`--review_status` 可选值：
- `pending_review` - 待审核（默认）
- `approved` - 通过
- `needs_optimization` - 优化
- `optimization_pending_review` - 优化待审核
- `unavailable` - 不可用

### 测试类型

`--test_type` 可选值：
- `smoke` - 冒烟测试
- `functional` - 功能测试（默认）
- `boundary` - 边界测试
- `exception` - 异常测试
- `permission` - 权限测试
- `security` - 安全测试
- `compatibility` - 兼容性测试

`--is_optimization` 标志（布尔型，无需传值）：在 edit_testcase 时带上此标志，会自动将状态设为 `optimization_pending_review`（优化待审核），用于AI优化后的用例提交。**一次调用即可完成编辑+状态更新。**
- ✅ 正确用法：`python whart_tools.py --action edit_testcase --project_id 1 --case_id 51 ... --is_optimization`
- ❌ 错误用法：`--is_optimization true`（不要传值）

## 使用示例

```bash
# 获取项目列表
python whart_tools.py --action get_projects

# 获取项目1的模块
python whart_tools.py --action get_modules --project_id 1

# 根据模块名称获取模块ID
python whart_tools.py --action get_module_id --project_id 1 --module_name "用户登录模块"

# 获取用例列表
python whart_tools.py --action get_testcases --project_id 1 --module_id 5

# 获取用例详情（主流程）
python whart_tools.py --action get_testcase_detail --project_id 1 --case_id 10

# 获取最近一次执行结果
python whart_tools.py --action get_test_result --project_id 1 --case_id 10

# 新增用例
python whart_tools.py --action add_testcase \
  --project_id 1 \
  --module_id 5 \
  --name "登录功能测试" \
  --level P0 \
  --precondition "用户已注册" \
  --steps '[{"step_number":1,"description":"输入用户名","expected_result":"用户名显示"}]' \
  --notes "冒烟测试"

# 上传单张截图
python whart_tools.py --action upload_screenshot \
  --project_id 1 \
  --case_id 10 \
  --file_path "step1.png" \
  --title "登录页面截图" \
  --step_number 1

# 批量上传截图
python whart_tools.py --action upload_screenshots \
  --project_id 1 \
  --case_id 10 \
  --file_paths "step1.png,step2.png,step3.png" \
  --title "登录测试截图"
```

## 输出格式

所有操作返回 JSON 格式结果，便于解析处理。

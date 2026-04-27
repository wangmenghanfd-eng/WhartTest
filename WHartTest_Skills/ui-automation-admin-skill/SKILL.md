---
name: ui-automation-admin-skill
description: WHartTest 平台内置的 UI 自动化管理工具。用于查询和维护 UI 模块、页面、元素、页面步骤、测试用例、公共数据。适合在需要直接读写平台 UI 自动化结构化数据时使用。
---

# UI Automation Admin Skill

这个 skill 直接操作 WHartTest 平台自身的 `UI 自动化` 模块，不依赖外部 MCP。

适用场景：

- 查询 UI 模块树
- 查询页面、元素、页面步骤、测试用例
- 新增 UI 模块、页面、元素、页面步骤、测试用例
- 批量更新页面步骤详情
- 批量更新测试用例步骤
- 查询项目公共数据

## 使用原则

1. 优先先查后改，避免重复创建。
2. 批量更新步骤时，参数必须传 JSON 数组字符串。
3. 写入页面步骤详情前，先确认元素 ID 已存在。
4. 写入测试用例步骤前，先确认页面步骤 ID 已存在。

## 可用动作

- `get_module_tree`
- `list_pages`
- `list_elements`
- `list_page_steps`
- `get_page_step_detail`
- `list_testcases`
- `get_testcase_detail`
- `list_public_data`
- `create_module`
- `create_page`
- `create_element`
- `create_page_step`
- `update_page_step_details`
- `create_testcase`
- `update_case_steps`

## 常用示例

```bash
python ui_automation_admin.py --action get_module_tree --project_id 2
```

```bash
python ui_automation_admin.py --action create_page \
  --project_id 2 \
  --module_id 10 \
  --name "登录页" \
  --url "https://practice.expandtesting.com/login"
```

```bash
python ui_automation_admin.py --action update_page_step_details \
  --page_step_id 15 \
  --steps '[{"step_type":0,"element":21,"ope_key":"fill","ope_value":{"value":"${username}"}},{"step_type":0,"element":22,"ope_key":"click","ope_value":{}}]'
```

```bash
python ui_automation_admin.py --action update_case_steps \
  --test_case_id 5 \
  --steps '[{"page_step":15},{"page_step":16}]'
```

## 输出格式

所有动作都返回 JSON，便于 AI 继续处理。

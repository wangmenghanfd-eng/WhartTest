# WHartTest 项目上下文交接文档

> 给新会话 Cascade 使用——读完此文即可接手，无需再重新扫描整个工程。最后更新：2026-06-29。

---

## 1. 项目简介

**WHartTest** 是一个 AI 驱动的测试自动化平台，当前版本 **v2.2.0**。
- 后端：Django + DRF + LangGraph + Celery（含 Beat 调度）
- 前端：Vue 3 + Vite + Arco Design + Pinia
- 存储：PostgreSQL + Redis + Qdrant（向量库）
- AI：LLM（LangGraph 智能体）+ MCP 工具（Playwright、内置 WHartTest 工具、远程 MCP）+ RAG 知识库
- 部署：Docker Compose，一键启动 6~7 个服务
- 测试覆盖：3 个核心模块共 **127 个单元测试**（见 §10）

本地部署根目录：`/Users/wangmenghan/WHartTest`。用户时区：**UTC+4 (Asia/Dubai)**，Django 默认配置时区：**Asia/Shanghai (UTC+8)**（定时任务支持按任务覆盖时区，见 §5.2）。

---

## 1.5 最新状态变化（2026-06-18）

> 这次把 scenario worktree 的工作按组并入 dev,并梳理了运行环境/正式库现状。要点:

1. **接口场景(scenario)已合入 dev**:模型(`ApiScenario`/`ApiScenarioStep`/`ApiScenarioExecutionRecord`/`ApiScenarioStepRecord`)、迁移 `0002–0005`、执行引擎(`services.execute_api_scenario` + `_execute_api_record` + JS 步骤执行器 `js_script_runner.js`)、场景 API(`ApiScenarioViewSet`/`ApiScenarioExecutionRecordViewSet` + 路由 + `execute_api_scenario_task`)、前端「接口场景」Tab(`ApiAutomationScenarios.vue`)。**正式库已是迁移后状态**(0001–0005 全部 applied),且有真实场景数据(scenario 29 / step 138 / 执行记录 41 行)。
2. **scenario 分支 `codex/feature-api-automation-dev` 仍有未合的独立功能**（**已于 2026-06-29 全部合入并部署,见 §1.6**;以下为当时 hold 记录):
   - **batchAiEnhance 批量 AI 增强**(后端 `batch_ai_enhance` action + 前端批量增强 UI,依赖 `ai_enhance` 的 `suggested_override`/`fast_mode` 扩展)
   - **B-1 模块树可视化过滤**(`tree` 端点按 `_visible_module_ids` 只显示有内容的模块)
   - **B-2 模块递归子树过滤**(Definition/TestCase/Script/ExecutionRecord 的 `module` 过滤含子模块,`_expand_module_ids`)
   - **B-3 generate_case 替换语义**(同 definition 已有用例时先删后建,返回 `replaced`)
3. **版本检查改本地化**:`versionService.ts` 已从 GitHub Releases API 改为读 `WHartTest_Vue/public/version-meta.json`(去外网依赖,适配内网)。**发版需手动维护该 JSON 的 `latest` 字段**,否则前端永远显示"已是最新"。
4. **单元测试数**:api_automation 现 **71**(含场景 3 项:`test_execute_api_scenario_shares_extracted_variables` / `test_scenario_create_and_execute_endpoint` / `test_scenario_list_supports_parent_module_filter`);三模块合计 **125**(见 §10)。
5. **运行环境切换待办** ⚠️（**已于 2026-06-29 完成,见 §1.6**）:此前 `wharttest-backend` 容器跑的是 2f41 worktree 的镜像(代码 build 时 COPY,非挂载);媒体已 `rsync --ignore-existing` 合并、DB 已备份 `data/backups/wharttest-20260618-150633.sql`(26M)。现已从 dev 重 build 并切换。

---

## 1.6 最新状态变化（2026-06-29）

> §1.5 列为"未合"的 4 个独立功能已全部合入 dev 并部署上线;运行环境已切到 dev。

1. **scenario 分支的 4 个独立功能已全部合入 dev**(§1.5 第 2 点待办清零):
   - **B-2 模块递归子树过滤**(`0e843a9`):`_expand_module_ids` 用于 Definition/TestCase/Script/ExecutionRecord 的 `module` 过滤,递归含子模块;不传 module 行为不变。
   - **B-1 模块树可视化过滤**(`306b90a`):`modules/tree/` 经 `_visible_module_ids` 只返回有内容的模块+祖先,空则 `.none()`;`ApiModuleSerializer.get_children` 按 visible_ids 过滤。
   - **B-3 generate_case 替换语义**(`fd491ef`):同 definition 已有 `source=definition` 用例时先删后建,返回 `replaced`。⚠️ 边界:`existing_cases.delete()` 删到被 `ApiScenarioStep.test_case`(PROTECT)引用的用例会 ProtectedError 500,目前按原样合入未加保护。
   - **batchAiEnhance 批量 AI 增强**:**方案B**(后端 `256f097`)——不引入 scenario 那 946 行老 schema(target/json_path_length),而在 dev 的 #1 版 `enhance_api_case` 上加 `suggested_override`/`fast_mode` 钩子 + `batch_ai_enhance` action;**方案C**(前端 `3b404ba`)——只复用用例表多选 + 「批量AI增强」按钮 + 结果提示,不做 scenario 的 3 弹窗预览/逐条编辑。**#1 全程保留**;顺手修了 scenario 原代码隐患(`close_old_connections` 串行路径误关主连接 → 改为仅线程 worker 关线程本地连接)。
2. **运行环境已切到 dev 并完成本批部署**(§1.5 第 5 点完成):backend 已从 dev 重 build(镜像 `wharttest-backend:latest`,`ffcbd94`)、重建;working_dir/data 挂载均为 dev;`migrate` 对正式库 no-op;场景 / `batch-ai-enhance` / `modules/tree` 端点 401(路由在)、health healthy。**dev = origin/dev = 运行容器**,一致到 `3b404ba`。
3. **2f41 worktree 已退役**(`git worktree remove`);分支 `codex/feature-api-automation-dev`(@ `a1c6bcb`)保留在本地 + origin;旧 rollback 镜像已清理(仅留 `:latest`);DB 备份 `data/backups/wharttest-20260618-150633.sql` 保留。
4. **单元测试数**:api_automation **73**(新增 `ApiBatchAiEnhanceTests` 2 项);三模块合计 **127**。

---

## 2. 工程结构

```
WHartTest/
├── WHartTest_Django/             # Django 后端（主要业务代码）
│   ├── accounts/                 # 用户账户/认证
│   ├── api_automation/           # ★ 接口自动化（OpenAPI 导入 + 用例 + 批量执行 + AI 增强 + 功能用例转换 + UI Trace 导入 + 报告/定时）
│   ├── api_keys/                 # API Key 管理
│   ├── knowledge/                # 知识库 + RAG + 嵌入
│   ├── langgraph_integration/    # LLM 配置 + LangGraph 集成
│   ├── orchestrator_integration/ # Agent 编排层（chat 主入口）
│   ├── mcp_tools/                # MCP 工具集成
│   ├── task_center/              # 定时任务中心（Celery Beat，支持 UI/API/Suite 三模块）
│   ├── testcases/                # 测试用例 + 测试套件
│   ├── ui_automation/            # UI 自动化（Playwright + WebSocket 派单到 Actuator）
│   ├── requirements/             # 需求管理
│   ├── prompts/                  # 提示词管理
│   ├── projects/                 # 项目/成员
│   └── wharttest_django/         # Django settings & urls
├── WHartTest_Vue/                # Vue 前端
├── WHartTest_MCP/                # 内置 MCP 工具（WHartTest_tools、ms_mcp_api）
├── WHartTest_Actuator/           # 桌面执行器（Tkinter GUI 可关，TUI/Headless 可用）
├── WHartTest_Skills/             # Claude Skills（playwright / draw / internal-kb / actuator-ops / ui-automation-admin）
├── docker-compose.yml            # 主 compose（已经过若干修复）
├── docker-compose.local.yml      # 本地开发用
└── data/
    └── logs/app.log              # 后端日志（重要！排错就看这个）
```

### 2.1 Django 模块权责

| 模块 | 职责 | 关键模型 |
|------|------|---------|
| `langgraph_integration` | LLM 配置存储、LangGraph 节点 | `LLMConfig` |
| `orchestrator_integration` | Chat SSE 流、Agent 主循环 | `agent_loop_view.py` |
| `knowledge` | 文档、向量化、RAG 查询 | `KnowledgeBase`, `KnowledgeGlobalConfig` |
| `mcp_tools` | 远程 MCP 配置、持久会话 | `RemoteMCPConfig`, `MCPTool` |
| `task_center` | 定时任务调度（基于 django-celery-beat），支持 UI/API/Suite 三种模块 | `ScheduledTask`, `TaskExecution` |
| `ui_automation` | UI 自动化页面/步骤/用例/执行 + 执行器 WebSocket 派单 | `UiTestCase`, `UiBatchExecutionRecord`, ... |
| `api_automation` | 接口自动化（OpenAPI 导入、环境配置、用例、批次、AI 增强、功能用例转接口、UI Trace 转接口、报告/定时） | `ApiTestCase`, `ApiBatchExecutionRecord`, ... |
| `testcases` | 功能测试用例、测试套件、AI 用例生成 | `TestCase`, `TestSuite` |

### 2.2 前端路由要点

- `/langgraph-chat` — LLM 对话
- `/knowledge-management` — 知识库
- `/ui-automation` — UI 自动化（Tab：页面/步骤/用例/执行记录/批量执行/公共数据/环境/执行器）
- `/api-automation` — 接口自动化（OpenAPI 导入、用例编辑、批量执行、AI 增强、功能用例/Trace 转换、报告、定时任务）
- `/testcases` — 测试用例管理（含套件）
- `/task-center` — 定时任务（UI/API/Suite 三种调度类型）
- `/requirements` — 需求管理
- `/system-management/*` — 系统管理（LLM 配置、MCP 配置、API Key）

---

## 3. Docker Compose 服务拓扑

| 服务名 | 容器名 | 端口映射 | 作用 |
|--------|--------|---------|------|
| postgres | wharttest-postgres | - | 主数据库 |
| redis | wharttest-redis | - | 缓存 + Celery broker |
| qdrant | wharttest-qdrant | - | 向量数据库 |
| **backend** | **wharttest-backend** | 8000→8912 | Django + Celery worker + Celery beat（supervisord 管理） |
| frontend | wharttest-frontend | 80→8913 | Nginx 静态资源 |
| mcp | wharttest-mcp | - | 内置 WHartTest MCP |
| **playwright-mcp** | **wharttest-playwright-mcp** | 8931→8916 | Playwright MCP 服务 |
| xinference（注释掉） | - | - | 本地 Embedding/Rerank 模型 |

**访问 URL**：
- 前端：http://localhost:8913
- 后端 API：http://localhost:8912（经 nginx proxy） / 容器内 8000
- Playwright-MCP：从后端访问 `http://playwright-mcp:8931/mcp`

**默认登录**：`admin` / `admin123456`

---

## 4. 当前已验证模块状态

| 模块 | 状态 | 备注 |
|------|------|------|
| LLM 对话 | ✅ | SiliconFlow Qwen2.5-7B（免费） |
| 知识库 + RAG | ✅ | 上传/Embedding/检索全链路通 |
| 需求管理 | ✅ | 已有样例文档 |
| 测试用例 + 套件 | ✅ | AI 生成 + 手动编辑 |
| UI 自动化（AI 驱动） | ✅ | the-internet.herokuapp.com 登录用例 |
| UI 自动化（Actuator 派单） | ✅ | WebSocket 派单 + OPEN 任务调度开关 |
| 接口自动化 | ✅ | OpenAPI 导入 + 单个/批量执行 + 默认环境自动创建 + AI 增强/功能用例转换/UI Trace 导入 + 报告/定时 |
| 任务中心 | ✅ | UI/API/Suite 三种调度都通；时区支持按任务覆盖 |
| 单元测试 | ✅ | 127 个测试覆盖 ui_automation/api_automation/task_center（api_automation 含场景3+批量增强2 项） |
| Playwright-MCP | ✅ | 容器可运行 |

---

## 5. 仍需特别留意的关键修复

> 较早期的修复（playwright-mcp 启动、MCP 连接超时、Embedding 配置等）已稳定运行多个会话，归档在 §11 历史修复，本节只列**仍可能影响新需求**的几条。

### 5.1 执行器任务调度 OPEN 开关 ✅（2026-04-21）

**目标**：前端 OPEN 开关真实生效，关闭后执行器不再收新任务。

**关键改动**：

| 文件 | 改动 |
|------|------|
| `ui_automation/consumers.py` | `SocketUserManager.get_actuator()` 过滤 `is_open=True` 的执行器 |
| `ui_automation/views.py` | 新增 `POST /api/ui-automation/actuators/toggle_open/`；`trigger_batch_execution` 暂停时返回 503 "执行器 xxx 已暂停接单" |
| `WHartTest_Vue/src/features/ui-automation/views/ActuatorList.vue` | OPEN switch 可点击切换 |

**生效路径**：
- 手动执行（WebSocket）→ `get_actuator()` 拒绝
- 定时任务（HTTP `trigger_batch_execution`）→ 返回 503 → Celery `TaskExecution` 标记 FAILED → 前端"触发失败"

**注意**：状态保存在 backend 内存（`consumer.actuator_info['is_open']`），执行器重连后会被执行器上报值覆盖（默认 True）。已有单元测试 `SocketUserManagerActuatorTests` + `TriggerBatchExecutionViewTests` 锁定。

### 5.2 定时任务时区错位 ✅（2026-04-21，方案 B）

**问题**：用户在 UTC+4，Django 默认 UTC+8，定时任务执行时间总是错位 4 小时。

**修复**：`ScheduledTask` 模型加 `task_timezone` 字段（CharField，默认 `Asia/Shanghai`），`scheduler.py:register_periodic_task` 改用 `task.task_timezone` 写入 `CrontabSchedule.timezone`；前端 `TaskFormModal.vue` 表单加时区下拉，默认值读取浏览器 `Intl.DateTimeFormat().resolvedOptions().timeZone`。

**遗留**：已存在的任务 `task_timezone` 默认 `Asia/Shanghai`，要改 UTC+4 须编辑任务后重新保存（触发 `register_periodic_task` 更新）。已有单元测试 `SchedulerRegistrationTests` 锁定。

### 5.3 AI 驱动 Playwright 测试稳定性（2026-04-21） ✅

**踩过的坑及修复**：

1. **AI 反复执行 `npx playwright install`** — `orchestrator_integration/builtin_tools/skill_tools.py` 加 `_FORBIDDEN_CMD_PREFIXES`
2. **并发用例互相清空截图目录** — 同 skill_tools.py，`case_dir_key` 加 chat_session_id 后缀
3. **Playwright 浏览器容器重建后丢失** — `docker-compose.local.yml` 加 named volume `playwright-browsers:/root/.cache/ms-playwright`
4. **截图历次累积** — `testcases/tasks.py` 每次执行前清空旧截图
5. **AI 输出不调用 `finish_test_case_execution`** — `agent_loop_view.py` 提示词 Rule 9 强化
6. **`waitForURL` 成功被判失败** — `agent_loop_view.py` 信号提取改为 `secure_path` 单信号判 success；`clear_success` 优先于 `clear_failure`
7. **`whart_tools.py` 参数歧义** — `argparse.ArgumentParser(allow_abbrev=False)`

### 5.4 Actuator 桌面执行器启动（2026-04-21） ✅

**正确启动命令**：
```bash
cd /Users/wangmenghan/WHartTest/WHartTest_Actuator
python3.11 main.py   # ← 必须 3.11+，代码用了 PEP 604 联合语法
```

**配置要点**（`config.toml`）：
- `use_gui = false`（除非装了 PySide6）
- API/WS 端口写主机映射 `8912`，不是容器内的 `8000`：
  - `ws://127.0.0.1:8912/ws/ui/actuator/`
  - `http://127.0.0.1:8912`

---

## 6. 已知问题 / 待办

### 6.1 视觉模型在 chat 中的选用
视觉模型（`LLMConfig` id=3）默认 `is_active=False`，前端要支持"按消息选模型"才能用到，未验证此 UI。

### 6.2 Context 100% 问题（LLM 对话）
旧对话历史太长、单个 7B 模型 `ctx=32k` 被吃满，会出现回复乱码/重复点号。清理历史或换大 ctx 模型可解。

### 6.3 未验证的 UI 路径
- 公共数据、环境配置（UI 自动化）的前端 CRUD 流
- Prompts 管理详细流
- 远程 MCP Ping/同步具体 UI

### 6.4 执行器相关待办（可选）
- 前端 `TestCaseList.vue` 暂停接单时的提示语可优化
- DEBUG 字段目前纯展示，执行器/后端均无逻辑使用——可考虑移除，或实现 debug 模式
- 执行器重连时 `is_open` 会被执行器自身上报值覆盖前端的设置——若要保留服务端状态需扩展 SET_ACTUATOR_INFO 协议

### 6.5 Skills 模块安全提示
Skills 具备较高系统执行权限，**严禁公网暴露**，仅限内网/可信网络部署。详见 README 安全声明。

---

## 7. 关键文件速查表

| 文件 | 用途 |
|------|------|
| `/Users/wangmenghan/WHartTest/docker-compose.yml` | Docker 服务定义（已改 2 处：playwright-mcp working_dir、backend healthcheck 改 TCP） |
| `/Users/wangmenghan/WHartTest/.env.example` | 环境变量模板 |
| `/Users/wangmenghan/WHartTest/data/logs/app.log` | 后端主日志 |
| `WHartTest_Django/wharttest_django/settings.py` | Django 设置（时区、Celery、DB） |
| `WHartTest_Django/orchestrator_integration/agent_loop_view.py` | Chat SSE 入口 |
| `WHartTest_Django/mcp_tools/persistent_client.py` | 持久 MCP session（已加 30s 超时） |
| `WHartTest_Django/knowledge/services.py` | `CustomAPIEmbeddings`、`VectorStoreManager` |
| `WHartTest_Django/knowledge/models.py` | `KnowledgeGlobalConfig`（单例） |
| `WHartTest_Django/task_center/scheduler.py` | 定时任务注册（cron + 时区） |
| `WHartTest_Django/task_center/tasks.py` | `execute_scheduled_task` Celery task（UI/API/Suite 三分支） |
| `WHartTest_Django/ui_automation/consumers.py` | WebSocket 派单 + `SocketUserManager`（OPEN 开关） |
| `WHartTest_Django/ui_automation/views.py` | UI 自动化 REST + `trigger_batch_execution` 内部接口 |
| `WHartTest_Django/api_automation/services.py` | 接口执行核心：`_render_value`、`_assert_response`、`_extract_variables`、`_compare`、`_get_by_path`、`_build_url`、OpenAPI 导入 |
| `WHartTest_Django/api_automation/ai_enhance.py` | LLM 给用例补全 assertions/extractors（`enhance_api_case`） |
| `WHartTest_Django/api_automation/ai_from_functional.py` | 功能用例 → 接口用例 AI 生成（preview / materialize） |
| `WHartTest_Django/api_automation/trace_to_api_cases.py` | UI 执行 trace 的网络请求 → 接口用例（preview / materialize） |
| `WHartTest_Django/api_automation/tasks.py` | `execute_api_batch_task`、`execute_api_case_task` |
| `WHartTest_Django/langgraph_integration/models.py` | `LLMConfig` 定义 |

---

## 8. 实用命令速查

```bash
# 查看后端容器进程
docker exec wharttest-backend sh -c "cat /proc/*/cmdline 2>/dev/null | tr '\0' ' '"

# 进入 Django shell（排查 DB 用）
docker exec -it wharttest-backend python manage.py shell

# 查后端日志
tail -f /Users/wangmenghan/WHartTest/data/logs/app.log

# 查 Celery Beat 日志
docker logs wharttest-backend 2>&1 | grep beat

# 重启后端
docker restart wharttest-backend

# 查 LLM 配置
docker exec wharttest-backend python manage.py shell -c "
from langgraph_integration.models import LLMConfig
for c in LLMConfig.objects.all():
    print(c.id, c.name, 'active=', c.is_active)
"

# 跑全部单元测试（首次需先清掉 test_wharttest 库）
docker exec wharttest-postgres psql -U postgres -c "DROP DATABASE IF EXISTS test_wharttest;"
docker exec wharttest-backend python manage.py test ui_automation api_automation task_center -v 1
```

---

## 9. 跟用户对话的偏好 / 约定

- **语言**：中文
- **风格**：简洁、直接，给结论不啰嗦
- **验证方式**：优先用 Playwright MCP（`mcp0_browser_*` 工具）进到前端点一遍，而不是只看代码
- **修改原则**：除非明确要改，否则不动与任务无关的文件；bug 就修根因，不要加补丁
- **代码注释**：除非明确要求，不要主动加注释
- **Git 工作流**：用户在 `dev` 分支开发测试，验证通过后自己手动合 master
- **远程仓库**：https://github.com/wangmenghanfd-eng/WhartTest.git

---

## 10. 单元测试基础设施（2026-04-27 新增）

### 覆盖模块与文件
| 模块 | 测试文件 | 测试数 |
|------|---------|--------|
| `ui_automation` | `WHartTest_Django/ui_automation/tests.py` | 25 |
| `api_automation` | `WHartTest_Django/api_automation/tests.py` | 73 |
| `task_center` | `WHartTest_Django/task_center/tests.py` | 29 |
| **合计** | | **127** |

### 关键覆盖点（每条都对应 §5 / §6 的修复，回归保护用）
- **OPEN 开关**：`SocketUserManagerActuatorTests`、`TriggerBatchExecutionViewTests`
- **任务时区**：`SchedulerRegistrationTests.test_register_daily_uses_task_timezone`
- **接口断言/变量替换**：`ApiServiceHelperTests`
- **OpenAPI 导入幂等**：`OpenApiImportExtraTests`
- **批量执行状态计算**：`UiBatchExecutionStatisticsTests`、`ApiBatchTaskTests`
- **定时任务校验规则**：`ScheduledTaskValidationTests`
- **定时任务执行分支**：`ScheduledTaskExecutionTests`（含 disabled/missing/no-cases/once-disable 四个分支）

### 跑测试

```bash
# Docker 容器内的 tests.py 是 build 时 COPY 进去的，不是挂载卷
# 改完 host 文件需要先 cp 进去再跑：
docker cp WHartTest_Django/ui_automation/tests.py wharttest-backend:/app/ui_automation/tests.py

# 跑单模块
docker exec wharttest-backend python manage.py test ui_automation -v 2

# 跑全部
docker exec wharttest-backend python manage.py test ui_automation api_automation task_center
```

### CI 接入建议
还没接入。建议加到 GitHub Actions 的 `docker-build.yml` 后置步骤里，PR 必须通过测试才能合入。

---

## 11. 历史修复（已稳定，仅作记录）

| 修复 | 日期 | 现状 |
|------|------|------|
| Playwright-MCP 启动 `MODULE_NOT_FOUND` | 早期 | `docker-compose.yml` 给 `playwright-mcp` 加 `working_dir: /app` |
| MCP 连接挂死 | 早期 | `mcp_tools/persistent_client.py` `get_session()` 加 30s `asyncio.wait_for` |
| Embedding 配置 | 早期 | `KnowledgeGlobalConfig` 用 SiliconFlow `BAAI/bge-m3` |
| Unauthorized API 告警 30s 一条 | 早期 | backend healthcheck 改纯 TCP 端口检查 |
| `LLMConfig.objects.get(is_active=True)` 脆弱 | 2026-04-21 | 主流程已全部改为 `.filter(...).first()` + 空值保护 |

---

## 12. 开启新会话时的建议第一步

1. 读这份文档
2. 执行 `docker ps` 确认服务都健康
3. 针对用户请求定位到 §7 的对应文件，不用重新扫描整个仓库
4. 若是 UI 自动化执行器调度 → §5.1
5. 若是任务中心时区 → §5.2
6. 若是 AI 驱动 Playwright 测试问题 → §5.3
7. 若是 Actuator 启动问题 → §5.4
8. 改了代码记得跑 §10 的单元测试，特别是涉及 OPEN/timezone/批量执行的部分

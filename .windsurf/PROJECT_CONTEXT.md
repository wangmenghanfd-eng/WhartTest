# WHartTest 项目上下文交接文档

> 给新会话 Cascade 使用——读完此文即可接手，无需再重新扫描整个工程。最后更新：2026-04-20。

---

## 1. 项目简介

**WHartTest** 是一个 AI 驱动的测试自动化平台，当前版本 **v2.2.0**。
- 后端：Django + DRF + LangGraph + Celery
- 前端：Vue 3 + Vite + Arco Design + Pinia
- 存储：PostgreSQL + Redis + Qdrant（向量库）
- AI：LLM（LangGraph 智能体）+ MCP 工具（Playwright、WHartTest 自身工具、远程 MCP）+ RAG 知识库
- 部署：Docker Compose，一键启动 6~7 个服务

本地部署根目录：`/Users/wangmenghan/WHartTest`。用户时区：**UTC+4**，Django 配置时区：**Asia/Shanghai (UTC+8)**（二者相差 4h，踩过坑，见 §6）。

---

## 2. 工程结构（顶层）

```
WHartTest/
├── WHartTest_Django/          # Django 后端（主要业务代码）
│   ├── accounts/              # 用户账户/认证
│   ├── api_keys/              # API Key 管理
│   ├── knowledge/             # 知识库 + RAG + 嵌入
│   ├── langgraph_integration/ # LLM 配置 + LangGraph 集成
│   ├── orchestrator_integration/  # Agent 编排层（chat 主入口）
│   ├── mcp_tools/             # MCP 工具集成
│   ├── task_center/           # 定时任务中心（Celery Beat）
│   ├── testcases/             # 测试用例
│   ├── ui_automation/         # UI 自动化（Playwright）
│   ├── requirements/          # 需求管理
│   ├── prompts/               # 提示词管理
│   ├── projects/              # 项目/成员
│   └── wharttest_django/      # Django settings & urls
├── WHartTest_Vue/             # Vue 前端
├── WHartTest_MCP/             # 内置 MCP 工具（WHartTest_tools、ms_mcp_api）
├── WHartTest_Actuator/        # 桌面执行器（Tkinter GUI）
├── WHartTest_Skills/          # Claude Skills（agent-browser / playwright / draw / weknora-kb）
├── docker-compose.yml         # 主 compose 文件（改过）
├── docker-compose.local.yml   # 本地开发用
└── data/                      # 持久化数据卷
    └── logs/app.log           # 后端日志（重要！排错就看这个）
```

### 2.1 Django 模块权责

| 模块 | 职责 | 关键模型 |
|------|------|---------|
| `langgraph_integration` | LLM 配置存储、LangGraph 节点 | `LLMConfig` |
| `orchestrator_integration` | Chat SSE 流、Agent 主循环 | `agent_loop_view.py` |
| `knowledge` | 文档、向量化、RAG 查询 | `KnowledgeBase`, `KnowledgeGlobalConfig` |
| `mcp_tools` | 远程 MCP 配置、持久会话 | `RemoteMCPConfig`, `MCPTool` |
| `task_center` | 定时任务调度（基于 django-celery-beat） | `ScheduledTask`, `TaskExecution` |
| `ui_automation` | UI 自动化页面/步骤/用例/执行 | 多个模型 |

### 2.2 前端路由要点

- `/langgraph-chat` — LLM 对话
- `/knowledge-management` — 知识库
- `/ui-automation` — UI 自动化（Tab：页面/步骤/用例/执行记录/批量执行/公共数据/环境）
- `/testcases` — 测试用例管理
- `/task-center` — 定时任务
- `/requirements` — 需求管理
- `/system-management/*` — 系统管理（LLM 配置、MCP 配置、API Key）

---

## 3. Docker Compose 服务拓扑

`docker-compose.yml` 中定义以下服务（默认启用）：

| 服务名 | 容器名 | 端口映射 | 作用 |
|--------|--------|---------|------|
| postgres | wharttest-postgres | - | 主数据库 |
| redis | wharttest-redis | - | 缓存 + Celery broker |
| qdrant | wharttest-qdrant | - | 向量数据库 |
| **backend** | **wharttest-backend** | 8000→8912（见下） | Django + Celery worker + Celery beat（supervisord 管理） |
| frontend | wharttest-frontend | 80→8913 | Nginx 静态资源 |
| mcp | wharttest-mcp | - | 内置 WHartTest MCP |
| **playwright-mcp** | **wharttest-playwright-mcp** | 8931→8916 | Playwright MCP 服务 |
| xinference（注释掉） | - | - | 本地 Embedding/Rerank 模型 |

**访问 URL**：
- 前端：http://localhost:8913
- 后端 API：http://localhost:8912（经 nginx proxy） / 容器内 8000
- Playwright-MCP：从后端访问 `http://playwright-mcp:8931/mcp`

**登录凭证**：`admin` / `admin123456`

---

## 4. 当前验证状态（2026-04-20 已验证通过）

| 模块 | 状态 | 备注 |
|------|------|------|
| LLM 对话 | ✅ | 使用 SiliconFlow Qwen2.5-7B（免费） |
| 知识库 | ✅ | 创建/上传/Embedding/RAG 查询全链路通 |
| 需求管理 | ✅ | 已有 "Expand Testing" 样例文档 |
| UI 自动化 | ✅ | 8条执行记录（6成2败） |
| 测试管理 | ✅ | 6条测试用例 |
| 任务中心 | ⚠️ | 页面正常，**定时任务不自动触发（时区/时间窗问题，待修，见 §6.5）** |
| Playwright-MCP | ✅ | 容器可运行，已修复 MODULE_NOT_FOUND |

---

## 5. 本次会话应用的修复（已生效）

### 5.1 Playwright-MCP 启动失败 ✅
**症状**：容器启动即 `MODULE_NOT_FOUND cli.js`。
**修复**：`docker-compose.yml` 给 `playwright-mcp` 加 `working_dir: /app`。

### 5.2 MCP 连接挂死 ✅
**症状**：Chat 在获取 MCP session 时无限等待。
**修复**：`WHartTest_Django/mcp_tools/persistent_client.py` 的 `_PersistentSessionEntry.get_session()` 加 30s `asyncio.wait_for` 超时。

### 5.3 Embedding 配置 ✅
通过 Django shell 更新 `KnowledgeGlobalConfig`：
- `embedding_service = 'openai'`
- `api_base_url = 'https://api.siliconflow.cn/v1'`
- `api_key = <SiliconFlow Key，取自 LLMConfig>`
- `model_name = 'BAAI/bge-m3'`（1024 维）

### 5.4 LLM 配置整理 ✅
`LLMConfig` 表当前状态：
- **id=2** `Qwen/Qwen2.5-7B-Instruct`（SiliconFlow）— **必须保持 `is_active=True`**
- **id=3** `Qwen/Qwen2.5-VL-32B-Instruct`（视觉模型，`is_active=False`，手动选用）

### 5.5 Unauthorized API 告警 ✅（改配置，重启后生效）
**症状**：日志每 30s 一条 `WARNING django.request: Unauthorized: /api/`。
**根因**：backend healthcheck 访问 `/api/` 返回 401，urllib 抛异常但日志已打出。
**修复**：`docker-compose.yml` backend healthcheck 改为纯 TCP 端口检查：
```yaml
test: [ "CMD", "python", "-c", "import socket; s=socket.create_connection(('localhost',8000),timeout=5); s.close()" ]
```
下次 `docker-compose up -d` 重启生效。

---

## 6. 已知问题 / 待办

### 6.1 ✅ `agent_loop_view.py` 的 `LLMConfig.objects.get(is_active=True)` 脆弱 — **已修复（2026-04-21）**
**修复内容**：
- `agent_loop_view.py` 主 chat 流（line ~1533）：`.get()` 改为 `.filter(is_active=True).first()` + 空值保护
- `models.py` `compress_old_history`（line ~239）：同上
- Resume 路径之前已修复，现已全部统一

### 6.2 视觉模型在 chat 中的选用
视觉模型（id=3）当前 `is_active=False`，不会被默认 chat 使用。前端应支持"按消息选模型"才能用到它；未验证此 UI 链路。

### 6.3 Context 100% 问题（LLM 对话）
前端对话 Context 进度条显示 100%，因为旧对话历史太多；单个 7B 模型 ctx=32k 被吃满，导致回复出现乱码/重复点号。清理历史或换大 ctx 模型可解。

### 6.4 未验证但存在的模块
- 批量执行（UI 自动化）
- 公共数据、环境配置（UI 自动化）
- 执行器（Actuator）桌面端
- Prompts 管理
- 远程 MCP Ping/同步（具体 UI 路径未走）

### 6.5 ✅ **定时任务时区错位 — 已修复（2026-04-21，方案 B）**

**修复内容**：
1. `task_center/models.py`：`ScheduledTask` 增加 `task_timezone` 字段（CharField, default=`Asia/Shanghai`）
2. `task_center/migrations/0005_scheduledtask_task_timezone.py`：对应 migration
3. `task_center/scheduler.py`：`register_periodic_task` 改用 `task.task_timezone`（不再硬编码 `timezone.get_current_timezone()`）
4. `task_center/serializers.py`：`task_timezone` 加入可写字段列表
5. `TaskFormModal.vue`：表单新增"时区"下拉选择器（daily/weekly/hourly 时显示），默认值读取浏览器时区（`Intl.DateTimeFormat().resolvedOptions().timeZone`），提供 8 个常用时区选项（含 Asia/Dubai UTC+4、Asia/Shanghai UTC+8 等）

**部署步骤**：重新构建并重启 backend + frontend 容器即可，migration 会自动执行。

**注意**：已存在的任务 `task_timezone` 默认为 `Asia/Shanghai`，若要改为 UTC+4，编辑任务后重新保存即可触发 `register_periodic_task` 更新 `CrontabSchedule`。

**验证**：
```bash
docker exec wharttest-backend python manage.py shell -c "
from django_celery_beat.models import PeriodicTask
pt = PeriodicTask.objects.get(name='scheduled_task_1')
print('enabled:', pt.enabled)
print('last_run_at:', pt.last_run_at)
print('total_run_count:', pt.total_run_count)
c = pt.crontab
print('crontab:', c.hour, c.minute, c.timezone)
"
```

---

## 7. 关键文件速查表

| 文件 | 用途 |
|------|------|
| `/Users/wangmenghan/WHartTest/docker-compose.yml` | Docker 服务定义（已改 2 处：playwright-mcp、backend healthcheck） |
| `/Users/wangmenghan/WHartTest/.env.example` | 环境变量模板 |
| `/Users/wangmenghan/WHartTest/data/logs/app.log` | 后端主日志 |
| `WHartTest_Django/wharttest_django/settings.py` | Django 设置（时区、Celery、DB） |
| `WHartTest_Django/orchestrator_integration/agent_loop_view.py` | Chat SSE 入口（`LLMConfig.objects.get(is_active=True)` 在这里） |
| `WHartTest_Django/mcp_tools/persistent_client.py` | 持久 MCP session（已加 30s 超时） |
| `WHartTest_Django/knowledge/services.py` | `CustomAPIEmbeddings`、`VectorStoreManager` |
| `WHartTest_Django/knowledge/models.py` | `KnowledgeGlobalConfig`（单例） |
| `WHartTest_Django/task_center/scheduler.py` | 定时任务注册（cron 写入在这） |
| `WHartTest_Django/task_center/tasks.py` | `execute_scheduled_task` Celery task |
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

# 重启后端（会重启 supervisord 中的 django/celery/beat 三个进程）
docker restart wharttest-backend

# 查 LLM 配置
docker exec wharttest-backend python manage.py shell -c "
from langgraph_integration.models import LLMConfig
for c in LLMConfig.objects.all():
    print(c.id, c.name, 'active=', c.is_active)
"

# 查知识库 Embedding 配置
docker exec wharttest-backend python manage.py shell -c "
from knowledge.models import KnowledgeGlobalConfig
c = KnowledgeGlobalConfig.get_config()
print(c.embedding_service, c.api_base_url, c.model_name)
"
```

---

## 9. 跟用户对话的偏好 / 约定

- **语言**：中文
- **风格**：简洁、直接，给结论不啰嗦
- **验证方式**：优先用 Playwright MCP（`mcp0_browser_*` 工具）进到前端点一遍，而不是只看代码
- **修改原则**：除非明确要改，否则不动与任务无关的文件；bug 就修根因，不要加补丁
- **当前待办优先级**：§6.5 的定时任务时区问题是用户最关心的

---

## 10. 开启新会话时的建议第一步

1. 读这份文档
2. 执行 `docker ps` 确认服务都健康
3. 针对用户请求定位到 §7 的对应文件，不用重新扫描整个仓库
4. 如果用户新开会话后第一句是"继续定时任务问题"——直接进入 §6.5 的修复方案 B 或 C

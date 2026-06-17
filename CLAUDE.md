# WHartTest — Claude Code 项目说明

AI 驱动的测试自动化平台,v2.2.0。
详细的工程结构、文件速查表、命令大全、历史修复见 `docs/PROJECT_CONTEXT.md`——**需要时再读对应章节,不必每次扫全仓**。

## 技术栈
- 后端:Django + DRF + LangGraph + Celery(含 Beat 调度)
- 前端:Vue 3 + Vite + Arco Design + Pinia
- 存储:PostgreSQL + Redis + Qdrant(向量库)
- AI:LLM(LangGraph 智能体)+ MCP 工具(Playwright / 内置 WHartTest / 远程 MCP)+ RAG
- 部署:Docker Compose

本地根目录 `/Users/wangmenghan/WHartTest`。
用户时区 UTC+4 (Asia/Dubai);Django 默认时区 Asia/Shanghai (UTC+8),定时任务支持按任务覆盖时区。

## 协作约定(重要)
- **语言**:中文。
- **风格**:简洁直接,给结论,不啰嗦。
- **修改原则**:除非明确要求,不动与任务无关的文件;bug 修根因,不加补丁。
- **注释**:除非明确要求,不要主动加代码注释。
- **验证方式**:优先用 Playwright MCP 进前端点一遍,而不是只看代码。
- **Git**:用户在 `dev` 分支开发测试,验证通过后自己手动合 master。远程仓库 https://github.com/wangmenghanfd-eng/WhartTest.git
- 改完代码记得跑相关单元测试(见下),尤其涉及 OPEN 开关 / 时区 / 批量执行的部分。

## 常用命令
```bash
# 后端日志(排错首选)
tail -f /Users/wangmenghan/WHartTest/data/logs/app.log

# 进 Django shell(排查 DB)
docker exec -it wharttest-backend python manage.py shell

# 重启后端
docker restart wharttest-backend

# 跑单元测试:⚠️ 绝不要 docker cp 进运行中的 wharttest-backend 容器——它服务的可能是
# 另一个 worktree,cp 会覆盖它的代码、弄坏线上(踩过坑)。
# 正确做法:从镜像新起一个 --rm 一次性容器,把改动文件 bind-mount 进去再跑,跑完即销毁。
docker exec wharttest-postgres psql -U postgres -c "DROP DATABASE IF EXISTS test_wharttest;"  # 首次/重跑前清测试库
docker run --rm --network wharttest_wharttest-network \
  -e DATABASE_TYPE=postgres -e POSTGRES_DB=wharttest -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres \
  -v "$PWD/WHartTest_Django/<module>/services.py:/app/<module>/services.py:ro" \
  -v "$PWD/WHartTest_Django/<module>/tests.py:/app/<module>/tests.py:ro" \
  --entrypoint python wharttest-backend \
  manage.py test ui_automation api_automation task_center -v 1
# 按需多 -v 挂载你改动的文件;不改的文件用镜像里自带的即可。
```

## 服务与访问
- 前端 http://localhost:8913,后端 API http://localhost:8912(经 nginx proxy)
- 默认登录 `admin` / `admin123456`
- 容器内访问 Playwright-MCP:`http://playwright-mcp:8931/mcp`

## 仍需留意的坑(细节见 docs/PROJECT_CONTEXT.md §5)
- **执行器 OPEN 开关**:状态存在 backend 内存,执行器重连后会被其上报值(默认 True)覆盖。
- **定时任务时区**:由 `ScheduledTask.task_timezone` 字段控制;已存在的旧任务默认 `Asia/Shanghai`,要改 UTC+4 须编辑任务后重新保存。
- **AI 驱动 Playwright**:已有一批修复(禁止 `npx playwright install`、按 chat_session_id 隔离截图目录、单信号判 success 等),改 `orchestrator_integration/builtin_tools/skill_tools.py` 或 `agent_loop_view.py` 前先看 §5.3。
- **Actuator 桌面执行器**:必须 `python3.11+`(用了 PEP 604 联合语法);端口写主机映射 `8912`,不是容器内 `8000`。

## 安全
Skills 具备较高系统执行权限,严禁公网暴露,仅限内网/可信网络部署。

## 开新会话第一步
1. 需要时读 `docs/PROJECT_CONTEXT.md` 对应章节定位文件,不用重新扫全仓。
2. `docker ps` 确认服务都健康。
3. 改了代码跑对应单元测试。

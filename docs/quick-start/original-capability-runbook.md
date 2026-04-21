# WHartTest 原始功能上手与联调手册

## 目标

这份手册用于帮助团队先跑通 `WHartTest` 的原始能力，再决定二次开发方向。首轮联调遵循两个原则：

- 先跑通不依赖 LLM 的链路，先把平台、执行器、UI 自动化本身跑顺。
- 先使用外部练习站点，避免把平台问题和业务站点问题混在一起。

首轮默认使用：

- 主练习站：`Expand Testing Practice`
- 备用站：`The Internet`

参考站点：

- [Expand Testing Practice](https://practice.expandtesting.com/)
- [The Internet](https://the-internet.herokuapp.com/)

## 模块地图

| 模块 | 路由入口 | 核心对象 | 首轮是否依赖 LLM | 首轮要做什么 |
| --- | --- | --- | --- | --- |
| 项目管理 | `/projects` | 项目、项目成员、项目凭证 | 否 | 新建练手项目，补齐项目凭证中的目标站点地址 |
| 需求管理 | `/requirements` | 需求文档、拆分模块、评审报告 | 是 | 第二阶段用一份小型练习文档做上传、拆分、评审演示 |
| 用例管理 | `/testcases` | 功能测试用例、审核状态、执行记录 | 部分依赖 | 第二阶段验证“需求到用例生成”链路 |
| UI 自动化 | `/ui-automation` | 环境配置、公共数据、页面、页面步骤、UI 用例、执行器、执行记录 | 否 | 第一阶段重点，先手工创建并执行 UI 用例 |
| 测试套件 | `/testsuites` | 套件、批量执行 | 否 | UI 用例跑通后做一次批量执行验证 |
| 任务中心 | `/task-center` | 定时任务、执行记录 | 否 | 作为增强项，最后验证即可 |
| LLM 配置 | `/llm-configs` | 大模型连接配置 | 是 | 第二阶段启用需求评审和 AI 生成用例前必须完成 |
| LLM 对话 | `/langgraph-chat` | 对话、提示词、Skills/MCP 工具调用 | 是 | 第二阶段再启用 |

## 最短联调路径

### 1. 先确认服务访问入口

如果你使用的是仓库默认 Docker 启动方式，常用入口通常是：

- 前端：`http://localhost:8913`
- 后端 API：`http://localhost:8912`
- MCP：`http://localhost:8914`
- Playwright MCP：`http://localhost:8916`

注意：

- 前端能打开，不代表执行器一定能连上。
- `WHartTest_Actuator` 默认连接的是 `127.0.0.1:8000`，而 Docker 暴露给宿主机的后端通常是 `8912`。

### 2. 新建一个专用练手项目

在 `项目管理` 中创建一个单独项目，建议命名：

- `Expand Testing 练手项目`

建议描述：

- `用于验证 WHartTest 原始功能、UI 自动化链路和执行器联调`

创建项目后，至少补一条项目凭证。这里最关键的不是账号密码，而是 `项目地址`：

| 字段 | 建议值 |
| --- | --- |
| 项目地址 | `https://practice.expandtesting.com/` |
| 用户名 | `practice` |
| 密码 | `SuperSecretPassword!` |
| 角色 | `practice-demo` |

说明：

- 当前项目“目标系统地址”不是单独项目字段，而是在项目凭证里通过 `system_url` 维护。
- 这条数据后续可以给 AI 生成和联调说明提供上下文。

### 3. 在 UI 自动化中先建环境配置

进入 `/ui-automation`，在 `环境配置` 页签创建一条默认环境：

| 字段 | 建议值 |
| --- | --- |
| 名称 | `expand-testing-chromium` |
| 基础 URL | `https://practice.expandtesting.com/` |
| 浏览器 | `chromium` |
| 无头模式 | 首轮建议 `否` |
| 视口宽度 | `1280` |
| 视口高度 | `720` |
| 超时时间 | `30000` |
| 默认环境 | `是` |

建议：

- 首轮调试把 `无头模式` 设为 `否`，便于肉眼确认动作和定位问题。
- 稳定后再切回无头模式做回归。

### 4. 先录入一组公共数据

进入 `公共数据` 页签，先只建字符串类型，避免首轮调试被复杂变量结构干扰。

| Key | 建议值 | 用途 |
| --- | --- | --- |
| `login_username` | `practice` | 登录成功场景 |
| `login_password` | `SuperSecretPassword!` | 登录成功场景 |
| `wrong_username` | `wrongUser` | 登录失败场景 |
| `wrong_password` | `WrongPassword` | 登录失败场景 |
| `login_success_text` | `You logged into a secure area!` | 成功断言 |
| `login_error_username` | `Invalid username.` | 失败断言 |
| `login_error_password` | `Invalid password.` | 失败断言 |
| `notes_name` | `WHartTest Smoke` | 表单输入样例 |

### 5. 连接执行器并确认在线

执行器目录在 [WHartTest_Actuator/README.md](/Users/wangmenghan/WHartTest/WHartTest_Actuator/README.md) 已说明。首轮推荐直接命令行启动。

如果你现在是 Docker 方式启动平台，推荐在本机这样启动执行器：

```bash
cd /Users/wangmenghan/WHartTest/WHartTest_Actuator
pip install -r requirements.txt
python main.py \
  --server ws://127.0.0.1:8912/ws/ui/actuator/ \
  --api http://127.0.0.1:8912 \
  --gui
```

如果你使用无 GUI 登录，则需要先把 `config.toml` 中的账号密码改成当前系统真实账号。注意默认示例里密码是 `admin123`，而仓库快速启动文档中的默认管理员密码通常是 `admin123456`。

执行器在线后，`UI 自动化 -> 执行器` 页签应能看到在线实例。

### 6. 先创建一个 UI 模块

在 UI 自动化左侧模块树中，先建一个根模块：

- `登录与基础交互`

首轮所有页面、页面步骤、测试用例都先挂在这个模块下，避免一开始拆得太散。

### 7. 第一批只做 3 个稳定场景

这 3 个场景的目标不是覆盖，而是快速建立“可执行、可观测、可复现”的闭环。

#### 场景 A：登录成功

- 页面：`登录页`
- 访问地址：`/login`
- 预期：
  - 输入 `practice / SuperSecretPassword!`
  - 点击登录后进入 `/secure`
  - 页面出现 `You logged into a secure area!`

#### 场景 B：登录失败

- 页面：`登录页`
- 访问地址：`/login`
- 预期：
  - 错误用户名或错误密码时停留在登录页
  - 出现对应错误提示

#### 场景 C：动态加载

- 页面：`动态加载`
- 访问地址：`/dynamic-loading`
- 预期：
  - 触发加载后，等待结果出现
  - 成功断言动态内容可见

说明：

- 这 3 个场景分别覆盖了基本导航、输入、点击、等待、断言和错误分支。
- 如果这一步还没稳，不建议直接上 iframe、shadow DOM 或多窗口。

### 8. 第二批补 2 到 3 个中复杂场景

首轮推荐从下面挑 2 到 3 个：

| 站点 | 场景 | 推荐原因 |
| --- | --- | --- |
| Expand Testing | `Web inputs` | 适合验证输入与断言 |
| Expand Testing | `IFrame` | 适合验证 frame 切换 |
| Expand Testing | `Shadow DOM` | 适合验证复杂定位 |
| Expand Testing | `Multiple Windows` | 适合验证窗口切换 |
| The Internet | `Add/Remove Elements` | 适合验证动态元素 |
| The Internet | `Context Menu` | 适合验证右键菜单 |

建议顺序：

1. `Web inputs`
2. `IFrame`
3. `Shadow DOM`

### 9. 先跑 UI 自动化最小闭环

第一阶段验收标准：

- 能登录平台
- 能创建练手项目
- 能创建环境配置
- 能创建公共数据
- 能看到在线执行器
- 能手工创建并执行至少 3 条 UI 用例
- 能查看执行结果、截图、Trace 或执行日志

如果上述 7 项还未稳定，不要先把问题归因到大模型。

## 第二阶段：补齐依赖 LLM 的原始能力

当第一阶段稳定后，再补第二阶段。

### 1. 配置 LLM

进入 `/llm-configs`，填入一个可用的大模型配置。只要能稳定响应即可，首轮不追求最强模型。

### 2. 上传一份小型练习需求文档

推荐直接使用仓库内置的练习文档：

- [expand-testing-requirement.md](/Users/wangmenghan/WHartTest/docs/quick-start/expand-testing-requirement.md)

需求管理已经支持上传 `PDF / DOC / DOCX / TXT / Markdown`，所以首轮直接使用 `Markdown` 即可。

### 3. 跑通需求链路

建议最短路径：

1. 上传练习文档
2. 按标题层级拆分模块
3. 做一次需求评审
4. 从某个模块生成一批测试用例
5. 观察生成结果是否与练习站点真实页面匹配

### 4. 再把结果映射回 UI 自动化

第二阶段重点不是让 AI 一步到位，而是确认：

- 需求模块结构是否合理
- 生成用例是否贴近真实页面
- 用例字段是否适合你们后续公司落地

## LLM 依赖矩阵

### 可以先脱离 LLM 跑通的部分

- 登录平台
- 项目管理
- UI 自动化环境配置
- UI 自动化公共数据
- 页面、页面步骤、UI 用例的手工创建
- 执行器连接
- UI 用例执行、截图、Trace、执行记录
- 测试套件批量执行
- 任务中心的非 AI 调度能力

### 需要 LLM 才有意义的部分

- 需求评审
- AI 生成测试用例
- LLM 对话
- 基于项目凭证、知识库和提示词的智能补全能力

## 常见坑位

### 执行器连不上

优先检查：

- 是否把执行器连到了 `8912` 而不是默认 `8000`
- WebSocket 地址是否写成了 `/ws/ui/actuator/`
- 是否已经成功登录执行器

### 执行器登录失败

优先检查：

- 是否沿用了执行器示例配置中的 `admin123`
- 当前平台默认管理员密码是否实际为 `admin123456`

### AI 生成结果与页面不一致

优先检查：

- 项目凭证中的 `项目地址` 是否填写正确
- UI 自动化中的 `环境配置` 是否与当前练习站一致
- 提示词是否过于泛化

### 需求拆分效果差

优先检查：

- 是否使用了结构清晰的 `Markdown` 或 `DOCX`
- 标题层级是否清楚
- 是否选择了合适的标题级别进行拆分

## 二开前的最小输出物

完成首轮上手后，至少保留三类结果：

1. 哪些原始能力已经稳定跑通
2. 卡点更偏配置、模型、执行器还是页面稳定性
3. 哪些地方和公司使用场景不匹配

建议配合这份记录模板一起使用：

- [adoption-gap-checklist.md](/Users/wangmenghan/WHartTest/docs/quick-start/adoption-gap-checklist.md)


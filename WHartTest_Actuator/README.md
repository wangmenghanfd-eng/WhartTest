# UI自动化执行器 (WHartTest Actuator)

独立的UI自动化执行器服务，通过WebSocket连接Django后端，接收并执行自动化测试任务。

## 架构设计


```
┌─────────────┐     WebSocket      ┌──────────────────┐
│   Django    │ ◄────────────────► │   Actuator       │
│   Backend   │                    │   (执行器)        │
│             │                    │                  │
│ - Consumer  │ ◄─ 发送任务 ────── │ - WebSocketClient│
│ - 任务分发   │ ◄─ 返回结果 ────── │ - TaskConsumer   │
└─────────────┘                    │ - Executor       │
                                   └──────────────────┘
                                          │
                                          ▼
                                   ┌──────────────────┐
                                   │  Playwright      │
                                   │  (浏览器自动化)   │
                                   └──────────────────┘
```

## 通信协议

### 消息格式 (SocketDataModel)
```json
{
    "code": 200,
    "msg": "success",
    "user": "username",
    "is_notice": 2,
    "data": {
        "func_name": "u_test_case",
        "func_args": {
            "case_id": 1
        }
    }
}
```

### 支持的任务类型
- `u_page_steps` - 执行页面步骤
- `u_test_case` - 执行测试用例
- `u_test_case_batch` - 批量执行用例
- `u_stop_execution` - 停止执行
- `u_step_result` - 步骤执行结果
- `u_case_result` - 用例执行结果

## 安装

```bash
cd WHartTest_Actuator
pip install -r requirements.txt
```

## 使用

### 基本启动
```bash
python main.py
```

本仓库本地 Docker 环境默认后端地址是 `http://127.0.0.1:8912`，对应 WebSocket 为
`ws://127.0.0.1:8912/ws/ui/actuator/`。如果你不是用本仓库的 Docker 环境，而是直接
`python manage.py runserver`，再按实际端口覆盖即可。

### 指定服务器地址
```bash
python main.py --server ws://192.168.1.100:8912/ws/ui/actuator/
```

### 指定执行器ID
```bash
python main.py --id actuator-01 --server ws://localhost:8912/ws/ui/actuator/
```

### 完整参数
```bash
python main.py \
    --server ws://localhost:8912/ws/ui/actuator/ \
    --api http://localhost:8912 \
    --id my-actuator \
    --log-level DEBUG
```

## 参数说明

| 参数 | 短参数 | 默认值 | 说明 |
|------|--------|--------|------|
| --server | -s | ws://localhost:8912/ws/ui/actuator/ | WebSocket服务器地址 |
| --api | -a | http://localhost:8912 | API服务器地址 |
| --id | -i | actuator-{pid} | 执行器唯一标识 |
| --log-level | -l | INFO | 日志级别 |

## macOS 常驻启动

如果你希望执行器在关闭终端后仍然常驻运行，可以使用本仓库自带的 `launchd` 安装脚本：

```bash
cd WHartTest_Actuator
bash install_launch_agent.sh
```

安装完成后会创建用户级 `LaunchAgent`：
- Label: `com.wharttest.actuator`
- 配置文件: `~/Library/LaunchAgents/com.wharttest.actuator.plist`
- 日志文件:
  - `../data/logs/actuator-launchd.out.log`
  - `../data/logs/actuator-launchd.err.log`

卸载方式：

```bash
cd WHartTest_Actuator
bash uninstall_launch_agent.sh
```

## 工作流程

1. **连接服务器**: 执行器启动后通过WebSocket连接Django后端
2. **等待任务**: 监听来自服务器的执行任务
3. **获取详情**: 通过REST API获取用例/步骤详细信息
4. **生成脚本**: 将步骤配置转换为Playwright代码
5. **执行测试**: 调用Playwright执行浏览器自动化
6. **返回结果**: 通过WebSocket将执行结果发送回服务器

## OPEN 开关语义

任务派发前，后端会优先选择 `is_open=true` 的执行器。

- `OPEN = 开`：执行器在线且允许接收新任务
- `OPEN = 关`：执行器仍保持在线，但后端不会再给它派发新任务

这适合做临时摘机、维护、浏览器环境排查，不需要真的退出执行器进程。
无论是“自动选择执行器”还是“明确指定某个执行器”，后端都会先检查 `is_open=true` 才允许派单。

当前列表页中的 `DEBUG` 没有接入真实远程调试语义，默认不作为可操作开关使用。

## 打包成独立 EXE

执行器支持打包成独立可执行文件，方便分发部署。

### 安装打包依赖

```bash
# 使用 uv
uv pip install pyinstaller

# 或使用 pip
pip install pyinstaller
```

### 执行打包

```bash
cd WHartTest_Actuator
uv run python build_exe.py
```

### 输出目录

```
dist/WHartTest_Actuator/
├── WHartTest_Actuator.exe  # 主程序
├── config.toml             # 配置文件
├── start.bat               # GUI模式启动脚本
├── start_no_gui.bat        # 无GUI模式启动脚本
├── browsers/               # Playwright浏览器（首次运行自动下载）
└── data/                   # 数据目录
    ├── browser/            # 浏览器用户数据
    ├── screenshots/        # 截图
    └── traces/             # Trace文件
```

### 使用说明

1. 将 `dist/WHartTest_Actuator/` 目录复制到目标机器
2. 编辑 `config.toml` 配置服务器地址和账号
3. 双击 `start.bat` 启动（GUI模式）或 `start_no_gui.bat`（无GUI模式）

**首次运行**：
- 首次运行会自动下载 Chromium 浏览器（约 150MB）
- 浏览器会下载到 `browsers/` 目录
- 后续运行无需重复下载

## 分布式部署

执行器支持分布式部署，多个执行器可以同时连接到一个Django后端：

```bash
# 机器A
python main.py --id actuator-machine-a --server ws://server:8912/ws/ui/actuator/

# 机器B  
python main.py --id actuator-machine-b --server ws://server:8912/ws/ui/actuator/

# 机器C
python main.py --id actuator-machine-c --server ws://server:8912/ws/ui/actuator/
```

服务器会自动将任务分发给可用的执行器。

## 文件说明

```
WHartTest_Actuator/
├── main.py              # 主入口，启动执行器
├── models.py            # 消息模型定义
├── websocket_client.py  # WebSocket客户端
├── consumer.py          # 任务消费者
├── executor.py          # Playwright执行引擎
├── browser_installer.py # 浏览器安装检查模块
├── build_exe.py         # 打包脚本
├── actuator.spec        # PyInstaller配置
├── requirements.txt     # 依赖
└── README.md            # 说明文档
```

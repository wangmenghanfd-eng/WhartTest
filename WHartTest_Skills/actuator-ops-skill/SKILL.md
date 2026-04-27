---
name: actuator-ops-skill
description: WHartTest 执行器运维工具。用于查看在线执行器、切换 OPEN 接单状态、查看最近 UI 自动化执行记录，以及读取平台与执行器日志。
---

# Actuator Ops Skill

这个 skill 面向执行器运维，不负责真正执行测试。

适用场景：

- 查看在线执行器列表
- 切换 `OPEN`，控制是否接新任务
- 查看最近 UI 自动化执行记录
- 查看单条执行记录详情
- 查看最近平台日志
- 查看最近执行器 launchd 日志

## 可用动作

- `list_actuators`
- `get_status`
- `toggle_open`
- `list_recent_ui_execution_records`
- `get_ui_execution_record`
- `tail_actuator_log`
- `tail_platform_log`

## 常用示例

```bash
python actuator_ops.py --action list_actuators
```

```bash
python actuator_ops.py --action toggle_open --actuator_id WHartTest-001 --is_open false
```

```bash
python actuator_ops.py --action list_recent_ui_execution_records --project_id 2 --limit 5
```

```bash
python actuator_ops.py --action tail_actuator_log --log_file err --lines 80
```

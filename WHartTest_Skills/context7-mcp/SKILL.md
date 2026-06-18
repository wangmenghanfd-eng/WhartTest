---
name: context7-mcp
description: This skill should be used when the user asks about libraries, frameworks, API references, or needs code examples. Activates for setup questions, code generation involving libraries, or mentions of specific frameworks like React, Vue, Next.js, Prisma, Supabase, etc.
---

# Context7 文档检索 Skill

这个 Skill 在 WHartTest 中已经提供了**可执行入口**，不要再尝试使用不存在的 `ctx7` CLI。

统一使用：

```bash
python run.py ask --library "react" --query "How do I clean up useEffect with async work?"
python run.py library "next.js" --query "app router auth middleware" --json
python run.py docs "/vercel/next.js" --query "How to add middleware that redirects unauthenticated users"
```

## 适用场景

- 查询框架 / SDK / API 的最新文档
- 获取库的最佳匹配 ID
- 基于官方文档生成代码示例

## 命令说明

### 1. 一步问答（推荐）

```bash
python run.py ask --library "prisma" --query "How to define one-to-many relations with cascade delete?"
```

- 先检索最佳库 ID
- 再自动获取相关文档片段

### 2. 只查库 ID

```bash
python run.py library "react" --query "hooks state management"
```

### 3. 已知库 ID 时直接查文档

```bash
python run.py docs "/reactjs/react.dev" --query "How do I use useState?"
```

## 说明

- 默认优先走 Context7 官方 API
- 未配置 `CONTEXT7_API_KEY` 时，会走匿名配额
- 如果用户明确提到某个库/框架，优先使用这个 Skill，而不是凭记忆回答

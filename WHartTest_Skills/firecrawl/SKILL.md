---
name: firecrawl
description: Search, scrape, and interact with the web via the Firecrawl CLI. Use this skill whenever the user wants to search the web, find articles, research a topic, look something up online, scrape a webpage, grab content from a URL, get data from a website, crawl documentation, download a site, or interact with pages that need clicks or logins. Also use when they say "fetch this page", "pull the content from", "get the page at https://", or reference external websites. This provides real-time web search with full page content and interact capabilities — beyond what Claude can do natively with built-in tools. Do NOT trigger for local file operations, git commands, deployments, or code editing tasks.
---

# Firecrawl Web Skill

这个 Skill 在 WHartTest 中已经提供了**可执行入口**，不要再假设容器里一定存在 `firecrawl` CLI。

统一使用：

```bash
python run.py status
python run.py search --query "latest React 19 release notes" --limit 5
python run.py scrape --url "https://docs.firecrawl.dev/introduction"
```

## 当前实现策略

- 如果配置了 `FIRECRAWL_API_KEY`，优先调用 Firecrawl 官方 API
- 如果没有配置 key：
  - `search` 走平台内置兼容搜索
  - `scrape` 走平台内置兼容抓取
- `interact / crawl / monitor` 暂未在本地 skill 入口实现，遇到这类需求请优先使用浏览器技能或 Firecrawl MCP

## 命令说明

### 查看状态

```bash
python run.py status
```

### 搜索网页

```bash
python run.py search --query "Django async ORM docs" --limit 5
python run.py search --query "Next.js auth middleware" --limit 3 --json
```

### 抓取页面

```bash
python run.py scrape --url "https://docs.firecrawl.dev/api-reference/introduction"
python run.py scrape --url "https://context7.com/docs/api-guide" --json
```

## 说明

- 如果用户只是需要网页检索/抓取，优先用这个 Skill
- 如果需要复杂点击、登录、分页交互，优先改用浏览器类 Skill

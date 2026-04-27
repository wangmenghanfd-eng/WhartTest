---
name: internal-kb-skill
description: WHartTest 平台内置知识库工具。用于查询平台自己的知识库、查看全局知识库配置、查看文档列表，以及测试 embedding / reranker 连接状态。
---

# Internal Knowledge Base Skill

这个 skill 直接对接 WHartTest 平台自己的知识库模块，不再使用外部 WeKnora。

适用场景：

- 列出平台知识库
- 查看知识库全局配置
- 查看知识库系统状态
- 查询某个知识库
- 查看知识库文档
- 测试 embedding 连接
- 测试 reranker 连接

## 可用动作

- `list_knowledge_bases`
- `get_global_config`
- `get_system_status`
- `list_documents`
- `query_knowledge_base`
- `test_embedding_connection`
- `test_reranker_connection`

## 常用示例

```bash
python internal_kb.py --action list_knowledge_bases
```

```bash
python internal_kb.py --action query_knowledge_base \
  --knowledge_base_id 2e5d0b94-c02b-4fae-8c45-bb47b7f9cbab \
  --query "WHartTest 是什么平台"
```

```bash
python internal_kb.py --action test_reranker_connection \
  --reranker_service xinference \
  --reranker_api_url http://xinference:9997 \
  --reranker_model_name bge-reranker-v2-m3
```

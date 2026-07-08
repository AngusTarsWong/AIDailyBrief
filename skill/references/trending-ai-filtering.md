# Trending AI 相关性过滤与丰富介绍

## 流程

```
Phase 1: run-briefing.py 抓取 Trending → 16-25 个项目
Phase 1.5: Jina 抓取前 10 个项目的 GitHub 页面 → page_content (前 500 字)
Phase 2: translate-sections.py 生成翻译任务
  → 每个 Trending 项目的 prompt 包含 AI 相关性判断指令
  → 不相关的项目: {"skip": true, "reason": "原因"}
  → 相关的项目: desc_zh 150-250 字，结合知识补充背景
Phase 2.5: merge-batches.py 过滤 skip 项目 → enriched JSON
Phase 3: generate-report.py → HTML 报告
```

## translate-sections.py Trending prompt 模板

```python
prompt = f"""请将以下 GitHub Trending 项目翻译为中文。

**重要**：
- 请先判断该项目是否与 AI/LLM/Agent/机器学习/自动化相关
- 如果**不相关**（如通用工具列表、纯前端框架、非 AI 的 DevOps 工具等），请输出：
  {{"skip": true, "reason": "不相关的原因"}}
- 如果**相关**，请输出详细翻译

项目名称: {p.get('name', '')}
项目描述: {p.get('desc', '')}
语言标签: {p.get('lang', '')}
主题: {', '.join(p.get('topics', []))}
{f'项目页面内容摘要:\n{page_content}' if page_content else ''}

请输出 JSON 格式（只输出 JSON，不要其他内容）：
{{
  "name_zh": "中文项目名称（如有合适的中文译名）",
  "desc_zh": "详细的中文项目介绍（150-250字）。要求：结合项目名称、描述、技术栈，用你自己的知识补充该项目背景，说明它解决什么问题、有什么特点、适合谁用。不要只是直译原文，要写出有信息量的介绍。",
  "lang_zh": "中文语言名称"
}}"""
```

## merge-batches.py skip 处理

```python
if translation.get('skip'):
    item['_skip'] = True
    item['_skip_reason'] = translation.get('reason', '')
    continue

# 最后过滤
raw[section] = [item for item in raw[section] if not item.get('_skip')]
```

## generate-report.py desc_zh 守卫

```python
def enrich_trending(project):
    desc_zh = project.get('desc_zh', '')
    # 优先使用翻译管道已生成的 desc_zh（足够长说明已翻译）
    if desc_zh and len(desc_zh) > 80:
        project['desc_en'] = project.get('desc', '')
        return
    # 否则用本地字典兜底
    ...
```

## 效果对比

| 指标 | 旧方案 | 新方案 |
|------|--------|--------|
| 描述长度 | 50-100 字 | 187-247 字（平均 204 字） |
| 信息量 | 直译原文 | 结合知识补充背景、特点、适用场景 |
| AI 过滤 | 硬编码关键词列表 | LLM 判断，自动过滤非 AI 项目 |
| 上下文 | 仅 Trending 页面描述 | + GitHub README 前 500 字 |

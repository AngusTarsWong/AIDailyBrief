# Release Notes Translation Pipeline

## 问题

`generate-report.py` 支持渲染 `release_highlights_zh`（中文版迭代记录），但**标准翻译流水线不处理 release summaries**。

翻译管道（`translate-sections.py` + `translate-batches.py`）只翻译：
- 项目名、描述（`name_zh`, `desc_zh`）
- 论文标题/摘要（`title_zh`, `summary_zh`）
- Blog 标题（`title_zh`）
- 新闻标题（`title_zh`）

**不包括**：GitHub releases 的 `summary` 字段。

## 影响

- 如果 release 的 `summary` 是英文（来自 `extract_highlights()` 提取），报告中会显示英文
- 如果 release 有 `release_highlights_zh`（由子 Agent 生成），则显示中文
- 大多数情况下 release 只有英文 `summary`，没有 `release_highlights_zh`

## 补充翻译脚本

当需要翻译 release notes 时，使用以下流程：

### 1. 收集待翻译的 release summaries

```python
import json
with open('/tmp/llm-briefing-enriched-{DATE}.json') as f:
    data = json.load(f)

releases_to_translate = []
for p in data.get('github', []):
    for i, r in enumerate(p.get('releases', [])):
        s = r.get('summary', '')
        if s and not r.get('release_highlights_zh'):
            releases_to_translate.append({
                'project': p['name'],
                'tag': r.get('name', r.get('tag', '')),
                'summary': s,
                'index': i
            })
```

### 2. 批量翻译

使用 delegate_task 或 execute_code，将 release summaries 分批（每批 3-5 条）发送给 LLM 翻译：

```
你是一个技术翻译助手，请将以下 GitHub 版本更新记录翻译为中文。
要求：
1. 保留技术术语的英文原名（Vue、React、API、SDK 等）
2. 翻译要准确、简洁，符合中文技术文档风格
3. 每个版本用一段中文概括核心改动（100-200字）
4. 输出 JSON 格式：{"项目名 - 版本号": "中文翻译", ...}
```

### 3. 合并回 enriched JSON

```python
for key, translation in translations.items():
    for p in data['github']:
        for r in p.get('releases', []):
            tag = r.get('name', r.get('tag', ''))
            if f"{p['name']} - {tag}" == key:
                r['release_highlights_zh'] = translation
```

### 4. 重新生成 HTML

```bash
/opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/generate-report.py
```

## 长期方案

可将 release notes 翻译整合进 `translate-batches.py`，作为翻译任务的一部分。

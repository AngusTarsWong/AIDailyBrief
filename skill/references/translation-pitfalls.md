# 翻译管线陷阱记录

## 2026-07-07 全链路验证发现

### 1. merge-batches.py section 名映射错误

**现象**：合并后论文的 `title_zh` 和 `summary_zh` 全部为 MISSING。

**根因**：raw JSON 中的 key 是 `papers`（复数），merge 脚本循环时生成 task_id `papers-0`，但翻译结果文件的 key 是 `paper-0`（单数）。

**映射表**：
| raw JSON key | task_id 前缀 |
|---|---|
| `github_trending` | `trending-` |
| `github` | `github-` |
| `papers` | `paper-` |
| `blogs` | `blog-` |
| `news` | `news-` |
| `hn` | `hn-` |

### 2. generate-report.py enrich 函数覆盖翻译

**现象**：即使 enriched JSON 中已有完整的 `title_zh` / `summary_zh`，渲染后仍显示英文。

**根因**：`enrich_paper()` 无条件执行兜底逻辑，覆盖已有翻译。blog 标题清洗和新闻标题翻译同理。

**修复**：每个 enrich 函数开头加守卫：
```python
if item.get('title_zh') and item.get('summary_zh'):
    return  # 已有翻译，跳过
```

### 3. generate-report.py summary 渲染未使用 summary_zh

**现象**：Blog 和 News 的摘要显示英文原文（`page_content` 前 200 字符），而非 LLM 翻译的中文摘要。

**根因**：渲染时直接用 `b.get('page_content', '')[:200]` 而非 `b.get('summary_zh', '')`。

**修复**：
```python
# Blog
summary = b.get('summary_zh', '') or b.get('page_content', '')[:200]
# News
summary = n.get('summary_zh', '') or n.get('desc', '')[:150]
```

### 4. 子 Agent task_id 编号偏移

**现象**：subagent 翻译 batch-9 时写入了 `paper-1` 到 `paper-5`，但期望的是 `paper-0` 到 `paper-4`。

**根因**：subagent 在 prompt 中自行编号，容易从 1 开始。

**修复方案**：
- 在翻译 prompt 中明确 "索引从 0 开始"
- 或在合并脚本中做编号归一化
- 或在 subagent 完成后验证并修正

### 5. HN 板块未渲染

**现象**：raw JSON 中有 `hn` 数据（3-4 条），但 HTML 报告中不显示。

**根因**：`generate-report.py` 只渲染了 `news`，没有将 `hn` 合并到 news 或单独渲染。

**待修复**：需要在 Phase 2.5 合并时将 `hn` 翻译结果合并到 raw JSON，并在 Phase 3 渲染时包含 HN 条目。

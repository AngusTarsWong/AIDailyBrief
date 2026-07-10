#!/usr/bin/env python3
"""翻译服务：逐个翻译每个项目/条目，确保翻译完整性和稳定性。

用法：
    python translate-sections.py <raw-json-path>

输出：
    生成一个翻译任务清单文件，AI agent 逐个处理后写入 enriched JSON。
"""
import json, sys, os
from datetime import datetime

if len(sys.argv) < 2:
    # 自动查找今天的 raw JSON
    DATE_STR = os.environ.get('BRIEF_DATE', datetime.now().strftime('%Y-%m-%d'))
    RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
else:
    RAW_JSON = sys.argv[1]
    DATE_STR = os.path.basename(RAW_JSON).replace('llm-briefing-raw-', '').replace('.json', '')

if not os.path.exists(RAW_JSON):
    print(f"❌ 找不到原始数据: {RAW_JSON}")
    sys.exit(1)

with open(RAW_JSON) as f:
    raw = json.load(f)

# 生成翻译任务清单
tasks = []

# ── 1. GitHub Trending ──
for i, p in enumerate(raw.get('github_trending', [])):
    page_content = p.get('page_content', '')[:500]
    
    prompt_parts = [
        "请将以下 GitHub Trending 项目翻译为中文。",
        "",
        "**重要**：",
        "- 请先判断该项目是否与 AI/LLM/Agent/机器学习/自动化相关",
        "- 如果**不相关**（如通用工具列表、纯前端框架、非 AI 的 DevOps 工具等），请输出：",
        '  {"skip": true, "reason": "不相关的原因"}',
        "- 如果**相关**，请输出详细翻译",
        "",
        f"项目名称: {p.get('name', '')}",
        f"项目描述: {p.get('desc', '')}",
        f"语言标签: {p.get('lang', '')}",
        f"主题: {', '.join(p.get('topics', []))}",
    ]
    if page_content:
        prompt_parts.append(f"项目页面内容摘要:\n{page_content}")
    prompt_parts.extend([
        "",
        "请输出 JSON 格式（只输出 JSON，不要其他内容）：",
        "{",
        '  "name_zh": "中文项目名称（如有合适的中文译名）",',
        '  "desc_zh": "详细的中文项目介绍（150-250字）。要求：结合项目名称、描述、技术栈，用你自己的知识补充该项目背景，说明它解决什么问题、有什么特点、适合谁用。不要只是直译原文，要写出有信息量的介绍。",',
        '  "lang_zh": "中文语言名称"',
        "}",
    ])
    
    tasks.append({
        'task_id': f'trending-{i}',
        'section': 'github_trending',
        'index': i,
        'type': 'project',
        'name': p.get('name', ''),
        'prompt': '\n'.join(prompt_parts),
    })

# ── 2. GitHub 热门项目 ──
for i, p in enumerate(raw.get('github', [])):
    releases_info = ''
    for j, r in enumerate(p.get('releases', [])):
        tag = r.get('tag', '')
        name = r.get('name', '')
        summary = r.get('summary', '')
        if summary:
            releases_info += f"\n  Release {j+1} ({tag}): {name}\n    {summary[:200]}"
    
    tasks.append({
        'task_id': f'github-{i}',
        'section': 'github',
        'index': i,
        'type': 'project_with_releases',
        'name': p.get('name', ''),
        'prompt': f"""请将以下 GitHub 热门项目及其版本更新记录翻译为中文。

项目名称: {p.get('name', '')}
Stars: {p.get('stars', 0):,}
语言: {p.get('lang', '')}
项目描述: {p.get('desc', '')}
主题: {', '.join(p.get('topics', []))}
最后更新: {p.get('updated', '')}{releases_info}

请输出 JSON 格式（只输出 JSON，不要其他内容）：
{{
  "name_zh": "中文项目名称（如有合适的中文译名）",
  "desc_zh": "详细的中文项目描述（基于项目名称、描述、主题等上下文进行准确翻译，80-150字）",
  "lang_zh": "中文语言名称",
  "releases": [
    {{
      "tag": "{p['releases'][0]['tag'] if p.get('releases') else ''}",
      "release_highlights_zh": ["中文改动说明1", "中文改动说明2", ...]
    }}
  ]
}}

注意：
- desc_zh 要详细、准确，体现项目的核心功能和特点
- release_highlights_zh 是字符串数组，每个元素一条中文改动说明
- 如果没有 release body 或无法提取，设为空数组 []
- 只输出 JSON，不要其他内容"""
    })

# ── 3. arXiv 论文 ──
for i, p in enumerate(raw.get('papers', [])):
    tasks.append({
        'task_id': f'paper-{i}',
        'section': 'papers',
        'index': i,
        'type': 'paper',
        'name': p.get('title', '')[:50],
        'prompt': f"""请将以下 arXiv 论文翻译为中文：

标题: {p.get('title', '')}
日期: {p.get('date', '')}
摘要: {p.get('summary', '')[:400]}

请输出 JSON 格式（只输出 JSON，不要其他内容）：
{{
  "title_zh": "中文论文标题",
  "summary_zh": "中文论文摘要（150-200字，保留关键术语的英文原名）"
}}"""
    })

# ── 4. Blog ──
for i, p in enumerate(raw.get('blogs', [])):
    page_content = p.get('page_content', '')[:500]
    tasks.append({
        'task_id': f'blog-{i}',
        'section': 'blogs',
        'index': i,
        'type': 'blog',
        'name': p.get('title', '')[:50],
        'prompt': f"""请将以下 Blog 文章翻译为中文摘要：

标题: {p.get('title', '')}
来源: {p.get('source', '')}
日期: {p.get('date', '')}
正文内容:
{page_content if page_content else '(无正文内容)'}

请输出 JSON 格式（只输出 JSON，不要其他内容）：
{{
  "title_zh": "中文标题（简洁准确）",
  "summary_zh": "中文内容摘要（80-120字，概括核心内容）"
}}"""
    })

# ── 5. 新闻 ──
for i, p in enumerate(raw.get('news', []) + raw.get('hn', [])):
    section = 'news' if i < len(raw.get('news', [])) else 'hn'
    idx = i if section == 'news' else i - len(raw.get('news', []))
    page_content = p.get('page_content', '')[:300]
    tasks.append({
        'task_id': f'{section}-{idx}',
        'section': section,
        'index': idx,
        'type': 'news',
        'name': p.get('title', '')[:50],
        'prompt': f"""请将以下新闻翻译为中文摘要：

标题: {p.get('title', '')}
来源: {p.get('source', '')}
日期: {p.get('date', '')}
描述: {p.get('desc', '')}
{f'正文内容: {page_content}' if page_content else ''}

请输出 JSON 格式（只输出 JSON，不要其他内容）：
{{
  "title_zh": "中文新闻标题",
  "summary_zh": "中文新闻摘要（80-120字）"
}}"""
    })

# 输出任务清单
TASKS_JSON = f"/tmp/llm-briefing-tasks-{DATE_STR}.json"
with open(TASKS_JSON, 'w') as f:
    json.dump({
        'date': DATE_STR,
        'total_tasks': len(tasks),
        'tasks': tasks,
    }, f, ensure_ascii=False, indent=2)

print(f"✅ 生成 {len(tasks)} 个翻译任务")
print(f"📦 任务清单: {TASKS_JSON}")

# 统计各板块数量
sections = {}
for t in tasks:
    s = t['section']
    sections[s] = sections.get(s, 0) + 1
for s, c in sorted(sections.items()):
    print(f"   {s}: {c} 个任务")

#!/usr/bin/env python3
"""翻译任务分组：将翻译任务按板块和批次分组，每批 3-5 个项目。

确保每个翻译批次有足够的上下文专注度，避免信息丢失。
"""
import json, sys, os
from datetime import datetime

DATE_STR = datetime.now().strftime('%Y-%m-%d')
TASKS_JSON = f"/tmp/llm-briefing-tasks-{DATE_STR}.json"

if not os.path.exists(TASKS_JSON):
    print(f"❌ 找不到任务清单: {TASKS_JSON}")
    print("请先运行: python translate-sections.py")
    sys.exit(1)

with open(TASKS_JSON) as f:
    task_data = json.load(f)

tasks = task_data['tasks']

# 按板块分组
sections = {}
for t in tasks:
    s = t['section']
    if s not in sections:
        sections[s] = []
    sections[s].append(t)

# 每个板块分成小批次（每批最多 5 个项目）
BATCH_SIZE = 5
batches = []
batch_id = 0

for section, section_tasks in sections.items():
    for i in range(0, len(section_tasks), BATCH_SIZE):
        batch = section_tasks[i:i+BATCH_SIZE]
        batch_id += 1
        
        # 构建批次翻译提示
        prompts = []
        expected_fields = {}
        
        for t in batch:
            prompts.append(f"\n=== {t['task_id']} ===")
            prompts.append(t['prompt'])
            
            # 记录期望的字段
            if t['type'] == 'project':
                expected_fields[t['task_id']] = ['name_zh', 'desc_zh', 'lang_zh']
            elif t['type'] == 'project_with_releases':
                expected_fields[t['task_id']] = ['name_zh', 'desc_zh', 'lang_zh', 'releases']
            elif t['type'] == 'paper':
                expected_fields[t['task_id']] = ['title_zh', 'summary_zh']
            elif t['type'] == 'blog':
                expected_fields[t['task_id']] = ['title_zh', 'summary_zh']
            elif t['type'] == 'news':
                expected_fields[t['task_id']] = ['title_zh', 'summary_zh']
        
        batch_prompt = f"""你是一个专业的 AI/技术翻译助手。请将以下 {len(batch)} 个项目/条目翻译为中文。

**重要规则**：
1. 每个项目都要完整翻译，不要遗漏任何字段
2. 翻译要准确、专业，保留通用技术术语的英文原名（如 API、CLI、LLM、Agent 等）
3. 只输出 JSON，不要其他内容
4. 每个项目的翻译结果用 task_id 作为 key

{chr(10).join(prompts)}

请输出 JSON 格式，结构如下：
{{
  "{batch[0]['task_id']}": {{...翻译结果...}}"""
        if len(batch) > 1:
            batch_prompt += f",\n  \"{batch[1]['task_id']}\": {{...翻译结果...}}"
        if len(batch) > 2:
            batch_prompt += ",\n  ..."
        batch_prompt += "\n}}"

        batches.append({
            'batch_id': f'batch-{batch_id}',
            'section': section,
            'task_ids': [t['task_id'] for t in batch],
            'count': len(batch),
            'prompt': batch_prompt,
            'expected_fields': expected_fields,
            'output_file': f'/tmp/llm-briefing-batch-{batch_id}.json',
        })

# 输出批次信息
BATCHES_JSON = f"/tmp/llm-briefing-batches-{DATE_STR}.json"
with open(BATCHES_JSON, 'w') as f:
    json.dump({
        'date': DATE_STR,
        'total_batches': len(batches),
        'total_tasks': len(tasks),
        'batches': batches,
    }, f, ensure_ascii=False, indent=2)

print(f"✅ 生成 {len(batches)} 个翻译批次（共 {len(tasks)} 个任务）")
print(f"📦 批次清单: {BATCHES_JSON}")
print(f"   每批最多 {BATCH_SIZE} 个项目")
print()
for b in batches:
    print(f"  {b['batch_id']}: {b['section']} ({b['count']} 个项目) -> {b['output_file']}")

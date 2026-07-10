#!/usr/bin/env python3
"""合并翻译批次结果：将所有批次的翻译结果合并到 enriched JSON。

读取 raw JSON 作为基底，叠加各批次的翻译结果。
"""
import json, os, sys
from datetime import datetime

DATE_STR = os.environ.get('BRIEF_DATE', datetime.now().strftime('%Y-%m-%d'))
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
BATCHES_JSON = f"/tmp/llm-briefing-batches-{DATE_STR}.json"
ENRICHED_JSON = f"/tmp/llm-briefing-enriched-{DATE_STR}.json"

if not os.path.exists(RAW_JSON):
    print(f"❌ 找不到原始数据: {RAW_JSON}")
    sys.exit(1)

if not os.path.exists(BATCHES_JSON):
    print(f"⚠️ 找不到批次清单: {BATCHES_JSON}")
    print("将使用 raw JSON 作为输出（无翻译）")
    # 直接复制 raw JSON
    with open(RAW_JSON) as f:
        raw = json.load(f)
    with open(ENRICHED_JSON, 'w') as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    print(f"✅ 已复制 raw JSON -> enriched JSON")
    sys.exit(0)

with open(RAW_JSON) as f:
    raw = json.load(f)

with open(BATCHES_JSON) as f:
    batches_data = json.load(f)

# 收集所有批次的翻译结果
all_translations = {}
translated_count = 0
missing_count = 0

for batch in batches_data['batches']:
    output_file = batch['output_file']
    if os.path.exists(output_file):
        with open(output_file) as f:
            try:
                batch_data = json.load(f)
                # 兼容两种格式：{"results": {...}} 或直接是翻译结果字典
                batch_results = batch_data.get('results', batch_data)
                all_translations.update(batch_results)
                translated_count += len(batch_results)
                print(f"  ✅ {batch['batch_id']}: {len(batch_results)} 个翻译结果")
            except json.JSONDecodeError as e:
                print(f"  ❌ {batch['batch_id']}: JSON 解析失败 - {e}")
                missing_count += batch['count']
    else:
        print(f"  ⏭️ {batch['batch_id']}: 文件不存在 {output_file}")
        missing_count += batch['count']

# section 名到 task_id 前缀的映射
SECTION_PREFIX = {
    'github_trending': 'trending',
    'github': 'github',
    'papers': 'paper',
    'blogs': 'blog',
    'news': 'news',
    'hn': 'hn',
}

# 将翻译结果合并到 raw JSON
for section, prefix in SECTION_PREFIX.items():
    items = raw.get(section, [])
    for i, item in enumerate(items):
        task_id = f'{prefix}-{i}'
        if task_id in all_translations:
            translation = all_translations[task_id]
            # 处理 skip 标记（非 AI 相关的 Trending 项目）
            if translation.get('skip'):
                item['_skip'] = True
                item['_skip_reason'] = translation.get('reason', '')
                continue
            # 合并翻译字段
            for key, value in translation.items():
                if key == 'releases' and isinstance(value, list):
                    # 特殊处理 releases：合并到对应的 release 对象
                    for j, rel in enumerate(value):
                        if j < len(item.get('releases', [])):
                            item['releases'][j].update(rel)
                else:
                    item[key] = value

# 过滤掉标记为 skip 的项目（非 AI 相关的 Trending）
for section in SECTION_PREFIX:
    if section in raw:
        raw[section] = [item for item in raw[section] if not item.get('_skip')]

# 输出 enriched JSON
with open(ENRICHED_JSON, 'w') as f:
    json.dump(raw, f, ensure_ascii=False, indent=2)

print(f"\n✅ 合并完成: {translated_count} 个翻译，{missing_count} 个缺失")
print(f"📦 Enriched JSON: {ENRICHED_JSON}")

#!/usr/bin/env python3
"""LLM & Agent Daily Briefing — 合并各子 Agent 产出的 enriched section JSON"""
import json, os
from datetime import datetime

DATE_STR = datetime.now().strftime('%Y-%m-%d')
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
ENRICHED_JSON = f"/tmp/llm-briefing-enriched-{DATE_STR}.json"

SECTIONS = ['github_trending', 'github', 'papers', 'blogs', 'news']

def merge():
    """读取 raw JSON 作为 base，叠加各板块 enriched section"""
    with open(RAW_JSON) as f:
        raw = json.load(f)
    
    merged = {'date': raw.get('date', DATE_STR)}
    enriched_count = 0
    fallback_count = 0
    
    for section in SECTIONS:
        section_file = f"/tmp/llm-briefing-enriched-{section}-{DATE_STR}.json"
        if os.path.exists(section_file):
            with open(section_file) as f:
                section_data = json.load(f)
            merged[section] = section_data
            enriched_count += len(section_data)
            print(f"  ✅ {section}: enriched ({len(section_data)} 条)")
        else:
            merged[section] = raw.get(section, [])
            fallback_count += len(merged[section])
            print(f"  ⚠️ {section}: 无 enriched section，降级 raw ({len(merged[section])} 条)")
    
    merged['hn'] = raw.get('hn', [])
    
    with open(ENRICHED_JSON, 'w') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    
    total = enriched_count + fallback_count
    print(f"\n✅ 合并完成: {enriched_count} enriched + {fallback_count} raw fallback = {total} 条总计")
    return merged

if __name__ == '__main__':
    merge()

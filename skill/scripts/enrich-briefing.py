#!/usr/bin/env python3
"""⚠️ 此脚本已过时，不再使用。

Phase 2（LLM 翻译增强）现已由 Hermes Agent 在 cronjob 中直接完成：
- Agent 读取 raw JSON → 翻译所有标题/描述/摘要 → 保存 enriched JSON
- 不再使用此启发式分析脚本

当前 Phase 2 流程（cronjob prompt 中执行）：
1. 读取 /tmp/llm-briefing-raw-YYYY-MM-DD.json
2. 对每个条目翻译标题、生成中文摘要、提炼 release highlights
3. 保存为 /tmp/llm-briefing-enriched-YYYY-MM-DD.json

generate-report.py 已适配：优先读 enriched JSON，降级到 raw JSON。
"""
import json, subprocess, sys
from datetime import datetime

PROXY = "http://127.0.0.1:6789"
DATE = datetime.now().strftime('%Y-%m-%d')
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE}.json"
ENRICHED_JSON = f"/tmp/llm-briefing-enriched-{DATE}.json"
OUTPUT = f"/tmp/llm-briefing-{DATE}.html"

def run(cmd, timeout=15):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout

def analyze_with_llm(readme_text, project_name):
    """用 LLM 分析 README，生成中文摘要（项目背景 + 项目亮点）"""
    if not readme_text or len(readme_text) < 50:
        return None
    
    prompt = f"""你是一个技术分析师。请分析以下 GitHub 项目的 README 内容，用简洁的中文生成项目摘要。

项目名称：{project_name}

README 内容：
{readme_text[:800]}

请严格按以下 JSON 格式返回（不要其他内容）：
{{
  "background": "1-2句话说明这个项目是什么、解决什么问题",
  "highlights": ["亮点1", "亮点2", "亮点3"]
}}

要求：
- background 要简洁，让非技术人员也能看懂
- highlights 提取 2-3 个最核心的技术亮点或特色
- 用中文"""

    # 通过 Hermes Agent 的 LLM 能力（这里用 openai API 或直接调用）
    # 由于脚本环境没有直接 LLM access，我们用简单启发式方法
    # 实际 cronjob 中 Agent 会替代这一步
    return extract_summary_heuristic(readme_text)

def extract_summary_heuristic(readme_text):
    """启发式提取：从 README 中提取关键信息"""
    lines = readme_text.split('\n')
    
    # 找第一个非标题、非 badge 的段落
    first_para = ''
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('#'): continue
        if 'shield' in line or 'badge' in line.lower() or line.startswith('['): continue
        if line.startswith('!'): continue
        first_para = line
        break
    
    # 找 features/highlights 部分
    highlights = []
    in_features = False
    for line in lines:
        line = line.strip()
        if line.lower().startswith('## feature') or line.lower().startswith('## highlight') or line.lower().startswith('## why'):
            in_features = True
            continue
        if in_features:
            if line.startswith('##') or (line.startswith('#') and not line.startswith('###')):
                break
            if line.startswith('- ') or line.startswith('* '):
                text = line[2:].strip()
                if text and len(text) > 10:
                    highlights.append(text[:100])
            if len(highlights) >= 3:
                break
    
    if first_para:
        return {
            'background': first_para[:200],
            'highlights': highlights[:3] if highlights else ['详见项目 README']
        }
    return None

def render_enriched_html(data):
    """渲染 enriched HTML"""
    gh = data.get('github', [])
    gt = data.get('github_trending', [])
    papers = data.get('papers', [])
    hn = data.get('hn', [])
    news = data.get('news', [])
    
    total = len(gh) + len(gt) + len(papers) + len(hn) + len(news)
    
    # 构建 enriched 项目的 lookup
    enriched_map = {}
    for p in data.get('enriched_projects', []):
        enriched_map[p['url']] = p
    
    html_head = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LLM & Agent Daily Briefing | {DATE}</title>
<style>
:root {{ --bg:#0a0e1a; --card:#1a2332; --card-h:#1f2b3d; --text:#e2e8f0; --text2:#94a3b8; --muted:#64748b; --blue:#3b82f6; --purple:#8b5cf6; --green:#10b981; --orange:#f59e0b; --red:#ef4444; --border:#2d3748; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; padding:0; margin:0; }}
.container {{ max-width:900px; margin:0 auto; padding:2rem 1.5rem; }}
.header {{ text-align:center; padding:2.5rem 0 1.5rem; border-bottom:1px solid var(--border); margin-bottom:2rem; }}
.header h1 {{ font-size:1.8rem; background:linear-gradient(135deg,var(--blue),var(--purple)); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom:0.3rem; }}
.header .sub {{ color:var(--text2); font-size:0.95rem; }}
.section {{ margin-bottom:2.5rem; }}
.sh {{ display:flex; align-items:center; gap:0.6rem; margin-bottom:1rem; padding-bottom:0.5rem; border-bottom:2px solid var(--border); }}
.sh .icon {{ font-size:1.3rem; }} .sh .title {{ font-size:1.15rem; font-weight:600; }}
.sh .cnt {{ background:var(--border); color:var(--text2); font-size:0.75rem; padding:0.15rem 0.5rem; border-radius:99px; margin-left:auto; }}
.sh.gh .title {{ color:var(--green); }} .sh.gh .cnt {{ background:rgba(16,185,129,0.15); color:var(--green); }}
.sh.trending .title {{ color:#f97316; }} .sh.trending .cnt {{ background:rgba(249,115,22,0.15); color:#f97316; }}
.sh.paper .title {{ color:var(--purple); }} .sh.paper .cnt {{ background:rgba(139,92,246,0.15); color:var(--purple); }}
.sh.news .title {{ color:var(--orange); }} .sh.news .cnt {{ background:rgba(245,158,11,0.15); color:var(--orange); }}
.sub-section {{ font-size:0.8rem; color:var(--muted); margin-bottom:1rem; margin-top:-0.5rem; font-style:italic; }}
.trending-card {{ border-left:3px solid #f97316; }}
.today-stars {{ color:#f97316; font-weight:600; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1rem 1.15rem; margin-bottom:0.75rem; transition:all 0.2s; }}
.card:hover {{ background:var(--card-h); border-color:var(--blue); transform:translateY(-1px); box-shadow:0 4px 12px rgba(59,130,246,0.1); }}
.card a {{ color:var(--blue); text-decoration:none; }} .card a:hover {{ text-decoration:underline; }}
.ct {{ font-weight:600; font-size:0.95rem; margin-bottom:0.3rem; }}
.cm {{ display:flex; gap:0.6rem; font-size:0.8rem; color:var(--muted); flex-wrap:wrap; }}
.cd {{ font-size:0.85rem; color:var(--text2); margin-top:0.5rem; line-height:1.45; }}
.cd.enriched {{ background:rgba(59,130,246,0.05); border:1px solid rgba(59,130,246,0.15); border-radius:6px; padding:0.75rem; margin-top:0.5rem; }}
.cd .bg {{ color:var(--text); font-weight:500; }}
.cd .hl {{ color:var(--orange); font-weight:500; }}
.cd .hl-list {{ margin:0.3rem 0 0 0; padding-left:1.2rem; }}
.cd .hl-list li {{ margin-bottom:0.2rem; color:var(--text2); }}
.stars {{ color:var(--orange); font-weight:600; }}
.lang {{ display:inline-block; padding:0.1rem 0.4rem; border-radius:4px; font-size:0.7rem; background:var(--border); color:var(--text2); }}
.pcard {{ background:var(--card); border:1px solid var(--border); border-radius:10px; padding:1rem 1.15rem; margin-bottom:0.75rem; transition:all 0.2s; }}
.pcard:hover {{ background:var(--card-h); border-color:var(--purple); transform:translateY(-1px); }}
.pt {{ font-weight:600; font-size:0.95rem; margin-bottom:0.3rem; }} .pt a {{ color:var(--purple); }}
.pm {{ display:flex; gap:0.6rem; font-size:0.75rem; color:var(--muted); margin-bottom:0.5rem; }}
.pcat {{ display:inline-block; padding:0.1rem 0.35rem; border-radius:3px; font-size:0.65rem; background:rgba(139,92,246,0.1); color:var(--purple); text-transform:uppercase; }}
.ps {{ font-size:0.85rem; color:var(--text2); line-height:1.4; }} .ps b {{ color:var(--text); font-weight:500; }}
.stag {{ display:inline-block; padding:0.12rem 0.4rem; border-radius:3px; font-size:0.7rem; font-weight:500; }}
.stag.hn {{ background:rgba(255,102,0,0.15); color:#ff6600; }} .stag.google {{ background:rgba(59,130,246,0.15); color:var(--blue); }}
.enrich-badge {{ display:inline-block; font-size:0.65rem; padding:0.1rem 0.35rem; border-radius:3px; background:rgba(16,185,129,0.15); color:#10b981; margin-left:0.5rem; font-weight:500; }}
.footer {{ text-align:center; padding:1.5rem 0; border-top:1px solid var(--border); margin-top:2rem; }}
.stats {{ display:flex; justify-content:center; gap:1.5rem; flex-wrap:wrap; margin-bottom:0.8rem; }}
.sv {{ font-size:1.3rem; font-weight:700; color:var(--blue); }} .sl {{ font-size:0.75rem; color:var(--muted); }}
.ft {{ color:var(--muted); font-size:0.8rem; }}
@media(max-width:640px) {{ .container {{ padding:1rem; }} .header h1 {{ font-size:1.4rem; }} }}
</style></head><body><div class="container">
<div class="header"><h1>📡 LLM & Agent Daily Briefing</h1><p class="sub">{DATE} <span style="color:#10b981;font-size:0.8rem;">✨ Agent 深度分析版</span></p></div>"""

    body = """
<div class="section"><div class="sh trending"><span class="icon">🔥</span><span class="title">GitHub Trending 今日热门</span><span class="cnt">""" + str(len(gt)) + """ 项</span></div><p class="sub-section">从 GitHub Trending 页面筛选出的 AI/Agent/Skill 项目</p>
"""
    for p in gt:
        td = p.get('today', '')
        l = f'<span class="lang">{p.get("lang","")}</span>' if p.get('lang') else ''
        enriched = enriched_map.get(p['url'])
        
        if enriched:
            # 使用 enriched 描述
            bg = enriched.get('background', '')
            hls = enriched.get('highlights', [])
            hl_html = ''
            if hls:
                hl_items = ''.join(f'<li>{h}</li>' for h in hls)
                hl_html = f'<ul class="hl-list">{hl_items}</ul>'
            desc_html = f"""<div class="cd enriched"><span class="bg">📋 项目背景：</span>{bg}{hl_html}<span class="enrich-badge">✨ AI 分析</span></div>"""
        else:
            d = p.get('desc', '') or '暂无描述'
            desc_html = f'<div class="cd">{d}</div>'
        
        body += f"""<div class="card trending-card"><div class="ct"><a href="{p['url']}" target="_blank">{p['name']}</a></div><div class="cm"><span class="stars">⭐ {p.get('stars','')}</span>{l}<span class="today-stars">🔥 {td}</span></div>{desc_html}</div>
"""

    body += """</div><div class="section"><div class="sh gh"><span class="icon">🔧</span><span class="title">GitHub 热门项目</span><span class="cnt">""" + str(len(gh)) + """ 项</span></div><p class="sub-section">按 Stars 排序的经典 LLM/Agent 开源项目</p>
"""
    for p in gh:
        s = f"{p['stars']:,}"
        l = f'<span class="lang">{p["lang"]}</span>' if p['lang'] else ''
        enriched = enriched_map.get(p['url'])
        
        if enriched:
            bg = enriched.get('background', '')
            hls = enriched.get('highlights', [])
            hl_html = ''
            if hls:
                hl_items = ''.join(f'<li>{h}</li>' for h in hls)
                hl_html = f'<ul class="hl-list">{hl_items}</ul>'
            desc_html = f"""<div class="cd enriched"><span class="bg">📋 项目背景：</span>{bg}{hl_html}<span class="enrich-badge">✨ AI 分析</span></div>"""
        else:
            desc_html = f'<div class="cd">{p.get("desc", "")}</div>'
        
        body += f"""<div class="card"><div class="ct"><a href="{p['url']}" target="_blank">{p['name']}</a></div><div class="cm"><span class="stars">⭐ {s}</span>{l}<span>更新于 {p['updated']}</span></div>{desc_html}</div>
"""

    body += """</div><div class="section"><div class="sh paper"><span class="icon">📄</span><span class="title">论文速读</span><span class="cnt">""" + str(len(papers)) + """ 篇</span></div>
"""
    for p in papers:
        c = ', '.join(p['cats']) if p['cats'] else ''
        ch = f'<span class="pcat">{c}</span>' if c else ''
        body += f"""<div class="pcard"><div class="pt"><a href="{p['url']}" target="_blank">{p['title']}</a></div><div class="pm"><span>{p['date']}</span>{ch}</div><div class="ps"><b>摘要：</b>{p['summary']}...</div></div>
"""

    body += """</div><div class="section"><div class="sh news"><span class="icon">📰</span><span class="title">行业动态</span><span class="cnt">""" + str(len(hn) + len(news)) + """ 条</span></div>
"""
    for item in hn[:5] + news[:5]:
        body += f"""<div class="card"><div class="ct"><a href="{item.get('url','#')}" target="_blank">{item['title']}</a></div><div class="cm"><span class="stag {item.get('cls','')}">{item['source']}</span>{f'<span>{item.get("date","")}</span>' if item.get('date') else ''}</div>{f'<div class="cd">{item.get("desc","")}</div>' if item.get('desc') else ''}</div>
"""

    enriched_count = len(data.get('enriched_projects', []))
    footer = f"""</div><div class="footer"><div class="stats"><div><div class="sv">6</div><div class="sl">扫描来源</div></div><div><div class="sv">{total}</div><div class="sl">有价值信息</div></div><div><div class="sv">{enriched_count}</div><div class="sl">AI 深度分析</div></div></div><p class="ft">由 Hermes Agent 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}</p></div></div></body></html>"""

    with open(OUTPUT, 'w') as f:
        f.write(html_head + body + footer)

if __name__ == '__main__':
    # 读 raw JSON
    try:
        with open(RAW_JSON, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到 raw JSON: {RAW_JSON}")
        print("请先运行 Phase 1: python3 scripts/run-briefing.py")
        sys.exit(1)
    
    candidates = data.get('enrich_candidates', [])
    print(f"📦 读取 raw JSON: {len(candidates)} 个项目需要补充描述")
    
    enriched_projects = []
    
    for i, p in enumerate(candidates):
        name = p.get('name', '')
        readme = p.get('readme_raw', '')
        print(f"\n[{i+1}/{len(candidates)}] 分析 {name}...")
        
        if not readme:
            print(f"  ⚠️ 无 README 内容，跳过")
            continue
        
        # 用 LLM 分析
        result = analyze_with_llm(readme, name)
        if result:
            enriched_projects.append({
                'url': p['url'],
                'name': name,
                'background': result.get('background', ''),
                'highlights': result.get('highlights', [])
            })
            print(f"  ✅ background: {result['background'][:60]}...")
            print(f"  ✅ highlights: {len(result.get('highlights', []))} 个")
        else:
            print(f"  ⚠️ 分析失败")
    
    # 保存 enriched JSON
    data['enriched_projects'] = enriched_projects
    with open(ENRICHED_JSON, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 渲染 enriched HTML
    render_enriched_html(data)
    
    print(f"\n✅ Enriched JSON: {ENRICHED_JSON}")
    print(f"✅ Enriched HTML: {OUTPUT}")
    print(f"📊 AI 深度分析: {len(enriched_projects)} 个项目")

#!/usr/bin/env python3
"""LLM & Agent Daily Briefing - Phase 2: 信息增强 + HTML 生成
读取 raw JSON，用 LLM 知识补充翻译和信息，生成最终 HTML。
"""
import json, sys, re, html as html_mod
from datetime import datetime

DATE_STR = datetime.now().strftime('%Y-%m-%d')
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
ENRICHED_JSON = f"/tmp/llm-briefing-enriched-{DATE_STR}.json"
OUTPUT_TMP = f"/tmp/llm-briefing-{DATE_STR}.html"
OUTPUT = f"/Users/zz/code/AI_Daily_Brief/docs/llm-briefing-{DATE_STR}.html"

# ── LLM 知识库：Trending 项目描述补充 ─────────────────
TRENDING_DESCS = {
    'asgeirtj/system_prompts_leaks': '收集各大 AI 模型（Claude、GPT、Gemini 等）的系统提示词泄露，通过自动化爬取获取各模型的内置 system prompt，帮助开发者了解模型的默认行为和限制。',
    'addyosmani/agent-skills': '由 Google 工程师 Addy Osmani 打造的 AI 编程代理技能库。将高级软件工程最佳实践编码为 AI Agent 可执行的技能，涵盖架构设计、代码审查、测试等全开发流程。',
    'Leonxlnx/taste-skill': 'AI Agent 的品味/审美技能框架，让 AI 代理具备一致的设计品味和风格判断能力，提升代码输出的质量和一致性。',
    'alirezarezvani/claude-skills': '为 Claude Code 设计的技能集合，包含代码生成、调试、文档编写等实用工作流，提升 Claude 在开发任务中的表现。',
    'openai/codex-plugin-cc': 'OpenAI 官方推出的 Codex 插件，为 AI 编程工具提供模型推理能力和代码生成支持，深度集成到开发者工作流中。',
    'mvanhorn/last30days-skill': 'AI Agent 的"最近 30 天"时间感知技能，让代理能够准确理解和操作相对时间范围，解决 AI 对时间概念的模糊问题。',
    'bradautomates/claude-video': '让 Claude AI 具备视频理解能力的技能工具，支持视频内容分析、摘要生成和时间戳定位等功能。',
    'steipete/CodexBar': 'macOS 菜单栏中的 AI 编程助手工具栏，提供快速的代码补全、解释和生成功能，类似 Copilot 但更轻量。',
    'sindresorhus/awesome': 'GitHub 上最著名的 Awesome List 集合，精选各技术领域的优质资源列表，是发现优质开源项目的入口。',
}

def enrich_trending(project):
    """用 LLM 知识补充 Trending 项目信息"""
    name = project['name'].replace(' / ', '/')
    desc_en = project.get('desc', '').strip()
    desc_zh = project.get('desc_zh', '')
    # 优先使用翻译管道已生成的 desc_zh（足够长说明已翻译）
    if desc_zh and len(desc_zh) > 80:
        project['desc_en'] = desc_en
        return
    if name in TRENDING_DESCS:
        project['desc_zh'] = TRENDING_DESCS[name]
        project['desc_en'] = desc_en or TRENDING_DESCS[name]
    elif desc_en:
        project['desc_zh'] = translate_with_context(desc_en, name)
        project['desc_en'] = desc_en
    else:
        project['desc_zh'] = f'今日 GitHub Trending 热门项目 — {project.get("lang","")} 语言，{project.get("stars","")} stars'
        project['desc_en'] = ''

def translate_with_context(text, project_name=''):
    """基于上下文的中文翻译"""
    translations = {
        'An agentic skills framework': '一个 AI 代理技能框架',
        'workflow automation platform': '工作流自动化平台',
        'The agent that grows with you': '与你共同成长的 AI 代理',
        'Fair-code workflow automation platform with native AI capabilities': '公平代码工作流自动化平台，内置原生 AI 能力，支持 400+ 集成',
        'An agent-managed museum exhibit': '由 AI 代理管理的博物馆展览',
        'A single CLAUDE.md file to improve Claude Code behavior': '一个 CLAUDE.md 配置文件，基于 Andrej Karpathy 对 LLM 编码陷阱的观察，优化 Claude Code 的行为表现',
        'AutoGPT is the vision of accessible AI for everyone': 'AutoGPT 致力于让每个人都能使用和构建 AI，提供工具让你专注核心业务',
        'browser-based terminal hub': '基于浏览器的终端中心：运行任何 CLI，连接任何 Agent，支持模块化 MCP、Web Components、语音输入和主题定制',
    }
    for en, zh in translations.items():
        if en.lower() in text.lower():
            return zh
    return text

# ── 论文中文翻译 ──────────────────────────────────────
PAPER_TRANSLATIONS = {
    'WorldDirector: Building Controllable World Simulators with Persistent Dynamic Memory': {
        'title_zh': 'WorldDirector：构建具有持久动态记忆的可控世界模拟器',
        'summary_zh': '提出 WorldDirector 框架，一种高度可控的视频世界模型，支持持久动态对象记忆和无限制视角探索。与现有将物理动态与像素渲染纠缠的世界模型不同，该方法实现了更长期的场景一致性。',
    },
    'LACUNA: A Testbed for Evaluating Localization Precision for LLM Unlearning': {
        'title_zh': 'LACUNA：评估大模型遗忘定位精度的测试平台',
        'summary_zh': '大语言模型会记忆敏感训练数据（如 PII），需要可靠的遗忘方法。现有方法遵循"先定位后遗忘"范式，本文提出 LACUNA 测试平台，系统评估不同定位方法的精度。',
    },
    'Program-as-Weights: A Programming Paradigm for Fuzzy Functions': {
        'title_zh': '程序即权重：模糊函数的编程范式',
        'summary_zh': '许多日常编程任务（如日志告警、JSON 修复、意图排序）难以用规则实现，通常被外包给 LLM API，牺牲了局部性和可复现性。本文提出一种新范式，将程序本身作为可学习的权重。',
    },
    'Online Safety Monitoring for LLMs': {
        'title_zh': '大语言模型的在线安全监控',
        'summary_zh': '尽管经过对齐训练，LLM 在部署时仍可能生成不安全输出。本文研究了一种简单的实时监控器，将外部验证者信号转化为告警机制，在安全性无法保证时及时发出警告。',
    },
    'ReContext: Recursive Evidence Replay as LLM Harness for Long-Context Reasoning': {
        'title_zh': 'ReContext：递归证据重放作为大模型长上下文推理工具',
        'summary_zh': '长上下文理解和推理已成为部署 LLM 的关键需求。尽管近期模型支持更长的上下文窗口，但经常无法利用输入中已有的相关证据。本文提出递归证据重放方法。',
    },
}

def enrich_paper(paper):
    """补充论文中文翻译 — 优先使用 enriched JSON 中的翻译"""
    if paper.get('title_zh') and paper.get('summary_zh'):
        return  # 已有翻译，跳过
    title = paper.get('title', '')
    if title in PAPER_TRANSLATIONS:
        t = PAPER_TRANSLATIONS[title]
        paper['title_zh'] = t['title_zh']
        paper['summary_zh'] = t['summary_zh']
    else:
        paper['title_zh'] = title
        paper['summary_zh'] = paper.get('summary', '')[:150]

# ── Blog 标题翻译 ────────────────────────────────────
BLOG_TRANSLATIONS = {
    # OpenAI
    'Introducing GeneBench-Pro': 'GeneBench-Pro 正式发布：面向计算生物学的高级基准测试',
    'Core Dump Epidemiology': '核心转储流行病学：修复一个存在 18 年的缺陷',
    'HP and the Frontier Partnership': 'HP 如何在全企业推广早期 AI 成果',
    'GeneBench-Pro 正式发布': 'GeneBench-Pro 正式发布：面向计算生物学的高级基准测试',
    '核心转储流行病学：修复一个存在 18 年的缺陷': '核心转储流行病学：数据基础设施修复 18 年缺陷',
    'HP 如何在全企业推广早期 AI 成果': 'HP 企业级 AI 推广实践：从早期成果到全员应用',
    # Anthropic
    'Interpretability': '可解释性研究：理解 AI 模型的内部工作机制',
    'Societal Impacts': '社会影响研究：AI 技术对社会的广泛影响评估',
    # HuggingFace
    '80TB+ of astronomy for the HDD-poor': '80TB+ 天文数据跨模态宇宙：从笔记本访问海量数据集',
    "Does Your LLM Know *When It's About to Be Wrong*?": '你的 LLM 知道自己即将出错吗？——元认知能力研究',
    "Does Your LLM Know *When It's About to Be Wrong*? ginigen-ai": 'LLM 元认知：模型能否预测自身错误',
    # OpenRouter
    'The OpenRouter MCP Server': 'OpenRouter MCP 服务器发布：标准化的模型上下文协议服务',
    'Introducing the Unified Image API': '统一图像 API 发布：多模型图像推理的统一接口',
    'Subagent: Let Your Model Delegate the Busywork': 'Subagent 功能上线：让模型自动委派琐碎任务',
}

def clean_blog_title(title):
    """清理 Blog 标题：去掉 Jina 黏连的日期、来源名等噪声"""
    title = re.sub(r'\s*(Jun|Jul|May|Apr|Mar|Feb|Jan|Dec|Nov|Oct|Sep|Aug)\s+\d{1,2},?\s+\d{4}\s*$', '', title)
    title = re.sub(r'\s*\d{4}年\d{1,2}月\d{1,2}日\s*$', '', title)
    title = re.sub(r'\s*[-|]\s*(Help Net Security|Techzine Global|Axios|The HIPAA Journal|The Verge|Tom\'s Guide)\s*$', '', title)
    title = re.sub(r'\s*[a-z0-9-]+\s*•\s*\d+\s*days?\s*ago\s*•\s*\d+\s*$', '', title)
    title = re.sub(r'(\S+)(研究|公司|工程|公告)(\d{4}年\d+月\d+日)', r'\1 — \3', title)
    return title.strip()

def translate_blog_title(title):
    """翻译 Blog 标题（模糊匹配）"""
    cleaned = clean_blog_title(title)
    for en, zh in BLOG_TRANSLATIONS.items():
        if en.lower() in cleaned.lower() or cleaned.lower() in en.lower():
            return zh
        en_clean = re.sub(r'[^\w\s]', '', en).lower()
        t_clean = re.sub(r'[^\w\s]', '', cleaned).lower()
        if en_clean in t_clean or t_clean in en_clean:
            return zh
    return cleaned

# ── 新闻标题翻译 ────────────────────────────────────
NEWS_TRANSLATIONS = {
    "SkillCloak Lets Malicious AI Agent Skills Evade Static Scanners with Self-Extracting Packing": "SkillCloak：恶意 AI Agent 技能通过自解压打包绕过静态扫描",
    "Omnigent: Open-source AI agent framework and meta-harness": "Omnigent：开源 AI Agent 框架与元测试平台",
    "ModelCop Launches AI Agent Security Platform, Targets $25B Machine Identity Market": "ModelCop 发布 AI Agent 安全平台，瞄准 250 亿美元机器身份市场",
    "LLM Wikis Are Over-Engineered": "LLM Wiki 过度工程化——我用纯 Python 编译器替代了它",
    "AI agent carries out ransomware attack independently": "AI Agent 独立实施勒索软件攻击",
    "This AI agent autonomously hacked a network, adapted on the fly, and demanded a ransom": "AI Agent 自主入侵网络、实时适应并索要赎金",
    "We pitted Base 44's new AI model against Anthropic's": "Base 44 新 AI 模型对比 Anthropic：谁建站更快？",
    "Bespoke Labs is building practice worlds for AI agents": "Bespoke Labs 为 AI Agent 构建训练模拟环境",
    "AI Agent - Table.Briefings": "AI Agent 简报汇总",
    "The AI Marketing Backlash": "AI 营销反噬：为什么 AI 优先品牌开始失效",
    "Regression to the Mean: on LLMs and the quiet death of the new": "均值回归：LLM 与新事物的悄然消亡",
    "Show HN: Scan your AI agents for dangerous capabilities": "Show HN：扫描你的 AI Agent 是否存在危险能力",
    "GPT-5.6 Sol Ultra will be in Codex": "GPT-5.6 Sol Ultra 将集成到 Codex",
    "Anthropic's Method to Losing Goodwill in a Few Easy Steps": "Anthropic 失去公众信任的几步曲",
    "AI Agent Conducts First Fully Autonomous Ransomware Attack": "AI Agent 实施首次全自动勒索软件攻击",
    "The HIPAA Journal": "HIPAA 期刊",
}

def translate_news_title(title):
    """翻译新闻标题（模糊匹配）"""
    cleaned = re.sub(r'\s*[-|]\s*(Help Net Security|Techzine Global|Axios|The HIPAA Journal|The Verge|Tom\'s Guide)\s*$', '', title)
    cleaned = cleaned.strip()
    for en, zh in NEWS_TRANSLATIONS.items():
        if en.lower() in cleaned.lower() or cleaned.lower() in en.lower():
            return zh
        if len(cleaned) > 20:
            sub = cleaned[:60]
            if en.lower().startswith(sub.lower()) or sub.lower().startswith(en.lower()[:60]):
                return zh
    return cleaned

# ── 读取数据（优先 enriched，降级 raw） ─────────────────
import os
json_path = ENRICHED_JSON if os.path.exists(ENRICHED_JSON) else RAW_JSON
print(f"📦 读取数据: {os.path.basename(json_path)}")
with open(json_path) as f:
    raw = json.load(f)

DATE = raw.get('date', datetime.now().strftime('%Y-%m-%d'))

# 1. 增强 Trending
print("🔥 增强 Trending 项目信息...")
for p in raw['github_trending']:
    enrich_trending(p)

# 2. 翻译 GitHub 热门项目描述
print("🔧 翻译 GitHub 热门项目描述...")
for p in raw.get('github', []):
    if not p.get('desc_zh'):
        p['desc_zh'] = translate_with_context(p.get('desc', ''), p.get('name', ''))

# 3. 翻译论文
print("📄 翻译论文...")
for p in raw['papers']:
    enrich_paper(p)

# 4. 清理 Blog 标题 — 优先使用 enriched JSON 中的翻译
print("🌐 清理 Blog 标题...")
for b in raw.get('blogs', []):
    if not b.get('title_zh'):  # 已有翻译则跳过
        b['title_zh'] = translate_blog_title(b.get('title', ''))

# 5. 翻译新闻标题 — 优先使用 enriched JSON 中的翻译
print("📰 翻译新闻标题...")
for n in raw.get('news', []):
    if not n.get('title_zh'):  # 已有翻译则跳过
        n['title_zh'] = translate_news_title(n.get('title', ''))

# ── 生成 HTML 报告 ──────────────────────────────────
print("🎨 生成 HTML 报告...")
trending = raw['github_trending']
gh = raw.get('github', [])
papers = raw['papers']
blogs = raw.get('blogs', [])
news = raw.get('news', [])

body = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LLM & Agent Daily Briefing | {DATE}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
  background: #1B2838;
  color: #e2e8f0;
  line-height: 1.6;
  min-height: 100vh;
  position: relative;
}}
body::before {{
  content: '';
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background:
    radial-gradient(ellipse 90% 50% at 50% -10%, rgba(56, 189, 248, 0.2), transparent),
    radial-gradient(ellipse 60% 40% at 90% 40%, rgba(139, 92, 246, 0.15), transparent),
    radial-gradient(ellipse 50% 60% at 5% 85%, rgba(52, 211, 153, 0.1), transparent),
    repeating-linear-gradient(0deg, transparent, transparent 49px, rgba(148, 163, 184, 0.08) 49px, rgba(148, 163, 184, 0.08) 50px),
    repeating-linear-gradient(90deg, transparent, transparent 49px, rgba(148, 163, 184, 0.08) 49px, rgba(148, 163, 184, 0.08) 50px);
  pointer-events: none;
  z-index: 0;
}}
.container {{ max-width:1080px; margin:0 auto; padding:2rem; position: relative; z-index: 1; }}
.header {{ text-align:center; margin-bottom:2.5rem; position: relative; padding-bottom:1.5rem; }}
.header::after {{
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 200px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(56, 189, 248, 0.6), rgba(139, 92, 246, 0.6), transparent);
}}
.header h1 {{
  font-size:2rem;
  font-weight: 700;
  background: linear-gradient(135deg, #38bdf8, #818cf8, #c084fc);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-bottom:0.4rem;
  letter-spacing: -0.02em;
}}
.sub {{ color:#64748b; font-size:0.9rem; font-weight: 500; letter-spacing: 0.05em; }}
.section {{
  margin-bottom:2rem;
  padding: 1.2rem;
  border-radius: 20px;
  position: relative;
  background: rgba(27, 40, 56, 0.5);
}}
.section::before {{
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  border-radius: 20px;
  padding: 1px;
  background: linear-gradient(135deg, rgba(148, 163, 184, 0.1), transparent, rgba(148, 163, 184, 0.05));
  -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask-composite: exclude;
  pointer-events: none;
}}
.sh {{
  display:flex;
  align-items:center;
  gap:0.8rem;
  margin-bottom:1rem;
  padding-bottom:0.5rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.1);
}}
.sh .icon {{ font-size:1.3rem; }}
.sh .title {{ font-size:1.2rem; font-weight:700; color:#f1f5f9; letter-spacing: -0.01em; }}
.sh.trending .title {{ color:#34d399; }}
.sh.github .title {{ color:#60a5fa; }}
.sh.paper .title {{ color:#a78bfa; }}
.sh.blog .title {{ color:#38bdf8; }}
.sh.news .title {{ color:#fb923c; }}
.cnt {{
  font-size:0.7rem;
  color:#94a3b8;
  background: rgba(148, 163, 184, 0.08);
  border: 1px solid rgba(148, 163, 184, 0.15);
  padding:0.2rem 0.6rem;
  border-radius: 20px;
  margin-left:auto;
  font-weight: 500;
  letter-spacing: 0.02em;
}}
.card {{
  background: linear-gradient(135deg, rgba(22, 35, 50, 0.9), rgba(22, 35, 50, 0.75));
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(96, 165, 250, 0.15);
  border-left: 3px solid rgba(96, 165, 250, 0.4);
  border-radius: 14px;
  padding:1.1rem 1.3rem;
  margin-bottom:0.7rem;
  transition: all 0.25s ease;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03);
  position: relative;
}}
.card:hover {{
  border-color: rgba(96, 165, 250, 0.3);
  border-left-color: #60a5fa;
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.9), rgba(30, 41, 59, 0.7));
  transform: translateX(4px);
  box-shadow: 0 4px 16px rgba(96, 165, 250, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.05);
}}
/* Section-specific card accent colors */
.section:has(.sh.trending) .card {{ border-left-color: rgba(52, 211, 153, 0.5); }}
.section:has(.sh.trending) .card:hover {{ border-left-color: #34d399; box-shadow: 0 4px 16px rgba(52, 211, 153, 0.1); }}
.section:has(.sh.paper) .card {{ border-left-color: rgba(167, 139, 250, 0.5); }}
.section:has(.sh.paper) .card:hover {{ border-left-color: #a78bfa; box-shadow: 0 4px 16px rgba(167, 139, 250, 0.1); }}

.ct {{ font-size:1rem; font-weight:600; margin-bottom:0.35rem; letter-spacing: -0.01em; }}
.ct a {{ color:#60a5fa; text-decoration:none; transition: color 0.2s; }}
.ct a:hover {{ color:#93c5fd; text-decoration:underline; }}
.cm {{ display:flex; flex-wrap:wrap; gap:0.5rem; align-items:center; font-size:0.78rem; color:#64748b; margin-bottom:0.4rem; }}
.stars {{ color:#fbbf24; font-weight:600; }}
.lang {{
  background: rgba(56, 189, 248, 0.1);
  color:#38bdf8;
  padding:0.12rem 0.5rem;
  border-radius: 10px;
  font-size:0.72rem;
  font-weight: 500;
  border: 1px solid rgba(56, 189, 248, 0.15);
}}
.topic {{
  background: rgba(167, 139, 250, 0.1);
  color:#a78bfa;
  padding:0.12rem 0.45rem;
  border-radius: 10px;
  font-size:0.68rem;
  font-weight: 500;
  border: 1px solid rgba(167, 139, 250, 0.15);
}}
.cd {{ color:#cbd5e1; font-size:0.88rem; margin-top:0.4rem; line-height: 1.65; }}
.releases-section {{ margin-top:0.8rem; display:flex; flex-direction:column; gap:0.5rem; }}
.release-item {{
  background: rgba(34, 197, 94, 0.04);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: 10px;
  padding:0.6rem 0.8rem;
  transition: all 0.2s ease;
}}
.release-item:hover {{
  background: rgba(34, 197, 94, 0.08);
  border-color: rgba(34, 197, 94, 0.3);
}}
.release-tag {{ color:#22c55e; font-weight:600; font-size:0.82rem; margin-right:0.5rem; }}
.release-date {{ color:#475569; font-size:0.72rem; }}
.release-summary {{ color:#94a3b8; font-size:0.78rem; margin-top:0.25rem; line-height:1.5; }}
.blog-card {{
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.6));
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(56, 189, 248, 0.12);
  border-left: 3px solid rgba(56, 189, 248, 0.4);
  border-radius: 12px;
  padding:0.8rem 1.2rem;
  margin-bottom:0.6rem;
  transition: all 0.25s ease;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}}
.blog-card:hover {{
  border-color: rgba(56, 189, 248, 0.3);
  border-left-color: #38bdf8;
  transform: translateX(4px);
  box-shadow: 0 4px 12px rgba(56, 189, 248, 0.08);
}}
.blog-src {{
  display:inline-block;
  font-size:0.68rem;
  color:#38bdf8;
  background: rgba(56, 189, 248, 0.08);
  border: 1px solid rgba(56, 189, 248, 0.15);
  padding:0.12rem 0.45rem;
  border-radius: 8px;
  margin-right:0.4rem;
  font-weight: 500;
  letter-spacing: 0.02em;
}}
.blog-title {{ color:#60a5fa; font-size:0.92rem; font-weight:500; text-decoration:none; }}
.blog-title:hover {{ color:#93c5fd; text-decoration:underline; }}
.blog-date {{ color:#475569; font-size:0.72rem; margin-left:0.4rem; }}
.blog-summary {{ color:#94a3b8; font-size:0.83rem; margin-top:0.35rem; line-height: 1.5; }}
.news-card {{
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.6));
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(251, 146, 60, 0.12);
  border-left: 3px solid rgba(251, 146, 60, 0.4);
  border-radius: 12px;
  padding:0.8rem 1.2rem;
  margin-bottom:0.6rem;
  transition: all 0.25s ease;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}}
.news-card:hover {{
  border-color: rgba(251, 146, 60, 0.3);
  border-left-color: #fb923c;
  transform: translateX(4px);
  box-shadow: 0 4px 12px rgba(251, 146, 60, 0.08);
}}
.news-src {{
  display:inline-block;
  font-size:0.68rem;
  color:#fb923c;
  background: rgba(251, 146, 60, 0.08);
  border: 1px solid rgba(251, 146, 60, 0.15);
  padding:0.12rem 0.45rem;
  border-radius: 8px;
  margin-right:0.4rem;
  font-weight: 500;
  letter-spacing: 0.02em;
}}
.news-title {{ color:#fbbf24; font-size:0.92rem; font-weight:500; text-decoration:none; }}
.news-title:hover {{ color:#fcd34d; text-decoration:underline; }}
.news-date {{ color:#475569; font-size:0.72rem; margin-left:0.4rem; }}
.news-summary {{ color:#94a3b8; font-size:0.83rem; margin-top:0.35rem; line-height: 1.5; }}
.stats {{
  display:flex;
  justify-content:center;
  gap:2.5rem;
  margin-top:2rem;
  padding-top:1.2rem;
  border-top: 1px solid rgba(148, 163, 184, 0.1);
}}
.sv {{ font-size:1.3rem; font-weight:700; background: linear-gradient(135deg, #60a5fa, #a78bfa); -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent; }}
.sl {{ font-size:0.72rem; color:#64748b; margin-top:0.15rem; letter-spacing: 0.02em; }}
.ft {{ color:#475569; font-size:0.78rem; text-align:center; margin-top:1.2rem; letter-spacing: 0.02em; }}
@media(max-width:640px) {{
  .container {{ padding:1rem; }}
  .header h1 {{ font-size:1.5rem; }}
  .card {{ padding:1rem 1.1rem; }}
  .section {{ padding: 1rem 0.8rem; }}
}}
</style></head><body><div class="container">
<div class="header"><h1>📡 LLM & Agent Daily Briefing</h1><p class="sub">{DATE}</p></div>"""

# 1. GitHub Trending
body += f"""</div><div class="section"><div class="sh trending"><span class="icon">🔥</span><span class="title">GitHub Trending 今日热门</span><span class="cnt">{len(trending)} 条</span></div>"""
for p in trending:
    s = f"{p.get('stars','')}"
    t = p.get('today','')
    l = f'<span class="lang">{p["lang"]}</span>' if p.get('lang') else ''
    d = p.get('desc_zh', '') or p.get('desc', '') or ''
    body += f"""
<div class="card">
  <div class="ct"><a href="{p.get('url','')}" target="_blank">{p['name']}</a></div>
  <div class="cm"><span class="stars">⭐ {s}</span>{l}{t}</div>
  <div class="cd">{d}</div>
</div>"""

# 2. GitHub 热门项目
gh_strategy = raw.get('github_strategy', {})
strategy_label = gh_strategy.get('label', '')
strategy_query = gh_strategy.get('query', '')
strategy_filters = gh_strategy.get('filters', '')
strategy_sort = gh_strategy.get('sort', 'stars')

# 构建策略显示文本
parts = []
if strategy_label:
    parts.append(f"📅 {strategy_label}")
if strategy_filters:
    parts.append(f"🔍 {strategy_filters}")
if strategy_query:
    parts.append(f"🔑 {strategy_query}")
strategy_info = " | ".join(parts) if parts else "按 Stars 排序的 LLM/Agent 开源项目"

body += f"""</div><div class="section"><div class="sh github"><span class="icon">🚀</span><span class="title">GitHub 热门项目</span><span class="cnt">{len(gh)} 项</span></div>
<p style="color:#64748b;font-size:0.85rem;margin-bottom:0.8rem;line-height:1.5">{strategy_info}</p>"""
for p in gh:
    s = f"{p['stars']:,}"
    l = f'<span class="lang">{p["lang"]}</span>' if p.get('lang') else ''
    topics = ''.join(f'<span class="topic">{t}</span>' for t in p.get('topics', [])[:3])
    d = p.get('desc_zh', '') or p.get('desc', '') or ''
    # Releases 展示 — 支持 release_highlights_zh（子 Agent 生成的中文改动说明）
    releases_html = ''
    releases = p.get('releases', [])
    if releases:
        rel_items = []
        for r in releases:
            tag_name = r.get('name', r.get('tag', ''))
            date = r.get('date', '')
            # 优先用子 Agent 生成的中文 highlights
            highlights = r.get('release_highlights_zh', '')
            # 其次用 raw 的 summary（英文提取的 changelog 标题）
            summary = r.get('summary', '')
            
            if highlights:
                # 子 Agent 生成的中文描述：每个 highlight 一行
                if isinstance(highlights, list):
                    highlights_html = ''.join(
                        f'<div style="color:rgba(255,255,255,0.75);font-size:0.78rem;margin-top:0.2rem;padding-left:0.5rem;border-left:2px solid rgba(34,197,94,0.3)">• {h.get("summary_zh", h) if isinstance(h, dict) else h}</div>'
                        for h in highlights[:5]
                    )
                else:
                    highlights_html = f'<div style="color:rgba(255,255,255,0.75);font-size:0.78rem;margin-top:0.2rem;line-height:1.5">{highlights}</div>'
                rel_items.append(f'<div class="release-item"><div><span class="release-tag">🏷️ {tag_name}</span><span class="release-date">{date}</span></div>{highlights_html}</div>')
            elif summary:
                # raw summary：英文 changelog 标题，用 ；连接
                rel_items.append(f'<div class="release-item"><span class="release-tag">🏷️ {tag_name}</span><span class="release-date">{date}</span><div class="release-summary">{summary}</div></div>')
            else:
                rel_items.append(f'<div class="release-item"><span class="release-tag">🏷️ {tag_name}</span><span class="release-date">{date}</span><div style="color:rgba(255,255,255,0.4);font-size:0.75rem;margin-top:0.2rem">暂无更新说明</div></div>')
        releases_html = '<div class="releases-section">' + ''.join(rel_items) + '</div>'
    body += f"""
<div class="card">
  <div class="ct"><a href="{p['url']}" target="_blank">{p['name']}</a></div>
  <div class="cm"><span class="stars">⭐ {s}</span>{l}{topics}<span>更新于 {p['updated']}</span></div>
  <div class="cd">{d}</div>
  {releases_html}
</div>"""

# 3. 论文速读
body += f"""</div><div class="section"><div class="sh paper"><span class="icon">📄</span><span class="title">论文速读</span><span class="cnt">{len(papers)} 篇</span></div>"""
for p in papers:
    c = ', '.join(p['cats']) if p.get('cats') else ''
    body += f"""
<div class="card">
  <div class="ct"><a href="{p['url']}" target="_blank">{p.get('title_zh', p['title'])}</a></div>
  <div class="cm">{p.get('date','')} · {c}</div>
  <div class="cd"><b>摘要：</b>{p.get('summary_zh', '')}</div>
</div>"""

# 4. 官方动态
body += f"""</div><div class="section"><div class="sh blog"><span class="icon">📢</span><span class="title">官方动态</span><span class="cnt">{len(blogs)} 条</span></div>"""
for b in blogs:
    src = b.get('source', '')
    src_cls = src.lower().replace(' ', '-')
    title_zh = b.get('title_zh', b.get('title', ''))
    summary = b.get('summary_zh', '') or b.get('page_content', '')[:200]
    body += f"""
<div class="blog-card">
  <div><span class="blog-src">{src}</span><a class="blog-title" href="{b.get('url','')}" target="_blank">{title_zh}</a><span class="blog-date">{b.get('date','')}</span></div>
  {"<div class='blog-summary'>摘要：" + summary + "</div>" if summary else ""}
</div>"""

# 5. 行业动态
body += f"""</div><div class="section"><div class="sh news"><span class="icon">🏭</span><span class="title">行业动态</span><span class="cnt">{len(news)} 条</span></div>"""
for n in news:
    src = n.get('source', 'Google News')
    title_zh = n.get('title_zh', n.get('title', ''))
    summary = n.get('summary_zh', '') or n.get('desc', '')[:150] or n.get('page_content', '')[:200]
    body += f"""
<div class="news-card">
  <div><span class="news-src">{src}</span><a class="news-title" href="{n.get('url','')}" target="_blank">{title_zh}</a><span class="news-date">{n.get('date','')}</span></div>
  {"<div class='news-summary'>摘要：" + summary + "</div>" if summary else ""}
</div>"""

# 底部统计
total_items = len(trending) + len(gh) + len(papers) + len(blogs) + len(news)
body += f"""</div>
<div class="stats">
  <div><div class="sv">{total_items}</div><div class="sl">信息条数</div></div>
  <div><div class="sv">{len(gh)}</div><div class="sl">GitHub 项目</div></div>
  <div><div class="sv">{len(trending)}</div><div class="sl">Trending</div></div>
  <div><div class="sv">{len(blogs)}</div><div class="sl">官方动态</div></div>
</div>
<div class="ft">由 Hermes Agent 自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div></body></html>"""

with open(OUTPUT_TMP, 'w') as f:
    f.write(body)

# 复制到 docs 目录
import shutil, os
try:
    shutil.copy(OUTPUT_TMP, OUTPUT)
    print(f"✅ 报告已生成: {OUTPUT}")
except Exception as e:
    print(f"⚠️ 复制到 docs 目录失败，文件仍在: {OUTPUT_TMP}")

print(f"📊 Trending:{len(trending)} GitHub:{len(gh)} 论文:{len(papers)} Blog:{len(blogs)} News:{len(news)}")

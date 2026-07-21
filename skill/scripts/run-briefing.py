#!/usr/bin/env python3
"""LLM & Agent Daily Briefing - 数据采集（Phase 1）
只负责采集原始数据，保存为 JSON。翻译和信息增强交给 LLM。

新增能力：
- GitHub 热门项目的 releases 抓取（最近 3 个版本的 changelog）
- Blog 正文内容抓取（供 LLM 生成中文摘要）
- 新闻正文内容抓取（供 LLM 生成中文摘要）
"""
import json, subprocess, re, html as html_mod, base64, time, os
from datetime import datetime

PROXY = "http://127.0.0.1:6789"
REPORT_DATE = os.environ.get('BRIEF_DATE')
REPORT_DATETIME = datetime.strptime(REPORT_DATE, '%Y-%m-%d') if REPORT_DATE else datetime.now()
DATE_STR = REPORT_DATETIME.strftime('%Y-%m-%d')
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"

def run(cmd, timeout=15):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return r.stdout

def cdp_navigate(url):
    out = run(f"curl -s -X POST --data-raw '{url}' http://localhost:3456/new", timeout=10)
    try: return json.loads(out).get('targetId', '')
    except: return ''

def cdp_eval(target_id, expression, timeout=15):
    """CDP 执行 JS 表达式，expression 中的换行符会替换为空格避免 shell 问题"""
    expr = expression.replace('\n', ' ').replace('\r', '')
    # 用临时文件传递 expression 避免 shell 引号问题
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
        f.write(expr)
        f.flush()
        out = run(f"curl -s -X POST 'http://localhost:3456/eval?target={target_id}' --data-binary @{f.name}", timeout=timeout)
    try:
        r = json.loads(out)
        val = r.get('value', '')
        return json.loads(val)
    except: return ''

def cdp_close(target_id):
    run(f"curl -s 'http://localhost:3456/close?target={target_id}'", timeout=5)

def gh_run(cmd, timeout=15):
    """执行 gh CLI 命令，自动设置代理环境变量"""
    env = os.environ.copy()
    env['HTTPS_PROXY'] = PROXY
    env['https_proxy'] = PROXY
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
    return r.stdout

def curl_api_get(url, timeout=15):
    """GitHub CLI 认证可能失效；失败时回退到未认证 REST API。"""
    try:
        out = run(f'curl -s --connect-timeout 10 -m {timeout} -x {PROXY} "{url}"', timeout=timeout + 5)
        if not out or len(out) < 10:
            return {}
        data = json.loads(out)
        if isinstance(data, dict) and data.get('message') and 'rate limit' in data['message'].lower():
            return {}
        return data
    except Exception:
        return {}

def gh_api_search_repos(query, filters, sort, per_page=15):
    """使用 gh CLI 调用 GitHub Search API（已认证，5000 req/h）"""
    import time as _time
    from urllib.parse import quote
    
    # 构建查询字符串
    if filters:
        raw_q = f'{query} {filters}'
    else:
        raw_q = query
    
    for attempt in range(3):
        try:
            out = gh_run(
                f'gh api "search/repositories?q={raw_q.replace(" ", "+")}&sort={sort}&order=desc&per_page={per_page}"',
                timeout=15
            )
            if not out or len(out) < 10:
                if attempt < 2:
                    _time.sleep(2)
                    continue
                return {}
            data = json.loads(out)
            if isinstance(data, dict) and data.get('items') is not None:
                return data
        except Exception as e:
            if attempt < 2:
                _time.sleep(2)
                continue
            break

    # gh token 失效时使用未认证 REST API 回退；每日采集请求量低于 60/h 限额。
    q_encoded = quote(raw_q)
    url = f'https://api.github.com/search/repositories?q={q_encoded}&sort={sort}&order=desc&per_page={per_page}'
    data = curl_api_get(url, timeout=15)
    return data if isinstance(data, dict) else {}

def gh_api_get(endpoint, timeout=10):
    """使用 gh CLI 调用 GitHub API 任意端点"""
    try:
        out = gh_run(f'gh api "{endpoint}"', timeout=timeout)
        if not out or len(out) < 10:
            raise ValueError("empty gh output")
        return json.loads(out)
    except:
        data = curl_api_get(f'https://api.github.com/{endpoint}', timeout=timeout)
        return data

def clean_release_body(body):
    """清理 release body，返回可用于提取的纯文本"""
    body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
    body = re.sub(r'\[([^\]]*?)\]\(https?://.*?\)', r'\1', body)
    body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
    return body

def extract_highlights(body, max_items=4):
    """从 release body 中提取 highlights（支持多种格式）"""
    lines = [l.strip() for l in body.split('\n') if l.strip()]
    summary_parts = []
    in_section = False

    for line in lines:
        # 检测关键区域（支持 ## ✨ Highlights、### Bug Fixes、## Features 等）
        if line.startswith('##') or line.startswith('###'):
            lower = line.lower()
            keywords = ['highlight', 'changes', 'what', 'new', 'feature', 'bug fix', 'fix', 'improvement', 'breaking']
            if any(kw in lower for kw in keywords):
                in_section = True
                continue
            elif in_section and not any(kw in lower for kw in keywords):
                # 遇到下一个非关键区域标题时停止
                if line.startswith('##'):
                    in_section = False
                continue

        if not in_section:
            continue

        # 跳过 HTML 内容（n8n 的 stage-review badge 等）
        if line.startswith('<') or line.startswith('<!--'):
            continue

        if line.startswith('- ') or line.startswith('* '):
            clean = line[2:].strip()
            # 去掉感谢信息
            clean = re.sub(r'\s*Thanks?[\s,]*@.*$', '', clean)
            # 去掉 PR 编号和 commit hash
            clean = re.sub(r'\s*\(#[\d]+\)\s*', ' ', clean)
            clean = re.sub(r'\s*by\s+@\S+', '', clean)
            clean = re.sub(r'\s*\([a-f0-9]{7,}\)\s*', ' ', clean)
            # 清理 markdown 格式
            clean = re.sub(r'\*\*(.+?)\*\*', r'\1', clean)
            clean = re.sub(r'`([^`]+)`', r'\1', clean)
            clean = clean.strip('[]')
            # 去掉 scope 前缀（如 core:、ai:，markdown 已清理）
            clean = re.sub(r'^[\w\-]+:\s*', '', clean)

            # 处理 **标题** — 描述 格式
            if ' — ' in clean:
                title_part = clean.split(' — ')[0].strip()
                if title_part and len(title_part) < 80:
                    summary_parts.append(title_part)
            elif ':' in clean and len(clean.split(':')[0]) < 40:
                title_part = clean.split(':')[0].strip()
                if title_part and len(title_part) < 60:
                    summary_parts.append(title_part)
            elif clean and len(clean) < 80 and not clean.startswith('-'):
                summary_parts.append(clean)
            elif clean and len(clean) >= 80:
                # 长描述也保留，但截断
                summary_parts.append(clean[:100])

            if len(summary_parts) >= max_items:
                break

    return summary_parts

def fetch_releases(repo_owner, repo_name, limit=3):
    """获取 GitHub 仓库最近 N 个 release（带 changelog 摘要）— 使用 gh CLI"""
    import re
    data = gh_api_get(f'repos/{repo_owner}/{repo_name}/releases?per_page={limit}')

    if isinstance(data, list) and len(data) > 0:
        releases = []
        for r in data[:limit]:
            body = r.get('body') or ''
            clean_body = clean_release_body(body)

            # 尝试提取 highlights
            summary_parts = extract_highlights(clean_body)

            # 如果没有 highlights，提取前几个有意义的段落
            if not summary_parts and clean_body:
                # 去掉标题行，取前几个非空段落
                paragraphs = []
                for line in clean_body.split('\n'):
                    line = line.strip()
                    if not line or line.startswith('#') or line.startswith('---'):
                        continue
                    # 去掉纯 markdown 符号行
                    if line in ('---', '***'):
                        continue
                    # 清理后保留
                    clean = re.sub(r'\*\*(.+?)\*\*', r'\1', line)
                    clean = re.sub(r'`([^`]+)`', r'\1', clean)
                    if clean and len(clean) > 10:
                        paragraphs.append(clean[:120])
                        if len(paragraphs) >= 3:
                            break
                summary_parts = paragraphs[:3]

            summary = '；'.join(summary_parts)[:250] if summary_parts else ''
            releases.append({
                'tag': r.get('tag_name', ''),
                'name': r.get('name', '') or r.get('tag_name', ''),
                'date': r.get('published_at', '')[:10],
                'summary': summary,
            })
        return releases

    return []

# ── 已报道项目追踪 ─────────────────────────────────
SEEN_REPOS_FILE = "/tmp/llm-briefing-seen-repos.json"

def load_seen_repos():
    """加载已报道项目历史记录"""
    if os.path.exists(SEEN_REPOS_FILE):
        try:
            with open(SEEN_REPOS_FILE) as f:
                return json.load(f)
        except:
            return {}
    return {}

def should_report_repo(name, seen_repos, item):
    """判断是否应该报道这个项目
    - 从未报道过：报道
    - 已报道但有新 release：报道（标记为 updated）
    - 已报道但最近更新了（pushed 晚于 last_seen）：报道（标记为 updated）
    """
    if name not in seen_repos:
        return True, "new"
    
    info = seen_repos[name]
    last_seen = info.get('last_seen', '')
    last_tags = set(info.get('last_release_tags', []))
    last_updated = info.get('last_updated', '')
    
    # 检查是否有新 release
    new_tags = set()
    for r in (item.get('releases') or []):
        tag = r.get('tag', '')
        if tag and tag not in last_tags:
            new_tags.add(tag)
    
    if new_tags:
        return True, f"updated (新 release: {', '.join(new_tags)})"
    
    # 检查是否有新的 push
    current_updated = item.get('updated', '')
    if current_updated and current_updated > last_updated:
        return True, f"updated (新活跃: {current_updated})"
    
    return False, "already seen"

def update_seen_repos(seen_repos, repos_to_update):
    """更新已报道项目记录"""
    for repo in repos_to_update:
        name = repo['name']
        if name not in seen_repos:
            seen_repos[name] = {'report_count': 0}
        seen_repos[name]['report_count'] += 1
        seen_repos[name]['last_seen'] = DATE_STR
        seen_repos[name]['last_updated'] = repo.get('updated', '')
        # 记录 release tags
        tags = [r.get('tag', '') for r in repo.get('releases', []) if r.get('tag')]
        if tags:
            seen_repos[name]['last_release_tags'] = tags
    with open(SEEN_REPOS_FILE, 'w') as f:
        json.dump(seen_repos, f, ensure_ascii=False, indent=2)
    print(f"  📋 已报道项目记录已更新 ({len(seen_repos)} 个项目)")

def fetch_project_details_jina(repo_name, timeout=20):
    """用 Jina 抓取 GitHub 项目页，获取完整 README 内容"""
    try:
        url = f'https://github.com/{repo_name}'
        out = run(f'curl -s --connect-timeout 10 -m {timeout} -x {PROXY} "https://r.jina.ai/{url}"', timeout=timeout + 5)
        if out and len(out) > 200:
            # 提取 Title 行的项目描述
            title_match = re.search(r'Title: GitHub - .+?: (.+)', out)
            desc_from_title = title_match.group(1).strip() if title_match else ''
            
            # 提取 Markdown Content 后的有效内容（去掉开头的 badge 和图片行）
            content_match = re.search(r'Markdown Content:\n(.+)', out, re.DOTALL)
            if content_match:
                md_content = content_match.group(1)
                # 去掉前 50 行中的纯图片/badge 行，找到第一个有意义的文本行作为描述补充
                lines = md_content.split('\n')
                meaningful_lines = []
                for line in lines[:60]:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith('![Image') or line.startswith('[') and 'camo.githubusercontent' in line:
                        continue
                    if line.startswith('http') and 'badge' in line.lower():
                        continue
                    meaningful_lines.append(line)
                    if len(meaningful_lines) >= 15:
                        break
                
                # 从有意义的内容中提取描述（通常是第一个非 badge 段落）
                desc_from_content = ''
                for line in meaningful_lines[:5]:
                    if line and not line.startswith('#') and len(line) > 20:
                        desc_from_content = line[:200]
                        break
                
                # 拼接描述
                if desc_from_title and desc_from_content:
                    full_desc = f"{desc_from_title}\n{desc_from_content}"
                elif desc_from_title:
                    full_desc = desc_from_title
                elif desc_from_content:
                    full_desc = desc_from_content
                else:
                    full_desc = ''
                
                return {
                    'desc': full_desc[:500],
                    'page_content': '\n'.join(meaningful_lines[:20])[:2000],
                }
    except Exception as e:
        print(f"    ⚠️ Jina 抓取失败: {e}")
    return None

def fetch_page_content_jina(url, timeout=20):
    """用 Jina Reader API 抓取页面正文内容（返回 Markdown）"""
    try:
        out = run(f'curl -s --connect-timeout 8 -x {PROXY} "https://r.jina.ai/{url}"', timeout=timeout)
        if out and len(out) > 100:
            lines = out.split('\n')
            in_content = False
            content_lines = []
            for line in lines:
                if line.startswith('Markdown Content:'):
                    in_content = True
                    continue
                if in_content:
                    content_lines.append(line)
                    if len(content_lines) >= 15:
                        break
            content = '\n'.join(content_lines).strip()
            if len(content) > 50:
                return content
        return ''
    except Exception:
        return ''

# ── 动态搜索策略 ─────────────────────────────────────
def get_daily_search_strategy():
    """根据星期几轮换搜索策略，避免每天都是同样的项目"""
    from datetime import timedelta
    today = REPORT_DATETIME
    day = today.weekday()  # 0=周一, 6=周日
    
    # 动态日期计算
    d30 = (today - timedelta(days=30)).strftime('%Y-%m-%d')
    d14 = (today - timedelta(days=14)).strftime('%Y-%m-%d')
    d7 = (today - timedelta(days=7)).strftime('%Y-%m-%d')
    d3 = (today - timedelta(days=3)).strftime('%Y-%m-%d')
    d1 = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    
    strategies = [
        # 周一：热门新势力（近 30 天有 push，按 stars）
        {
            'query': 'LLM OR AI agent OR MCP OR RAG',
            'filters': f'pushed:>{d30}',
            'sort': 'stars',
            'label': '热门新势力（近 30 天活跃）'
        },
        # 周二：新创建项目（近 7 天）
        {
            'query': 'AI agent OR autonomous OR workflow automation',
            'filters': f'created:>{d7}',
            'sort': 'stars',
            'label': '新创建项目（近 7 天）'
        },
        # 周三：中型潜力股（stars 500-50000）
        {
            'query': 'agent OR "AI tool" OR coding assistant',
            'filters': 'stars:500..50000',
            'sort': 'stars',
            'label': '中型潜力股（500-50K stars）'
        },
        # 周四：新兴话题（MCP/embedding/vector）
        {
            'query': 'MCP OR embedding OR "vector database" OR "AI framework"',
            'filters': f'pushed:>{d14}',
            'sort': 'stars',
            'label': '新兴话题（MCP/Vector/Embedding）'
        },
        # 周五：最近更新活跃
        {
            'query': 'LLM OR AI agent OR machine learning',
            'filters': f'pushed:>{d3}',
            'sort': 'updated',
            'label': '最近活跃（近 3 天 push）'
        },
        # 周六：AI 工具生态
        {
            'query': 'AI plugin OR agent skill OR prompt engineering',
            'filters': 'stars:100..20000',
            'sort': 'stars',
            'label': 'AI 工具生态（插件/技能）'
        },
        # 周日：按 stars 排序的经典搜索
        {
            'query': 'LLM OR AI agent OR "large language model"',
            'filters': f'pushed:>{d30}',
            'sort': 'stars',
            'label': '经典热门（近 30 天活跃）'
        },
    ]
    
    return strategies[day]

def github_search_with_retry(query, filters, sort, per_page=8, retries=2):
    """GitHub Search API 请求，带重试"""
    import time as _time
    from urllib.parse import quote
    
    # 正确 URL 编码查询字符串
    if filters:
        raw_q = f'{query} {filters}'
    else:
        raw_q = query
    q_encoded = quote(raw_q)
    
    for attempt in range(retries + 1):
        try:
            # 先试直连，失败则走代理
            url = f'https://api.github.com/search/repositories?q={q_encoded}&sort={sort}&order=desc&per_page={per_page}'
            out = run(f'curl -s --connect-timeout 5 -m 10 "{url}"')
            if not out or len(out) < 10:
                # 直连失败，走代理
                out = run(f'curl -s --connect-timeout 10 -m 15 -x {PROXY} "{url}"')
            if not out:
                if attempt < retries:
                    _time.sleep(3)
                    continue
                return {}
            data = json.loads(out)
            if isinstance(data, dict):
                if data.get('message') and 'rate limit' in data['message'].lower():
                    if attempt < retries:
                        wait = 3 * (attempt + 1)
                        print(f"    ⏳ GitHub API 限速，{wait}s 后重试...")
                        _time.sleep(wait)
                        continue
                    return {}
                return data
            elif isinstance(data, list):
                # API 限速返回了 list
                if attempt < retries:
                    _time.sleep(3)
                    continue
                return {}
        except:
            if attempt < retries:
                _time.sleep(2)
                continue
    return {}

# ── 初始化结果 ────────────────────────────────────────
results = {'github': [], 'github_trending': [], 'papers': [], 'hn': [], 'news': [], 'blogs': []}
seen_repos = load_seen_repos()  # 提前加载已报道项目记录

# ── 1. GitHub Trending ────────────────────────────
print("🔥 GitHub Trending...")
try:
    # Jina 抓取 Trending 页面（不需要 CDP，返回结构化 Markdown）
    out = run(f'curl -s --connect-timeout 10 -m 30 -x {PROXY} "https://r.jina.ai/https://github.com/trending"', timeout=35)
    if out and 'Trending' in out:
        # 解析 Jina 返回的 Markdown
        lines = out.split('\n')
        projects = []
        current = {}
        for line in lines:
            line = line.strip()
            # 匹配项目标题: ## [owner/name](url)
            m = re.match(r'## \[(.+?)\]\((.+?)\)', line)
            if m:
                if current.get('name'):
                    projects.append(current)
                repo_name = re.sub(r'\s*/\s*', '/', m.group(1)).strip()
                current = {'name': repo_name, 'url': m.group(2), 'desc': ''}
                continue
            # 匹配描述行（标题下一行，通常是纯文本描述）
            if current.get('name') and not current.get('desc') and line and not line.startswith('##') and not line.startswith('['):
                # 排除包含 Built by / stars / forks 的行
                if 'Built by' not in line and 'stars' not in line and '[' not in line:
                    current['desc'] = line
                    continue
            # 匹配语言/stars/today 信息
            if current.get('name') and ('Built by' in line or 'stars' in line or 'today' in line.lower()):
                # 提取语言
                lang_match = re.match(r'^([A-Za-z0-9\s\+\#\.-]+?)\[', line)
                if lang_match:
                    current['lang'] = lang_match.group(1).strip()
                # 提取总 stars
                stars_match = re.search(r'\[(\d[\d,]*)\]', line)
                if stars_match:
                    current['stars'] = stars_match.group(1)
                # 提取今日 stars
                today_match = re.search(r'(\d[\d,]*)\s+stars\s+today', line, re.IGNORECASE)
                if today_match:
                    current['today'] = today_match.group(1) + ' stars today'
        if current.get('name'):
            projects.append(current)

        # 全部保留，让 LLM 子 Agent 自行判断
        results['github_trending'] = projects
        print(f"  ✅ {len(results['github_trending'])} 个项目（全部保留，由 LLM 筛选）")
except Exception as e:
    print(f"  ⚠️ Trending 抓取失败: {e}")

# Jina 偶发超时或返回非 Markdown 时，直接读取 GitHub 页面作为备用源，
# 避免把采集失败误当成“今天没有 Trending 项目”。
if not results['github_trending']:
    try:
        trending_html = run(
            f'curl -sL --connect-timeout 10 -m 30 -x {PROXY} "https://github.com/trending"',
            timeout=35,
        )
        articles = re.findall(
            r'<article\b(?=[^>]*class="[^"]*Box-row)[^>]*>(.*?)</article>',
            trending_html,
            re.DOTALL,
        )
        if not articles:
            articles = re.split(r'<h2 class="h3 lh-condensed">', trending_html)[1:]
        projects = []
        for article in articles:
            repo = re.search(r'href="/([^"?#]+/[^"?#]+)"', article)
            if not repo:
                continue
            name = repo.group(1).strip('/')
            if '/' not in name or name in {p.get('name') for p in projects}:
                continue
            desc = ''
            desc_match = re.search(r'<p[^>]*>(.*?)</p>', article, re.DOTALL)
            if desc_match:
                desc = html_mod.unescape(re.sub(r'<[^>]+>', ' ', desc_match.group(1))).strip()
                desc = re.sub(r'\s+', ' ', desc)
            language = ''
            lang_match = re.search(r'itemprop="programmingLanguage"[^>]*>(.*?)</span>', article, re.DOTALL)
            if lang_match:
                language = html_mod.unescape(re.sub(r'<[^>]+>', '', lang_match.group(1))).strip()
            stars = re.search(r'([\d,]+)\s+stars\s+today', html_mod.unescape(re.sub(r'<[^>]+>', ' ', article)), re.I)
            projects.append({
                'name': name,
                'url': f'https://github.com/{name}',
                'desc': desc,
                'lang': language,
                'today': f'{stars.group(1)} stars today' if stars else '',
            })
        results['github_trending'] = projects
        print(f"  ↪️ Jina 无有效结果，GitHub 页面备用源补齐 {len(projects)} 个项目")
    except Exception as e:
        print(f"  ⚠️ Trending 备用源失败: {e}")
print(f"  ✅ {len(results['github_trending'])} 个项目")

# ── 1.5 用 Jina 补充 Trending 项目详情 ────────────
if results.get('github_trending'):
    print("  🔍 用 Jina 补充 Trending 项目详情...")
    for p in results['github_trending'][:10]:  # 只抓前 10 个，控制时间
        try:
            repo_name = p['name']
            details = fetch_project_details_jina(repo_name, timeout=15)
            if details and details.get('page_content'):
                p['page_content'] = details['page_content'][:500]
                print(f"    ✅ {repo_name}: {len(details['page_content'])} chars")
            else:
                print(f"    ⚠️ {repo_name}: 无额外内容")
        except Exception as e:
            print(f"    ⚠️ {p.get('name', '?')}: {e}")
    print("  ✅ Trending 详情补充完成")


# ── 2. GitHub 热门项目（动态搜索 + 已报道项目过滤）──
print("🔧 GitHub 热门项目...")
strategy = get_daily_search_strategy()
print(f"  📅 今日策略: {strategy['label']}")
print(f"     关键词: {strategy['query']}")
if strategy['filters']:
    print(f"     过滤: {strategy['filters']}")

MIN_GITHUB_ITEMS = 10  # 保底至少 10 个项目
seen_names = set()  # 本轮去重
github_query_used = strategy['query']
github_filters_used = strategy['filters']
github_sort_used = strategy['sort']

def collect_github_items(query, filters, sort, label=""):
    """搜索并过滤已报道项目，返回 (new_items, filtered_out) — 使用 gh CLI"""
    new_items = []
    filtered_out = []
    
    data = gh_api_search_repos(query, filters, sort, per_page=15)
    if not data.get('items'):
        return new_items, filtered_out
    
    for item in data.get('items', [])[:15]:
        name = item.get('full_name', '')
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        
        parts = name.split('/')
        releases = []
        if len(parts) == 2:
            try:
                releases = fetch_releases(parts[0], parts[1], 3)
            except:
                pass
        
        item_obj = {
            'name': name,
            'desc': item.get('description') or '',
            'stars': item.get('stargazers_count', 0),
            'lang': item.get('language') or '',
            'updated': item.get('updated_at', '')[:10],
            'url': item.get('html_url', ''),
            'topics': item.get('topics', [])[:5],
            'is_top': True,
            'releases': releases,
        }
        
        should_report, reason = should_report_repo(name, seen_repos, item_obj)
        if should_report:
            new_items.append((item_obj, reason))
            if releases:
                print(f"  📦 {name}: {len(releases)} releases [{reason}]")
            else:
                print(f"  📌 {name} [{reason}]")
        else:
            filtered_out.append(item_obj)
    
    return new_items, filtered_out

new_count = 0
updated_count = 0
filtered_out = []
filtered_out2 = []
filtered_out3 = []

# 第 1 轮：今日策略
new_items, filtered_out = collect_github_items(
    strategy['query'], strategy['filters'], strategy['sort']
)
results['github'].extend([item for item, _ in new_items])
for _, reason in new_items:
    if reason == 'new':
        new_count += 1
    else:
        updated_count += 1

# 第 2 轮：如果不足 10 个，去掉过滤条件重搜
if len(results['github']) < MIN_GITHUB_ITEMS:
    print(f"  🔍 仅 {len(results['github'])} 个，放宽条件重搜（移除过滤）...")
    new_items2, filtered_out2 = collect_github_items(
        strategy['query'], '', 'stars'
    )
    github_filters_used = ''
    github_query_used = strategy['query'] + ' (无过滤)'
    github_sort_used = 'stars'
    results['github'].extend([item for item, _ in new_items2])
    for _, reason in new_items2:
        if reason == 'new':
            new_count += 1
        else:
            updated_count += 1

# 第 3 轮：如果仍不足，换经典关键词
if len(results['github']) < MIN_GITHUB_ITEMS:
    print(f"  🔍 仅 {len(results['github'])} 个，换经典关键词重搜...")
    from datetime import timedelta
    d30_fallback = (REPORT_DATETIME - timedelta(days=30)).strftime('%Y-%m-%d')
    new_items3, filtered_out3 = collect_github_items(
        'LLM OR AI agent OR "large language model"', f'pushed:>{d30_fallback}', 'stars'
    )
    github_query_used = 'LLM OR AI agent OR "large language model" (保底)'
    github_filters_used = f'pushed:>{d30_fallback}'
    github_sort_used = 'stars'
    results['github'].extend([item for item, _ in new_items3])
    for _, reason in new_items3:
        if reason == 'new':
            new_count += 1
        else:
            updated_count += 1

# 保底：如果仍不足 5 个，从本轮过滤掉的项目里补充（最近更新的）
if len(results['github']) < 5:
    all_filtered = filtered_out + filtered_out2 + filtered_out3
    all_filtered.sort(key=lambda x: x.get('updated', ''), reverse=True)
    needed = 5 - len(results['github'])
    print(f"  🔓 数量不足，从已报道项目中补充 {needed} 个...")
    for fb in all_filtered[:needed]:
        results['github'].append(fb)
        print(f"    🔄 {fb['name']} [补充报道]")

print(f"  ✅ {new_count} 新项目，{updated_count} 更新项目")

print(f"  ✅ 共 {len(results['github'])} 个项目")

# ── 3. 用 Jina 补充项目详细描述 ──────────────────────
print("  🔍 用 Jina 补充项目详细描述...")
jina_count = 0
for p in results['github'] + results['github_trending']:
    if not p.get('desc') or len(p['desc']) < 30:
        parts = p['url'].replace('https://github.com/', '').split('/')
        if len(parts) >= 2:
            repo_name = f"{parts[0]}/{parts[1]}"
            info = fetch_project_details_jina(repo_name)
            if info:
                if info.get('desc') and (not p.get('desc') or len(info['desc']) > len(p['desc'])):
                    p['desc'] = info['desc']
                if info.get('page_content'):
                    p['page_content'] = info['page_content']
                jina_count += 1
                print(f"    ✅ {p['name']}: Jina 抓取完成")
            else:
                # 降级：用 GitHub API (gh CLI)
                info = gh_api_get(f'repos/{parts[0]}/{parts[1]}')
                if info.get('description'):
                    p['desc'] = info['description']
                    jina_count += 1
    if not p.get('desc') or len(p['desc']) < 10:
        p['desc'] = p['name']
print(f"  ✅ 描述补充完成（{jina_count} 个项目）")

# ── 4. arXiv 论文 ──────────────────────────────────
print("📄 arXiv...")
arxiv_url = 'https://export.arxiv.org/api/query?search_query=all:%22large+language+model%22+OR+all:%22AI+agent%22+OR+all:%22LLM%22+OR+all:%22multi-agent%22&sortBy=submittedDate&sortOrder=descending&max_results=8'
out3 = run(f'curl -s --connect-timeout 15 -m 30 -x {PROXY} "{arxiv_url}"', timeout=35)
entries = re.findall(r'<entry>(.*?)</entry>', out3, re.DOTALL)
for entry in entries[:5]:
    title = re.search(r'<title>(.*?)</title>', entry, re.DOTALL)
    published = re.search(r'<published>(.*?)</published>', entry)
    summary = re.search(r'<summary>(.*?)</summary>', entry, re.DOTALL)
    link = re.search(r'<link href="(.*?)" rel="alternate"', entry)
    cats = re.findall(r'<category term="(.*?)"', entry)
    if title:
        results['papers'].append({
            'title': title.group(1).strip().replace('\n', ' '),
            'date': published.group(1)[:10] if published else '',
            'summary': summary.group(1).strip().replace('\n', ' ')[:300] if summary else '',
            'url': link.group(1) if link else '',
            'cats': cats[:2],
        })

# export.arxiv.org 在代理网络下偶有空响应；改用 arXiv 当日 new listing 作为备用源。
# 备用源只在 API 未返回论文时启用，并保留真实的 listing 日期与论文链接。
if not results['papers']:
    try:
        listing = run(
            f'curl -sL --connect-timeout 15 -m 30 -x {PROXY} "https://arxiv.org/list/cs.AI/new"',
            timeout=35,
        )
        records = re.findall(r'<dt>(.*?)</dt>\s*<dd>(.*?)</dd>', listing, re.DOTALL)
        keywords = ('llm', 'large language', 'agent', 'language model', 'multi-agent', 'agentic')
        for dt, dd in records:
            title_match = re.search(r"<div class=['\"]list-title[^>]*>.*?</span>(.*?)</div>", dd, re.DOTALL)
            id_match = re.search(r"href=['\"]/abs/([^'\"?#]+)['\"]", dt)
            if not title_match or not id_match:
                continue
            title = html_mod.unescape(re.sub(r'<[^>]+>', ' ', title_match.group(1)))
            title = re.sub(r'\s+', ' ', title).strip()
            if not any(keyword in title.lower() for keyword in keywords):
                continue
            paper_id = id_match.group(1)
            abstract_html = run(
                f'curl -sL --connect-timeout 10 -m 20 -x {PROXY} "https://arxiv.org/abs/{paper_id}"',
                timeout=25,
            )
            abstract_match = re.search(r'<blockquote class="abstract mathjax">.*?</span>(.*?)</blockquote>', abstract_html, re.DOTALL)
            summary = ''
            if abstract_match:
                summary = html_mod.unescape(re.sub(r'<[^>]+>', ' ', abstract_match.group(1)))
                summary = re.sub(r'\s+', ' ', summary).strip()[:500]
            results['papers'].append({
                'title': title,
                'date': DATE_STR,
                'summary': summary,
                'url': f'https://arxiv.org/abs/{paper_id}',
                'cats': ['cs.AI'],
            })
            if len(results['papers']) >= 5:
                break
        print(f"  ↪️ arXiv API 无有效结果，new listing 备用源补齐 {len(results['papers'])} 篇论文")
    except Exception as e:
        print(f"  ⚠️ arXiv 备用源失败: {e}")
print(f"  ✅ {len(results['papers'])} 论文")

# ── 5. Hacker News ─────────────────────────────────
print("📰 HN...")
out4 = run('curl -s --connect-timeout 10 "https://hacker-news.firebaseio.com/v0/topstories.json"')
try:
    ids = json.loads(out4)[:15]
    kws = ['llm', 'gpt', 'claude', ' ai ', ' ai,', 'agent', 'openai', 'anthropic', 'deepmind', 'language model', 'transformer', 'gemini', 'llama', 'mistral', 'artificial intelligence']
    for sid in ids:
        out5 = run(f'curl -s --connect-timeout 3 "https://hacker-news.firebaseio.com/v0/item/{sid}.json"')
        try:
            item = json.loads(out5)
            t = item.get("title", "").lower()
            if any(kw in t for kw in kws):
                url = item.get('url', '')
                results['hn'].append({
                    'title': item.get('title',''),
                    'url': url,
                    'source': 'Hacker News',
                    'cls': 'hn',
                    'date': datetime.fromtimestamp(item.get('time',0)).strftime('%Y-%m-%d') if item.get('time') else '',
                    'page_content': fetch_page_content_jina(url, 12) if url else '',
                })
        except: pass
except: pass
print(f"  ✅ {len(results['hn'])} HN")

# ── 6. Google News ─────────────────────────────────
print("📰 Google News...")
out6 = run(f'curl -s --connect-timeout 15 -x {PROXY} "https://news.google.com/rss/search?q=LLM+OR+%22large+language+model%22+OR+%22AI+agent%22&hl=en-US&gl=US&ceid=US:en"')
if out6:
    items = re.findall(r'<item>(.*?)</item>', out6, re.DOTALL)
    for item in items[:8]:
        title = re.search(r'<title>(.*?)</title>', item, re.DOTALL)
        link = re.search(r'<link>(.*?)</link>', item)
        source = re.search(r'<source>(.*?)</source>', item)
        pub = re.search(r'<pubDate>(.*?)</pubDate>', item)
        desc = re.search(r'<description>(.*?)</description>', item, re.DOTALL)
        if title:
            raw_url = link.group(1) if link else ''
            # 尝试从 Google News redirect URL 中提取真实 URL
            real_url = ''
            if raw_url and 'news.google.com/rss/articles/' in raw_url:
                # 用 Jina 直接抓原始 URL
                try:
                    out = run(f'curl -s --connect-timeout 6 -m 8 -x {PROXY} "https://r.jina.ai/{raw_url}"', timeout=10)
                    if out:
                        # 从 Jina 响应中提取 URL
                        url_match = re.search(r'URL Source: (https?://\S+)', out)
                        if url_match:
                            real_url = url_match.group(1).strip()
                except: pass
            results['news'].append({
                'title': html_mod.unescape(title.group(1).strip()),
                'url': real_url or raw_url,
                'source': html_mod.unescape(source.group(1)) if source else 'Google News',
                'cls': 'google',
                'date': pub.group(1) if pub else '',
                'desc': html_mod.unescape(desc.group(1))[:150] if desc else '',
                'page_content': '',  # 仅对前 3 条新闻抓取
            })
print(f"  ✅ {len(results['news'])} 新闻")

# 仅对前 3 条新闻抓取正文内容
print("  📖 抓取新闻正文内容...")
for n in results['news'][:3]:
    if n['url']:
        content = fetch_page_content_jina(n['url'], 10)
        n['page_content'] = content
        if content:
            print(f"    ✅ {n['title'][:40]}: {len(content)} chars")

# ── 7. 官网 Blog ───────────────────────────────────
# 不把官方动态采集绑定到本地 CDP 浏览器：定时环境通常没有 3456 服务。
def fetch_blog_list_jina(src, limit=3):
    """通过 Jina Reader 读取官方列表页，提取最近文章链接。"""
    try:
        out = run(
            f'curl -s --connect-timeout 8 -m 20 -x {PROXY} "https://r.jina.ai/{src["url"]}"',
            timeout=25,
        )
        if not out or 'Markdown Content:' not in out:
            return []
        posts, seen = [], set()
        for title, url in re.findall(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', out):
            title = re.sub(r'^Image\s+\d+:\s*', '', title).strip()
            # 列表卡片常把类别与日期拼在标题末尾；保留文章标题本身。
            title = re.sub(
                r'\s+(Product|Research|Safety|Engineering|Company|Announcements?|Policy|'
                r'Applied AI|Global Affairs|AI Adoption)\s+'
                r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},\s+\d{4}.*$',
                '', title,
            ).strip()
            title_lower = title.lower()
            if (len(title) < 12 or len(title) > 180 or url in seen or
                    title.startswith('![') or title_lower.startswith('skip to ') or
                    title_lower in {'announcements', 'newsroom', 'view more news'} or
                    any(token in url for token in ('images.', 'videos.', 'cdn.'))):
                continue
            seen.add(url)
            posts.append({'title': title, 'url': url})
            if len(posts) >= limit:
                break
        return posts
    except Exception as e:
        print(f"  ⚠️ {src['name']} Jina: {e}")
        return []

print("🌐 官网 Blog 列表...")
blog_sources = [
    {'name': 'OpenAI', 'url': 'https://openai.com/news/', 'pattern': '/index/'},
    {'name': 'Anthropic', 'url': 'https://www.anthropic.com/news', 'pattern': '/news/'},
    {'name': 'Hugging Face', 'url': 'https://huggingface.co/blog', 'pattern': '/blog/'},
    {'name': '魔搭 ModelScope', 'url': 'https://modelscope.cn/blogs', 'pattern': '/blogs/'},
    {'name': 'OpenRouter', 'url': 'https://openrouter.ai/blog', 'pattern': '/blog/'},
]
for src in blog_sources:
    posts = fetch_blog_list_jina(src)
    try:
        if not posts:
            tid = cdp_navigate(src['url'])
            if not tid:
                continue
            time.sleep(6)
            pattern = src['pattern']
            posts = cdp_eval(tid, rf'(() => {{ const links = document.querySelectorAll("a"); const posts = []; const seen = new Set(); for (const a of links) {{ const t = a.textContent.trim().replace(/\s+/g, " "); const h = a.getAttribute("href"); if (t && t.length > 15 && t.length < 150 && h && h.includes("{pattern}") && !seen.has(t)) {{ seen.add(t); const fullUrl = h.startsWith("http") ? h : new URL(h, window.location.origin).href; posts.push({{title: t, url: fullUrl}}); }} if (posts.length >= 3) break; }} return JSON.stringify(posts); }})()', timeout=10)
            cdp_close(tid)
        if posts and isinstance(posts, list):
            for p in posts[:3]:
                title = p.get('title', '').strip()
                skip_words = ['中文', 'english', '日本語', 'korean', 'sign in', 'login', 'subscribe', 'newsletter', 'all posts', 'filter', 'search', ' pro ', 'enterprise', 'support', 'pricing', 'documentation', 'api reference', 'changelog']
                if any(skip in title.lower() for skip in skip_words):
                    continue
                results['blogs'].append({
                    'title': title,
                    'url': p.get('url', ''),
                    'source': src['name'],
                    'date': '',
                    'page_content': '',  # LLM 按需抓取
                })
    except Exception as e:
        print(f"  ⚠️ {src['name']}: {e}")

# 去重
seen_blogs = set()
unique_blogs = []
for b in results['blogs']:
    key = b['title'][:60]
    if key not in seen_blogs:
        seen_blogs.add(key)
        unique_blogs.append(b)
results['blogs'] = unique_blogs[:15]

# 仅对前 3 篇 Blog 抓取正文内容（避免超时）
print("  📖 抓取 Blog 正文内容...")
for b in results['blogs'][:3]:
    if b['url']:
        content = fetch_page_content_jina(b['url'], 12)
        b['page_content'] = content
        if content:
            print(f"    ✅ {b['title'][:40]}: {len(content)} chars")
print(f"  ✅ {len(results['blogs'])} 条")

# ── 更新已报道项目记录 ──────────────────────────────
if results['github']:
    update_seen_repos(seen_repos, results['github'])

# ── 保存原始 JSON ──────────────────────────────────
with open(RAW_JSON, 'w') as f:
    json.dump({
        'date': DATE_STR,
        'github': results['github'],
        'github_trending': results['github_trending'],
        'papers': results['papers'],
        'hn': results['hn'],
        'news': results['news'],
        'blogs': results['blogs'],
        'github_strategy': {
            'query': github_query_used,
            'filters': github_filters_used,
            'sort': github_sort_used,
            'label': strategy['label'],
        },
    }, f, ensure_ascii=False, indent=2)

total = sum(len(v) for v in results.values())
print(f"\n✅ 数据采集完成: {total} 条原始数据")
print(f"📦 Raw JSON: {RAW_JSON}")
print(f"   Trending:{len(results['github_trending'])} GitHub:{len(results['github'])} 论文:{len(results['papers'])} Blog:{len(results['blogs'])} HN:{len(results['hn'])} News:{len(results['news'])}")

# 复制一份到 docs 目录方便查看
import shutil, os
docs_dir = "/Users/zz/code/AI_Daily_Brief/docs"
try:
    os.makedirs(docs_dir, exist_ok=True)
    docs_file = f"{docs_dir}/llm-briefing-raw-{DATE_STR}.json"
    shutil.copy(RAW_JSON, docs_file)
    print(f"📋 已复制到 docs: {docs_file}")
except Exception as e:
    print(f"  ⚠️ 复制到 docs 失败: {e}")

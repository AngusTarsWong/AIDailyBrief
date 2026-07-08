# GitHub API 连接与搜索技巧

## gh CLI 访问方式（当前方案）

自 2026-07-07 起，所有 GitHub API 调用（Search、Repo、Releases）统一使用 `gh` CLI，通过已认证 token 访问（5000 req/h，远高于未认证的 60 req/h）。

**核心函数**：

```python
def gh_run(cmd, timeout=15):
    \"\"\"执行 gh 命令，自动设置代理环境变量\"\"\"
    env = os.environ.copy()
    env['HTTPS_PROXY'] = PROXY
    env['https_proxy'] = PROXY
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
    return r.stdout

def gh_api_get(endpoint, timeout=10):
    \"\"\"调用任意 GitHub API 端点\"\"\"
    try:
        out = gh_run(f'gh api "{endpoint}"', timeout=timeout)
        if not out or len(out) < 10:
            return {}
        return json.loads(out)
    except:
        return {}

def gh_api_search_repos(query, filters, sort, per_page=15):
    \"\"\"搜索仓库（替代旧的 github_search_with_retry）\"\"\"
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
                    time.sleep(2)
                    continue
                return {}
            return json.loads(out)
        except:
            if attempt < 2:
                time.sleep(2)
                continue
            return {}
    return {}
```

**为什么从 curl 切换到 gh CLI**：
- 速率限制从 60 → 5000 req/h，不再担心未认证限流
- `gh api` 自带认证 token，不需要手动拼接 Authorization header
- 代理通过环境变量注入，不需要在 curl 命令中加 `-x`
- 输出格式一致，不需要处理不同 API 的认证差异

**⚠️ 代理环境变量必须设置**：`gh` CLI 默认不走代理，必须设置 `HTTPS_PROXY` 环境变量。`gh_run` 函数已自动处理。

**⚠️ gh 没有 `gh trending` 命令**：Trending 页面仍使用 Jina 抓取，不受此变更影响。

## Search API 查询编码

使用 `gh api` 时，查询字符串中的空格用 `+` 替换即可（gh 内部会处理）。对于含引号的复杂查询，确保正确编码：

```python
# gh api 方式：空格替换为 + 即可
f'gh api "search/repositories?q={raw_q.replace(" ", "+")}&sort={sort}&per_page={per_page}"'
```

**陷阱**：如果 `gh api` 返回空数组 `[]` 而非 `{"items": [...]}` 对象，说明查询条件过于严格（如 `created:>昨天` 当天无新项目），需要降级到不带过滤的经典搜索。

## 旧方案（curl 裸 API，已废弃但保留）

旧的 `safe_api_get` 和 `github_search_with_retry` 函数仍保留在代码中，但已不再被调用。如需回退到 curl 方式，替换函数名即可恢复。旧方案的关键点：
- 直连不通时自动走代理（`-x {PROXY}`）
- 限速时可能返回 `list` 类型而非 `dict`，需做类型检查

## GitHub Search API URL 编码

查询字符串必须用 `urllib.parse.quote()` 编码，不能手动用 `+` 拼接：

```python
from urllib.parse import quote

# 错误：手动拼接，特殊字符（引号、空格、>）可能被 curl 错误解析
url = f'https://api.github.com/search/repositories?q={query}+{filters}'

# 正确：URL 编码
from urllib.parse import quote
q_encoded = quote(f'{query} {filters}')
url = f'https://api.github.com/search/repositories?q={q_encoded}&sort={sort}&order=desc&per_page={per_page}'
```

**陷阱**：未正确编码的查询会静默返回 0 结果（HTTP 200 但 `total_count: 0`），不会报错，极难排查。

## `github_strategy` 输出字段

`run-briefing.py` 会在 raw JSON 中写入 `github_strategy` 字段，记录当日实际使用的搜索条件：

```json
{
  "github_strategy": {
    "query": "AI agent OR autonomous OR workflow automation (无过滤)",
    "filters": "",
    "sort": "stars",
    "label": "新创建项目（近 7 天）"
  }
}
```

- `query`：实际使用的关键词（fallback 时标注 `(无过滤)` 或 `(保底)`）
- `filters`：实际使用的过滤条件（fallback 到无过滤时为空字符串）
- `sort`：实际使用的排序方式
- `label`：今日策略标签名

`generate-report.py` 读取此字段并在 HTML 报告的 "GitHub 热门项目" 标题下方显示，格式如 `📅 新创建项目（近 7 天） | 🔍 created:>2026-06-30 | 🔑 AI agent OR autonomous ...`，方便用户一眼看出当日生效的搜索策略。

## 动态搜索策略（避免每日重复）

按星期轮换 GitHub Search API 查询条件：

| 星期 | 策略 | 过滤条件 |
|------|------|---------|
| 周一 | 热门新势力 | `pushed:>{30天前}` |
| 周二 | 新创建项目 | `created:>{7天前}` |
| 周三 | 中型潜力股 | `stars:500..50000` |
| 周四 | 新兴话题 | `pushed:>{14天前}` |
| 周五 | 最近活跃 | `pushed:>{3天前}` |
| 周六 | AI 工具生态 | `stars:100..20000` |
| 周日 | 经典热门 | `pushed:>{30天前}` |

日期必须用 `datetime.now() - timedelta(days=N)` 动态计算，不能硬编码。

**降级策略**：如果过滤条件导致搜索结果为空，自动降级到不带过滤条件的经典搜索。

## 已报道项目追踪（seen-repos）

维护 `/tmp/llm-briefing-seen-repos.json` 记录历史报道过的项目：

```json
{
  "NousResearch/hermes-agent": {
    "report_count": 3,
    "last_seen": "2026-07-07",
    "last_updated": "2026-07-06",
    "last_release_tags": ["v2026.7.1", "v2026.6.28"]
  }
}
```

**纳入规则**：
- 从未报道 → 直接纳入，标记 `new`
- 已报道但有新 release → 纳入，标记 `updated`
- 已报道但最近更新了（pushed > last_seen）→ 纳入，标记 `updated`
- 已报道且无更新 → 跳过

**重要**：`seen_repos = load_seen_repos()` 必须在脚本顶部（results 初始化后）加载，不能延迟到 GitHub section 内部。否则：
1. 末尾的 `update_seen_repos()` 调用会 NameError
2. 无法在多个 section 间共享状态

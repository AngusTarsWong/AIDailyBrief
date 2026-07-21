---
name: llm-daily-briefing
description: 每日 LLM & Agent 领域动态播报 — 涵盖 GitHub Trending、热门项目、arXiv 论文、官方 Blog、行业新闻
category: automation
---

# LLM Daily Briefing

## 概述

每日自动播报 LLM/Agent 领域最新动态，涵盖 6 大数据源，生成 HTML 可视化报告。

**核心原则**：宁多勿少，信息齐全。翻译必须基于上下文由 LLM 亲自完成。

## 架构：逐批翻译流水线

```
┌─────────────────┐    ┌──────────────────────────────────┐    ┌─────────────────────┐    ┌─────────────────┐    ┌──────────────────────┐
│  Phase 1 采集   │───▶│  Phase 2 逐批翻译                  │───▶│  Phase 2.5 合并      │───▶│  Phase 3 HTML   │
│  (Python)       │    │  (每批 3-5 个项目，专注翻译)       │    │  (Python)           │    │  (Python)       │
│  raw JSON       │    │  各批次写 batch-{N}.json           │    │  merged enriched    │    │  ~/code/AI_Daily_Brief/docs/     │
│  /tmp/          │    │  /tmp/llm-briefing-batch-{N}.json  │    │  /tmp/              │    │  html           │
│                 │    │                                  │    │                     │    │                 │    │ Phase 4 终检          │
│                 │    │                                  │    │                     │    │                 │───▶│ 内容准确性 + HTML QA  │
└─────────────────┘    └──────────────────────────────────┘    └─────────────────────┘    └─────────────────┘    └──────────────────────┘
```

### Phase 1 — 数据采集（Python 脚本）

只负责从各数据源采集原始数据，保存为 JSON。**不做任何翻译或信息增强。**

```bash
/opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/run-briefing.py
```

**输出**：
- `/tmp/llm-briefing-raw-YYYY-MM-DD.json` — 原始采集数据，含 `github_strategy` 字段（记录当日实际使用的搜索关键词、过滤条件、排序方式和 fallback 标记）
- 自动复制：`~/code/AI_Daily_Brief/docs/llm-briefing-raw-YYYY-MM-DD.json`

### Phase 2 — 逐批翻译（Hermes Agent 执行）

**将翻译任务拆分为小批次（每批 3-5 个项目），逐个批次处理**，确保每个翻译任务有足够的上下文专注度，避免信息丢失。

**工作流程**：

1. **生成任务清单**：
   ```bash
   /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/translate-sections.py
   /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/translate-batches.py
   ```
   生成 `/tmp/llm-briefing-batches-{DATE}.json`，包含所有翻译批次。

2. **逐批翻译**：
   - 读取批次清单
   - 对于每个批次，使用批次 prompt 调用 LLM 进行翻译
   - 将翻译结果保存为 `/tmp/llm-briefing-batch-{N}.json`
   - 验证结果完整性（每个 task_id 都有翻译，字段齐全）

3. **合并结果**：
   ```bash
   /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/merge-batches.py
   ```

**为什么逐批翻译**：
- 旧方案（5 个子 Agent 各处理整个板块）容易因上下文过长导致翻译截断或遗漏
- 新方案每批只处理 3-5 个项目，LLM 可以专注完成每个翻译任务
- 翻译质量更高，不会部分翻译部分遗漏

### Phase 2.5 — 合并（Python 脚本）

读取 raw JSON 作为基底，叠加各批次翻译结果。

```bash
/opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/merge-batches.py
```

**逻辑**：
1. 读取 raw JSON 作为 base
2. 依次读取 `/tmp/llm-briefing-batch-{N}.json`（**注意：文件结构为 `{"batch_id": "...", "results": {task_id: translation}}`**，必须先取 `results` 字段再 `update` 到翻译字典）
3. 将每个 task_id 的翻译结果合并到对应的 raw JSON 条目中
4. **降级机制**：若某个 batch 文件缺失，该批次对应的条目保留英文原文
5. 合并后输出 `/tmp/llm-briefing-enriched-{DATE}.json`，并**同步为正式交付物** `docs/llm-briefing-enriched-{DATE}.json`
6. **验证**：合并后检查 enriched JSON 中随机条目的 `_zh` 字段（如 `desc_zh`、`name_zh`），若全为空说明合并失败（通常是 `results` 提取错误）

### Phase 3 — HTML 渲染（Python 脚本）

读取合并后的 enriched JSON（优先）或 raw JSON（降级），渲染最终的深色主题卡片式报告。

```bash
/opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/generate-report.py
```

**读取逻辑**：`generate-report.py` 优先读取 enriched JSON，如果不存在则降级到 raw JSON。

**策略回显**：`generate-report.py` 从 raw JSON 的 `github_strategy` 字段读取当日搜索策略，并在 HTML 报告的 "GitHub 热门项目" 标题下方显示（如 `📅 新创建项目（近 7 天） | 🔍 created:>2026-06-30 | 🔑 AI agent OR autonomous ...`），方便用户一眼看出今日生效的搜索条件。如果触发了 fallback，会自动标注 `(无过滤)` 或 `(保底)`。

**输出**：
- `/tmp/llm-briefing-YYYY-MM-DD.html`（临时文件）
- 自动复制：`~/code/AI_Daily_Brief/docs/llm-briefing-YYYY-MM-DD.html`
- 自动固化：`~/code/AI_Daily_Brief/docs/llm-briefing-enriched-YYYY-MM-DD.json`（必须与 HTML 使用同一份数据）

### Phase 4 — HTML 内容准确性终检（交付门禁）

Phase 3 仅生成候选 HTML；**Phase 4 通过前不得把它视为最终日报或发布到 docs/GitHub**。检查 enriched JSON、候选 HTML 和原始链接是否一致，并按以下顺序执行：

1. **内容一致性**：卡片数量与 enriched JSON 各板块一致；标题、摘要、日期、来源、链接均对应同一条原始记录。
2. **事实与日期**：项目描述、新闻摘要和官方动态不含无依据的细节；历史日报中的文章日期不得晚于报告日期（允许前一自然日时区缓冲）。
3. **文本质量**：项目介绍符合“定位 → 核心机制 → 解决问题/适用场景”；新闻为文章级摘要；禁止英文原文直嵌、来源级占位摘要和模板套话。
4. **HTML 效果**：确认所有板块、卡片、统计数和链接正常渲染；检查空板块、重复卡片、导航/图片误抓、HTML 转义泄漏与占位文本。
5. **交付物完整性**：`docs/llm-briefing-{DATE}.html`、`docs/llm-briefing-raw-{DATE}.json`、`docs/llm-briefing-enriched-{DATE}.json` 必须同时存在；HTML 卡片数必须与 docs/enriched 一致。缺少 enriched JSON 时不得发布。

发现问题时，修复 raw/enriched 或翻译批次后重新运行 Phase 3，再从第 1 项复检。输出应记录为：板块数量、翻译覆盖率、发现/修复的问题和最终通过状态。

## GitHub API 访问方式

### gh CLI（推荐，已认证，5000 req/h）

当前 skill 已切换为使用 `gh` CLI 访问 GitHub API，相比之前的裸 curl + 未认证 API，有以下优势：
- **速率限制提升**：从未认证的 60 req/h 提升到 5000 req/h
- **稳定性更高**：通过 gh 的认证机制，不再依赖未认证的有限配额
- **结构化输出**：`gh api` 返回标准 JSON，不需要手动拼接 URL 和处理分页

**核心函数**：
- `gh_run(cmd, timeout)` — 执行 gh 命令，自动设置代理环境变量（`HTTPS_PROXY`）
- `gh_api_search_repos(query, filters, sort, per_page)` — 搜索仓库，替代旧的 `github_search_with_retry`
- `gh_api_get(endpoint, timeout)` — 调用任意 GitHub API 端点（如 releases、repo info）

**代理配置**：`gh` CLI 通过环境变量 `HTTPS_PROXY` 设置代理，所有 gh 调用都会自动注入代理配置。

```python
def gh_run(cmd, timeout=15):
    env = os.environ.copy()
    env['HTTPS_PROXY'] = PROXY
    env['https_proxy'] = PROXY
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout, env=env)
    return r.stdout

def gh_api_get(endpoint, timeout=10):
    try:
        out = gh_run(f'gh api "{endpoint}"', timeout=timeout)
        if not out or len(out) < 10:
            return {}
        return json.loads(out)
    except:
        return {}
```

**gh CLI 的局限**：
- `gh` 没有 `gh trending` 命令，Trending 页面仍需 Jina 抓取
- 启动开销比 curl 稍重，但对每天跑一次的场景影响可忽略

### 旧方案（curl 裸 API，已废弃）

旧的 `safe_api_get` 和 `github_search_with_retry` 函数仍保留在代码中，但已不再被调用。如需回退，可替换函数名恢复。

## 数据源（宁多勿少）

| 数据源 | 获取方式 | 说明 |
|--------|---------|------|
| **GitHub Trending** | Jina Reader API | 抓取全部 trending 页面（约 16-25 个），不做关键词过滤，全部交给 LLM 子 Agent 智能筛选 |
| **GitHub 热门项目** | GitHub Search API | **动态搜索策略**：按星期轮换查询条件（关键词 + 时间窗口 + stars 区间），避免每日重复；**已报道项目过滤**：维护 `/tmp/llm-briefing-seen-repos.json`，从未报道的新项目直接加入，已报道但有新 release 或新活跃的项目重新报道并标记 "updated" |
| **arXiv 论文** | arXiv API | 搜索 LLM/AI agent 最新论文，取前 5-8 篇 |
| **Hacker News** | HN Firebase API | 从 top stories 中筛选 AI 相关 |
| **Google News** | Google RSS | 搜索 LLM/AI agent 相关新闻 |
| **官网 Blog** | CDP 抓取 | OpenAI、Anthropic（`/research`）、HuggingFace、OpenRouter |

## 翻译原则

- **全量翻译**：所有板块（Trending、热门项目、论文、Blog、新闻）的标题和摘要都翻译为中文
- **基于上下文**：根据项目名称、领域知识进行准确翻译，不是简单机器翻译
- **技术术语**：保留通用技术名词（API、CLI、MCP、LLM 等），其余尽量中文
- **宁多勿少**：每个条目都要有中文标题和中文描述/摘要
- **优先 enriched**：`generate-report.py` 优先读取 LLM 生成的 enriched JSON（含完整翻译），降级到 raw JSON 时用字典兜底

## 报告格式

- **HTML 格式**，深色主题，卡片式布局
- Trending 置顶（绿色主题）
- 各板块用不同颜色区分
- 所有链接可点击
- **GitHub 热门项目的 Releases 区域**：每个版本以独立卡片展示，包含版本号（🏷️）、日期、改动摘要
  - 样式：`.release-item` 绿色半透明背景 + 绿色边框 + 圆角
  - 格式：`🏷️ 版本号 | 日期` + 改动摘要（用 `；` 连接多条 bullet）
- 底部统计栏：总条数、GitHub 项目数、Trending 数、官方动态数

## 定时任务配置

```yaml
name: daily-llm-briefing
schedule: "0 9 * * *"  # 每天早 9 点
prompt: |
  1. 运行采集脚本: /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/run-briefing.py
  2. 生成翻译任务: /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/translate-sections.py && translate-batches.py
  3. 读取 /tmp/llm-briefing-batches-{today}.json
  4. **逐批翻译**：对于每个批次，使用批次 prompt 调用 LLM 翻译，结果保存为 /tmp/llm-briefing-batch-{N}.json
  5. 合并翻译结果: /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/merge-batches.py
  6. 生成 HTML: /opt/homebrew/bin/python3.11 ~/.hermes/skills/llm-daily-briefing/scripts/generate-report.py
  7. **Phase 4 终检**：对 enriched JSON、HTML、标题/摘要/日期/链接及渲染效果执行内容准确性检查；有问题则修复并重新执行第 6 步。
  8. 仅在终检通过后汇报生成结果（总条数、各板块数量、翻译覆盖率、终检状态）
```

## 网络代理规则（关键）

| 目标 | 代理策略 | 原因 |
|------|---------|------|
| **GitHub API**（gh CLI） | **自动通过 HTTPS_PROXY 环境变量走代理** | `gh_run` 函数已设置代理，无需手动加 `-x` |
| **Jina 抓 GitHub Trending** | **可用**（走代理） | `github.com/trending` 正常返回 Markdown |
| **Jina 抓 GitHub Releases** | **不可用** | `/releases` 路径返回 403 AbuseAlleviationError |
| **arXiv API** | **走代理** | 直连会超时 |
| **Google News** | 走代理 | 境外站点 |
| **境内站点**（魔搭等） | 直连 | 更快更稳定，走代理可能超时 |

## GitHub API 访问方式

### gh CLI（推荐，已认证，5000 req/h）

当前 skill 已切换为使用 `gh` CLI 访问 GitHub API，详见 `references/github-api-patterns.md`。

核心优势：
- **速率限制提升**：从未认证的 60 req/h 提升到 5000 req/h
- **稳定性更高**：通过 gh 的认证机制，不再依赖未认证的有限配额
- **代理自动注入**：通过 `HTTPS_PROXY` 环境变量，不需要在每个 curl 命令中加 `-x`

**局限**：`gh` 没有 `gh trending` 命令，Trending 页面仍需 Jina 抓取。

## GitHub Releases 获取

### gh CLI 请求（当前方案）

```python
data = gh_api_get(f'repos/{owner}/{repo}/releases?per_page=3')
```

不再需要处理直连/代理切换，`gh_run` 已自动设置代理环境变量。速率限制从 60 → 5000 req/h，基本不会触发限速。

### ⚠️ GitHub Search API 返回类型陷阱

使用 `gh api` 时，如果查询条件过于严格（如 `created:>昨天` 当天无新项目），可能返回空数组 `[]` 而非预期的对象。解析时需检查：

```python
data = json.loads(out)
if isinstance(data, dict):
    for item in data.get('items', [])[:8]:
        # 正常处理
elif isinstance(data, list):
    # API 限速返回了 list，跳过或重试
    pass
```

### Release body 清洗规则

从 GitHub API 获取的 release body 包含大量噪声，提取 changelog 前必须清洗：

```python
import re

body = r.get('body') or ''
# 1. 去掉图片/badge
body = re.sub(r'!\[.*?\]\(.*?\)', '', body)
# 2. 去掉链接 URL（保留链接文字）
body = re.sub(r'\[([^\]]*?)\]\(https?://.*?\)', r'\1', body)
# 3. 去掉 HTML 注释（n8n 等项目会注入 <!-- stage-rev --> 等注释）
body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
# 4. 清理 markdown 格式
body = re.sub(r'\*\*(.+?)\*\*', r'\1', body)  # **bold** → bold
body = re.sub(r'`([^`]+)`', r'\1', body)       # `code` → code
# 5. 去掉感谢和 PR 编号、commit hash
body = re.sub(r'\s*Thanks?[\s,]*@.*$', '', body)
body = re.sub(r'\s*\(#[\d]+\)\s*', ' ', body)
body = re.sub(r'\s*\([a-f0-9]{7,}\)\s*', ' ', body)
# 6. 去掉 scope 前缀（先清 markdown 再去 scope）
body = re.sub(r'^[\w\-]+:\s*', '', body)
```

### 不同项目的 highlights 格式

- **openclaw**：`## ✨ Highlights` + `- **Feature:** description`（em dash 分隔）
- **hermes-agent**：`## ✨ Highlights`（二级标题！）+ `- **Title** — description`
- **n8n**：`### Bug Fixes` + `* **scope:** description`，body 中包含 HTML 注释
- **AutoGPT**：`### What's Changed` + `- #1234 - Feature description`
- **superpowers**：`- **Title.** description`（句号分隔）

提取逻辑：识别 highlights/Bug Fixes/Features/What's Changed 等区域 → 遍历 `- ` 或 `* ` 开头的行 → 提取改动描述 → 最多取 4 条。

### 重试机制

`gh_api_search_repos` 内置 3 次重试（2s 间隔），`gh_api_get` 有异常捕获。5000 req/h 配额下日常使用极少触发限速。

### 旧方案注意事项（curl + 未认证 API，已废弃）

⚠️ 如果回退到旧方案：Jina 对 `github.com` 域名会返回 **403 AbuseAlleviationError**（"DDoS attack suspected"）。所以当 GitHub API 限速时，**不要**依赖 Jina fallback 获取 releases。跳过即可。

## 文件输出到 docs 目录

**问题**：Hermes 沙箱（execute_code 和脚本运行）**无法直接写入 `~/code/AI_Daily_Brief/docs/`**（macOS 沙箱权限拒绝，`PermissionError: Operation not permitted`）。

**解决方案**：脚本先写入 `/tmp/`，然后用 `shutil.copy` 复制到 docs 目录：

```python
import shutil, os
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
OUTPUT_TMP = f"/tmp/llm-briefing-{DATE_STR}.html"
OUTPUT = f"/Users/zz/code/AI_Daily_Brief/docs/llm-briefing-{DATE_STR}.html"

# 写入 /tmp
with open(OUTPUT_TMP, 'w') as f:
    f.write(body)

# 复制到 docs 目录
try:
    shutil.copy(OUTPUT_TMP, OUTPUT)
except Exception as e:
    # 降级：终端中用 cp
    pass
```

终端命令：`cp /tmp/llm-briefing-2026-07-06.html ~/code/AI_Daily_Brief/docs/`

## 逐批翻译：批次输出格式

**批次结果文件**（每个批次一个文件）：
- `/tmp/llm-briefing-batch-{N}.json` — 包含该批次所有 task_id 的翻译结果

格式示例：
```json
{
  "github-0": {
    "name_zh": "Auto-FreeCF",
    "desc_zh": "Cloudflare Workers AI 账号 ID 和 Token 收集工具，支持多种自动化模式...",
    "lang_zh": "Python",
    "releases": [
      {"tag": "v4.3.1", "release_highlights_zh": ["Turnstile Token 注入", "反检测增强", ...]}
    ]
  },
  "github-1": {...},
  ...
}
```

`generate-report.py` 读取逻辑：

```python
import os
DATE_STR = datetime.now().strftime('%Y-%m-%d')
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
ENRICHED_JSON = f"/tmp/llm-briefing-enriched-{DATE_STR}.json"

# 优先读取 enriched（含完整翻译），降级到 raw
json_path = ENRICHED_JSON if os.path.exists(ENRICHED_JSON) else RAW_JSON
with open(json_path) as f:
    raw = json.load(f)
```

翻译逻辑只处理**没有 `desc_zh`** 的条目：

```python
for p in raw.get('github', []):
    if not p.get('desc_zh'):  # 已有翻译则跳过
        p['desc_zh'] = translate_with_context(p.get('desc', ''), p.get('name', ''))
```

## 技术要点

详见 `references/github-api-patterns.md`：GitHub API 连接模式（直连→代理自动降级）、Search API URL 编码、动态搜索策略、已报道项目追踪。

### Jina Reader API 使用模式

```python
# 基本用法（走代理）
out = run(f'curl -s --connect-timeout 8 -m 12 -x {PROXY} "https://r.jina.ai/{url}"', timeout=15)

# 提取正文内容
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
```

### Jina 抓取 GitHub Trending 解析模式

Jina 可以正常抓取 `github.com/trending`（与 releases 页面不同，trending 不受 403 限制）。返回的 Markdown 结构：

```markdown
## [owner/name](https://github.com/owner/name)
项目描述一行
Language[总stars] Built by [...] NNN stars today
```

解析代码：

```python
out = run(f'curl -s --connect-timeout 10 -m 30 -x {PROXY} "https://r.jina.ai/https://github.com/trending"', timeout=35)
projects = []
current = {}
for line in out.split('\n'):
    line = line.strip()
    m = re.match(r'## \[(.+?)\]\((.+?)\)', line)
    if m:
        if current.get('name'):
            projects.append(current)
        current = {'name': m.group(1), 'url': m.group(2), 'desc': ''}
    elif current.get('name') and not current.get('desc') and line:
        if 'Built by' not in line and 'stars' not in line:
            current['desc'] = line
    # 语言/stars/today 行：提取语言和今日 stars
```

**Trending 筛选策略：AI 相关性过滤 + 丰富介绍**

1. 不再使用硬编码关键词列表过滤，而是将全部 trending 项目交给翻译子 Agent
2. **翻译 prompt 中要求 Agent 先判断 AI 相关性**：与 AI/LLM/Agent/机器学习/自动化不相关的项目输出 `{"skip": true, "reason": "原因"}`
3. **相关项目的描述要求 150-250 字**：不只是直译原文，要结合项目名、技术栈和 Agent 自身知识补充项目背景、解决的问题、特点、适合谁用
4. `merge-batches.py` 会将标记 `_skip` 的项目从最终输出中过滤掉
5. 效果：非 AI 项目（如通用 awesome 列表）被自动过滤，保留的 AI 项目描述从 50-100 字提升到 187-247 字

**Trending 项目详情补充（Phase 1.5）**

采集完 Trending 后，`run-briefing.py` 会用 Jina 抓取前 10 个项目的 GitHub 页面（README），提取 `page_content` 字段（前 500 字）。这些内容传入翻译 prompt，帮助 Agent 写出更丰富的介绍。

```python
# run-briefing.py Phase 1.5：Trending 采集后执行
for p in results['github_trending'][:10]:  # 只抓前 10 个，控制时间
    details = fetch_project_details_jina(p['name'], timeout=15)
    if details and details.get('page_content'):
        p['page_content'] = details['page_content'][:500]
```

**generate-report.py 的 desc_zh 优先级**：`enrich_trending()` 函数开头检查 `desc_zh` 长度，如果已有翻译且 > 80 字（说明来自翻译管道），直接保留，不再用本地字典覆盖。

### GitHub 热门项目：动态搜索 + 已报道项目过滤

#### 动态搜索策略

每天轮换不同的 GitHub Search API 查询条件，避免每天返回同样的项目：

| 星期 | 策略 | 关键词 | 过滤条件 | 排序 |
|------|------|--------|---------|------|
| 周一 | 热门新势力 | LLM OR AI agent OR MCP OR RAG | `pushed:>{30天前}` | stars |
| 周二 | 新创建项目 | AI agent OR autonomous OR workflow automation | `created:>{7天前}` | stars |
| 周三 | 中型潜力股 | agent OR "AI tool" OR coding assistant | `stars:500..50000` | stars |
| 周四 | 新兴话题 | MCP OR embedding OR "vector database" OR "AI framework" | `pushed:>{14天前}` | stars |
| 周五 | 最近活跃 | LLM OR AI agent OR machine learning | `pushed:>{3天前}` | updated |
| 周六 | AI 工具生态 | AI plugin OR agent skill OR prompt engineering | `stars:100..20000` | stars |
| 周日 | 经典热门 | LLM OR AI agent OR "large language model" | `pushed:>{30天前}` | stars |

日期计算使用 `datetime.now() - timedelta(days=N)`，确保始终相对当前日期。

**降级策略**：如果过滤条件导致搜索结果为空，自动降级到不带过滤条件的经典搜索。

**三层搜索回退机制**（确保至少 10 个项目）：
1. **第 1 轮**：使用今日策略（关键词 + 过滤条件），`per_page=15`
2. **第 2 轮**：如果结果 < 10，去掉过滤条件重搜（保留关键词）
3. **第 3 轮**：如果仍 < 10，换经典关键词 `LLM OR AI agent OR "large language model"` + `pushed:>近30天`
4. **保底**：如果仍 < 5，从本轮去重过滤掉的已报道项目中按 `updated_at` 排序补充

#### 已报道项目追踪

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
- **从未报道**：直接纳入，标记 `new`
- **已报道但有新 release**：纳入，标记 `updated (新 release: v1.2.3)`
- **已报道但最近更新了**（pushed 时间晚于 last_seen）：纳入，标记 `updated (新活跃: 2026-07-06)`
- **已报道且无更新**：跳过，避免重复

**更新时机**：每次采集完成后，将本轮纳入的项目信息追加到 seen-repos 文件。

### Jina 补充项目详细描述

对描述过短（< 30 字符）的项目，使用 Jina Reader API 抓取 GitHub 项目页获取完整描述：

```bash
curl -s --connect-timeout 10 -m 20 -x {PROXY} "https://r.jina.ai/https://github.com/{owner}/{repo}"
```

**解析逻辑**：
1. 从 `Title: GitHub - {owner}/{repo}: {description}` 行提取项目描述
2. 从 `Markdown Content:` 后的内容中提取第一个有意义的文本段落（跳过 badge/图片行）
3. 拼接两部分作为完整描述
4. 同时保存 `page_content` 字段（前 20 行有意义的 Markdown），供子 Agent 深度翻译参考

**降级策略**：如果 Jina 抓取失败，降级到 GitHub API `repos/{owner}/{repo}` 获取 description。

### ⚠️ Jina 对不同 GitHub 路径的可用性

| 路径 | Jina 是否可用 | 说明 |
|------|--------------|------|
| `github.com/trending` | ✅ 可用 | 正常返回 Markdown，约 16-25 个项目 |
| `github.com/{owner}/{repo}` | ✅ 可用 | README 等内容可正常抓取 |
| `github.com/{owner}/{repo}/releases` | ❌ 403 | DDoS protection，不可用 |

### Google News URL 特殊处理

Google News RSS 返回的 URL 是 redirect 链接（`news.google.com/rss/articles/...`），不要用 CDP 打开（会超时）。用 Jina 抓 redirect URL 后从 `URL Source:` 行提取真实 URL：

```python
out = run(f'curl -s --connect-timeout 6 -m 8 -x {PROXY} "https://r.jina.ai/{raw_url}"', timeout=10)
url_match = re.search(r'URL Source: (https?://\S+)', out)
if url_match:
    real_url = url_match.group(1).strip()
```

### Blog/News 标题清洗

Jina 返回的标题常黏连日期和来源名（如 `"The OpenRouter MCP ServerJun 25, 2026"` 或 `"AI Agent Conducts First Fully Autonomous Ransomware Attack - The HIPAA Journal"`），翻译前必须用正则清理：

```python
def clean_blog_title(title):
    # 去掉末尾英文日期
    title = re.sub(r'\s*(Jun|Jul|May|Apr|...)\s+\d{1,2},?\s+\d{4}\s*$', '', title)
    # 去掉来源名
    title = re.sub(r'\s*[-|]\s*(Help Net Security|Techzine|Axios|...)\s*$', '', title)
    return title.strip()
```

匹配翻译字典时用**双向模糊匹配**：

```python
for en, zh in TRANSLATIONS.items():
    if en.lower() in cleaned.lower() or cleaned.lower() in en.lower():
        return zh
    # 去掉标点后再次匹配
    en_clean = re.sub(r'[^\w\s]', '', en).lower()
    t_clean = re.sub(r'[^\w\s]', '', cleaned).lower()
    if en_clean in t_clean or t_clean in en_clean:
        return zh
```

## CDP 使用要点

- **需要浏览器操作时先申请权限** — 如果需要操作浏览器（CDP 导航、截图等），先向用户申请权限，不要直接打开浏览器。
- **cdp_eval 的 shell 引号陷阱**：不要用 `-d '{expression}'` 直接传 JS 代码（JS 中的引号、换行符会被 shell 解析破坏）。把 JS 代码写入临时文件，用 `--data-binary @<file>` 传递。
- **CDP 返回双重 JSON 编码**：返回的 `value` 字段是双重 JSON 编码的字符串，需要 `json.loads(json.loads(r['value']))`。
- **境内站点不要用 CDP**：CDP 打开境内站点可能超时，优先直连或跳过。
- **GitHub releases 不要用 CDP**：JS 选择器 `a[href*="/releases/tag"]` 经常返回空数组。

### arXiv API

- **必须走代理**，直连会超时或被 rate limit：`curl -s --connect-timeout 15 -m 30 -x $PROXY "https://export.arxiv.org/api/query?..."`
- **⚠️ `run()` timeout 必须大于 curl `-m` 值**：`run()` 默认 `timeout=15`。如果 curl 用了 `-m 20` 或 `-m 30`，必须在 `run()` 调用中显式传 `timeout=N+5`（如 `timeout=25` 或 `timeout=35`）。否则 subprocess 会在 15s 杀掉 curl 进程，导致 `TimeoutExpired`。这是 `run-briefing.py` 中 arXiv 调用的已知陷阱 — 2026-07-08 因此失败两次。排查方法：`grep -n "run(.*-m " run-briefing.py`，对比所有 `-m N` 与 `timeout=` 参数。

### 运行环境

- 代理：`http://127.0.0.1:6789`（Clash Verge）
- CDP 端口：3456（Midscene browser automation）
- Python：`/opt/homebrew/bin/python3.11`

## HTML 样式设计

详见 `references/html-styling.md`。核心原则：深蓝底色 `#0b1120` + 50px 网格背景，每个板块包裹在独立的 section 容器中（padding + 渐变边框），卡片使用左侧 3px 彩色边框作为主要区分手段。各板块专属颜色：Trending=绿、GitHub=蓝、论文=紫、动态=天蓝、行业=橙。

## 文件结构

```
~/.hermes/skills/llm-daily-briefing/
├── SKILL.md                    # 本文档
├── scripts/
│   ├── run-briefing.py         # Phase 1：数据采集脚本（6 大数据源 → raw JSON）
│   ├── translate-sections.py   # Phase 2a：从 raw JSON 提取翻译任务清单
│   ├── translate-batches.py    # Phase 2b：将任务分组为小批次（每批 3-5 个）
│   ├── merge-batches.py        # Phase 2.5：合并各批次翻译结果到 enriched JSON
│   ├── generate-report.py      # Phase 3：读取 enriched/raw JSON → HTML 渲染
│   ├── merge-enriched.py       # ⚠️ 已废弃：旧版子 Agent 合并脚本
│   └── enrich-briefing.py      # ⚠️ 已废弃：旧版单 Agent 翻译脚本
├── references/
    ├── execution-notes.md      # 执行要点与陷阱
    ├── network-rules.md        # 网络代理规则
    ├── github-api-patterns.md  # GitHub API 连接、搜索、去重模式
    ├── trending-ai-filtering.md # Trending AI 相关性过滤 + 丰富介绍流程
    ├── html-styling.md         # HTML 报告 CSS 设计原则与样式规范
    └── release-notes-translation.md # Release notes 翻译流程（补充翻译 releases）
```

**输出文件**：
- `/tmp/llm-briefing-raw-YYYY-MM-DD.json` — 原始采集数据（Phase 1）
- `/tmp/llm-briefing-tasks-{DATE}.json` — 翻译任务清单（Phase 2a）
- `/tmp/llm-briefing-batches-{DATE}.json` — 翻译批次清单（Phase 2b）
- `/tmp/llm-briefing-batch-{N}.json` — 各批次翻译结果（Phase 2 逐个处理）
- `/tmp/llm-briefing-enriched-{DATE}.json` — 合并后的完整 enriched 数据（Phase 2.5）
- `/Users/zz/code/AI_Daily_Brief/docs/llm-briefing-YYYY-MM-DD.html` — 最终 HTML 报告（Phase 3）

## 关键陷阱（必读）

详见 `references/execution-notes.md`：

## 生成稳定性与内容质量门槛（必须验收）

### 官方动态：无浏览器依赖与日期真实性

- **Jina Reader 优先，CDP 仅作回退**：定时环境可能没有 `localhost:3456`，不得把官方动态采集完全依赖浏览器服务。对 OpenAI News、Anthropic News、Hugging Face Blog、ModelScope Blog、OpenRouter Blog，先用 Jina 列表页抓取；Jina 无结果时才尝试 CDP。
- **列表解析必须过滤噪声**：跳过 `Skip to ...`、`![Image ...]`、图片/CDN/视频链接、登录/订阅/定价/文档与栏目页。只保留实际文章链接，并对标题去除类别、日期和来源尾巴。
- **必须解析并保存发布日期**：不要把 Blog 的 `date` 留空。生成历史日报时，官方动态必须按 `BRIEF_DATE` 过滤（推荐保留当日和前一自然日的时区缓冲），绝不能拿“运行当天的最新文章”冒充历史日期内容。
- **空板块是失败信号**：采集后若 `blogs` 为 0，先检查 Jina 响应、过滤规则与链接解析；补充来源后才可生成报告。最终报告中至少应显示有效标题、来源、日期和中文摘要。

### 项目介绍：避免模板化翻译

每个 AI 相关项目介绍必须以 150–250 字说明：

1. **项目是什么**：类别、运行形态和所处生态；
2. **核心机制/能力**：用到的协议、模型、工作流或关键技术；
3. **解决的问题与适用对象**：为什么需要它、谁会使用、适合什么场景。

不得使用“开源项目 X，归属 Y 方向”“建议结合仓库文档”等通用套话，也不得将英文原始描述直接嵌入中文介绍。若仓库描述不足，先用 Jina 读取 README；必要时检索项目官网、GitHub Releases 或官方文档补充近期信息。Trending 中与 AI/LLM/Agent/ML 无直接关系的项目必须标记 `skip`，不能因为上榜而保留。

### 行业动态：标题与摘要必须对应原文

- 每条新闻必须有**简洁中文标题**与 80–120 字的**文章级摘要**，说明“发生了什么、关键机制/数据、为何值得关注”。
- 严禁使用“该动态来自…，聚焦 AI、模型或智能体进展”等来源级占位摘要；标题也不得保留“行业动态：英文标题”的前缀形式。
- Google News RSS 必须先经 Jina 解析 redirect，尽量读取真实文章来源或正文。若正文不可得，可基于标题和可验证的公开事实写谨慎摘要，不得臆造细节。

### 渲染前验收清单

在执行 `generate-report.py` 前和生成后分别检查：

- `github_trending`、`github`、`papers`、`blogs`、`news`、`hn` 的数量是否合理；
- 所有项目是否有非模板化 `desc_zh`，论文/Blog/新闻是否有 `title_zh` 和 `summary_zh`；
- HTML 不含“该动态来自”“聚焦 AI、模型或智能体进展”“建议结合仓库文档”等占位文本；
- 历史日期报告中的文章发布日期不得晚于报告日期（允许前一自然日时区缓冲）。

任何一项不满足时，应修复 raw/enriched 数据后重新渲染，不能把降级内容当成完成结果。

1. **GitHub API 使用 gh CLI** — `gh_run` 函数自动设置 `HTTPS_PROXY` 环境变量。旧方案（curl 直连+代理）已废弃但保留可回退。速率限制从 60 → 5000 req/h。
2. **GitHub Search API 返回类型检查** — 限速时可能返回 `list` 而非 `dict`，必须做 `isinstance(data, dict)` 检查
3. **Jina 抓不了 GitHub Releases 页面** — `/releases` 路径返回 403，但 `github.com/trending` 和 README 页面正常可用
4. **Trending 不做关键词过滤** — 全部 16-25 个项目交给 LLM 子 Agent 智能筛选，不再使用硬编码关键词列表
5. **Release body 必须清洗** — n8n 等项目包含 HTML 注释（`<!-- stage-rev -->`），不清洗会泄漏到摘要中
5. **arXiv API 必须走代理且 `run()` timeout 要匹配 curl `-m`** — 直连会超时/限流；`run()` 默认 timeout=15s，若 curl 用了 `-m 20` 或 `-m 30`，必须显式传 `timeout=N+5`（如 `timeout=35`）。否则 subprocess 先于 curl 超时，导致 `TimeoutExpired`。排查方法：`grep -n "run(.*-m " run-briefing.py` 逐一对照。
6. **境内站点直连** — 走代理可能超时
7. **cdp_eval 不要用 `-d` 直接传 JS** — 引号/换行会被 shell 破坏，用 tempfile + `--data-binary`
8. **Google News URL 不要用 CDP 打开** — redirect URL 太长会超时，用 Jina 提取真实 URL
9. **Blog/News 标题先清洗再翻译** — Jina 返回的标题常黏连日期和来源名
10. **文件先写 /tmp 再复制 docs 目录** — 沙箱无法直写 `~/code/AI_Daily_Brief/docs/`
12. **GitHub Trending 已不再使用 CDP** — 改用 Jina 抓取，不依赖浏览器环境，无需等待 JS 渲染
13. **GitHub Search API 查询字符串必须 URL 编码** — 用 `urllib.parse.quote(query)` 编码整个查询字符串，不要用 `+` 手动拼接。未编码的查询会导致静默返回 0 结果（HTTP 200 但 total_count: 0），不会报错，极难排查。详见 `references/github-api-patterns.md`。
14. **`seen_repos` 必须在脚本顶部加载** — 在 `results` 初始化后立即 `load_seen_repos()`，不要延迟到 GitHub section 内部加载。否则末尾的 `update_seen_repos` 调用会 NameError，且无法在多个 section 间共享。
15. **翻译必须逐批（每批 3-5 个项目）** — 不要一次性翻译整个板块（15+ 个项目），上下文过长会导致翻译截断或遗漏。旧方案（5 个子 Agent 各处理整个板块）已废弃，改用 `translate-sections.py` + `translate-batches.py` 拆分任务，逐个批次调用 LLM 翻译。**子 Agent 超时 fallback**：如果 delegate_task 翻译某批次超时（600s），不要重试 — 直接在 execute_code 中手动写翻译结果到 `/tmp/llm-briefing-batch-{N}.json`，继续后续批次。2026-07-08 batch-3 超时 600s（9 次 API 调用），手动补写后继续。
16. **`merge-batches.py` 中 raw JSON 的 section 名是复数，但 task_id 是单数** — raw JSON 使用 `papers`、`github_trending`、`blogs`，但 task_id 格式是 `paper-0`、`trending-0`、`blog-0`。合并时映射关系：`papers` → `paper-N`，`github_trending` → `trending-N`，`github` → `github-N`，`blogs` → `blog-N`，`news` → `news-N`，`hn` → `hn-N`。如果合并后某个板块的 `_zh` 字段全部缺失，大概率是 section 名映射错误。
17. **`generate-report.py` 的 enrich 函数不能覆盖已有的翻译** — `enrich_paper()`、blog 标题清洗、新闻标题翻译等函数在 enriched JSON 已存在翻译时，会错误地覆盖为兜底值。每个 enrich 函数开头必须加 `if item.get('title_zh') or item.get('desc_zh'): return` 守卫。同样，summary 渲染必须优先使用 `summary_zh`，降级到 `page_content`/`desc` 英文原文。
**`enrich_trending()` 特别守卫**：检查 `desc_zh` 长度，如果已有翻译且 > 80 字（说明来自翻译管道的丰富描述），直接 `return`，不再用本地字典覆盖。否则短描述会被覆盖为长描述，失去翻译价值。
18. **子 Agent 翻译时的 task_id 编号必须从 0 开始** — subagent 翻译时容易从 1 开始编号（如 `paper-1` 到 `paper-5`），但 merge 脚本期望 `paper-0` 到 `paper-4`。在翻译 prompt 中明确说明索引从 0 开始，或在合并前验证并修正编号。
19. **Trending AI 相关性过滤** — `translate-sections.py` 的 Trending prompt 要求 Agent 判断项目是否与 AI/LLM/Agent/ML 相关。不相关的项目输出 `{"skip": true, "reason": "原因"}`，`merge-batches.py` 会将 `_skip` 标记的项目从最终 enriched JSON 中过滤掉。避免非 AI 项目出现在报告中。
20. **Trending 描述必须丰富（150-250字）** — 翻译 prompt 明确要求不只直译，要结合项目知识补充背景、解决的问题、特点、适合谁用。`run-briefing.py` Phase 1.5 会用 Jina 抓取前 10 个 Trending 项目的 GitHub 页面，将 `page_content` 传入翻译 prompt 提供额外上下文。
21. **`merge-batches.py` 读取批次文件结构** — 每个批次文件（`/tmp/llm-briefing-batch-{N}.json`）的结构是 `{"batch_id": "...", "results": {"trending-0": {...}, ...}}`，翻译结果嵌套在 `results` 字段中。`merge-batches.py` 必须先取 `results` 再 `update`：`batch_results = batch_data.get('results', batch_data)`。如果直接 `json.load(f)` 后 `update`，会把 `batch_id`、`results` 等顶层键误认为 task_id，导致所有翻译丢失，enriched JSON 中 `_zh` 字段全部为空。2026-07-08 因此导致 43 个翻译全部未合并，重新生成报告才发现。验证方法：合并后检查 enriched JSON 中随机条目的 `_zh` 字段是否存在，若全为空则说明合并失败。
22. **Release notes 翻译不包含在标准流水线中** — 翻译管道（`translate-sections.py` + `translate-batches.py`）只翻译项目名、描述、论文、Blog 和新闻，**不翻译 GitHub releases 的 `summary` 字段**。`generate-report.py` 支持渲染 `release_highlights_zh`，但该字段需要手动补充翻译。流程见 `references/release-notes-translation.md`。当用户要求翻译版本迭代记录时，先收集 enriched JSON 中所有 `summary` 非空但 `release_highlights_zh` 为空的 release，分批（每批 3-5 条）翻译为中文，合并回 JSON 后重新生成 HTML。
23. **论文和官方动态可能为 0** — arXiv API 和 Blog 抓取（CDP/Jina）可能因网络或解析问题返回 0 条数据。生成报告前检查各板块数量，若论文或 Blog 为 0，需手动补充：
   - **论文**：`curl -s --connect-timeout 10 -m 20 -x $PROXY "https://export.arxiv.org/api/query?search_query=all:LLM&sortBy=submittedDate&sortOrder=descending&max_results=5"`，解析 XML 后追加到 `papers` 数组，手动翻译标题和摘要。
   - **官方动态**：用 Jina 抓取 OpenAI/Anthropic/HuggingFace/OpenRouter 的 Blog 列表页，提取最近 2-3 条有效文章标题，追加到 `blogs` 数组。注意 Jina 返回的标题可能黏连图片信息和日期，需清洗。
   - 补充后重新运行 `generate-report.py`。
24. **Jina Blog 列表解析陷阱** — Jina 抓取 Blog 列表页时，返回的 Markdown 包含图片行（`![Image X: ...]`）和日期黏连（`Core dump epidemiology... Engineering Jun 30, 2026`）。解析时必须：(1) 过滤 `images.ctfassets` 等 CDN 图片 URL；(2) 用正则去除 `Image \d+: ` 前缀；(3) 去除末尾的 `Category Mon DD, YYYY` 或开头的 `Mon DD, YYYY ` 日期；(4) 只保留 `title` 长度 > 10 且 URL 是有效文章链接（非图片）的条目。

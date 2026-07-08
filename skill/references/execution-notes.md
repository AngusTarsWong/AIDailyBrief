# 执行要点与陷阱

## cdp_eval 的 shell 引号问题

**问题**：`curl -d '{js_code}'` 中 JS 代码包含引号/换行时会被 shell 破坏。

**解决方案**：
```python
import tempfile
with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
    f.write(expr)
    f.flush()
    out = run(f"curl -s -X POST 'http://localhost:3456/eval?target={target_id}' --data-binary @{f.name}", timeout=timeout)
```

**返回格式**：CDP 返回的 `value` 字段是双重 JSON 编码：
```
{"value": "[\"tag1\", \"tag2\"]"}  # 需要 json.loads(json.loads(r['value']))
```

## Google News URL 处理

**问题**：Google News RSS 返回的 URL 是 redirect 链接，直接用 CDP 打开会超时（URL 太长）。

**解决方案**：
```python
# 用 Jina 抓 redirect URL，从响应中提取真实 URL
out = run(f'curl -s --connect-timeout 6 -m 8 -x {PROXY} "https://r.jina.ai/{raw_url}"', timeout=10)
url_match = re.search(r'URL Source: (https?://\S+)', out)
if url_match:
    real_url = url_match.group(1).strip()
```

## GitHub Releases Fallback

**API 重试机制**：`safe_api_get` 内置 2 次重试，指数退避（3s、6s）。连续限速后跳过 releases。

**不再使用 Jina fallback**：Jina 对 `github.com/{owner}/{repo}/releases` 路径返回 403 AbuseAlleviationError。

**但 Jina 可以抓取其他 GitHub 页面**：
- ✅ `github.com/trending` — 正常返回 Markdown（用于 Trending 采集）
- ✅ `github.com/{owner}/{repo}` — README 等内容可正常抓取
- ❌ `github.com/{owner}/{repo}/releases` — 403，不可用

**为什么不用 CDP 抓 Trending**：CDP 服务（端口 3456）不总是在线，且 JS 渲染慢、DOM 选择器可能随 GitHub 改版失效。Jina 更稳定。

**为什么不用 CDP 抓 Releases**：GitHub releases 页面的 JS 选择器 `a[href*="/releases/tag"]` 经常返回空数组。

## Release Body 清洗规则

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

**不同项目的 highlights 格式**：
- openclaw：`## ✨ Highlights` + `- **Feature:** description`（em dash 分隔）
- hermes-agent：`## ✨ Highlights`（二级标题！）+ `- **Title** — description`
- n8n：`### Bug Fixes` + `* **scope:** description`，body 中包含 HTML 注释
- AutoGPT：`### What's Changed` + `- #1234 - Feature description`
- superpowers：`- **Title.** description`（句号分隔）

提取逻辑：识别 highlights/Bug Fixes/Features/What's Changed 等区域 → 遍历 `- ` 或 `* ` 开头的行 → 提取改动描述 → 最多取 4 条。

## GitHub Search API 类型陷阱 ⚠️

GitHub Search API 在限速时**可能返回 `list` 类型**（而不是预期的 `{"message": "rate limit..."}` 字典）。

```python
# 错误做法：
data = json.loads(out)
for item in data.get('items', []):  # ❌ list 没有 .get() 方法

# 正确做法：
data = json.loads(out)
if isinstance(data, dict):
    for item in data.get('items', [])[:8]:
        # 正常处理
elif isinstance(data, list):
    # API 限速返回了 list，跳过或重试
    print(f"⚠️ API 返回 list 类型，跳过")
```

## generate-report.py 的 Release 渲染

HTML 报告中每个 release 以独立卡片展示：
```html
<div class="release-item">
  <span class="release-tag">🏷️ v2026.7.1-beta.2</span>
  <span class="release-date">2026-07-05</span>
  <div class="release-summary">OpenAI GPT-5.6 support；External harness attachment；...</div>
</div>
```
CSS 样式：绿色半透明背景 + 绿色边框 + 圆角。summary 用中文分号 `；` 连接多条 bullet。

## Jina Reader API 使用模式

```python
# 基本用法
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

## 三阶段流水线：Enriched JSON 模式

完整的流水线分为三个阶段，`generate-report.py` 需要优先读取 enriched JSON：

```python
# generate-report.py 的读取逻辑
import os
RAW_JSON = f"/tmp/llm-briefing-raw-{DATE_STR}.json"
ENRICHED_JSON = f"/tmp/llm-briefing-enriched-{DATE_STR}.json"
json_path = ENRICHED_JSON if os.path.exists(ENRICHED_JSON) else RAW_JSON
```

翻译逻辑只处理缺失 `desc_zh` 的条目（避免覆盖 LLM 翻译）：
```python
for p in raw.get('github', []):
    if not p.get('desc_zh'):
        p['desc_zh'] = translate_with_context(p.get('desc', ''), p.get('name', ''))
```

## 文件输出到桌面

Hermes 沙箱无法直接写入 `~/Desktop/`（macOS 沙箱权限）。脚本应：
1. 写入 `/tmp/` 目录（始终可用）
2. 用 `shutil.copy` 或终端 `cp` 复制到桌面

```python
import shutil, os
OUTPUT_TMP = f"/tmp/llm-briefing-{DATE_STR}.html"
OUTPUT = f"/Users/zz/Desktop/llm-briefing-{DATE_STR}.html"

with open(OUTPUT_TMP, 'w') as f:
    f.write(body)

try:
    shutil.copy(OUTPUT_TMP, OUTPUT)
except Exception as e:
    # 降级：终端中用 cp
    pass
```

## 子 Agent 并行架构（Phase 2 新模式）

**为什么拆分**：原 Phase 2 单 Agent 处理所有 6 个板块，长上下文导致翻译不完整、信息丢失。

**新架构**：5 个并行子 Agent，每个专注一个板块：
- 子 Agent 输出：`/tmp/llm-briefing-enriched-{section}-{DATE}.json`
- 合并脚本：`merge-enriched.py` 读取 raw JSON + 各 enriched section → 输出 `/tmp/llm-briefing-enriched-{DATE}.json`
- **降级机制**：若某板块子 Agent 失败/缺失，merge 脚本自动用 raw JSON 中对应板块填充

**Cron Job 流程**：
1. `run-briefing.py` → raw JSON
2. `delegate_task` 启动 5 个并行子 Agent（tasks 模式）
3. `merge-enriched.py` → merged enriched JSON
4. `generate-report.py` → HTML

## arXiv API 超时处理

arXiv API 走代理时偶尔会超时（`TimeoutExpired after 15s`），即使代理配置正确。这是网络不稳定导致的，非脚本问题。

**缓解策略**：
- `run-briefing.py` 的 arXiv 请求 timeout 已设为 20s（curl `-m 20`）
- 如果 arXiv 失败，脚本会中断，但 raw JSON 可能已部分写入
- 后续流程（merge-enriched + generate-report）支持降级读取，即使 arXiv 板块为空也能正常渲染 HTML
- 建议：arXiv timeout 时可适当增加 `-m` 值到 30s，或重试一次

## Blog 数据源更新（Anthropic）

Anthropic 的 Blog 已从 `/blog` 迁移到 `/research`：
```python
{'name': 'Anthropic', 'url': 'https://www.anthropic.com/research', 'pattern': '/research/'}
```

## 境内站点处理

- 魔搭 ModelScope 等境内站点**不要走代理**
- CDP 打开境内站点可能超时，优先直连或跳过

## Blog/News 标题清洗正则

Jina 返回的标题常黏连日期和来源名，翻译前必须清洗：

```python
def clean_blog_title(title):
    # 去掉末尾英文日期（Jun 25, 2026）
    title = re.sub(r'\s*(Jun|Jul|May|Apr|Mar|Feb|Jan|Dec|Nov|Oct|Sep|Aug)\s+\d{1,2},?\s+\d{4}\s*$', '', title)
    # 去掉中文日期（2026年6月30日）
    title = re.sub(r'\s*\d{4}年\d{1,2}月\d{1,2}日\s*$', '', title)
    # 去掉来源名（- Help Net Security | The HIPAA Journal 等）
    title = re.sub(r'\s*[-|]\s*(Help Net Security|Techzine Global|Axios|The HIPAA Journal|The Verge|Tom\'s Guide)\s*$', '', title)
    return title.strip()
```

翻译字典匹配用**双向模糊匹配**：
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

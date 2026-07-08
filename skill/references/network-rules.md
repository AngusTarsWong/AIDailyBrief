# 网络代理规则

## 核心原则

**GitHub API 必须直连，不走代理！** 未认证 API 对直连 IP 宽松（60次/小时），但走 Clash 代理后代理 IP 被共享限速，极易爆 403。

## 完整代理策略表

| 目标 | 代理策略 | curl 示例 | 原因 |
|------|---------|-----------|------|
| **GitHub API** (`api.github.com`) | **直连** | `curl -s --connect-timeout 8 -m 10 "https://api.github.com/..."` | 代理 IP 被共享限速，直连反而稳定 |
| **GitHub Search API** | **直连** | `curl -s --connect-timeout 15 -m 20 "https://api.github.com/search/repositories?..."` | 同上；⚠️ 限速时可能返回 `list` 类型而非 `dict` |
| **Jina Reader** (`r.jina.ai`) | 走代理 | `curl -s --connect-timeout 8 -m 12 -x $PROXY "https://r.jina.ai/{url}"` | 境外站点 |
| **Jina 抓 GitHub 页面** | ❌ 不可用 | — | Jina 对 github.com 返回 403 AbuseAlleviationError（"DDoS attack suspected"） |
| **arXiv API** (`export.arxiv.org`) | **走代理** | `curl -s --connect-timeout 10 -m 20 -x $PROXY "https://export.arxiv.org/..."` | 直连会超时 |
| **Google News** (`news.google.com`) | 走代理 | `curl -s --connect-timeout 15 -x $PROXY "https://news.google.com/rss/..."` | 境外站点 |
| **境内站点**（魔搭 ModelScope 等） | 直连 | `curl -s --connect-timeout 10 -m 15 "https://modelscope.cn/..."` | 更快更稳定，走代理可能超时 |

## GitHub API 限速表现

1. **直连限速**：返回 `{"message": "API rate limit exceeded...", "documentation_url": "..."}`（标准 JSON）
2. **代理限速**：同样返回上述 JSON，但频率更高（代理 IP 被大量用户共享）
3. **极端情况**：Search API 可能返回 `list` 类型而非 `dict`（可能是 GitHub 的异常响应）

**应对策略**：
- 所有 GitHub API 请求统一用 `safe_api_get()` 函数，自动检测限速并**重试 2 次**（指数退避 3s/6s）
- 连续 3 次仍限速时跳过 releases 抓取（Jina fallback 也不可靠）
- `safe_api_get` 的 retry 参数可调整，默认 2 次

## Jina Reader API 注意事项

- 对 **github.com** 域名：返回 403 AbuseAlleviationError，**不可用**
- 对大多数境外站点：正常工作
- 超时建议：`--connect-timeout 8 -m 12`
- 仅抓取前 15 行正文，避免响应过大

## 境内站点处理

以下站点应直连，不走代理：
- 魔搭 ModelScope (`modelscope.cn`)
- 其他 `.cn` 域名或已知的境内服务

CDP 打开境内站点可能超时，建议：
- 优先用 curl 直接抓取
- 或用 `safe_api_get()` 尝试 API
- 实在不行就跳过该条目

## 代理配置

```bash
PROXY="http://127.0.0.1:6789"  # Clash Verge
```

**走代理的 curl 命令**：`curl -s -x $PROXY "URL"`
**直连的 curl 命令**：`curl -s "URL"`（不加 `-x` 参数）

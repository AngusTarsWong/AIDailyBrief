# AI Daily Brief (AI 每日日报)

一个自动化的基于大语言模型与 Agent 技术的资讯收集 Skill，每天重点收集最新的 LLM 与 Agent 落地相关的开源项目、各家大模型厂商的最新动态、前沿论文和行业新闻。通过 AI 的深度参与（提取、过滤、翻译与丰富），大幅提升获取前沿技术资讯的效率。本项目也会定期将生成的日报报告归档，方便直接查看。

## 项目特点

- **多数据源聚合**：包含 GitHub Trending、GitHub 热门项目（动态搜索策略）、arXiv 最新论文、Hacker News、Google News 以及各主流大模型厂商（OpenAI, Anthropic 等）的官方博客。
- **全自动流水线**：从数据采集、多批次并发智能翻译与信息增强，到合并渲染生成深色主题的 HTML 报告，完全自动化。
- **高质量内容**：结合 LLM 进行上下文翻译，对 GitHub Trending 等条目进行 AI 相关性过滤并由大模型基于 README 等上下文撰写丰富的项目介绍。
- **宁多勿少**：内容详尽，涵盖项目背景、核心特性、最新 Releases 版本改动等信息。

## 目录结构

自动化 Skill 代码存放在 `skill/` 目录下（迁移自 Hermes 项目）：

```text
.
├── README.md                   # 本文档
└── skill/                      # 核心自动化执行逻辑
    ├── SKILL.md                # Skill 的详细说明与执行逻辑设计
    ├── scripts/                # 各阶段的执行脚本
    │   ├── run-briefing.py         # Phase 1: 数据采集，生成 raw JSON
    │   ├── translate-sections.py   # Phase 2a: 提取翻译任务清单
    │   ├── translate-batches.py    # Phase 2b: 将任务分组为小批次，交由 Agent 翻译
    │   ├── merge-batches.py        # Phase 2.5: 合并各批次翻译结果
    │   └── generate-report.py      # Phase 3: 生成 HTML 报告
    └── references/             # 执行模式、网络规则、样式设计等参考文档
```

## 执行流程

整个自动化流程分为三大阶段：

1. **Phase 1 - 数据采集 (`run-briefing.py`)**
   只负责从各数据源采集原始数据并保存为 `raw JSON`。不对数据做任何翻译或信息增强。
   *(此阶段会使用 Jina Reader 抓取 GitHub 页面和利用 `gh` CLI 调用 GitHub API)*

2. **Phase 2 - 逐批翻译与合并 (`translate-*.py` & `merge-batches.py`)**
   为避免大上下文导致翻译截断或遗漏，系统会将所有待翻译条目拆分为 3-5 个一组的小批次。
   - 利用 Agent 逐批次调用大模型进行上下文相关的专业翻译。
   - 合并所有的翻译结果，生成 `enriched JSON`。

3. **Phase 3 - 报告生成 (`generate-report.py`)**
   读取最终的增强数据，渲染出精美的深色主题卡片式 HTML 报告，包含各板块分类、Trending 置顶以及统计数据。最终生成的 HTML 会自动保存输出。

## 如何使用

建议配置定时任务（如每天上午 9 点）自动执行。详细的依赖配置与执行规则请参考 [`skill/SKILL.md`](./skill/SKILL.md)。

基本执行流：
```bash
# 1. 采集数据
python3 ./skill/scripts/run-briefing.py

# 2. 生成并执行翻译任务
python3 ./skill/scripts/translate-sections.py
python3 ./skill/scripts/translate-batches.py

# 3. 合并翻译
python3 ./skill/scripts/merge-batches.py

# 4. 生成报告
python3 ./skill/scripts/generate-report.py
```

## 注意事项

- 运行此 Skill 依赖于特定的网络代理规则（如 GitHub API、arXiv 需走代理，国内站点直连等，请参考 `skill/references/network-rules.md`）。
- 使用了 GitHub 的 API，推荐在运行环境中配置好 `gh` CLI 并完成认证。

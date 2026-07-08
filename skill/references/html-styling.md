# HTML 报告样式设计

## 设计原则

用户反馈：早期版本背景太深（纯黑/深紫渐变），卡片与背景区分度不够，内容区域难以区分。

**核心设计目标**：提升板块间和卡片间的视觉区分度，同时保持科技感的深色主题。

## 背景层设计

```css
/* 页面背景：深蓝底色 + 科技感网格 + 光晕 */
body {
  background: #0b1120;  /* 纯深蓝底，不用渐变 */
}
body::before {
  background:
    radial-gradient(ellipse 80% 50% at 50% -20%, rgba(56, 189, 248, 0.08), transparent),  /* 顶部蓝色光晕 */
    radial-gradient(ellipse 60% 40% at 80% 60%, rgba(139, 92, 246, 0.06), transparent),  /* 右侧紫色光晕 */
    repeating-linear-gradient(0deg, transparent, transparent 49px, rgba(148, 163, 184, 0.03) 49px, rgba(148, 163, 184, 0.03) 50px),  /* 网格横线 */
    repeating-linear-gradient(90deg, transparent, transparent 49px, rgba(148, 163, 184, 0.03) 49px, rgba(148, 163, 184, 0.03) 50px);  /* 网格竖线 */
}
```

**要点**：
- 页面底色用 `#0b1120`（深蓝）而非纯黑，提供基础深度
- 网格线（50px 间距）提供刻度感，增加科技氛围
- 顶部和右侧的光晕提供空间深度，避免平面感

## 板块容器（Section）

每个数据源板块（Trending、GitHub、论文、动态、新闻）都包裹在独立的 section 容器中：

```css
.section {
  margin-bottom: 2rem;
  padding: 1.2rem;
  border-radius: 20px;
  position: relative;
}
/* 渐变边框效果 */
.section::before {
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
}
```

**要点**：
- section 有独立的 padding 和圆角，形成物理分隔
- 渐变边框（mask-composite: xor 技巧）提供微妙的边界感
- 每个板块之间有明显的视觉间隔

## 卡片设计（核心区分度来源）

### 左侧彩色边框

所有卡片使用 `border-left: 3px solid` 作为主要区分手段：

```css
.card {
  background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(30, 41, 59, 0.6));
  border: 1px solid rgba(96, 165, 250, 0.12);
  border-left: 3px solid rgba(96, 165, 250, 0.4);
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
```

### 板块专属颜色（CSS :has 选择器）

```css
/* 根据 section 内的标题类型，自动调整卡片左边框颜色 */
.section:has(.sh.trending) .card { border-left-color: rgba(52, 211, 153, 0.5); }
.section:has(.sh.paper) .card { border-left-color: rgba(167, 139, 250, 0.5); }
/* blog-card 和 news-card 直接在内联样式中设置各自的 border-left-color */
```

| 板块 | 左边框颜色 | hover 颜色 |
|------|-----------|-----------|
| 🔥 Trending | `#34d399`（绿色） | `#34d399` |
| 🚀 GitHub | `#60a5fa`（蓝色） | `#60a5fa` |
| 📄 论文 | `#a78bfa`（紫色） | `#a78bfa` |
| 📢 动态 | `#38bdf8`（天蓝） | `#38bdf8` |
| 🏭 行业 | `#fb923c`（橙色） | `#fb923c` |

### Hover 效果

从 `translateY` 改为 `translateX`：

```css
.card:hover {
  transform: translateX(4px);  /* 向右滑动，左侧边框变亮 */
  border-left-color: #60a5fa;   /* 或对应板块颜色 */
  box-shadow: 0 4px 16px rgba(96, 165, 250, 0.1);
}
```

## 其他细节

- **标题渐变**：`#38bdf8 → #818cf8 → #c084fc` 三色渐变
- **标签**：缩小尺寸，降低透明度（`rgba(x, 0.08)` 背景 + `rgba(x, 0.15)` 边框）
- **正文颜色**：`#cbd5e1`（描述）、`#94a3b8`（摘要）、`#64748b`（日期/次要信息）
- **字体**：增加 "Noto Sans SC" 改善中文渲染
- **底部统计数字**：渐变色 `#60a5fa → #a78bfa`

## 移动端适配

```css
@media(max-width:640px) {
  .section { padding: 1rem 0.8rem; }  /* 减少板块内边距 */
  .card { padding: 1rem 1.1rem; }     /* 减少卡片内边距 */
}
```

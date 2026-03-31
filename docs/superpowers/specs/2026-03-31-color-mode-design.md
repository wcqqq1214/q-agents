# 涨跌色模式切换 Design Spec

**Date:** 2026-03-31  
**Status:** Approved

## Problem

中国用户习惯"红涨绿跌"，而系统默认使用西方惯例"绿涨红跌"。需要在设置页面提供切换选项，并持久化用户偏好。

## Approach

CSS 变量覆盖 + React Context。在 `<html>` 上切换 `.cn-mode` class，通过 CSS 变量覆盖实现颜色反转，业务组件零改动。

## Architecture

### 新增文件

- `frontend/src/components/providers/TrendColorProvider.tsx` — Context + localStorage 持久化
- `frontend/src/hooks/use-trend-color.ts` — 消费 Context 的 hook

### 修改文件

- `frontend/src/app/globals.css` — 新增 `.cn-mode` CSS 变量覆盖
- `frontend/src/app/layout.tsx` — 注册 TrendColorProvider + 注入防闪烁 blocking script
- `frontend/src/app/settings/page.tsx` — 新增 Display Preferences Card

## CSS Variables

`.cn-mode` class 覆盖以下变量（红涨绿跌）。选择器权重 `(0,1,0)`，足以覆盖 `:root` 默认值：

```css
.cn-mode {
  --chart-up: 0 84.2% 60.2%;
  --chart-down: 142.1 76.2% 36.3%;
  --chart-up-js: hsl(0deg, 84.2%, 60.2%);
  --chart-down-js: hsl(142.1deg, 76.2%, 36.3%);
  --chart-up-js-alpha: hsla(0deg, 84.2%, 60.2%, 0.6);
  --chart-down-js-alpha: hsla(142.1deg, 76.2%, 36.3%, 0.6);
}
```

Dark mode 使用 `.dark.cn-mode`（无空格，同时拥有两个 class 的 `<html>` 元素），权重 `(0,2,0)` 大于单独的 `.dark (0,1,0)`，确保正确覆盖：

```css
.dark.cn-mode {
  --chart-up: 0 72.2% 50.6%;
  --chart-down: 142.1 70.6% 45.3%;
  --chart-up-js: hsl(0deg, 72.2%, 50.6%);
  --chart-down-js: hsl(142.1deg, 70.6%, 45.3%);
  --chart-up-js-alpha: hsla(0deg, 72.2%, 50.6%, 0.6);
  --chart-down-js-alpha: hsla(142.1deg, 70.6%, 45.3%, 0.6);
}
```

## TrendColorProvider

命名采用 `TrendColor` 而非 `ColorMode`，避免与深浅色模式（Dark/Light Mode）混淆。

```tsx
type TrendMode = "western" | "chinese";

interface TrendColorContextValue {
  trendMode: TrendMode;
  setTrendMode: (mode: TrendMode) => void;
}
```

- 挂载时从 `localStorage.getItem("trend-color-mode")` 读取，默认 `"western"`
- 切换时写入 localStorage，并在 `document.documentElement` 上 toggle `.cn-mode` class
- SSR 阶段初始渲染用默认值，`useEffect` 后同步（配合 blocking script 消除 FOUC）

## 防 FOUC Blocking Script

在 `layout.tsx` 的 `<head>` 中注入内联 `<script>`，在 DOM 解析前同步执行：

```html
<script dangerouslySetInnerHTML={{ __html: `
  try {
    var m = localStorage.getItem('trend-color-mode');
    if (m === 'chinese') document.documentElement.classList.add('cn-mode');
  } catch(e) {}
` }} />
```

此脚本在 CSS 加载后、React hydration 前执行，确保首屏渲染时颜色已正确。

## Settings UI

在 Settings 页面新增 Card：

- **CardTitle:** Display Preferences（显示偏好）
- **CardDescription:** 配置图表涨跌颜色习惯
- 内含 shadcn `Switch` 组件
- Label: 涨跌色模式
- 关闭状态: 🌍 绿涨红跌（Western）
- 开启状态: 🇨🇳 红涨绿跌（Chinese）

## Data Flow

```
blocking script (同步) ──→ <html class="cn-mode"> (首屏无闪烁)
                                    ↑
localStorage ──→ TrendColorProvider (Context) ──→ setTrendMode()
                                    ↓
                         CSS variables 自动覆盖
                                    ↓
              KLineChart / StockCard / .text-chart-up/down
```

## Scope

- 不改动后端
- 不改动 KLineChart 或 StockCard 业务逻辑
- 不影响深色/浅色主题切换
- 不需要新增 API 端点

## Affected Files Summary

| File | Change |
|------|--------|
| `globals.css` | 新增 `.cn-mode` 和 `.dark.cn-mode` CSS 变量覆盖 |
| `TrendColorProvider.tsx` | 新建，Context + localStorage |
| `use-trend-color.ts` | 新建，消费 hook |
| `layout.tsx` | 注册 TrendColorProvider + 注入防闪烁 blocking script |
| `settings/page.tsx` | 新增 Display Preferences Card |

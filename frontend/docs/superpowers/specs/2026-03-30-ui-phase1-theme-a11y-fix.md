# Phase 1: 主题与 A11y 修复设计文档

**日期**: 2026-03-30  
**状态**: 设计已批准，待实施  
**范围**: UI Review Phase 1 - 主题生态与色彩适配 + 可访问性修复

## 概述

本设计文档描述了前端 UI 审计报告中 Phase 1 的修复方案，主要解决两个核心问题：

1. **主题系统一致性** - 清理所有硬编码的十六进制颜色值，建立基于 CSS 变量的涨跌颜色系统
2. **可访问性（A11y）** - 修复缺失和不规范的 ARIA 标签

## 目标

- 移除所有 `#` 十六进制硬编码颜色
- 移除所有 `text-green-500` / `text-red-500` 等非语义化 Tailwind 类名
- 建立全局统一的涨跌颜色变量系统（`--chart-up` / `--chart-down`）
- 确保图表在主题切换时能够正确重绘
- 为所有仅含图标的交互按钮添加 `aria-label`
- 将中文 ARIA 标签改为英文

## 技术约束

- 项目使用 **Tailwind CSS v4**，配置通过 `@theme inline` 在 CSS 中完成
- 不存在 `tailwind.config.ts` 文件
- 使用 `next-themes` 进行主题管理
- 图表库为 `lightweight-charts`（基于 Canvas，需要手动触发重绘）

## 设计详情

### 1. CSS 变量系统扩展

**文件**: `frontend/src/app/globals.css`

#### 1.1 在 `:root` 块中添加（浅色模式）

```css
:root {
  /* 现有变量... */
  --chart-up: 142.1 76.2% 36.3%; /* green-500 */
  --chart-down: 0 84.2% 60.2%; /* red-500 */
}
```

#### 1.2 在 `.dark` 块中添加（暗黑模式）

```css
.dark {
  /* 现有变量... */
  --chart-up: 142.1 70.6% 45.3%; /* green-400，提高亮度以改善对比度 */
  --chart-down: 0 72.2% 50.6%; /* red-400 */
}
```

#### 1.3 在 `@theme inline` 块中注册

```css
@theme inline {
  /* 现有变量... */
  --color-chart-up: hsl(var(--chart-up));
  --color-chart-down: hsl(var(--chart-down));
}
```

**关键技术细节**：

- `:root` 和 `.dark` 中定义的是**裸露的 HSL 通道值**（无 `hsl()` 包装），以支持透明度修饰符（如 `text-chart-up/50`）
- `@theme inline` 中必须用 `hsl()` 包装，否则 Tailwind 编译出的 CSS 会是非法的（`color: 142.1 76.2% 36.3%;`）
- 暗黑模式使用 400 色阶而非 500，避免高饱和度在暗色背景下造成视觉疲劳

**使用方式**：

- Tailwind 类名：`text-chart-up`、`bg-chart-down`、`text-chart-up/50`
- CSS 变量：`hsl(var(--chart-up))`、`hsl(var(--chart-up) / 0.6)`

### 2. KLineChart.tsx 硬编码颜色清理

**文件**: `frontend/src/components/chart/KLineChart.tsx`

#### 2.1 导入主题钩子

在文件顶部添加：

```typescript
import { useTheme } from "next-themes";
```

在组件内部获取主题状态：

```typescript
export function KLineChart({ selectedStock, assetType }: KLineChartProps) {
  const { resolvedTheme } = useTheme();
  // ... 其他状态
```

#### 2.2 颜色替换清单

| 位置                        | 原值                           | 新值                                                       |
| --------------------------- | ------------------------------ | ---------------------------------------------------------- |
| Line 222 (textColor)        | `'#d1d5db'`                    | `'hsl(var(--muted-foreground))'`                           |
| Line 225-226 (grid)         | `'#334155'`                    | `'hsl(var(--border))'`                                     |
| Line 229, 254 (borderColor) | `'#334155'`                    | `'hsl(var(--border))'`                                     |
| Line 260 (upColor)          | `'#22c55e'`                    | `'hsl(var(--chart-up))'`                                   |
| Line 261 (downColor)        | `'#ef4444'`                    | `'hsl(var(--chart-down))'`                                 |
| Line 262 (wickUpColor)      | `'#22c55e'`                    | `'hsl(var(--chart-up))'`                                   |
| Line 263 (wickDownColor)    | `'#ef4444'`                    | `'hsl(var(--chart-down))'`                                 |
| Line 313 (volume up)        | `'rgba(34, 197, 94, 0.6)'`     | `'hsl(var(--chart-up) / 0.6)'`                             |
| Line 313 (volume down)      | `'rgba(239, 68, 68, 0.6)'`     | `'hsl(var(--chart-down) / 0.6)'`                           |
| Line 341 (legend color)     | `isUp ? '#22c55e' : '#ef4444'` | `isUp ? 'hsl(var(--chart-up))' : 'hsl(var(--chart-down))'` |

#### 2.3 主题切换响应机制

在图表创建/更新的 `useEffect` 依赖数组中添加 `resolvedTheme`：

```typescript
useEffect(() => {
  // ... 图表创建和配置逻辑
}, [ohlcData, resolvedTheme]); // 添加 resolvedTheme 依赖
```

**Canvas 重绘机制说明**：

- Canvas API 原生支持解析包含 CSS 变量的颜色字符串（如 `'hsl(var(--chart-up))'`）
- 但 Canvas 是位图，不会自动响应 CSS 变量值的变化
- 当用户切换主题时，`resolvedTheme` 变化会触发 `useEffect` 重新执行
- `useEffect` 会销毁旧图表实例并创建新实例，从而应用新的颜色值

### 3. StockCard.tsx 涨跌颜色语义化

**文件**: `frontend/src/components/stock/StockCard.tsx`

#### 3.1 修改位置（Line 17）

**原代码**：

```typescript
const changeColor =
  stock.change === undefined
    ? "text-muted-foreground"
    : isPositive
      ? "text-green-500"
      : "text-red-500";
```

**修改为**：

```typescript
const changeColor =
  stock.change === undefined
    ? "text-muted-foreground"
    : isPositive
      ? "text-chart-up"
      : "text-chart-down";
```

**效果**：

- 股票卡片的涨跌颜色与 K 线图保持完全一致
- 自动支持主题切换（浅色模式 green-500/red-500，暗黑模式 green-400/red-400）
- 未来如需调整涨跌颜色（如支持美股红涨绿跌），只需修改 `globals.css` 中的变量定义

---

### 4. ARIA 标签修复

#### 4.1 ThemeToggle.tsx

**文件**: `frontend/src/components/layout/ThemeToggle.tsx`

**修改位置**：Line 23, 36

**原代码**：

```typescript
aria-label="切换主题"  // 未挂载时
aria-label={isDark ? '切换到浅色模式' : '切换到暗黑模式'}  // 挂载后
```

**修改为**：

```typescript
aria-label="Toggle theme"  // 未挂载时
aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}  // 挂载后
```

#### 4.2 ChatPanel.tsx

**文件**: `frontend/src/components/chat/ChatPanel.tsx`

**修改位置**：Line 111-117

**原代码**：

```typescript
<Button
  type="submit"
  size="icon"
  disabled={!selectedStock || !query.trim() || isAnalyzing}
>
  <Send className="h-4 w-4" />
</Button>
```

**修改为**：

```typescript
<Button
  type="submit"
  size="icon"
  disabled={!selectedStock || !query.trim() || isAnalyzing}
  aria-label="Send analysis query"
>
  <Send className="h-4 w-4" />
</Button>
```

#### 4.3 AssetSelector.tsx

**文件**: `frontend/src/components/asset/AssetSelector.tsx`

**修改位置**：Line 113-121

**原代码**：

```typescript
<Button
  variant="ghost"
  size="icon"
  className="h-6 w-6"
  onClick={() => fetchQuotes(true)}
  disabled={refreshing}
>
  <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
</Button>
```

**修改为**：

```typescript
<Button
  variant="ghost"
  size="icon"
  className="h-6 w-6"
  onClick={() => fetchQuotes(true)}
  disabled={refreshing}
  aria-label="Refresh quotes"
>
  <RefreshCw className={cn('h-3 w-3', refreshing && 'animate-spin')} />
</Button>
```

**额外修复**：同时修复了模板字符串拼接类名的问题，改用 `cn()` 工具函数。

---

## 验收标准

### 功能验收

1. **主题切换测试**
   - [ ] 在浅色模式下，K 线图涨跌颜色为 green-500/red-500
   - [ ] 在暗黑模式下，K 线图涨跌颜色为 green-400/red-400
   - [ ] 切换主题时，图表立即重绘并应用新颜色
   - [ ] 股票卡片的涨跌颜色与图表保持一致

2. **颜色一致性测试**
   - [ ] 全局搜索 `#` 十六进制颜色，确认前端代码中无残留
   - [ ] 全局搜索 `text-green-500` 和 `text-red-500`，确认已全部替换
   - [ ] 股票卡片和 K 线图的涨跌颜色视觉上完全一致

3. **可访问性测试**
   - [ ] 使用屏幕阅读器测试主题切换按钮，能正确朗读英文标签
   - [ ] 使用屏幕阅读器测试聊天发送按钮，能识别为 "Send analysis query"
   - [ ] 使用屏幕阅读器测试刷新按钮，能识别为 "Refresh quotes"
   - [ ] 使用键盘 Tab 键导航，所有按钮都能正确获得焦点

### 代码质量验收

- [ ] 所有修改的文件通过 ESLint 检查
- [ ] 所有修改的文件通过 TypeScript 类型检查
- [ ] 无 console 警告或错误
- [ ] 代码格式符合项目规范

---

## 实施顺序

建议按以下顺序实施，以便逐步验证：

1. **CSS 变量定义**（`globals.css`）
   - 先定义变量，确保 Tailwind 能正确编译

2. **StockCard.tsx**（最简单的修改）
   - 验证 `text-chart-up/down` 类名是否生效

3. **KLineChart.tsx**（最复杂的修改）
   - 逐个替换颜色值
   - 添加主题切换响应机制
   - 测试主题切换是否正常

4. **ARIA 标签修复**（独立的修改）
   - ThemeToggle.tsx
   - ChatPanel.tsx
   - AssetSelector.tsx

---

## 风险与注意事项

### 潜在风险

1. **Canvas 颜色解析兼容性**
   - 风险：部分旧版浏览器可能不支持 Canvas 解析 CSS 变量
   - 缓解：项目使用现代浏览器，风险较低

2. **主题切换性能**
   - 风险：图表重绘可能导致短暂的闪烁
   - 缓解：lightweight-charts 重绘速度很快，用户体验影响可接受

### 注意事项

1. **不要修改 `globals.css` 中现有的变量定义**，只添加新的 `--chart-up/down` 变量
2. **确保 `useEffect` 依赖数组正确**，避免无限重绘循环
3. **测试时使用真实的主题切换**，而不是浏览器开发者工具的强制暗黑模式

---

## 后续工作

Phase 1 完成后，可以继续进行：

- **Phase 2**: 桌面端流式布局优化（移除硬编码高度，使用 Flex/Grid）
- **Phase 3**: 代码质量提升与工具链配置（Prettier 插件、空状态处理）

---

## 参考资料

- [Tailwind CSS v4 文档](https://tailwindcss.com/docs)
- [shadcn/ui 主题系统](https://ui.shadcn.com/docs/theming)
- [WCAG 2.1 ARIA 标签指南](https://www.w3.org/WAI/WCAG21/Understanding/)
- [lightweight-charts API 文档](https://tradingview.github.io/lightweight-charts/)

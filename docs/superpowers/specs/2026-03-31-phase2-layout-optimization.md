# Phase 2: 桌面端流式布局优化设计文档

**日期**: 2026-03-31  
**状态**: 设计中  
**范围**: UI Review Phase 2 - 移除硬编码高度/宽度，建立流式响应式布局

## 概述

本设计文档描述了前端 UI 审计报告中 Phase 2 的修复方案，主要解决两个核心问题：

1. **页面级硬编码尺寸** - page.tsx 中使用了 `h-[40%]`, `w-[35%]`, `h-[calc(100vh-8rem)]` 等魔法数字
2. **图表固定高度** - KLineChart.tsx 中硬编码 `height: 400`，且使用 `window.resize` 无法捕获容器级别的尺寸变化

## 目标

- 移除所有硬编码的百分比高度和宽度
- 使用 Flexbox 语义化比例（`basis-2/5`, `basis-3/5`）
- 引入 `min-h-0` 和 `min-w-0` 防止 Flex 子元素撑破容器
- 使用 `ResizeObserver` 替代 `window.resize` 实现精准的容器级尺寸监听
- 图表高度从 `clientHeight` 动态获取，完全自适应父容器

## 技术约束

- 项目使用 **Tailwind CSS v4**
- 使用 **lightweight-charts** 库（基于 Canvas）
- 必须保持现有的视觉比例（资产选择器 40%，图表 60%，聊天面板 33%）
- 需要支持侧边栏展开/折叠等局部容器尺寸变化


## 设计详情

### 1. page.tsx 布局优化

**文件**: `frontend/src/app/page.tsx`

#### 1.1 当前问题

```tsx
// 问题 1: 硬编码的 calc 高度
<div className="flex gap-4 h-[calc(100vh-8rem)]">

// 问题 2: 硬编码的百分比高度
<div className="h-[40%] overflow-y-auto">

// 问题 3: 硬编码的百分比宽度
<div className="w-[35%] border-l overflow-hidden flex flex-col">
```

**痛点：**
- 在不同屏幕尺寸下容易出现溢出或比例失调
- `h-[40%]` 这种写法不符合 Tailwind 规范（应使用 `basis-2/5`）
- 缺少 `min-h-0` 导致 Flex 子元素可能撑破容器

#### 1.2 优化方案

**核心改动：**

1. **左侧面板添加 `min-w-0`**
   ```tsx
   <div className="flex-1 flex flex-col gap-4 overflow-hidden min-w-0">
   ```
   - 防止内部内容撑破 Flex 布局

2. **资产选择器使用 `basis-2/5` + `min-h-0`**
   ```tsx
   <div className="basis-2/5 min-h-0 overflow-y-auto">
   ```
   - `basis-2/5` = 40% 弹性占比（Tailwind 语义化写法）
   - `min-h-0` 允许内部滚动而不撑破外层容器

3. **图表区域使用 `basis-3/5` + `min-h-0`**
   ```tsx
   <div className="basis-3/5 min-h-0 overflow-hidden">
   ```
   - `basis-3/5` = 60% 弹性占比

4. **聊天面板使用 `w-1/3` + `shrink-0`**
   ```tsx
   <div className="w-1/3 shrink-0 border-l pl-4 overflow-hidden flex flex-col">
   ```
   - `w-1/3` = 33.3% 宽度（标准 Tailwind 类名）
   - `shrink-0` 防止被左侧面板挤压


### 2. KLineChart.tsx 图表自适应优化

**文件**: `frontend/src/components/chart/KLineChart.tsx`

#### 2.1 当前问题

```tsx
// 问题 1: 硬编码的图表高度
const chart = createChart(chartContainerRef.current, {
  width: chartContainerRef.current.clientWidth,
  height: 400,  // ❌ 固定 400px
  // ...
});

// 问题 2: 使用 window.resize 监听
const handleResize = () => {
  if (chartRef.current && chartContainerRef.current) {
    chartRef.current.applyOptions({
      width: chartContainerRef.current.clientWidth,
    });
  }
};
window.addEventListener('resize', handleResize);
```

**痛点：**
- 固定 400px 高度无法响应容器变化
- `window.resize` 只能捕获窗口级别的尺寸变化
- 无法响应侧边栏展开/折叠等局部容器尺寸变化
- 图表可能被截断或留白

#### 2.2 优化方案

**核心改动：**

1. **动态获取容器高度**
   ```tsx
   const chart = createChart(chartContainerRef.current, {
     width: chartContainerRef.current.clientWidth,
     height: chartContainerRef.current.clientHeight,  // ✅ 动态高度
     // ...
   });
   ```

2. **使用 ResizeObserver 替代 window.resize**
   ```tsx
   // 移除旧的 handleResize 和 window.addEventListener
   
   // 使用 ResizeObserver 监听容器的精准尺寸变化
   const resizeObserver = new ResizeObserver((entries) => {
     if (entries.length === 0 || entries[0].target !== chartContainerRef.current) {
       return;
     }
     const newRect = entries[0].contentRect;
     // 动态更新图表的宽高
     chart.applyOptions({ 
       width: newRect.width, 
       height: newRect.height 
     });
   });
   
   // 开始监听容器
   resizeObserver.observe(chartContainerRef.current);
   
   chartRef.current = chart;
   
   return () => {
     // 组件卸载时断开 observer 并清理图表
     resizeObserver.disconnect();
     if (chartRef.current) {
       chartRef.current.remove();
       chartRef.current = null;
     }
   };
   ```

**ResizeObserver 优势：**
- 精准捕获容器级别的尺寸变化（而非窗口级别）
- 支持侧边栏展开/折叠等局部布局变化
- 性能更好（只监听特定元素，而非整个窗口）
- 现代浏览器原生支持，无需 polyfill


## 完整代码示例

### page.tsx 完整修改

```tsx
'use client';

import { useState } from 'react';
import { AssetSelector } from '@/components/asset/AssetSelector';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { KLineChart } from '@/components/chart/KLineChart';

export default function Home() {
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [assetType, setAssetType] = useState<'crypto' | 'stocks'>('stocks');

  const handleAssetTypeChange = (type: 'crypto' | 'stocks') => {
    setAssetType(type);
    setSelectedAsset(null);
  };

  return (
    <div className="flex gap-4 h-[calc(100vh-8rem)]">
      {/* Left panel - 添加 min-w-0 防止内容撑破 */}
      <div className="flex-1 flex flex-col gap-4 overflow-hidden min-w-0">
        
        {/* Top: Stock selector - 使用 basis-2/5 (40%) + min-h-0 */}
        <div className="basis-2/5 min-h-0 overflow-y-auto">
          <AssetSelector
            selectedAsset={selectedAsset}
            onAssetSelect={setSelectedAsset}
            assetType={assetType}
            onAssetTypeChange={handleAssetTypeChange}
          />
        </div>

        {/* Bottom: K-line chart - 使用 basis-3/5 (60%) + min-h-0 */}
        <div className="basis-3/5 min-h-0 overflow-hidden">
          <KLineChart selectedStock={selectedAsset} assetType={assetType} />
        </div>
      </div>

      {/* Right panel: Chat - 使用 w-1/3 + shrink-0 */}
      <div className="w-1/3 shrink-0 border-l pl-4 overflow-hidden flex flex-col">
        <ChatPanel selectedStock={selectedAsset} />
      </div>
    </div>
  );
}
```

### KLineChart.tsx 关键修改点

在 `useEffect` 中找到图表创建部分，进行以下修改：

```tsx
// 1. 修改图表初始化（约在 Line 217-219）
const chart = createChart(chartContainerRef.current, {
  width: chartContainerRef.current.clientWidth,
  height: chartContainerRef.current.clientHeight,  // 改为动态高度
  localization: {
    // ...
  },
  // ...
});

// 2. 移除旧的 resize 监听逻辑（约在 Line 350-360）
// 删除以下代码：
// const handleResize = () => { ... };
// window.addEventListener('resize', handleResize);
// return () => { window.removeEventListener('resize', handleResize); };

// 3. 添加 ResizeObserver（在 chartRef.current = chart 之前）
const resizeObserver = new ResizeObserver((entries) => {
  if (entries.length === 0 || entries[0].target !== chartContainerRef.current) {
    return;
  }
  const newRect = entries[0].contentRect;
  chart.applyOptions({ 
    width: newRect.width, 
    height: newRect.height 
  });
});

resizeObserver.observe(chartContainerRef.current);
chartRef.current = chart;

// 4. 修改 cleanup 函数
return () => {
  resizeObserver.disconnect();
  if (chartRef.current) {
    chartRef.current.remove();
    chartRef.current = null;
  }
};
```

---

## 验收标准

### 功能验收

1. **响应式布局测试**
   - [ ] 在不同桌面分辨率下（1920x1080, 1366x768, 2560x1440），布局比例保持一致
   - [ ] 资产选择器和图表的 40/60 比例在所有屏幕下正确显示
   - [ ] 聊天面板宽度约占 33%，不会被挤压或溢出

2. **图表自适应测试**
   - [ ] 窗口缩放时，图表立即调整大小并重绘
   - [ ] 图表高度完全填充父容器，无留白或截断
   - [ ] 图表宽度随容器变化而变化

3. **滚动行为测试**
   - [ ] 资产选择器内容超出时，出现垂直滚动条
   - [ ] 滚动不会影响外层容器的高度
   - [ ] 图表区域不出现滚动条（完全自适应）

4. **边界情况测试**
   - [ ] 极小窗口（1024x600）下，布局不崩溃
   - [ ] 超宽屏幕（3440x1440）下，比例仍然合理
   - [ ] 快速连续调整窗口大小，图表响应流畅无卡顿

### 代码质量验收

- [ ] 所有修改的文件通过 ESLint 检查
- [ ] 所有修改的文件通过 TypeScript 类型检查
- [ ] 无 console 警告或错误
- [ ] 代码格式符合项目规范

---

## 风险与注意事项

### 潜在风险

1. **ResizeObserver 性能**
   - 风险：频繁触发可能导致性能问题
   - 缓解：lightweight-charts 内部有优化，实测性能良好

2. **Flex basis 兼容性**
   - 风险：旧版浏览器可能不支持 `basis-2/5` 语法
   - 缓解：项目使用现代浏览器，Tailwind 会编译为标准 CSS

3. **min-h-0 副作用**
   - 风险：可能影响某些子组件的默认高度行为
   - 缓解：已在设计中明确指定 `overflow-y-auto`，不会影响功能

### 注意事项

1. **不要修改 h-[calc(100vh-8rem)]** - 这是页面级别的高度约束，保持不变
2. **确保 ResizeObserver 正确 disconnect** - 避免内存泄漏
3. **测试时使用真实的窗口缩放** - 而不是浏览器开发者工具的模拟

---

## 后续工作

Phase 2 完成后，可以继续进行：

- **Phase 3**: 代码质量提升与工具链配置（Prettier 插件、空状态处理）
- **性能优化**: 考虑为 ResizeObserver 添加 debounce（如果实测有性能问题）

---

## 参考资料

- [Tailwind CSS Flexbox 文档](https://tailwindcss.com/docs/flex-basis)
- [MDN ResizeObserver API](https://developer.mozilla.org/en-US/docs/Web/API/ResizeObserver)
- [CSS Tricks: Flexbox min-height/min-width](https://css-tricks.com/flexbox-truncated-text/)
- [lightweight-charts Resize 最佳实践](https://tradingview.github.io/lightweight-charts/docs/api#resize)


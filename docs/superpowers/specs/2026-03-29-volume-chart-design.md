# Volume Chart Design Spec

**Date:** 2026-03-29
**Status:** Draft
**Scope:** `frontend/src/components/chart/KLineChart.tsx` only

---

## Overview

Add a synchronized volume histogram below the existing K-line candlestick chart. The volume bars share the same chart instance, X-axis, and crosshair as the main price chart. A fixed legend label in the top-left corner of the chart displays the volume value on crosshair hover via direct DOM manipulation (no React state, no re-renders).

---

## Architecture

**Single change point:** `KLineChart.tsx` — the chart `useEffect` block only.

No new files, no new components, no new props.

### Why single chart instance

`lightweight-charts` v5 supports multiple price scales on one chart. Assigning a `HistogramSeries` to a custom `priceScaleId` places it in its own vertical region while sharing the time axis natively. This gives:

- Zero-latency crosshair sync (same canvas)
- Native scroll/zoom sync (same time scale)
- Single resize handler (already present)

---

## Implementation Details

### 1. Main price scale margins

`scaleMargins` is a `PriceScaleOptions` property, not a series option. Apply it via `chart.priceScale('right').applyOptions()` after creating the series:

```ts
const series = chart.addSeries(CandlestickSeries, {
  upColor: '#22c55e',
  downColor: '#ef4444',
  wickUpColor: '#22c55e',
  wickDownColor: '#ef4444',
  priceScaleId: 'right',
});

chart.priceScale('right').applyOptions({
  scaleMargins: {
    top: 0.1,
    bottom: 0.25,
  },
});
```

### 2. Volume series registration

```ts
import { HistogramSeries } from 'lightweight-charts';

const volumeSeries = chart.addSeries(HistogramSeries, {
  priceScaleId: 'volume',
  priceFormat: { type: 'volume' },
});

chart.priceScale('volume').applyOptions({
  scaleMargins: {
    top: 0.8,   // volume area starts at 80% from top
    bottom: 0,
  },
});
```

### 3. Data mapping

Reuse the same `ohlcData` loop that builds `formattedData`. Build a parallel `volumeData` array:

```ts
const volumeData = ohlcData.map((d) => {
  const time = isIntradayData
    ? Math.floor(new Date(d.date).getTime() / 1000) as any
    : d.date.split('T')[0] as any;
  return {
    time,
    value: d.volume,
    color: d.close >= d.open
      ? 'rgba(34, 197, 94, 0.6)'   // green, matches upColor
      : 'rgba(239, 68, 68, 0.6)',  // red, matches downColor
  };
});

volumeSeries.setData(volumeData);
```

Alpha 0.6 keeps bars visually lighter than the candles above.

### 4. 浮动 Volume 图例（Floating Legend）

`priceScaleId: 'volume'` 默认以覆盖层模式运行，不渲染可见的 Y 轴，因此原生十字准线轴标签不会显示。采用行业标准做法：在图表容器内放置一个绝对定位的 DOM 节点，通过 `subscribeCrosshairMove` 直接操作 DOM 更新数值，**不使用 React state**（避免鼠标移动时触发组件重渲染）。

#### JSX 结构变更

图表容器需要改为 `relative` 定位，并在内部增加图例节点：

```tsx
// 新增 legendRef
const legendRef = useRef<HTMLDivElement>(null);

// JSX 中的图表区域（替换现有的 <div ref={chartContainerRef} className="flex-1" />）
<div className="flex-1 relative">
  <div ref={chartContainerRef} className="absolute inset-0" />
  <div
    ref={legendRef}
    className="absolute top-2 left-2 z-10 hidden text-xs font-mono
               bg-background/80 px-1.5 py-0.5 rounded pointer-events-none"
  />
</div>
```

#### useEffect 中的订阅逻辑

在 `volumeSeries.setData(volumeData)` 之后添加：

```ts
// 辅助函数：格式化成交量数值
const formatVolume = (vol: number): string => {
  if (vol >= 1_000_000) return (vol / 1_000_000).toFixed(2) + 'M';
  if (vol >= 1_000) return (vol / 1_000).toFixed(2) + 'K';
  return vol.toFixed(2);
};

chart.subscribeCrosshairMove((param) => {
  const legend = legendRef.current;
  if (!legend) return;

  if (
    !param.time ||
    param.point === undefined ||
    param.point.x < 0 ||
    param.point.y < 0
  ) {
    legend.style.display = 'none';
    return;
  }

  const volData = param.seriesData.get(volumeSeries) as { value: number } | undefined;
  if (volData) {
    legend.style.display = 'block';
    legend.textContent = `Vol  ${formatVolume(volData.value)}`;
  } else {
    legend.style.display = 'none';
  }
});
```

**关键点：**
- 用 `!param.time` 判断十字准线是否移出图表数据范围
- `param.seriesData` 永远是 `Map`（不会为 null），不要用 `!param.seriesData` 作为守卫
- `chart.remove()` 在现有 cleanup 中已经移除所有订阅，无需手动 `unsubscribeCrosshairMove`
- `OHLCRecord.volume` 可能是浮点数（加密货币），`formatVolume` 直接处理，无需预处理

---

## Visual Spec

| Region | Height share | Price scale |
|--------|-------------|-------------|
| K-line (candlestick) | ~75–80% | `right` |
| Volume (histogram) | ~20–25% | `volume` (custom) |

- Volume bars are green (rgba 0.6) when `close >= open`, red (rgba 0.6) otherwise
- Y-axis for volume starts at 0, scales independently from price
- Crosshair spans both regions simultaneously (native behavior)
- Scroll and zoom affect both regions simultaneously (native behavior)
- Volume Y-axis auto-scales so the tallest visible bar fills the volume region

---

## What Is Not Changing

- No new files
- No new props on `KLineChartProps`
- No changes to data fetching (`fetchData`, API calls)
- No changes to `TimeRangeSelector`, `AssetSelector`, or any other component
- No changes to the visible range logic
- No React state added for tooltip (direct DOM manipulation only)

---

## Acceptance Criteria

1. Volume bars appear below the K-line chart with correct proportions (~20% height)
2. Each bar color matches the corresponding candle (green/red)
3. Crosshair moves across both regions simultaneously (native behavior)
4. Scrolling and zooming keeps both regions in sync (native behavior)
5. 鼠标悬停时，图表左上角浮动图例显示当前 K 线的成交量数值（格式如 `1.23K` / `1.23M`），鼠标移出时隐藏；不引起组件重渲染
6. No regression on existing candlestick behavior (colors, time range, resize)
7. Empty data path (`ohlcData.length === 0`) is handled by the existing early-return guard — no additional handling needed

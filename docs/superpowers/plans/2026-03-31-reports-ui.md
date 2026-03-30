# Reports Area UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reports history page at `/reports` that lists past analysis queries with timestamps, CIO summaries, and expandable full-report views using mock data.

**Architecture:** A single `Accordion` in `page.tsx` wraps multiple `ReportCard` components, each rendering one `AccordionItem`. Expanding a card reveals a `Tabs` component with four report tabs (CIO, Quant, News, Social). A `stripMarkdown` utility produces clean plain-text summaries from raw Markdown report content.

**Tech Stack:** Next.js 16+, React 19, TypeScript strict, shadcn/ui (Accordion, Tabs, Badge, Card), date-fns 4.x, existing `MarkdownRenderer` component.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Install | `frontend/src/components/ui/accordion.tsx` | shadcn/ui Accordion primitives |
| Create | `frontend/src/lib/strip-markdown.ts` | Strip Markdown syntax → plain text |
| Create | `frontend/src/lib/mock-data/reports.ts` | `AnalysisReport` type + mock data array |
| Create | `frontend/src/components/reports/ReportCard.tsx` | AccordionItem + Tabs for one report |
| Modify | `frontend/src/app/reports/page.tsx` | Replace skeleton with real Accordion list |

---

## Task 1: Install Accordion component

**Files:**
- Create: `frontend/src/components/ui/accordion.tsx` (via shadcn CLI)

- [ ] **Step 1: Install the Accordion component**

```bash
cd /home/wcqqq21/q-agents/frontend && pnpm dlx shadcn@latest add accordion
```

Expected output: `✔ Done.` and a new file at `src/components/ui/accordion.tsx`.

- [ ] **Step 2: Verify the file exists**

```bash
ls /home/wcqqq21/q-agents/frontend/src/components/ui/accordion.tsx
```

Expected: file path printed, no error.

- [ ] **Step 3: Commit**

```bash
cd /home/wcqqq21/q-agents/frontend && git add src/components/ui/accordion.tsx
cd /home/wcqqq21/q-agents && git commit -m "feat(ui): install shadcn accordion component"
```

---

## Task 2: Create `stripMarkdown` utility

**Files:**
- Create: `frontend/src/lib/strip-markdown.ts`

- [ ] **Step 1: Create the utility file**

```typescript
// frontend/src/lib/strip-markdown.ts

/**
 * Strips common Markdown syntax from a string and returns plain text.
 * Used to produce clean summaries from LLM-generated Markdown reports.
 */
export function stripMarkdown(text: string): string {
  return text
    // Remove headings: # ## ###
    .replace(/^#{1,6}\s+/gm, '')
    // Remove bold/italic: **text**, *text*, __text__, _text_
    .replace(/(\*{1,2}|_{1,2})(.+?)\1/g, '$2')
    // Remove inline code: `code`
    .replace(/`(.+?)`/g, '$1')
    // Remove links: [text](url)
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Remove images: ![alt](url)
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    // Remove blockquotes: > text
    .replace(/^>\s+/gm, '')
    // Remove horizontal rules: --- or ***
    .replace(/^[-*]{3,}\s*$/gm, '')
    // Remove list markers: - item, * item, 1. item
    .replace(/^[\s]*[-*+]\s+/gm, '')
    .replace(/^[\s]*\d+\.\s+/gm, '')
    // Collapse multiple newlines to single space
    .replace(/\n+/g, ' ')
    // Collapse multiple spaces
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/**
 * Returns a plain-text summary truncated to maxLength characters.
 * Strips Markdown before truncating to avoid broken syntax fragments.
 */
export function markdownSummary(text: string, maxLength = 200): string {
  const plain = stripMarkdown(text);
  if (plain.length <= maxLength) return plain;
  return plain.slice(0, maxLength).trimEnd() + '...';
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/wcqqq21/q-agents && git add frontend/src/lib/strip-markdown.ts
git commit -m "feat(reports): add stripMarkdown utility"
```

---

## Task 3: Create mock data

**Files:**
- Create: `frontend/src/lib/mock-data/reports.ts`

- [ ] **Step 1: Create the mock data file**

```typescript
// frontend/src/lib/mock-data/reports.ts

// Mock-only type — NOT exported from lib/types.ts.
// Will be unified with the real API shape when backend integration is added.
export interface AnalysisReport {
  id: string;
  symbol: string;
  assetType: 'stocks' | 'crypto';
  query: string;
  timestamp: string; // ISO 8601
  reports: {
    cio: string;
    quant: string;
    news: string;
    social: string;
  };
}

export const mockReports: AnalysisReport[] = [
  {
    id: '1',
    symbol: 'NVDA',
    assetType: 'stocks',
    query: '分析英伟达近期走势，是否适合买入？',
    timestamp: new Date(Date.now() - 1000 * 60 * 90).toISOString(), // 90 min ago
    reports: {
      cio: `# CIO 投资决策报告 — NVDA

**结论：谨慎买入**

综合量化、新闻与社交情绪分析，英伟达当前处于技术性强势区间，但估值偏高，建议分批建仓。

## 核心逻辑

- **量化信号**：MACD 金叉，RSI 62（未超买），布林带中轨上方运行
- **新闻情绪**：正面，GTC 大会预期驱动，分析师目标价上调
- **社交情绪**：Reddit r/stocks 讨论热度高，散户情绪偏多

## 风险提示

1. 估值 P/E 超过 40x，存在回调风险
2. 宏观利率环境仍有不确定性
3. 竞争对手 AMD 新品发布可能分流市场关注

**建议仓位**：不超过组合的 5%，分 2-3 次建仓。`,
      quant: `# 量化分析报告 — NVDA

## 技术指标

| 指标 | 数值 | 信号 |
|------|------|------|
| 当前价格 | $875.40 | — |
| SMA 20 | $842.10 | 价格在均线上方 ✅ |
| SMA 50 | $798.30 | 价格在均线上方 ✅ |
| RSI (14) | 62.4 | 中性偏强 |
| MACD | +12.3 | 金叉 ✅ |
| 布林带上轨 | $920.00 | 距上轨 5.1% |

## ML 模型预测

- **5日收益率预测**：+2.3%（置信度 68%）
- **特征重要性**：成交量变化 > MACD > RSI

## 结论

技术面偏多，短期动能较强。`,
      news: `# 新闻情绪分析 — NVDA

## 情绪评分：+0.72（正面）

## 关键新闻摘要

1. **GTC 2026 大会预期**：黄仁勋将发布 Blackwell Ultra 架构，市场预期强烈
2. **数据中心营收**：Q4 数据中心营收同比增长 93%，超出预期
3. **分析师评级**：摩根士丹利上调目标价至 $1,000

## 风险新闻

- 美国对华芯片出口限制可能扩大，影响约 15% 营收
- 部分机构开始获利了结

## 分析的文章数量：47 篇`,
      social: `# 社交情绪分析 — NVDA

## Reddit 情绪评分：+0.68（偏多）

## 热门讨论主题

- **r/stocks**：讨论量 +340%，主要围绕 GTC 大会
- **r/wallstreetbets**：多头帖子占比 71%
- **r/investing**：理性讨论为主，关注估值风险

## 关键词词频

\`AI\` \`GTC\` \`Blackwell\` \`数据中心\` \`买入\`

## 分析帖子数：1,243 条`,
    },
  },
  {
    id: '2',
    symbol: 'AAPL',
    assetType: 'stocks',
    query: 'Apple Q1 财报后的投资机会分析',
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 5).toISOString(), // 5 hours ago
    reports: {
      cio: `# CIO 投资决策报告 — AAPL

**结论：持有，暂不加仓**

苹果 Q1 财报超预期，但 iPhone 销量增速放缓，AI 功能落地进度慢于预期。当前估值合理，建议持有现有仓位。

## 核心逻辑

- **量化信号**：价格在 SMA50 附近震荡，方向不明
- **新闻情绪**：中性，财报亮点与隐忧并存
- **社交情绪**：散户情绪中性，机构分歧较大

## 风险提示

1. 中国市场 iPhone 销量持续承压
2. Apple Intelligence 功能推进慢于竞争对手
3. 服务业务增速是否可持续存疑

**建议仓位**：维持现有仓位，等待更明确的 AI 战略信号。`,
      quant: `# 量化分析报告 — AAPL

## 技术指标

| 指标 | 数值 | 信号 |
|------|------|------|
| 当前价格 | $213.50 | — |
| SMA 20 | $218.30 | 价格在均线下方 ⚠️ |
| SMA 50 | $211.80 | 价格在均线上方 ✅ |
| RSI (14) | 48.2 | 中性 |
| MACD | -1.8 | 死叉 ⚠️ |

## 结论

技术面中性，短期方向不明，等待突破信号。`,
      news: `# 新闻情绪分析 — AAPL

## 情绪评分：+0.31（轻微正面）

## 关键新闻

1. Q1 营收 $1,243 亿，同比增长 4%，略超预期
2. 服务业务营收创历史新高 $268 亿
3. iPhone 销量同比下降 2%，中国市场压力明显

## 分析的文章数量：89 篇`,
      social: `# 社交情绪分析 — AAPL

## Reddit 情绪评分：+0.22（轻微正面）

## 热门讨论

- 财报后股价小幅下跌，散户情绪分歧
- 长期持有者仍看好服务业务增长逻辑

## 分析帖子数：876 条`,
    },
  },
  {
    id: '3',
    symbol: 'BTC',
    assetType: 'crypto',
    query: '比特币减半后的价格走势预测',
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 26).toISOString(), // 26 hours ago
    reports: {
      cio: `# CIO 投资决策报告 — BTC

**结论：积极买入**

比特币减半已完成，历史规律显示减半后 6-12 个月通常迎来主升浪。当前技术面强势，机构持仓持续增加。

## 核心逻辑

- **量化信号**：突破前高，成交量放大，趋势强劲
- **新闻情绪**：正面，ETF 资金持续流入
- **社交情绪**：加密社区情绪高涨，FOMO 情绪开始出现

## 风险提示

1. 监管风险仍存在，尤其是美国 SEC 态度
2. 宏观流动性收紧可能压制风险资产
3. 历史规律不代表未来，减半效应可能已被提前定价

**建议仓位**：组合中不超过 10%，做好波动率管理。`,
      quant: `# 量化分析报告 — BTC

## 技术指标

| 指标 | 数值 | 信号 |
|------|------|------|
| 当前价格 | $87,420 | — |
| SMA 20 | $82,100 | 价格在均线上方 ✅ |
| SMA 50 | $75,300 | 价格在均线上方 ✅ |
| RSI (14) | 71.2 | 超买区间 ⚠️ |
| MACD | +1,840 | 强势金叉 ✅ |

## 结论

技术面强势，但 RSI 进入超买区间，短期可能有回调。`,
      news: `# 新闻情绪分析 — BTC

## 情绪评分：+0.81（强烈正面）

## 关键新闻

1. 比特币现货 ETF 单日净流入 $8.2 亿，创历史新高
2. MicroStrategy 再次增持 5,000 枚 BTC
3. 萨尔瓦多比特币储备增值超 300%

## 分析的文章数量：203 篇`,
      social: `# 社交情绪分析 — BTC

## Reddit 情绪评分：+0.85（强烈正面）

## 热门讨论

- r/Bitcoin：减半庆祝帖铺天盖地，情绪极度乐观
- r/CryptoCurrency：讨论下一个价格目标 $100k
- Twitter/X：#Bitcoin 话题热度全球第三

## 分析帖子数：15,432 条`,
    },
  },
  {
    id: '4',
    symbol: 'TSLA',
    assetType: 'stocks',
    query: 'Tesla 交付量下滑，现在是抄底时机吗？',
    timestamp: new Date(Date.now() - 1000 * 60 * 60 * 24 * 3).toISOString(), // 3 days ago
    reports: {
      cio: `# CIO 投资决策报告 — TSLA

**结论：观望，不建议现在买入**

特斯拉 Q1 交付量同比下降 13%，为近年来最大跌幅。马斯克精力分散、品牌受损、竞争加剧，基本面短期难以改善。

## 核心逻辑

- **量化信号**：下跌趋势明确，均线系统空头排列
- **新闻情绪**：负面，交付数据引发广泛担忧
- **社交情绪**：散户分歧，部分死忠粉抄底，但主流情绪悲观

## 风险提示

1. 马斯克 DOGE 工作影响特斯拉管理层注意力
2. 中国市场比亚迪竞争持续加剧
3. Cybertruck 召回事件影响品牌形象

**建议仓位**：等待交付量企稳信号，暂不建仓。`,
      quant: `# 量化分析报告 — TSLA

## 技术指标

| 指标 | 数值 | 信号 |
|------|------|------|
| 当前价格 | $248.70 | — |
| SMA 20 | $278.40 | 价格在均线下方 ❌ |
| SMA 50 | $312.10 | 价格在均线下方 ❌ |
| RSI (14) | 34.1 | 接近超卖 |
| MACD | -18.6 | 死叉 ❌ |

## 结论

技术面弱势，下跌趋势未止，等待企稳信号。`,
      news: `# 新闻情绪分析 — TSLA

## 情绪评分：-0.58（负面）

## 关键新闻

1. Q1 交付量 336,681 辆，同比下降 13%，远低于预期
2. 欧洲多国特斯拉销量大幅下滑，品牌抵制情绪蔓延
3. 多家机构下调目标价

## 分析的文章数量：156 篇`,
      social: `# 社交情绪分析 — TSLA

## Reddit 情绪评分：-0.41（负面）

## 热门讨论

- r/TSLA：死忠粉与空头激烈争论
- r/investing：多数人建议等待更多数据
- Twitter/X：#TeslaDown 话题持续发酵

## 分析帖子数：4,891 条`,
    },
  },
];
```

- [ ] **Step 2: Commit**

```bash
cd /home/wcqqq21/q-agents && git add frontend/src/lib/mock-data/reports.ts
git commit -m "feat(reports): add AnalysisReport type and mock data"
```

---

## Task 4: Create `ReportCard` component

**Files:**
- Create: `frontend/src/components/reports/ReportCard.tsx`

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/reports/ReportCard.tsx
'use client';

import { format, formatDistanceToNow, isAfter, subHours } from 'date-fns';
import { AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { MarkdownRenderer } from '@/components/chat/MarkdownRenderer';
import { markdownSummary } from '@/lib/strip-markdown';
import type { AnalysisReport } from '@/lib/mock-data/reports';

interface ReportCardProps {
  report: AnalysisReport;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const cutoff = subHours(new Date(), 24);
  if (isAfter(date, cutoff)) {
    return formatDistanceToNow(date, { addSuffix: true });
  }
  return format(date, 'yyyy-MM-dd HH:mm');
}

const TAB_EMPTY = 'No report available.';

export function ReportCard({ report }: ReportCardProps) {
  const summary = markdownSummary(report.reports.cio, 200);

  return (
    <AccordionItem value={report.id} className="border rounded-lg px-4">
      <AccordionTrigger className="hover:no-underline py-4">
        <div className="flex flex-col gap-1.5 text-left w-full pr-4">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{report.symbol}</span>
            <Badge variant="outline" className="text-xs">
              {report.assetType}
            </Badge>
            <span className="ml-auto text-xs text-muted-foreground">
              {formatTimestamp(report.timestamp)}
            </span>
          </div>
          <p className="text-sm truncate text-foreground">{report.query}</p>
          <p className="text-xs text-muted-foreground line-clamp-2">{summary}</p>
        </div>
      </AccordionTrigger>

      <AccordionContent className="pb-4">
        <Tabs defaultValue="cio">
          <TabsList className="mb-4">
            <TabsTrigger value="cio">CIO 决策</TabsTrigger>
            <TabsTrigger value="quant">Quant 分析</TabsTrigger>
            <TabsTrigger value="news">News 情绪</TabsTrigger>
            <TabsTrigger value="social">Social 情绪</TabsTrigger>
          </TabsList>

          <TabsContent value="cio">
            {report.reports.cio ? (
              <MarkdownRenderer content={report.reports.cio} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>

          <TabsContent value="quant">
            {report.reports.quant ? (
              <MarkdownRenderer content={report.reports.quant} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>

          <TabsContent value="news">
            {report.reports.news ? (
              <MarkdownRenderer content={report.reports.news} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>

          <TabsContent value="social">
            {report.reports.social ? (
              <MarkdownRenderer content={report.reports.social} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>
        </Tabs>
      </AccordionContent>
    </AccordionItem>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/wcqqq21/q-agents && git add frontend/src/components/reports/ReportCard.tsx
git commit -m "feat(reports): add ReportCard component with accordion and tabs"
```

---

## Task 5: Rewrite `reports/page.tsx`

**Files:**
- Modify: `frontend/src/app/reports/page.tsx`

- [ ] **Step 1: Replace the file contents**

```tsx
// frontend/src/app/reports/page.tsx
'use client';

import { Accordion } from '@/components/ui/accordion';
import { mockReports } from '@/lib/mock-data/reports';
import { ReportCard } from '@/components/reports/ReportCard';

const sorted = [...mockReports].sort(
  (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
);

export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Analysis Reports</h1>
        <p className="text-muted-foreground mt-2">
          Browse all generated financial analysis reports
        </p>
      </div>

      {sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <p className="text-muted-foreground">
            No analyses yet. Run your first analysis from the main page.
          </p>
        </div>
      ) : (
        <Accordion type="multiple" className="flex flex-col gap-4">
          {sorted.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </Accordion>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/wcqqq21/q-agents && git add frontend/src/app/reports/page.tsx
git commit -m "feat(reports): replace skeleton with accordion report list"
```

---

## Task 6: Verify and lint

**Files:** none (verification only)

- [ ] **Step 1: Run TypeScript type check**

```bash
cd /home/wcqqq21/q-agents/frontend && pnpm type-check
```

Expected: no errors.

- [ ] **Step 2: Run ESLint**

```bash
cd /home/wcqqq21/q-agents/frontend && pnpm lint
```

Expected: no errors or warnings.

- [ ] **Step 3: If errors exist, fix them**

Common issues:
- Missing `'use client'` on a component that uses hooks → add `'use client'` at top of file
- `line-clamp-2` not recognized → use `overflow-hidden` + inline style, or ensure Tailwind config includes `@tailwindcss/line-clamp`
- Import path wrong → verify paths match the file map above

- [ ] **Step 4: Final commit if fixes were needed**

```bash
cd /home/wcqqq21/q-agents && git add -p && git commit -m "fix(reports): resolve lint and type errors"
```

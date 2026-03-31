// frontend/src/components/reports/ReportCard.tsx
"use client";

import { format, formatDistanceToNow, isAfter, subHours } from "date-fns";
import {
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { markdownSummary } from "@/lib/strip-markdown";
import type { AnalysisReport } from "@/lib/mock-data/reports";

interface ReportCardProps {
  report: AnalysisReport;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const cutoff = subHours(new Date(), 24);
  if (isAfter(date, cutoff)) {
    return formatDistanceToNow(date, { addSuffix: true });
  }
  return format(date, "yyyy-MM-dd HH:mm");
}

const TAB_EMPTY = "No report available.";

export function ReportCard({ report }: ReportCardProps) {
  const summary =
    markdownSummary(report.reports.cio, 200) || "No summary available.";

  return (
    <AccordionItem value={report.id} className="rounded-lg border px-4">
      <AccordionTrigger className="py-4 hover:no-underline">
        <div className="flex w-full flex-col gap-1.5 pr-4 text-left">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{report.symbol}</span>
            <Badge variant="outline" className="text-xs">
              {report.assetType}
            </Badge>
            <span className="ml-auto text-xs text-muted-foreground">
              {formatTimestamp(report.timestamp)}
            </span>
          </div>
          <p className="truncate text-sm text-foreground">{report.query}</p>
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {summary}
          </p>
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

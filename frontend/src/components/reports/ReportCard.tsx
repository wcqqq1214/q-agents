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
import type { Report } from "@/lib/types";
import { getReportQueryDisplay } from "./report-card-helpers";

interface ReportCardProps {
  report: Report;
}

function formatTimestamp(iso: string): string {
  if (!iso) return "Unknown time";

  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown time";

  const cutoff = subHours(new Date(), 24);
  if (isAfter(date, cutoff)) {
    return formatDistanceToNow(date, { addSuffix: true });
  }
  return format(date, "yyyy-MM-dd HH:mm");
}

const TAB_EMPTY = "No report available.";

export function ReportCard({ report }: ReportCardProps) {
  const cioText = report.reports?.cio ?? null;
  const quantText = report.reports?.quant ?? null;
  const newsText = report.reports?.news ?? null;
  const socialText = report.reports?.social ?? null;

  const summary =
    markdownSummary(report.reports?.cio ?? "", 200) || "No summary available.";
  const displayQuery = getReportQueryDisplay(report.query, report.symbol);

  return (
    <AccordionItem value={report.id} className="rounded-lg border px-4">
      <AccordionTrigger className="py-4 hover:no-underline">
        <div className="flex w-full flex-col gap-1.5 pr-4 text-left">
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{report.symbol}</span>
            <Badge variant="outline" className="text-xs">
              {report.asset_type}
            </Badge>
            <span className="ml-auto text-xs text-muted-foreground">
              {formatTimestamp(report.timestamp)}
            </span>
          </div>
          <p className="truncate text-sm text-foreground">
            {displayQuery || "No query available."}
          </p>
          <p className="line-clamp-2 text-xs text-muted-foreground">
            {summary}
          </p>
        </div>
      </AccordionTrigger>

      <AccordionContent className="pb-4">
        <Tabs defaultValue="cio">
          <TabsList className="mb-4">
            <TabsTrigger value="cio">CIO Decision</TabsTrigger>
            <TabsTrigger value="quant">Quant Analysis</TabsTrigger>
            <TabsTrigger value="news">News Sentiment</TabsTrigger>
            <TabsTrigger value="social">Social Sentiment</TabsTrigger>
          </TabsList>

          <TabsContent value="cio">
            {cioText ? (
              <MarkdownRenderer content={cioText} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>

          <TabsContent value="quant">
            {quantText ? (
              <MarkdownRenderer content={quantText} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>

          <TabsContent value="news">
            {newsText ? (
              <MarkdownRenderer content={newsText} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>

          <TabsContent value="social">
            {socialText ? (
              <MarkdownRenderer content={socialText} />
            ) : (
              <p className="text-sm text-muted-foreground">{TAB_EMPTY}</p>
            )}
          </TabsContent>
        </Tabs>
      </AccordionContent>
    </AccordionItem>
  );
}

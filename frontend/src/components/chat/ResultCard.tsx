"use client";

import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  AnalysisConnectionState,
  AnalysisStageCard,
  AnalysisStreamEvent,
} from "@/features/analysis-session/types";
import { AnalysisEventFeed } from "./AnalysisEventFeed";
import { AnalysisFinalReport } from "./AnalysisFinalReport";
import { AnalysisStageCards } from "./AnalysisStageCards";

interface ResultCardProps {
  connection: AnalysisConnectionState;
  error: string | null;
  events: AnalysisStreamEvent[];
  finalReport: string | null;
  isAnalyzing: boolean;
  query: string;
  stages: AnalysisStageCard[];
  symbol: string;
}

export function ResultCard({
  connection,
  error,
  events,
  finalReport,
  isAnalyzing,
  query,
  stages,
  symbol,
}: ResultCardProps) {
  return (
    <Card className="flex flex-1 flex-col overflow-hidden">
      <CardHeader className="gap-3 pb-2">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">{symbol}</CardTitle>
          {isAnalyzing ? (
            <Badge className="text-xs" variant="secondary">
              Streaming
            </Badge>
          ) : null}
          {connection === "completed" ? (
            <Badge className="text-xs" variant="default">
              Completed
            </Badge>
          ) : null}
          {connection === "failed" ? (
            <Badge className="text-xs" variant="destructive">
              Failed
            </Badge>
          ) : null}
        </div>
        <CardDescription className="truncate">{query}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4 overflow-y-auto">
        <AnalysisStageCards stages={stages} />
        <AnalysisEventFeed events={events} />
        <AnalysisFinalReport
          content={finalReport}
          error={error}
          isComplete={connection === "completed"}
        />

        {!isAnalyzing && !finalReport && !error && events.length === 0 ? (
          <div className="flex h-full items-center justify-center rounded-lg border border-dashed p-6 text-center">
            <p className="text-sm text-muted-foreground">
              Analysis results will appear here after the first streamed event.
            </p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

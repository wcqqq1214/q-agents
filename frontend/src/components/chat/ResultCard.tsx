"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface ResultCardProps {
  symbol: string;
  query: string;
  progress: string[];
  result: { final_decision?: string } | null;
  isAnalyzing: boolean;
}

export function ResultCard({
  symbol,
  query,
  progress,
  result,
  isAnalyzing,
}: ResultCardProps) {
  return (
    <Card className="flex flex-1 flex-col overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">{symbol}</CardTitle>
          {isAnalyzing && (
            <Badge variant="secondary" className="animate-pulse text-xs">
              Analyzing...
            </Badge>
          )}
        </div>
        <p className="truncate text-xs text-muted-foreground">{query}</p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col space-y-2 overflow-y-auto">
        {/* Progress */}
        {progress.length > 0 && (
          <div className="space-y-1">
            {progress.map((msg, i) => (
              <p
                key={i}
                className="flex items-start gap-1 text-xs text-muted-foreground"
              >
                <span className="mt-0.5 text-primary">•</span>
                <span>{msg}</span>
              </p>
            ))}
          </div>
        )}

        {/* Final Decision - Markdown formatted */}
        {result?.final_decision && (
          <div className="pt-1">
            <MarkdownRenderer content={String(result.final_decision)} />
          </div>
        )}

        {/* Empty state */}
        {!isAnalyzing && !result?.final_decision && progress.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center py-8 text-center">
            <p className="text-sm text-muted-foreground">
              Analysis results will appear here.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

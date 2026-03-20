'use client';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { MarkdownRenderer } from './MarkdownRenderer';

interface ResultCardProps {
  symbol: string;
  query: string;
  progress: string[];
  result: Record<string, unknown> | null;
  isAnalyzing: boolean;
}

export function ResultCard({ symbol, query, progress, result, isAnalyzing }: ResultCardProps) {
  return (
    <Card className="flex-1 overflow-hidden flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">{symbol}</CardTitle>
          {isAnalyzing && (
            <Badge variant="secondary" className="text-xs animate-pulse">
              Analyzing...
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate">{query}</p>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto space-y-2">
        {/* Progress */}
        {progress.length > 0 && (
          <div className="space-y-1">
            {progress.map((msg, i) => (
              <p key={i} className="text-xs text-muted-foreground flex items-start gap-1">
                <span className="text-primary mt-0.5">•</span>
                {msg}
              </p>
            ))}
          </div>
        )}

        {/* Final Decision - Markdown formatted */}
        {result && result.final_decision && (
          <div className="pt-1">
            <MarkdownRenderer content={String(result.final_decision)} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface AnalysisFinalReportProps {
  content: string | null;
  error: string | null;
  isComplete: boolean;
}

export function AnalysisFinalReport({
  content,
  error,
  isComplete,
}: AnalysisFinalReportProps) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="px-4 py-4">
        <CardTitle className="text-sm">Final CIO Report</CardTitle>
        <CardDescription>
          {error
            ? "The run ended before the final CIO synthesis was completed."
            : isComplete
              ? "Final portfolio view from the CIO agent."
              : "The final CIO synthesis appears after the run completes."}
        </CardDescription>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {content ? (
          <MarkdownRenderer content={content} />
        ) : error ? (
          <p className="text-sm leading-relaxed text-destructive">{error}</p>
        ) : (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-3/4" />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

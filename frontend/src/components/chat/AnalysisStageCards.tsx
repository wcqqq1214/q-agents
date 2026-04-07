import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardAction,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AnalysisStageCard } from "@/features/analysis-session/types";
import { cn } from "@/lib/utils";

interface AnalysisStageCardsProps {
  stages: AnalysisStageCard[];
}

const STATUS_COPY = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
} as const;

function getBadgeVariant(status: AnalysisStageCard["status"]) {
  if (status === "failed") {
    return "destructive";
  }

  if (status === "completed") {
    return "default";
  }

  if (status === "running") {
    return "secondary";
  }

  return "outline";
}

export function AnalysisStageCards({ stages }: AnalysisStageCardsProps) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <h3 className="text-sm font-semibold">Analysis Progress</h3>
        <p className="text-xs text-muted-foreground">
          Track Quant, News, Social, and CIO as the run progresses.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {stages.map((stage) => (
          <Card
            className={cn(
              "gap-0 py-4",
              stage.status === "running" && "border-primary/30 bg-primary/5",
              stage.status === "completed" && "border-primary/20 bg-primary/5",
              stage.status === "failed" &&
                "border-destructive/30 bg-destructive/5",
            )}
            key={stage.key}
          >
            <CardHeader className="px-4">
              <CardTitle className="text-sm">{stage.label}</CardTitle>
              <CardAction>
                <Badge variant={getBadgeVariant(stage.status)}>
                  {STATUS_COPY[stage.status]}
                </Badge>
              </CardAction>
              <CardDescription>
                {stage.message ?? `Waiting for ${stage.label} telemetry.`}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
    </div>
  );
}

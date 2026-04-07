"use client";

import { useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AnalysisStreamEvent } from "@/features/analysis-session/types";
import { cn } from "@/lib/utils";

interface AnalysisEventFeedProps {
  events: AnalysisStreamEvent[];
}

function getEventTone(event: AnalysisStreamEvent) {
  if (event.type === "error" || event.status === "failed") {
    return "bg-destructive";
  }

  if (event.type === "result" || event.status === "completed") {
    return "bg-primary";
  }

  if (event.type === "tool_call") {
    return "bg-chart-3";
  }

  return "bg-muted-foreground";
}

export function AnalysisEventFeed({ events }: AnalysisEventFeedProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    if (!autoScroll || !containerRef.current) {
      return;
    }

    containerRef.current.scrollTo({
      top: containerRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [autoScroll, events]);

  const handleScroll = () => {
    if (!containerRef.current) {
      return;
    }

    const { clientHeight, scrollHeight, scrollTop } = containerRef.current;
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 24;
    setAutoScroll(isNearBottom);
  };

  const scrollToLatest = () => {
    if (!containerRef.current) {
      return;
    }

    containerRef.current.scrollTo({
      top: containerRef.current.scrollHeight,
      behavior: "smooth",
    });
    setAutoScroll(true);
  };

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex flex-col gap-1">
            <CardTitle className="text-sm">Analysis Event Feed</CardTitle>
            <CardDescription>
              Sanitized tool calls, fetch summaries, and stage updates.
            </CardDescription>
          </div>

          {autoScroll ? (
            <Badge variant="outline">{events.length} events</Badge>
          ) : (
            <Button onClick={scrollToLatest} size="sm" variant="ghost">
              Jump to latest
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="px-0">
        <div
          className="max-h-64 overflow-y-auto px-4 pb-4"
          onScroll={handleScroll}
          ref={containerRef}
        >
          {events.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Waiting for the first telemetry event.
            </p>
          ) : (
            <ol className="flex flex-col gap-3">
              {events.map((event, index) => (
                <li
                  className="flex items-start gap-3"
                  key={
                    event.event_id ?? `${event.type}-${event.sequence ?? index}`
                  }
                >
                  <span
                    aria-hidden
                    className={cn(
                      "mt-1.5 size-2 shrink-0 rounded-full",
                      getEventTone(event),
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline">
                        {event.stage.toUpperCase()}
                      </Badge>
                      <span className="text-[11px] tracking-[0.18em] text-muted-foreground uppercase">
                        {event.type.replace("_", " ")}
                      </span>
                      {typeof event.sequence === "number" ? (
                        <span className="text-[11px] text-muted-foreground">
                          #{event.sequence}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-sm leading-relaxed text-foreground">
                      {event.message}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

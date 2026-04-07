"use client";

import { useEffect, useReducer, useRef, useState, useTransition } from "react";
import { Send } from "lucide-react";

import {
  createInitialAnalysisSessionState,
  reduceAnalysisSession,
} from "@/features/analysis-session/reducer";
import {
  selectAnalysisStageCards,
  selectFinalCioMarkdown,
  selectVisibleAnalysisEvents,
} from "@/features/analysis-session/selectors";
import { useToast } from "@/hooks/use-toast";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ResultCard } from "./ResultCard";

interface ChatPanelProps {
  selectedStock: string | null;
}

export function ChatPanel({ selectedStock }: ChatPanelProps) {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [submittedSymbol, setSubmittedSymbol] = useState("");
  const [session, dispatch] = useReducer(
    reduceAnalysisSession,
    undefined,
    createInitialAnalysisSessionState,
  );
  const [isPending, startTransition] = useTransition();
  const eventSourceRef = useRef<EventSource | null>(null);
  const sessionConnectionRef = useRef(session.connection);
  const { toast } = useToast();

  const closeStream = () => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
  };

  useEffect(() => {
    sessionConnectionRef.current = session.connection;
  }, [session.connection]);

  useEffect(() => {
    return () => {
      closeStream();
    };
  }, []);

  const handleStreamMessage = (
    event: MessageEvent<string>,
    source: EventSource,
  ) => {
    const parsedEvent = api.parseAnalysisStreamEvent(event.data);
    if (!parsedEvent) {
      console.error("Failed to parse SSE event:", event.data);
      return;
    }

    startTransition(() => {
      dispatch({ type: "stream_event", event: parsedEvent });
    });

    if (parsedEvent.type === "result") {
      source.close();
      closeStream();
      return;
    }

    if (parsedEvent.type === "error") {
      toast({
        title: "Analysis Error",
        description: parsedEvent.message,
        variant: "destructive",
      });
      source.close();
      closeStream();
    }
  };

  const handleStreamError = (source: EventSource) => {
    if (
      sessionConnectionRef.current === "completed" ||
      sessionConnectionRef.current === "failed"
    ) {
      return;
    }

    startTransition(() => {
      dispatch({
        type: "connection_error",
        message: "Connection lost to the analysis stream.",
      });
    });

    toast({
      title: "Connection Error",
      description: "Lost connection to server",
      variant: "destructive",
    });
    source.close();
    closeStream();
  };

  const placeholder = selectedStock
    ? `Ask about ${selectedStock}... (e.g., technical analysis, recent news)`
    : "Select a stock to start analysis";

  const stageCards = selectAnalysisStageCards(session);
  const visibleEvents = selectVisibleAnalysisEvents(session);
  const finalReport = selectFinalCioMarkdown(session);
  const isAnalyzing =
    session.connection === "connecting" ||
    session.connection === "streaming" ||
    isPending;
  const showResultCard =
    session.connection !== "idle" ||
    submittedQuery.length > 0 ||
    finalReport !== null;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!selectedStock || !query.trim() || isAnalyzing) {
      return;
    }

    closeStream();

    const fullQuery = `${query.trim()} ${selectedStock}`;
    setSubmittedQuery(query.trim());
    setSubmittedSymbol(selectedStock);
    dispatch({ type: "session_started" });

    const eventSource = api.createAnalyzeStream(fullQuery);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (messageEvent) => {
      handleStreamMessage(messageEvent, eventSource);
    };

    eventSource.onerror = () => {
      handleStreamError(eventSource);
    };

    setQuery("");
  };

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <div>
        <h2 className="text-lg font-semibold">
          {showResultCard ? "Analysis Progress" : "Analysis Chat"}
        </h2>
        <p className="text-xs text-muted-foreground">
          {showResultCard
            ? "Live stage telemetry and the final CIO report appear here."
            : selectedStock
              ? `Analyzing ${selectedStock}`
              : "Select a stock from the left panel"}
        </p>
      </div>

      {showResultCard ? (
        <ResultCard
          connection={session.connection}
          error={session.error}
          events={visibleEvents}
          finalReport={finalReport}
          isAnalyzing={isAnalyzing}
          query={submittedQuery}
          stages={stageCards}
          symbol={submittedSymbol}
        />
      ) : null}

      <form className="mt-auto flex gap-2" onSubmit={handleSubmit}>
        <Input
          className="flex-1 text-sm"
          disabled={!selectedStock || isAnalyzing}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={placeholder}
          value={query}
        />
        <Button
          aria-label="Send analysis query"
          disabled={!selectedStock || !query.trim() || isAnalyzing}
          size="icon"
          type="submit"
        >
          <Send data-icon="inline-start" />
        </Button>
      </form>
    </div>
  );
}

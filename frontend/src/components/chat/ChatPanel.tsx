'use client';

import { useState, useRef } from 'react';
import { Send } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { ResultCard } from './ResultCard';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import type { SSEEvent } from '@/lib/types';

interface ChatPanelProps {
  selectedStock: string | null;
}

export function ChatPanel({ selectedStock }: ChatPanelProps) {
  const [query, setQuery] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState<string[]>([]);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState('');
  const [submittedSymbol, setSubmittedSymbol] = useState('');
  const eventSourceRef = useRef<EventSource | null>(null);
  const { toast } = useToast();

  const placeholder = selectedStock
    ? `Ask about ${selectedStock}... (e.g., technical analysis, recent news)`
    : 'Select a stock to start analysis';

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStock || !query.trim() || isAnalyzing) return;

    // Close any existing connection
    eventSourceRef.current?.close();

    const fullQuery = `${query.trim()} ${selectedStock}`;
    setSubmittedQuery(query.trim());
    setSubmittedSymbol(selectedStock);
    setProgress([]);
    setResult(null);
    setIsAnalyzing(true);

    const es = api.createAnalyzeStream(fullQuery);
    eventSourceRef.current = es;

    es.onmessage = (event) => {
      try {
        const data: SSEEvent = JSON.parse(event.data);
        if (data.type === 'progress' && data.message) {
          setProgress((prev) => [...prev, data.message!]);
        } else if (data.type === 'result' && data.data) {
          setResult(data.data as Record<string, unknown>);
          es.close();
          setIsAnalyzing(false);
        } else if (data.type === 'error') {
          toast({ title: 'Analysis Error', description: data.message, variant: 'destructive' });
          es.close();
          setIsAnalyzing(false);
        }
      } catch (err) {
        console.error('Failed to parse SSE event:', err);
      }
    };

    es.onerror = () => {
      toast({ title: 'Connection Error', description: 'Lost connection to server', variant: 'destructive' });
      es.close();
      setIsAnalyzing(false);
    };

    setQuery('');
  };

  return (
    <div className="h-full flex flex-col p-4 gap-3">
      <div>
        <h2 className="text-lg font-semibold">Analysis Chat</h2>
        <p className="text-xs text-muted-foreground">
          {selectedStock ? `Analyzing ${selectedStock}` : 'Select a stock from the left panel'}
        </p>
      </div>

      {/* Result area */}
      {(progress.length > 0 || result) && (
        <ResultCard
          symbol={submittedSymbol}
          query={submittedQuery}
          progress={progress}
          result={result}
          isAnalyzing={isAnalyzing}
        />
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2 mt-auto">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder}
          disabled={!selectedStock || isAnalyzing}
          className="flex-1 text-sm"
        />
        <Button
          type="submit"
          size="icon"
          disabled={!selectedStock || !query.trim() || isAnalyzing}
        >
          <Send className="h-4 w-4" />
        </Button>
      </form>
    </div>
  );
}

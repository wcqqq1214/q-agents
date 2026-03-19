'use client';

import { useState, useEffect, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { StockCard } from './StockCard';
import { api } from '@/lib/api';
import type { StockInfo } from '@/lib/types';

const SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'];
const REFRESH_INTERVAL = 60000;

interface StockSelectorProps {
  selectedStock: string | null;
  onStockSelect: (symbol: string) => void;
}

export function StockSelector({ selectedStock, onStockSelect }: StockSelectorProps) {
  const [stocks, setStocks] = useState<StockInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchQuotes = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true);
    try {
      const data = await api.getStockQuotes(SYMBOLS);
      setStocks(data.quotes);
    } catch (err) {
      console.error('Failed to fetch stock quotes:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchQuotes();

    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        fetchQuotes();
      }
    }, REFRESH_INTERVAL);

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') fetchQuotes();
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [fetchQuotes]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Magnificent Seven
        </h2>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={() => fetchQuotes(true)}
          disabled={refreshing}
        >
          <RefreshCw className={`h-3 w-3 ${refreshing ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {loading
          ? SYMBOLS.map((s) => (
              <Skeleton key={s} className="h-12 w-full rounded-lg" />
            ))
          : stocks.map((stock) => (
              <StockCard
                key={stock.symbol}
                stock={stock}
                selected={selectedStock === stock.symbol}
                onClick={() => onStockSelect(stock.symbol)}
              />
            ))}
      </div>
    </div>
  );
}

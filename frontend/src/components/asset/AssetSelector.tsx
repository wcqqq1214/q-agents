"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StockCard } from "../stock/StockCard";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import {
  STOCK_POLL_INTERVAL_MS,
  canRefreshOnVisibility,
} from "@/lib/visibility-refresh";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";
import type { StockInfo, CryptoQuote } from "@/lib/types";

const SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"];
const CRYPTO_SYMBOLS = [
  { symbol: "BTC-USDT", name: "Bitcoin" },
  { symbol: "ETH-USDT", name: "Ethereum" },
];

interface AssetSelectorProps {
  selectedAsset: string | null;
  onAssetSelect: (symbol: string) => void;
  assetType: "crypto" | "stocks";
  onAssetTypeChange: (type: "crypto" | "stocks") => void;
}

export function AssetSelector({
  selectedAsset,
  onAssetSelect,
  assetType,
  onAssetTypeChange,
}: AssetSelectorProps) {
  const [stocks, setStocks] = useState<StockInfo[]>([]);
  const [cryptos, setCryptos] = useState<CryptoQuote[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { toast } = useToast();
  const lastRequestStartedAtRef = useRef<number | null>(null);
  const requestInFlightRef = useRef(false);

  const fetchStockQuotes = useCallback(
    async (isManual = false) => {
      if (isManual) setRefreshing(true);
      try {
        const data = await api.getStockQuotes(SYMBOLS);
        setStocks(data.quotes);
      } catch (err) {
        console.error("Failed to fetch stock quotes:", err);
        toast({
          title: "Failed to refresh stock data",
          description: "Unable to fetch latest quotes",
          variant: "destructive",
        });
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [toast],
  );

  const fetchCryptoQuotes = useCallback(
    async (isManual = false) => {
      if (isManual) setRefreshing(true);
      try {
        const symbols = CRYPTO_SYMBOLS.map((c) => c.symbol);
        const data = await api.getCryptoQuotes(symbols);
        setCryptos(data.quotes);
      } catch (err) {
        console.error("Failed to fetch crypto quotes:", err);
        toast({
          title: "Failed to refresh crypto data",
          description: "Unable to fetch latest quotes",
          variant: "destructive",
        });
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [toast],
  );

  const fetchQuotes = useCallback(
    async (isManual = false) => {
      lastRequestStartedAtRef.current = Date.now();
      requestInFlightRef.current = true;

      if (assetType === "crypto") {
        try {
          await fetchCryptoQuotes(isManual);
        } finally {
          requestInFlightRef.current = false;
        }
      } else {
        try {
          await fetchStockQuotes(isManual);
        } finally {
          requestInFlightRef.current = false;
        }
      }
    },
    [assetType, fetchCryptoQuotes, fetchStockQuotes],
  );

  useEffect(() => {
    void fetchQuotes();

    // 300000 ms (5 minutes)
    const interval = window.setInterval(() => {
      if (requestInFlightRef.current) {
        return;
      }
      if (document.visibilityState === "visible") {
        void fetchQuotes();
      }
    }, STOCK_POLL_INTERVAL_MS);

    const handleVisibilityChange = () => {
      if (requestInFlightRef.current) {
        return;
      }
      if (document.visibilityState !== "visible") {
        return;
      }

      if (
        canRefreshOnVisibility({
          now: Date.now(),
          lastRequestStartedAt: lastRequestStartedAtRef.current,
          inFlight: requestInFlightRef.current,
        })
      ) {
        void fetchQuotes();
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchQuotes]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <Tabs
          value={assetType}
          onValueChange={(value) =>
            onAssetTypeChange(value as "crypto" | "stocks")
          }
        >
          <TabsList>
            <TabsTrigger value="stocks">Stocks</TabsTrigger>
            <TabsTrigger value="crypto">Crypto</TabsTrigger>
          </TabsList>
        </Tabs>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={() => fetchQuotes(true)}
          disabled={refreshing}
          aria-label="Refresh quotes"
        >
          <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        {loading
          ? (assetType === "crypto" ? CRYPTO_SYMBOLS : SYMBOLS).map((s) => (
              <Skeleton
                key={typeof s === "string" ? s : s.symbol}
                className="h-12 w-full rounded-lg"
              />
            ))
          : assetType === "crypto"
            ? cryptos.map((crypto) => (
                <StockCard
                  key={crypto.symbol}
                  stock={{
                    symbol: crypto.symbol,
                    name: crypto.name,
                    logo: `/logos/${crypto.symbol}.png`,
                    price: crypto.price,
                    change: crypto.change,
                    changePercent: crypto.changePercent,
                  }}
                  selected={selectedAsset === crypto.symbol}
                  onClick={() => onAssetSelect(crypto.symbol)}
                />
              ))
            : stocks.map((stock) => (
                <StockCard
                  key={stock.symbol}
                  stock={stock}
                  selected={selectedAsset === stock.symbol}
                  onClick={() => onAssetSelect(stock.symbol)}
                />
              ))}
      </div>
    </div>
  );
}

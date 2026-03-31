"use client";

import Image from "next/image";
import { cn } from "@/lib/utils";
import type { StockInfo } from "@/lib/types";

interface StockCardProps {
  stock: StockInfo;
  selected: boolean;
  onClick: () => void;
}

export function StockCard({ stock, selected, onClick }: StockCardProps) {
  const isPositive = (stock.change ?? 0) >= 0;
  const changeColor =
    stock.change === undefined
      ? "text-muted-foreground"
      : isPositive
        ? "text-chart-up"
        : "text-chart-down";
  const changeIcon = isPositive ? "↑" : "↓";

  const formattedPrice =
    stock.price !== undefined
      ? new Intl.NumberFormat("en-US", {
          style: "currency",
          currency: "USD",
        }).format(stock.price)
      : "--";

  const formattedChange =
    stock.changePercent !== undefined
      ? `${changeIcon} ${Math.abs(stock.changePercent).toFixed(2)}%`
      : "--";

  // Check if this is a crypto asset (symbol contains '-')
  const isCrypto = stock.symbol.includes("-");

  return (
    <button
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg border p-2 text-left transition-all",
        "hover:bg-accent/50 hover:shadow-md",
        selected
          ? "border-primary bg-accent/30 shadow-sm"
          : "border-border bg-card",
      )}
    >
      {/* Logo */}
      <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center overflow-hidden rounded-full bg-muted">
        {stock.logo ? (
          <Image
            src={stock.logo}
            alt={stock.symbol}
            width={isCrypto ? 32 : 24}
            height={isCrypto ? 32 : 24}
            className={cn("object-contain", isCrypto ? "" : "p-1")}
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <span className="text-xs font-bold text-muted-foreground">
            {stock.symbol.slice(0, 2)}
          </span>
        )}
      </div>

      {/* Symbol + Price */}
      <div className="min-w-0 flex-1">
        <div className="text-sm leading-tight font-semibold">
          {stock.symbol}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {formattedPrice}
        </div>
      </div>

      {/* Change */}
      <div className={cn("flex-shrink-0 text-xs font-medium", changeColor)}>
        {formattedChange}
      </div>
    </button>
  );
}

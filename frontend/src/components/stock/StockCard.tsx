'use client';

import Image from 'next/image';
import { cn } from '@/lib/utils';
import type { StockInfo } from '@/lib/types';

interface StockCardProps {
  stock: StockInfo;
  selected: boolean;
  onClick: () => void;
}

export function StockCard({ stock, selected, onClick }: StockCardProps) {
  const isPositive = (stock.change ?? 0) >= 0;
  const changeColor = stock.change === undefined
    ? 'text-muted-foreground'
    : isPositive ? 'text-chart-up' : 'text-chart-down';
  const changeIcon = isPositive ? '↑' : '↓';

  const formattedPrice = stock.price !== undefined
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(stock.price)
    : '--';

  const formattedChange = stock.changePercent !== undefined
    ? `${changeIcon} ${Math.abs(stock.changePercent).toFixed(2)}%`
    : '--';

  // Check if this is a crypto asset (symbol contains '-')
  const isCrypto = stock.symbol.includes('-');

  return (
    <button
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-2 p-2 rounded-lg border text-left transition-all',
        'hover:shadow-md hover:bg-accent/50',
        selected
          ? 'border-primary bg-accent/30 shadow-sm'
          : 'border-border bg-card'
      )}
    >
      {/* Logo */}
      <div className="w-8 h-8 rounded-full overflow-hidden flex-shrink-0 bg-muted flex items-center justify-center">
        {stock.logo ? (
          <Image
            src={stock.logo}
            alt={stock.symbol}
            width={isCrypto ? 32 : 24}
            height={isCrypto ? 32 : 24}
            className={cn('object-contain', isCrypto ? '' : 'p-1')}
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
        ) : (
          <span className="text-xs font-bold text-muted-foreground">
            {stock.symbol.slice(0, 2)}
          </span>
        )}
      </div>

      {/* Symbol + Price */}
      <div className="flex-1 min-w-0">
        <div className="font-semibold text-sm leading-tight">{stock.symbol}</div>
        <div className="text-xs text-muted-foreground truncate">{formattedPrice}</div>
      </div>

      {/* Change */}
      <div className={cn('text-xs font-medium flex-shrink-0', changeColor)}>
        {formattedChange}
      </div>
    </button>
  );
}

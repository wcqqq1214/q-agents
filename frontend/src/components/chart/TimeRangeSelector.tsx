'use client';

import { Button } from '@/components/ui/button';
import type { TimeRange } from '@/lib/types';

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
  disabled?: boolean;
  assetType: 'crypto' | 'stocks';
}

const STOCK_RANGES: TimeRange[] = ['D', 'W', 'M', 'Y'];
const CRYPTO_RANGES: TimeRange[] = ['15M', '1H', '4H', '1D', '1W', '1M'];

export function TimeRangeSelector({ value, onChange, disabled, assetType }: TimeRangeSelectorProps) {
  const ranges = assetType === 'crypto' ? CRYPTO_RANGES : STOCK_RANGES;

  const labels: Record<TimeRange, string> = {
    'D': 'Day',
    'W': 'Week',
    'M': 'Month',
    'Y': 'Year',
    '15M': '15 Min',
    '1H': '1 Hour',
    '4H': '4 Hour',
    '1D': '1 Day',
    '1W': '1 Week',
    '1M': '1 Month',
    '1Y': 'All',  // Shows all available data (monthly bars)
  };

  return (
    <div className="flex gap-1">
      {ranges.map((range) => (
        <Button
          key={range}
          variant={value === range ? 'default' : 'outline'}
          size="sm"
          onClick={() => onChange(range)}
          disabled={disabled}
          className="min-w-[60px]"
        >
          {labels[range]}
        </Button>
      ))}
    </div>
  );
}

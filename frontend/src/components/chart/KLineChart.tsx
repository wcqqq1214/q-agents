'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, IChartApi, CandlestickData, ISeriesApi, CandlestickSeries } from 'lightweight-charts';
import { TimeRangeSelector } from './TimeRangeSelector';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import type { TimeRange, OHLCRecord } from '@/lib/types';

interface KLineChartProps {
  selectedStock: string | null;
}

function calculateDateRange(range: TimeRange): { start: string; end: string } {
  const end = new Date();
  const start = new Date();

  switch (range) {
    case 'D':
      // Day: load 2 years of data for zooming, initially show last 3 months
      start.setFullYear(start.getFullYear() - 2);
      break;
    case 'W':
      // Week: load 5 years of data for zooming, initially show last 1 year
      start.setFullYear(start.getFullYear() - 5);
      break;
    case 'M':
      // Month: load 10 years of data for zooming, initially show last 3 years
      start.setFullYear(start.getFullYear() - 10);
      break;
    case 'Y':
      // Year: load all available data (20 years)
      start.setFullYear(start.getFullYear() - 20);
      break;
  }

  return {
    start: start.toISOString().split('T')[0],
    end: end.toISOString().split('T')[0],
  };
}

export function KLineChart({ selectedStock }: KLineChartProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('D');
  const [ohlcData, setOhlcData] = useState<OHLCRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { toast } = useToast();

  // Fetch OHLC data
  const fetchData = useCallback(async () => {
    if (!selectedStock) {
      setOhlcData([]);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const { start, end } = calculateDateRange(timeRange);

      // Map frontend TimeRange to backend interval parameter
      const intervalMap: Record<TimeRange, string> = {
        'D': 'day',
        'W': 'week',
        'M': 'month',
        'Y': 'year',
      };

      const response = await api.getOHLC(
        selectedStock,
        start,
        end,
        intervalMap[timeRange]
      );
      setOhlcData(response.data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to load chart data';
      setError(message);
      toast({
        title: 'Failed to load chart',
        description: 'Unable to fetch OHLC data',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  }, [selectedStock, timeRange, toast]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Create and update chart
  useEffect(() => {
    if (!chartContainerRef.current || ohlcData.length === 0) {
      return;
    }

    // Clear previous chart if exists
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 400,
      localization: {
        locale: 'en-US',
        dateFormat: 'yyyy-MM-dd',
      },
      layout: {
        background: { color: 'transparent' },
        textColor: '#d1d5db',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      timeScale: {
        borderColor: '#334155',
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: '#334155',
      },
    });

    // Add candlestick series using v5 API
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#22c55e',
      downColor: '#ef4444',
      wickUpColor: '#22c55e',
      wickDownColor: '#ef4444',
    });

    // Convert and set data - lightweight-charts expects time as string in YYYY-MM-DD format
    const formattedData = ohlcData.map((d) => ({
      time: d.date,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    series.setData(formattedData);

    // Set initial visible range based on time granularity
    // This shows recent data while keeping all historical data available for zooming
    if (formattedData.length > 0) {
      const lastIndex = formattedData.length - 1;
      let visibleBars: number;

      switch (timeRange) {
        case 'D':
          visibleBars = 60; // Show ~3 months initially
          break;
        case 'W':
          visibleBars = 52; // Show ~1 year initially
          break;
        case 'M':
          visibleBars = 36; // Show ~3 years initially
          break;
        case 'Y':
          visibleBars = 5; // Show ~5 years initially
          break;
      }

      const fromIndex = Math.max(0, lastIndex - visibleBars + 1);
      chart.timeScale().setVisibleRange({
        from: formattedData[fromIndex].time as any,
        to: formattedData[lastIndex].time as any,
      });
    }

    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    chartRef.current = chart;

    return () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [ohlcData]);

  // Render
  if (!selectedStock) {
    return (
      <div className="h-full flex items-center justify-center border rounded-lg bg-card">
        <p className="text-sm text-muted-foreground">Select a stock to view chart</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex flex-col items-center justify-center border rounded-lg bg-card gap-2">
        <p className="text-sm text-destructive">{error}</p>
        <button
          onClick={fetchData}
          className="text-sm text-primary hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col border rounded-lg bg-card p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold">
          {selectedStock} - K-Line Chart
        </h3>
        <TimeRangeSelector
          value={timeRange}
          onChange={setTimeRange}
          disabled={loading}
        />
      </div>

      {/* Chart */}
      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      ) : ohlcData.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-muted-foreground">No data available</p>
        </div>
      ) : (
        <div ref={chartContainerRef} className="flex-1" />
      )}
    </div>
  );
}

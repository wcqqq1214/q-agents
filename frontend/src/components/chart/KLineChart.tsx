'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, IChartApi, CandlestickData, ISeriesApi, CandlestickSeries, HistogramSeries } from 'lightweight-charts';
import { TimeRangeSelector } from './TimeRangeSelector';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';
import type { TimeRange, OHLCRecord } from '@/lib/types';

interface KLineChartProps {
  selectedStock: string | null;
  assetType: 'crypto' | 'stocks';
}

function formatVolume(vol: number): string {
  if (vol >= 1_000_000) return (vol / 1_000_000).toFixed(2) + 'M';
  if (vol >= 1_000) return (vol / 1_000).toFixed(2) + 'K';
  return vol.toFixed(2);
}

function calculateDateRange(range: TimeRange): { start: string; end: string } {
  const end = new Date();
  const start = new Date();

  switch (range) {
    // Stock ranges
    case 'D':
      // Day: load all available data for zooming, initially show last 3 months
      start.setFullYear(start.getFullYear() - 10);
      break;
    case 'W':
      // Week: load all available data for zooming, initially show last 1 year
      start.setFullYear(start.getFullYear() - 10);
      break;
    case 'M':
      // Month: load all available data for zooming, initially show last 3 years
      start.setFullYear(start.getFullYear() - 10);
      break;
    case 'Y':
      // Year: load all available data (20 years)
      start.setFullYear(start.getFullYear() - 20);
      break;
    // Crypto short-term ranges
    case '15M':
      start.setDate(start.getDate() - 90); // Load 90 days for zooming
      break;
    case '1H':
      start.setDate(start.getDate() - 90); // Load 90 days for zooming
      break;
    case '4H':
      start.setDate(start.getDate() - 180); // Load 180 days for zooming
      break;
    // Crypto long-term ranges (load all available data for zooming)
    case '1D':
      start.setFullYear(start.getFullYear() - 10); // Load 10 years for zooming
      break;
    case '1W':
      start.setFullYear(start.getFullYear() - 10); // Load 10 years for zooming
      break;
    case '1M':
      start.setFullYear(start.getFullYear() - 10); // Load 10 years for zooming
      break;
    case '1Y':
      start.setFullYear(start.getFullYear() - 10); // Load 10 years for zooming
      break;
  }

  return {
    start: start.toISOString().split('T')[0],
    end: end.toISOString().split('T')[0],
  };
}

// Helper function to get current timezone information
function getTimezoneInfo(): { name: string; offset: string } {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const offsetMinutes = -new Date().getTimezoneOffset();
  const offsetHours = Math.floor(Math.abs(offsetMinutes) / 60);
  const offsetMins = Math.abs(offsetMinutes) % 60;
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const offsetStr = offsetMins > 0
    ? `UTC${sign}${offsetHours}:${offsetMins.toString().padStart(2, '0')}`
    : `UTC${sign}${offsetHours}`;
  return { name: timeZone, offset: offsetStr };
}

export function KLineChart({ selectedStock, assetType }: KLineChartProps) {
  const defaultTimeRange: TimeRange = assetType === 'crypto' ? '15M' : 'D';
  const [timeRange, setTimeRange] = useState<TimeRange>(defaultTimeRange);
  const [ohlcData, setOhlcData] = useState<OHLCRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const legendRef = useRef<HTMLDivElement>(null);
  const { toast } = useToast();
  const [timezoneInfo] = useState(getTimezoneInfo());

  // Reset timeRange when assetType changes
  useEffect(() => {
    const newDefaultRange: TimeRange = assetType === 'crypto' ? '15M' : 'D';
    setTimeRange(newDefaultRange);
  }, [assetType]);

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
      // Crypto supports: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
      // Stocks support: day, week, month, year
      const stockIntervalMap: Record<TimeRange, string> = {
        'D': 'day',
        'W': 'week',
        'M': 'month',
        'Y': 'year',
        '15M': '15m',
        '1H': '1h',
        '4H': '4h',
        '1D': '1d',
        '1W': '1w',
        '1M': '1m',
        '1Y': '1y',
      };

      const cryptoIntervalMap: Record<TimeRange, string> = {
        'D': '1d',      // Day view: use daily bars
        'W': '1d',      // Week view: use daily bars
        'M': '1d',      // Month view: use daily bars
        'Y': '1d',      // Year view: use daily bars
        '15M': '15m',   // 15-minute view
        '1H': '1h',     // 1-hour view
        '4H': '4h',     // 4-hour view
        '1D': '1d',     // 1-day view
        '1W': '1w',     // 1-week view
        '1M': '1M',     // 1-month button: use monthly bars
        '1Y': '1d',     // 1-year button: use daily bars
      };

      const intervalMap = assetType === 'crypto' ? cryptoIntervalMap : stockIntervalMap;

      const response = assetType === 'crypto'
        ? await api.getCryptoOHLC(
            selectedStock,
            start,
            end,
            intervalMap[timeRange]
          )
        : await api.getStockOHLC(
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
  }, [selectedStock, timeRange, assetType, toast]);

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
        // Custom time formatter for tooltips and crosshair
        timeFormatter: (timestamp: number | string) => {
          // For daily+ data, timestamp is a string (YYYY-MM-DD)
          if (typeof timestamp === 'string') {
            return timestamp;
          }
          // For intraday data, timestamp is Unix seconds
          const date = new Date(timestamp * 1000);
          // Format as YYYY-MM-DD HH:MM
          const year = date.getFullYear();
          const month = String(date.getMonth() + 1).padStart(2, '0');
          const day = String(date.getDate()).padStart(2, '0');
          const hours = String(date.getHours()).padStart(2, '0');
          const minutes = String(date.getMinutes()).padStart(2, '0');
          return `${year}-${month}-${day} ${hours}:${minutes}`;
        },
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
        secondsVisible: false,
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
      priceScaleId: 'right',
    });

    chart.priceScale('right').applyOptions({
      scaleMargins: {
        top: 0.1,
        bottom: 0.25,
      },
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceScaleId: 'volume',
      priceFormat: { type: 'volume' },
    });

    chart.priceScale('volume').applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0,
      },
    });

    // Convert and set data
    // For intraday data (crypto 15M, 1H, 4H), use Unix timestamp
    // For daily+ data, use YYYY-MM-DD format
    const isIntradayData = ['15M', '1H', '4H'].includes(timeRange);

    const formattedData: CandlestickData[] = [];
    const volumeData: { time: any; value: number; color: string }[] = [];

    for (const d of ohlcData) {
      // Use backend's timestamp field if available (for intraday data)
      // Otherwise parse date string for daily+ data
      const time = isIntradayData
        ? ((d as any).timestamp || Math.floor(new Date(d.date).getTime() / 1000) as any)
        : (d.date.split('T')[0] as any);

      formattedData.push({ time, open: d.open, high: d.high, low: d.low, close: d.close });
      volumeData.push({
        time,
        value: d.volume,
        color: d.close >= d.open ? 'rgba(34, 197, 94, 0.6)' : 'rgba(239, 68, 68, 0.6)',
      });
    }

    series.setData(formattedData);
    volumeSeries.setData(volumeData);

    chart.subscribeCrosshairMove((param) => {
      const legend = legendRef.current;
      if (!legend) return;

      if (
        !param.time ||
        param.point === undefined ||
        param.point.x < 0 ||
        param.point.y < 0
      ) {
        legend.style.display = 'none';
        return;
      }

      const ohlc = param.seriesData.get(series) as { open: number; high: number; low: number; close: number } | undefined;
      const volData = param.seriesData.get(volumeSeries) as { value: number } | undefined;

      if (ohlc && volData) {
        const change = ohlc.close - ohlc.open;
        const changePct = (change / ohlc.open) * 100;
        const isUp = change >= 0;
        const color = isUp ? '#22c55e' : '#ef4444';
        const sign = isUp ? '+' : '';

        legend.style.display = 'block';
        legend.innerHTML =
          `<span style="color:#d1d5db">O&nbsp;$${ohlc.open.toFixed(2)}</span>` +
          `&nbsp;&nbsp;<span style="color:#d1d5db">H&nbsp;$${ohlc.high.toFixed(2)}</span>` +
          `&nbsp;&nbsp;<span style="color:#d1d5db">L&nbsp;$${ohlc.low.toFixed(2)}</span>` +
          `&nbsp;&nbsp;<span style="color:#d1d5db">C&nbsp;$${ohlc.close.toFixed(2)}</span>` +
          `&nbsp;&nbsp;<span style="color:${color}">${sign}${changePct.toFixed(2)}%</span>` +
          `&nbsp;&nbsp;<span style="color:#9ca3af">Vol&nbsp;${formatVolume(volData.value)}</span>`;
      } else {
        legend.style.display = 'none';
      }
    });

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
        case '15M':
          visibleBars = 96; // Show ~1 day initially (24h)
          break;
        case '1H':
          visibleBars = 168; // Show ~1 week initially
          break;
        case '4H':
          visibleBars = 42; // Show ~1 week initially
          break;
        case '1D':
          visibleBars = 60; // Show ~2 months initially
          break;
        case '1W':
          visibleBars = 52; // Show ~1 year initially
          break;
        case '1M':
          visibleBars = 36; // Show ~3 years initially
          break;
        case '1Y':
          visibleBars = 5; // Show ~5 years initially
          break;
        default:
          visibleBars = 60;
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
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold">
            {selectedStock} K-Line Chart
          </h3>
          <span className="text-xs text-muted-foreground" title={timezoneInfo.name}>
            ({timezoneInfo.offset})
          </span>
        </div>
        <TimeRangeSelector
          value={timeRange}
          onChange={setTimeRange}
          disabled={loading}
          assetType={assetType}
        />
      </div>

      {/* Chart */}
      <div className="flex-1 relative">
        <div ref={chartContainerRef} className="absolute inset-0" />
        <div
          ref={legendRef}
          className="absolute top-2 left-2 z-10 hidden text-xs font-mono bg-background/80 px-1.5 py-0.5 rounded pointer-events-none"
        />
        {loading && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-background/60">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        )}
        {!loading && ohlcData.length === 0 && (
          <div className="absolute inset-0 z-20 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">No data available</p>
          </div>
        )}
      </div>
    </div>
  );
}

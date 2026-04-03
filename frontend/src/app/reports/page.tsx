// frontend/src/app/reports/page.tsx
"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import { cn } from "@/lib/utils";
import { ReportCard } from "@/components/reports/ReportCard";
import { Button } from "@/components/ui/button";
import { ReportsListSkeleton } from "@/components/reports/ReportsListSkeleton";
import { Accordion } from "@/components/ui/accordion";

function safeTimestampMs(timestamp: string): number {
  const ms = Date.parse(timestamp);
  return Number.isFinite(ms) ? ms : 0;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  async function loadReports(refresh: boolean) {
    try {
      if (refresh) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      const data = await api.getReports();
      setReports(() => {
        return data
          .map((report, index) => ({ report, index }))
          .sort((a, b) => {
            const aMs = safeTimestampMs(a.report.timestamp);
            const bMs = safeTimestampMs(b.report.timestamp);

            if (aMs !== bMs) return bMs - aMs;
            return a.index - b.index;
          })
          .map(({ report }) => report);
      });
    } catch (error) {
      console.error("Failed to load reports", error);
      setReports([]);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    void loadReports(false);
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Analysis Reports</h1>
          <p className="mt-2 text-muted-foreground">
            Browse all generated financial analysis reports
          </p>
        </div>
        <Button
          onClick={() => void loadReports(true)}
          disabled={isLoading || isRefreshing}
        >
          <RefreshCw
            data-icon="inline-start"
            className={cn(isRefreshing && "animate-spin")}
          />
          Refresh
        </Button>
      </div>

      {isLoading ? (
        <ReportsListSkeleton />
      ) : reports.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <p className="text-muted-foreground">
            No analyses yet. Run your first analysis from the main page.
          </p>
        </div>
      ) : (
        <Accordion type="multiple" className="flex flex-col gap-4">
          {reports.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </Accordion>
      )}
    </div>
  );
}

// frontend/src/app/reports/page.tsx
"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Report } from "@/lib/types";
import { Accordion } from "@/components/ui/accordion";
import { ReportCard } from "@/components/reports/ReportCard";

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  async function loadReports() {
    try {
      const data = await api.getReports();
      setReports(
        [...data].sort(
          (a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp),
        ),
      );
    } catch (error) {
      console.error("Failed to load reports", error);
      setReports([]);
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadReports();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Analysis Reports</h1>
        <p className="mt-2 text-muted-foreground">
          Browse all generated financial analysis reports
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading reports...</p>
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

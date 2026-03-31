// frontend/src/app/reports/page.tsx
'use client';

import { Accordion } from '@/components/ui/accordion';
import { mockReports } from '@/lib/mock-data/reports';
import { ReportCard } from '@/components/reports/ReportCard';

const sorted = [...mockReports].sort(
  (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
);

export default function ReportsPage() {
  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-3xl font-bold">Analysis Reports</h1>
        <p className="text-muted-foreground mt-2">
          Browse all generated financial analysis reports
        </p>
      </div>

      {sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <p className="text-muted-foreground">
            No analyses yet. Run your first analysis from the main page.
          </p>
        </div>
      ) : (
        <Accordion multiple className="flex flex-col gap-4">
          {sorted.map((report) => (
            <ReportCard key={report.id} report={report} />
          ))}
        </Accordion>
      )}
    </div>
  );
}

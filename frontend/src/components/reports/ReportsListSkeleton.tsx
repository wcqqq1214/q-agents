// frontend/src/components/reports/ReportsListSkeleton.tsx

import { Skeleton } from "@/components/ui/skeleton";

export function ReportsListSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      {Array.from({ length: 3 }).map((_, index) => (
        <Skeleton key={index} className="h-24 w-full rounded-lg" />
      ))}
    </div>
  );
}

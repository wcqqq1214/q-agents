"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useTrendColor } from "@/hooks/use-trend-color";

export default function SettingsPage() {
  const { trendMode, setTrendMode, isMounted } = useTrendColor();

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <div className="mb-8">
        <h1 className="mb-2 text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground">
          Manage frontend display preferences for charts and market visuals.
        </p>
      </div>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Display Preferences</CardTitle>
            <CardDescription>
              Configure chart color conventions for price movements.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between gap-4">
              <div className="space-y-0.5">
                <Label>Price Color Convention</Label>
                <p className="text-sm text-muted-foreground">
                  {!isMounted
                    ? "Loading..."
                    : trendMode === "chinese"
                      ? "Red = Up, Green = Down"
                      : "Green = Up, Red = Down"}
                </p>
              </div>
              <Switch
                aria-label="Toggle price color convention"
                checked={isMounted ? trendMode === "chinese" : false}
                disabled={!isMounted}
                onCheckedChange={(checked: boolean) =>
                  setTrendMode(checked ? "chinese" : "western")
                }
              />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

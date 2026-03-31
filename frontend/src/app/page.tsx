"use client";

import { useState } from "react";
import { AssetSelector } from "@/components/asset/AssetSelector";
import { ChatPanel } from "@/components/chat/ChatPanel";
import { KLineChart } from "@/components/chart/KLineChart";

export default function Home() {
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [assetType, setAssetType] = useState<"crypto" | "stocks">("stocks");

  const handleAssetTypeChange = (type: "crypto" | "stocks") => {
    setAssetType(type);
    setSelectedAsset(null); // Clear selection when switching asset type
  };

  return (
    <div className="flex h-[calc(100vh-8rem)] gap-4">
      {/* Left panel */}
      <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-hidden">
        {/* Top: Stock selector (40% height) */}
        <div className="min-h-0 basis-2/5 overflow-y-auto">
          <AssetSelector
            selectedAsset={selectedAsset}
            onAssetSelect={setSelectedAsset}
            assetType={assetType}
            onAssetTypeChange={handleAssetTypeChange}
          />
        </div>

        {/* Bottom: K-line chart (60% height) */}
        <div className="min-h-0 basis-3/5 overflow-hidden">
          <KLineChart selectedStock={selectedAsset} assetType={assetType} />
        </div>
      </div>

      {/* Right panel: Chat */}
      <div className="flex w-1/3 shrink-0 flex-col overflow-hidden border-l pl-4">
        <ChatPanel selectedStock={selectedAsset} />
      </div>
    </div>
  );
}

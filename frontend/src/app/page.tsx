'use client';

import { useState } from 'react';
import { AssetSelector } from '@/components/asset/AssetSelector';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { KLineChart } from '@/components/chart/KLineChart';

export default function Home() {
  const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
  const [assetType, setAssetType] = useState<'crypto' | 'stocks'>('stocks');

  const handleAssetTypeChange = (type: 'crypto' | 'stocks') => {
    setAssetType(type);
    setSelectedAsset(null); // Clear selection when switching asset type
  };

  return (
    <div className="flex gap-4 h-[calc(100vh-8rem)]">
      {/* Left panel */}
      <div className="flex-1 flex flex-col gap-4 overflow-hidden">
        {/* Top: Stock selector (40% height) */}
        <div className="h-[40%] overflow-y-auto">
          <AssetSelector
            selectedAsset={selectedAsset}
            onAssetSelect={setSelectedAsset}
            assetType={assetType}
            onAssetTypeChange={handleAssetTypeChange}
          />
        </div>

        {/* Bottom: K-line chart (60% height) */}
        <div className="flex-1 overflow-hidden">
          <KLineChart selectedStock={selectedAsset} assetType={assetType} />
        </div>
      </div>

      {/* Right panel: Chat */}
      <div className="w-[35%] border-l overflow-hidden flex flex-col">
        <ChatPanel selectedStock={selectedAsset} />
      </div>
    </div>
  );
}

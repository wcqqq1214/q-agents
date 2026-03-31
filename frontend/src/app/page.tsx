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
      <div className="flex-1 flex flex-col gap-4 overflow-hidden min-w-0">
        {/* Top: Stock selector (40% height) */}
        <div className="basis-2/5 min-h-0 overflow-y-auto">
          <AssetSelector
            selectedAsset={selectedAsset}
            onAssetSelect={setSelectedAsset}
            assetType={assetType}
            onAssetTypeChange={handleAssetTypeChange}
          />
        </div>

        {/* Bottom: K-line chart (60% height) */}
        <div className="basis-3/5 min-h-0 overflow-hidden">
          <KLineChart selectedStock={selectedAsset} assetType={assetType} />
        </div>
      </div>

      {/* Right panel: Chat */}
      <div className="w-1/3 shrink-0 border-l pl-4 overflow-hidden flex flex-col">
        <ChatPanel selectedStock={selectedAsset} />
      </div>
    </div>
  );
}

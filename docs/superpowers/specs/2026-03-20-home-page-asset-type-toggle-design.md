---
name: Home Page Asset Type Toggle Design
description: Add crypto/stocks toggle to Home page with component renaming for future crypto support
type: design
date: 2026-03-20
---

# Home Page Asset Type Toggle Design

## Overview

Add a toggle UI to the Home page that allows users to switch between crypto and stocks asset types. This is a UI-only change with no functional logic implementation yet. The design also includes renaming components from stock-specific to asset-generic names to support future crypto functionality.

## Goals

1. Add crypto/stocks toggle buttons to the asset selector header
2. Rename StockSelector to AssetSelector for better semantic accuracy
3. Add state management infrastructure for asset type selection
4. Maintain existing functionality while preparing for future crypto integration

## Non-Goals

- Implementing actual crypto data fetching
- Changing the data display logic based on asset type
- Adding crypto-specific components or API calls

## Component Renaming

### Files to Rename

- `frontend/src/components/stock/StockSelector.tsx` → `frontend/src/components/asset/AssetSelector.tsx`

### Code Changes

**Component and Interface Names:**
- `StockSelector` → `AssetSelector`
- `StockSelectorProps` → `AssetSelectorProps`

**Props and Variables:**
- `selectedStock` → `selectedAsset`
- `onStockSelect` → `onAssetSelect`

**Affected Files:**
- `frontend/src/app/page.tsx` (Home page)
- `frontend/src/components/asset/AssetSelector.tsx` (renamed from StockSelector)
- Any other files importing StockSelector

## UI Design

### Layout

The toggle will be placed in the AssetSelector header, replacing the current "Stocks" text label:

```
┌─────────────────────────────────────┐
│ [Crypto] [Stocks]        [Refresh]  │
└─────────────────────────────────────┘
```

- Left side: Tabs component with "Crypto" and "Stocks" options
- Right side: Existing refresh button (unchanged)

### Component Structure

**Tabs Configuration:**
- Component: Use existing `Tabs` component from `@/components/ui/tabs`
- Variant: `default` (button-style with background)
- Labels: English text - "Crypto" and "Stocks"
- Default selection: "Stocks"

### Visual Specifications

- Remove the existing `<h2>` element that displays "Stocks"
- Use flexbox layout: `flex items-center justify-between`
- Tabs on the left, refresh button on the right
- Maintain existing spacing and styling for the refresh button

## State Management

### Home Page State

Add new state to track the selected asset type:

```typescript
const [assetType, setAssetType] = useState<'crypto' | 'stocks'>('stocks');
```

### Props Flow

**Home → AssetSelector:**
```typescript
interface AssetSelectorProps {
  selectedAsset: string | null;
  onAssetSelect: (symbol: string) => void;
  assetType: 'crypto' | 'stocks';
  onAssetTypeChange: (type: 'crypto' | 'stocks') => void;
}
```

**AssetSelector Implementation:**
- Tabs component is controlled by `assetType` prop
- Tab changes trigger `onAssetTypeChange` callback
- Current data fetching logic remains unchanged (still fetches stocks)

## Implementation Details

### File Structure

```
frontend/src/
├── app/
│   └── page.tsx                          # Update imports and variable names
├── components/
│   ├── asset/                            # New directory (renamed from stock)
│   │   └── AssetSelector.tsx             # Renamed, add Tabs UI
│   └── stock/
│       └── StockCard.tsx                 # No changes needed
```

### AssetSelector Header Changes

**Before:**
```tsx
<div className="flex items-center justify-between">
  <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
    Stocks
  </h2>
  <Button ... />
</div>
```

**After:**
```tsx
<div className="flex items-center justify-between">
  <Tabs value={assetType} onValueChange={onAssetTypeChange}>
    <TabsList variant="default">
      <TabsTrigger value="crypto">Crypto</TabsTrigger>
      <TabsTrigger value="stocks">Stocks</TabsTrigger>
    </TabsList>
  </Tabs>
  <Button ... />
</div>
```

### Home Page Changes

**State Addition:**
```typescript
const [assetType, setAssetType] = useState<'crypto' | 'stocks'>('stocks');
const [selectedAsset, setSelectedAsset] = useState<string | null>(null);
```

**Component Usage:**
```tsx
<AssetSelector
  selectedAsset={selectedAsset}
  onAssetSelect={setSelectedAsset}
  assetType={assetType}
  onAssetTypeChange={setAssetType}
/>
```

## Future Extensibility

This design prepares for future crypto integration:

1. **State Infrastructure**: The `assetType` state in Home page can be used to conditionally render different content
2. **Generic Naming**: AssetSelector can handle both crypto and stock data
3. **Props Interface**: The component already accepts the asset type, making it easy to add conditional logic later
4. **Component Structure**: The Tabs UI naturally supports adding more asset types if needed

## Testing Considerations

### Manual Testing Checklist

1. Verify Tabs render correctly in the header
2. Verify clicking Crypto/Stocks tabs changes the active state
3. Verify refresh button still works
4. Verify stock selection still works
5. Verify no console errors
6. Verify responsive layout (if applicable)

### Visual Regression

- Compare before/after screenshots of the AssetSelector header
- Ensure Tabs styling matches the design system
- Verify spacing and alignment

## Migration Notes

### Breaking Changes

None - this is an internal refactoring. No external APIs or props are changed in a breaking way.

### Backward Compatibility

The component maintains all existing functionality. The renaming is purely semantic and doesn't affect behavior.

## Why This Approach

**Why rename now instead of later?**
- Avoids technical debt
- Makes the codebase more maintainable
- Prevents confusion when crypto functionality is added
- Single PR is easier to review than split changes

**Why put state in Home page instead of AssetSelector?**
- Allows other components to react to asset type changes in the future
- Follows React best practices (lift state up)
- Makes the data flow explicit and traceable

**Why use Tabs instead of custom buttons?**
- Leverages existing design system component
- Provides built-in accessibility features
- Consistent with other toggle UIs in the project
- Less code to maintain

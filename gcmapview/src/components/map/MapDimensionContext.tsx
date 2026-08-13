import { useState, type ReactNode } from 'react';
import { MapDimensionContext } from './useMapDimension';

export function MapDimensionProvider({ children }: { children: ReactNode }) {
  const [is3d, setIs3d] = useState(false);
  const [adjustElevatedHeights, setAdjustElevatedHeights] = useState(true);
  return (
    <MapDimensionContext.Provider value={{ is3d, adjustElevatedHeights, setIs3d, setAdjustElevatedHeights }}>
      {children}
    </MapDimensionContext.Provider>
  );
}

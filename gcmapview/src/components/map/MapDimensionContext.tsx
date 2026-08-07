import { createContext, useContext, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react';

type MapDimensionContextValue = {
  is3d: boolean;
  setIs3d: Dispatch<SetStateAction<boolean>>;
};

const MapDimensionContext = createContext<MapDimensionContextValue | null>(null);

export function MapDimensionProvider({ children }: { children: ReactNode }) {
  const [is3d, setIs3d] = useState(false);
  return <MapDimensionContext.Provider value={{ is3d, setIs3d }}>{children}</MapDimensionContext.Provider>;
}

export function useMapDimension() {
  const value = useContext(MapDimensionContext);
  if (!value) {
    throw new Error('useMapDimension must be used within MapDimensionProvider');
  }
  return value;
}

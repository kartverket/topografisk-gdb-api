import { createContext, useContext, type Dispatch, type SetStateAction } from 'react';

type MapDimensionContextValue = {
  is3d: boolean;
  adjustElevatedHeights: boolean;
  setIs3d: Dispatch<SetStateAction<boolean>>;
  setAdjustElevatedHeights: Dispatch<SetStateAction<boolean>>;
};

const MapDimensionContext = createContext<MapDimensionContextValue | null>(null);

function useMapDimension() {
  const value = useContext(MapDimensionContext);
  if (!value) {
    throw new Error('useMapDimension must be used within MapDimensionProvider');
  }
  return value;
}

export { MapDimensionContext, useMapDimension };

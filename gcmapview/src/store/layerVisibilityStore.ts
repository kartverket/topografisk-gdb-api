import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const MAP_LAYER_IDS = ['parcels', 'buildings', 'platformEdges', 'trackCentres'] as const;

export type MapLayerId = (typeof MAP_LAYER_IDS)[number];

export const MAP_LAYER_LABELS: Record<MapLayerId, string> = {
  parcels: 'Cadastre parcels',
  buildings: 'Cadastre buildings',
  platformEdges: 'Bane platform edges',
  trackCentres: 'Bane track centres'
};

export type LayerVisibility = Record<MapLayerId, boolean>;

const defaultVisibility: LayerVisibility = {
  parcels: true,
  buildings: true,
  platformEdges: true,
  trackCentres: true
};

type LayerVisibilityState = {
  visibility: LayerVisibility;
  setLayerVisible: (id: MapLayerId, visible: boolean) => void;
  toggleLayer: (id: MapLayerId) => void;
};

export const useLayerVisibilityStore = create<LayerVisibilityState>()(
  persist(
    set => ({
      visibility: { ...defaultVisibility },
      setLayerVisible: (id, visible) =>
        set(state => ({
          visibility: { ...state.visibility, [id]: visible }
        })),
      toggleLayer: id =>
        set(state => ({
          visibility: {
            ...state.visibility,
            [id]: !state.visibility[id]
          }
        }))
    }),
    { name: 'gcmapview-layer-visibility' }
  )
);

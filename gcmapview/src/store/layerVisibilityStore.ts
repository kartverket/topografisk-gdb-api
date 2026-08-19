import { create } from 'zustand';
import { type CollectionId, getDatasetCollectionIds } from '../api/geocomponentsApi';

export const MAP_LAYER_IDS = [
  'parcels',
  'buildings',
  'platformEdges',
  'trackCentres',
  'bygning',
  'bygningOmrade',
  'bygningSenterlinje',
  'bygningPosisjon'
] as const;

export type MapLayerId = (typeof MAP_LAYER_IDS)[number];

export const MAP_LAYER_LABELS: Record<MapLayerId, string> = {
  parcels: 'Matrikkelparseller',
  buildings: 'Matrikkelbygninger',
  platformEdges: 'FKB-Bane plattformkanter',
  trackCentres: 'FKB-Bane spormidt',
  bygning: 'Bygning linjeverk',
  bygningOmrade: 'Bygning område',
  bygningSenterlinje: 'Bygning senterlinje',
  bygningPosisjon: 'Bygning posisjon'
};

export const MAP_LAYER_COLLECTION_IDS: Record<MapLayerId, CollectionId> = {
  parcels: 'parcels',
  buildings: 'buildings',
  platformEdges: 'jernbaneplattformkant',
  trackCentres: 'spormidt',
  bygning: 'bygning',
  bygningOmrade: 'bygning_omrade',
  bygningSenterlinje: 'bygning_senterlinje',
  bygningPosisjon: 'bygning_posisjon'
};

export type LayerVisibility = Record<MapLayerId, boolean>;

const defaultVisibility: LayerVisibility = {
  parcels: true,
  buildings: true,
  platformEdges: true,
  trackCentres: true,
  bygning: true,
  bygningOmrade: true,
  bygningSenterlinje: true,
  bygningPosisjon: true
};

type LayerVisibilityState = {
  visibility: LayerVisibility;
  availableLayerIds: readonly MapLayerId[];
  isLoadingAvailableLayers: boolean;
  hasResolvedAvailableLayers: boolean;
  setVisibility: (visibility: LayerVisibility) => void;
  setLayerVisible: (id: MapLayerId, visible: boolean) => void;
  toggleLayer: (id: MapLayerId) => void;
  resolveAvailableLayerIds: () => Promise<readonly MapLayerId[]>;
};

export function filterUnavailableLayers(
  visibility: LayerVisibility,
  availableLayerIds: readonly MapLayerId[]
): LayerVisibility {
  const availableLayers = new Set(availableLayerIds);

  return MAP_LAYER_IDS.reduce((nextVisibility, layerId) => {
    nextVisibility[layerId] = availableLayers.has(layerId) ? visibility[layerId] : false;
    return nextVisibility;
  }, {} as LayerVisibility);
}

let resolveAvailableLayerIdsPromise: Promise<readonly MapLayerId[]> | undefined;

export const useLayerVisibilityStore = create<LayerVisibilityState>()((set, get) => ({
  visibility: { ...defaultVisibility },
  availableLayerIds: [],
  isLoadingAvailableLayers: true,
  hasResolvedAvailableLayers: false,
  setVisibility: visibility => set({ visibility: { ...visibility } }),
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
    })),
  resolveAvailableLayerIds: () => {
    if (get().hasResolvedAvailableLayers) {
      return Promise.resolve(get().availableLayerIds);
    }

    if (resolveAvailableLayerIdsPromise) {
      return resolveAvailableLayerIdsPromise;
    }

    set({ isLoadingAvailableLayers: true });

    resolveAvailableLayerIdsPromise = getDatasetCollectionIds()
      .then(availableCollectionIds =>
        MAP_LAYER_IDS.filter(layerId => availableCollectionIds.has(MAP_LAYER_COLLECTION_IDS[layerId]))
      )
      .catch(cause => {
        console.warn('[gcmapview] could not load dataset layer availability', cause);
        return MAP_LAYER_IDS;
      })
      .then(availableLayerIds => {
        set({
          availableLayerIds,
          hasResolvedAvailableLayers: true,
          isLoadingAvailableLayers: false
        });
        return availableLayerIds;
      })
      .finally(() => {
        resolveAvailableLayerIdsPromise = undefined;
      });

    return resolveAvailableLayerIdsPromise;
  }
}));

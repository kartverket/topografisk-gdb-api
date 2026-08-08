import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { LayerVisibility } from './layerVisibilityStore';

export type FavoriteMapView = {
  name: string;
  center: [number, number];
  zoom: number;
  visibility?: LayerVisibility;
};

type LegacyFavoriteMapView = {
  center: [number, number];
  zoom: number;
};

type MapViewState = {
  favoriteViews: FavoriteMapView[];
  activeFavoriteName?: string;
  saveFavoriteView: (view: FavoriteMapView) => void;
  selectFavoriteView: (name: string) => void;
  removeFavoriteView: (name: string) => void;
};

type PersistedMapViewState = Partial<MapViewState> & {
  favoriteView?: LegacyFavoriteMapView;
};

function normalizedActiveFavoriteName(favoriteViews: FavoriteMapView[], activeFavoriteName?: string) {
  return favoriteViews.some(favoriteView => favoriteView.name === activeFavoriteName)
    ? activeFavoriteName
    : favoriteViews[0]?.name;
}

export const useMapViewStore = create<MapViewState>()(
  persist(
    set => ({
      favoriteViews: [],
      activeFavoriteName: undefined,
      saveFavoriteView: favoriteView =>
        set(state => {
          const existingIndex = state.favoriteViews.findIndex(view => view.name === favoriteView.name);
          const favoriteViews =
            existingIndex >= 0
              ? state.favoriteViews.map((view, index) => (index === existingIndex ? favoriteView : view))
              : [...state.favoriteViews, favoriteView];

          return {
            favoriteViews,
            activeFavoriteName: favoriteView.name
          };
        }),
      selectFavoriteView: activeFavoriteName =>
        set(state =>
          state.favoriteViews.some(favoriteView => favoriteView.name === activeFavoriteName)
            ? { activeFavoriteName }
            : {}
        ),
      removeFavoriteView: nameToRemove =>
        set(state => {
          const favoriteViews = state.favoriteViews.filter(favoriteView => favoriteView.name !== nameToRemove);
          return {
            favoriteViews,
            activeFavoriteName:
              state.activeFavoriteName === nameToRemove
                ? favoriteViews[0]?.name
                : normalizedActiveFavoriteName(favoriteViews, state.activeFavoriteName)
          };
        })
    }),
    {
      name: 'gcmapview-favorite-view',
      version: 3,
      migrate: persistedState => {
        const state = (persistedState ?? {}) as PersistedMapViewState;

        if (Array.isArray(state.favoriteViews)) {
          return {
            favoriteViews: state.favoriteViews,
            activeFavoriteName: normalizedActiveFavoriteName(state.favoriteViews, state.activeFavoriteName)
          };
        }

        if (state.favoriteView) {
          const favoriteViews: FavoriteMapView[] = [{ name: 'Favorite 1', ...state.favoriteView }];
          return {
            favoriteViews,
            activeFavoriteName: favoriteViews[0].name
          };
        }

        return {
          favoriteViews: [],
          activeFavoriteName: undefined
        };
      }
    }
  )
);
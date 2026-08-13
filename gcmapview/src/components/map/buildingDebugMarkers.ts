import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection } from '../../map/geojson';
import { featureCentroid } from './mapViewGeometry';

export type BuildingDebugMarkerState = {
  markers: maplibregl.Marker[];
};

export function createBuildingDebugMarkerState(): BuildingDebugMarkerState {
  return { markers: [] };
}

export function clearBuildingDebugMarkers(state: BuildingDebugMarkerState) {
  for (const marker of state.markers) {
    marker.remove();
  }

  state.markers = [];
}

export function setBuildingDebugMarkerVisibility(state: BuildingDebugMarkerState, visible: boolean) {
  for (const marker of state.markers) {
    marker.getElement().style.display = visible ? '' : 'none';
  }
}

export function updateBuildingDebugMarkers(
  state: BuildingDebugMarkerState,
  map: maplibregl.Map,
  buildings: FeatureCollection,
  visible: boolean
) {
  clearBuildingDebugMarkers(state);

  state.markers = buildings.features.flatMap(building => {
    const centroid = featureCentroid(building);
    if (!centroid) {
      return [];
    }

    const markerElement = document.createElement('div');
    markerElement.className =
      'h-1.5 w-1.5 rounded-full border border-white bg-black shadow-[0_0_0_1px_rgb(0_0_0/0.45)]';
    markerElement.title = `Building ${building.id ?? ''}`.trim();
    markerElement.style.display = visible ? '' : 'none';

    return [
      new maplibregl.Marker({
        element: markerElement,
        anchor: 'center'
      })
        .setLngLat([centroid[0], centroid[1]])
        .addTo(map)
    ];
  });
}

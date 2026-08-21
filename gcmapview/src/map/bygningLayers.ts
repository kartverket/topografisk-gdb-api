import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection } from './geojson';
import { normalizeLineworkFeatureCollection } from './lineworkHeight';

export const bygningSourceId = 'bygning-linework';
export const bygningLayerId = 'bygning-linework-line';

export function bygningLayerFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return normalizeBygningFeatureCollection(featureCollection);
}

export function normalizeBygningFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return normalizeLineworkFeatureCollection(featureCollection);
}

export function addBygningSourcesAndLayers(map: maplibregl.Map, bygning: FeatureCollection) {
  map.addSource(bygningSourceId, {
    type: 'geojson',
    data: bygningLayerFeatureCollection(bygning)
  });
  map.addLayer({
    id: bygningLayerId,
    type: 'line',
    source: bygningSourceId,
    paint: {
      'line-color': '#000000',
      'line-opacity': 0.95,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.8, 14, 2.2]
    }
  });
}

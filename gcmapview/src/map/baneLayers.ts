import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection } from './geojson';
import { normalizeLineworkFeatureCollection } from './lineworkHeight';
import { heightColorExpression } from './map3d';

export const platformEdgesSourceId = 'bane-platform-edges';
export const trackCentresSourceId = 'bane-track-centres';

export const platformEdgesLayerId = 'bane-platform-edges-line';
export const trackCentresLayerId = 'bane-track-centres-line';

export function normalizeBaneFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return normalizeLineworkFeatureCollection(featureCollection);
}

export function addBaneSourcesAndLayers(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection
) {
  map.addSource(platformEdgesSourceId, {
    type: 'geojson',
    data: normalizeBaneFeatureCollection(platformEdges)
  });
  map.addSource(trackCentresSourceId, {
    type: 'geojson',
    data: normalizeBaneFeatureCollection(trackCentres)
  });
  map.addLayer({
    id: platformEdgesLayerId,
    type: 'line',
    source: platformEdgesSourceId,
    paint: {
      'line-color': '#000000',
      'line-opacity': 0.9,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 14, 4]
    }
  });
  map.addLayer({
    id: trackCentresLayerId,
    type: 'line',
    source: trackCentresSourceId,
    paint: {
      'line-color': heightColorExpression(),
      'line-opacity': 0.95,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 14, 5]
    }
  });
}

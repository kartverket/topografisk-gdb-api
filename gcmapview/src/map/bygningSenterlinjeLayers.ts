import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection } from './geojson';
import { normalizeBygningFeatureCollection } from './bygningLayers';

export const bygningSenterlinjeSourceId = 'bygning-senterlinje';
export const bygningSenterlinjeLayerId = 'bygning-senterlinje-line';
export const bygningSenterlinjeColor = '#8a5a2b';

export function bygningSenterlinjeLayerFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return normalizeBygningFeatureCollection(featureCollection);
}

export function normalizeBygningSenterlinjeFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return normalizeBygningFeatureCollection(featureCollection);
}

export function addBygningSenterlinjeSourceAndLayer(map: maplibregl.Map, bygningSenterlinje: FeatureCollection) {
  map.addSource(bygningSenterlinjeSourceId, {
    type: 'geojson',
    data: bygningSenterlinjeLayerFeatureCollection(bygningSenterlinje)
  });
  map.addLayer({
    id: bygningSenterlinjeLayerId,
    type: 'line',
    source: bygningSenterlinjeSourceId,
    paint: {
      'line-color': bygningSenterlinjeColor,
      'line-opacity': 0.95,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.7, 14, 1.8]
    }
  });
}
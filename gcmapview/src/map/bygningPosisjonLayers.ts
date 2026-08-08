import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection } from './geojson';

export const bygningPosisjonSourceId = 'bygning-posisjon';
export const bygningPosisjonLayerId = 'bygning-posisjon-circle';

export function normalizeBygningPosisjonFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return featureCollection;
}

export function addBygningPosisjonSourceAndLayer(map: maplibregl.Map, bygningPosisjon: FeatureCollection) {
  map.addSource(bygningPosisjonSourceId, {
    type: 'geojson',
    data: normalizeBygningPosisjonFeatureCollection(bygningPosisjon)
  });

  map.addLayer({
    id: bygningPosisjonLayerId,
    type: 'circle',
    source: bygningPosisjonSourceId,
    paint: {
      'circle-color': '#111111',
      'circle-opacity': 0.9,
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 10, 2.5, 16, 5.5],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 10, 0.6, 16, 1.4]
    }
  });
}
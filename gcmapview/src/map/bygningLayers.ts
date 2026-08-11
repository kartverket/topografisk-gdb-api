import * as maplibregl from 'maplibre-gl';
import type { FeatureCollection, Position } from './geojson';
import { maxCoordinateHeight } from './map3d';

export const bygningSourceId = 'bygning-linework';
export const bygningLayerId = 'bygning-linework-line';

export function bygningLayerFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return normalizeBygningFeatureCollection(featureCollection);
}

export function normalizeBygningFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map(feature => {
      if (!feature.geometry?.coordinates || !Array.isArray(feature.geometry.coordinates)) {
        return feature;
      }

      if (feature.geometry.type === 'LineString') {
        const coordinates = feature.geometry.coordinates as Position[];
        return {
          ...feature,
          properties: {
            ...(feature.properties ?? {}),
            height: maxCoordinateHeight(coordinates)
          },
          geometry: {
            type: 'LineString',
            coordinates
          }
        };
      }

      if (feature.geometry.type === 'MultiLineString') {
        const coordinates = feature.geometry.coordinates as Position[][];
        return {
          ...feature,
          properties: {
            ...(feature.properties ?? {}),
            height: Math.max(0, ...coordinates.map(maxCoordinateHeight))
          },
          geometry: {
            type: 'MultiLineString',
            coordinates
          }
        };
      }

      return feature;
    })
  };
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

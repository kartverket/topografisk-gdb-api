import type { FeatureCollection, Position } from './geojson';
import { maxCoordinateHeight } from './map3d';

export function normalizeLineworkFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
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

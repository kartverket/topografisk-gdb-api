import * as maplibregl from 'maplibre-gl';
import type { Feature, FeatureCollection, Position } from './geojson';

export const bygningOmradeSourceId = 'bygning-omrade';
export const bygningOmradeFillLayerId = 'bygning-omrade-fill';
export const bygningOmradeOutlineLayerId = 'bygning-omrade-outline';
export const bygningOmradeExtrusionSourceId = 'bygning-omrade-3d';
export const bygningOmradeExtrusionLayerId = 'bygning-omrade-extrusion';
export const bygningOmradeFillColor = '#a727a1';
export const bygningOmradeOutlineColor = '#601c5a';

const MIN_BYGNING_OMRADE_EXTRUSION_HEIGHT_M = 0.5;

function maxPolygonCoordinateHeight(coordinates: Position[]): number {
  let maxHeight = 0;

  for (const position of coordinates) {
    const z = position[2];
    if (typeof z === 'number' && Number.isFinite(z)) {
      maxHeight = Math.max(maxHeight, z);
    }
  }

  return maxHeight;
}

function polygonHeights(feature: Feature): number[] {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates || !Array.isArray(coordinates)) {
    return [];
  }

  if (feature.geometry?.type === 'Polygon') {
    return (coordinates as Position[][]).map(maxPolygonCoordinateHeight);
  }

  if (feature.geometry?.type === 'MultiPolygon') {
    return (coordinates as Position[][][]).flatMap(polygon => polygon.map(maxPolygonCoordinateHeight));
  }

  return [];
}

function featureHeight(feature: Feature): number {
  return Math.max(0, ...polygonHeights(feature));
}

function adjustedHeight(height: number, heightOffset: number): number {
  if (!Number.isFinite(height) || height <= 0) {
    return MIN_BYGNING_OMRADE_EXTRUSION_HEIGHT_M;
  }

  return Math.max(MIN_BYGNING_OMRADE_EXTRUSION_HEIGHT_M, height - heightOffset);
}

export function lowestPositiveBygningOmradeHeight(featureCollection: FeatureCollection): number {
  let minimum = Number.POSITIVE_INFINITY;

  for (const feature of featureCollection.features) {
    for (const height of polygonHeights(feature)) {
      if (height > 0) {
        minimum = Math.min(minimum, height);
      }
    }
  }

  return Number.isFinite(minimum) ? minimum : 0;
}

export function bygningOmradeExtrusionFeatureCollection(
  featureCollection: FeatureCollection,
  heightOffset = 0
): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map(feature => {
      const height = featureHeight(feature);

      return {
        ...feature,
        properties: {
          ...(feature.properties ?? {}),
          elevation: height,
          base: 0,
          height: adjustedHeight(height, heightOffset)
        }
      };
    })
  };
}

export function addBygningOmradeSourceAndLayers(map: maplibregl.Map, bygningOmrade: FeatureCollection) {
  map.addSource(bygningOmradeSourceId, {
    type: 'geojson',
    data: bygningOmrade
  });

  map.addLayer({
    id: bygningOmradeFillLayerId,
    type: 'fill',
    source: bygningOmradeSourceId,
    filter: ['==', '$type', 'Polygon'],
    paint: {
      'fill-color': bygningOmradeFillColor,
      'fill-opacity': 0.18,
      'fill-outline-color': '#000000'
    }
  });

  map.addLayer({
    id: bygningOmradeOutlineLayerId,
    type: 'line',
    source: bygningOmradeSourceId,
    filter: ['==', '$type', 'Polygon'],
    paint: {
      'line-color': bygningOmradeOutlineColor,
      'line-opacity': 1,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.8, 14, 2.2]
    }
  });
}
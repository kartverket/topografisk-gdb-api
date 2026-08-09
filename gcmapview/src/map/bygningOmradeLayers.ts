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
const MAX_BYGNING_OMRADE_HEIGHT_RANGE_M = 50;

type HeightRange = {
  minimum: number;
  maximum: number;
};

type FeatureHeightContext = {
  center?: [number, number];
  range?: HeightRange;
};

function isPlausibleHeightRange(range: HeightRange | undefined): range is HeightRange {
  if (!range) {
    return false;
  }

  return range.maximum >= range.minimum && range.maximum - range.minimum <= MAX_BYGNING_OMRADE_HEIGHT_RANGE_M;
}

function polygonCoordinateHeightRange(coordinates: Position[]): HeightRange | undefined {
  let minimum = Number.POSITIVE_INFINITY;
  let maximum = 0;

  for (const position of coordinates) {
    const z = position[2];
    if (typeof z === 'number' && Number.isFinite(z) && z > 0) {
      minimum = Math.min(minimum, z);
      maximum = Math.max(maximum, z);
    }
  }

  if (!Number.isFinite(minimum)) {
    return undefined;
  }

  const range = { minimum, maximum };
  return isPlausibleHeightRange(range) ? range : undefined;
}

function polygonCenter(coordinates: Position[]): [number, number] | undefined {
  if (coordinates.length === 0) {
    return undefined;
  }

  const [xSum, ySum] = coordinates.reduce(([x, y], [positionX, positionY]) => [x + positionX, y + positionY], [0, 0]);
  return [xSum / coordinates.length, ySum / coordinates.length];
}

function featureHeightRange(feature: Feature): HeightRange | undefined {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates || !Array.isArray(coordinates)) {
    return undefined;
  }

  let minimum = Number.POSITIVE_INFINITY;
  let maximum = 0;

  const mergeRange = (range: HeightRange | undefined) => {
    if (!range) {
      return;
    }

    minimum = Math.min(minimum, range.minimum);
    maximum = Math.max(maximum, range.maximum);
  };

  if (feature.geometry?.type === 'Polygon') {
    for (const ring of coordinates as Position[][]) {
      mergeRange(polygonCoordinateHeightRange(ring));
    }
  }
  if (feature.geometry?.type === 'MultiPolygon') {
    for (const polygon of coordinates as Position[][][]) {
      for (const ring of polygon) {
        mergeRange(polygonCoordinateHeightRange(ring));
      }
    }
  }

  if (!Number.isFinite(minimum)) {
    return undefined;
  }

  return { minimum, maximum };
}

function featureCenter(feature: Feature): [number, number] | undefined {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates || !Array.isArray(coordinates)) {
    return undefined;
  }

  const centers: Array<[number, number]> = [];

  if (feature.geometry?.type === 'Polygon') {
    for (const ring of coordinates as Position[][]) {
      const center = polygonCenter(ring);
      if (center) {
        centers.push(center);
      }
    }
  }

  if (feature.geometry?.type === 'MultiPolygon') {
    for (const polygon of coordinates as Position[][][]) {
      for (const ring of polygon) {
        const center = polygonCenter(ring);
        if (center) {
          centers.push(center);
        }
      }
    }
  }

  if (centers.length === 0) {
    return undefined;
  }

  const [xSum, ySum] = centers.reduce(([x, y], [centerX, centerY]) => [x + centerX, y + centerY], [0, 0]);
  return [xSum / centers.length, ySum / centers.length];
}

function nearestFeatureHeightRange(contexts: FeatureHeightContext[], targetIndex: number): HeightRange | undefined {
  const targetCenter = contexts[targetIndex]?.center;
  if (!targetCenter) {
    return contexts.find(context => context.range)?.range;
  }

  let nearestRange: HeightRange | undefined;
  let nearestDistance = Number.POSITIVE_INFINITY;

  for (let index = 0; index < contexts.length; index += 1) {
    if (index === targetIndex) {
      continue;
    }

    const candidate = contexts[index];
    if (!candidate?.range || !candidate.center) {
      continue;
    }

    const dx = candidate.center[0] - targetCenter[0];
    const dy = candidate.center[1] - targetCenter[1];
    const distance = dx * dx + dy * dy;
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestRange = candidate.range;
    }
  }

  return nearestRange ?? contexts.find(context => context.range)?.range;
}

function baseHeight(height: number | undefined): number {
  if (typeof height !== 'number' || !Number.isFinite(height) || height <= 0) {
    return 0;
  }

  return height;
}

function topHeight(height: number | undefined, currentBaseHeight: number): number {
  if (typeof height !== 'number' || !Number.isFinite(height) || height <= 0) {
    return 0;
  }

  return Math.max(currentBaseHeight + MIN_BYGNING_OMRADE_EXTRUSION_HEIGHT_M, height);
}

export function lowestPositiveBygningOmradeHeight(featureCollection: FeatureCollection): number {
  let minimum = Number.POSITIVE_INFINITY;

  for (const feature of featureCollection.features) {
    const range = featureHeightRange(feature);
    if (isPlausibleHeightRange(range) && range.minimum > 0) {
      minimum = Math.min(minimum, range.minimum);
    }
  }

  return Number.isFinite(minimum) ? minimum : 0;
}

export function bygningOmradeExtrusionFeatureCollection(
  featureCollection: FeatureCollection,
  heightOffset = 0
): FeatureCollection {
  const contexts: FeatureHeightContext[] = featureCollection.features.map(feature => ({
    center: featureCenter(feature),
    range: featureHeightRange(feature)
  }));

  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map((feature, index) => {
      const range = contexts[index]?.range ?? nearestFeatureHeightRange(contexts, index);
      const elevation = range?.maximum ?? 0;
      const base = baseHeight(range?.minimum);
      const height = topHeight(range?.maximum, base);

      return {
        ...feature,
        properties: {
          ...(feature.properties ?? {}),
          elevation,
          base,
          height,
          zOffset: heightOffset
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
    filter: ['==', ['geometry-type'], 'Polygon'],
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
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: {
      'line-color': bygningOmradeOutlineColor,
      'line-opacity': 1,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 0.8, 14, 2.2]
    }
  });
}
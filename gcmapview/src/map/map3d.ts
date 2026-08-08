import type { ExpressionSpecification } from 'maplibre-gl';
import type { Feature, FeatureCollection, Position } from './geojson';

export const platformEdgesExtrusionSourceId = 'bane-platform-edges-3d';
export const trackCentresExtrusionSourceId = 'bane-track-centres-3d';
export const bygningExtrusionSourceId = 'bygning-linework-3d';
export const platformEdgesExtrusionLayerId = 'bane-platform-edges-extrusion';
export const trackCentresExtrusionLayerId = 'bane-track-centres-extrusion';
export const bygningExtrusionLayerId = 'bygning-linework-extrusion';
export const buildingsExtrusionLayerId = 'buildings-extrusion';

export const DEFAULT_3D_PITCH = 60;
export const FLOOR_HEIGHT_M = 3;
export const ELEVATED_LINE_WIDTH_M = 3;
export const BYGNING_ELEVATED_LINE_WIDTH_M = 1.5;
/** Vertical thickness of elevated line beams (meters). */
export const ELEVATED_LINE_THICKNESS_M = 2;
const MIN_EXTRUSION_HEIGHT_M = 0.5;

function lineCoordinateSets(feature: Feature): Position[][] {
  if (!feature.geometry?.coordinates || !Array.isArray(feature.geometry.coordinates)) {
    return [];
  }

  if (feature.geometry.type === 'LineString') {
    return [feature.geometry.coordinates as Position[]];
  }

  if (feature.geometry.type === 'MultiLineString') {
    return feature.geometry.coordinates as Position[][];
  }

  return [];
}

function adjustedHeight(z: number | undefined, heightOffset: number): number {
  if (typeof z !== 'number' || !Number.isFinite(z) || z <= 0) {
    return 0;
  }

  return Math.max(0, z - heightOffset);
}

function segmentFootprint(lon1: number, lat1: number, lon2: number, lat2: number, widthMeters: number): Position[] {
  const midLat = (((lat1 + lat2) / 2) * Math.PI) / 180;
  const metersPerDegLat = 110_540;
  const metersPerDegLon = 111_320 * Math.cos(midLat);
  const dx = (lon2 - lon1) * metersPerDegLon;
  const dy = (lat2 - lat1) * metersPerDegLat;
  const length = Math.hypot(dx, dy) || 1;
  const offsetX = (-dy / length) * (widthMeters / 2);
  const offsetY = (dx / length) * (widthMeters / 2);
  const dLon = offsetX / metersPerDegLon;
  const dLat = offsetY / metersPerDegLat;

  return [
    [lon1 + dLon, lat1 + dLat],
    [lon2 + dLon, lat2 + dLat],
    [lon2 - dLon, lat2 - dLat],
    [lon1 - dLon, lat1 - dLat],
    [lon1 + dLon, lat1 + dLat]
  ];
}

/**
 * Approximate elevated LineStrings and MultiLineStrings as thin fill-extrusion beams.
 *
 * Z is used as elevation (base/height), not as a column from the ground.
 * That matters for MapLibre: translucent fill-extrusion punches holes where
 * footprints overlap in the same layer — tall ground-to-Z columns at crossings
 * overlap heavily and crop each other down to the basemap.
 */
export function elevatedLineSegments(
  featureCollection: FeatureCollection,
  widthMeters = ELEVATED_LINE_WIDTH_M,
  thicknessMeters = ELEVATED_LINE_THICKNESS_M,
  heightOffset = 0
): FeatureCollection {
  const features: Feature[] = [];
  const halfThickness = Math.max(thicknessMeters, MIN_EXTRUSION_HEIGHT_M) / 2;

  for (const feature of featureCollection.features) {
    for (const coordinates of lineCoordinateSets(feature)) {
      for (let index = 0; index < coordinates.length - 1; index += 1) {
        const start = coordinates[index];
        const end = coordinates[index + 1];
        if (!start || !end) continue;

        const rawZ1 = adjustedHeight(start[2], 0);
        const rawZ2 = adjustedHeight(end[2], 0);
        const rawMidZ = (rawZ1 + rawZ2) / 2;
        const z1 = adjustedHeight(start[2], heightOffset);
        const z2 = adjustedHeight(end[2], heightOffset);
        const midZ = (z1 + z2) / 2;
        const base = Math.max(0, midZ - halfThickness);
        const height = Math.max(base + MIN_EXTRUSION_HEIGHT_M, midZ + halfThickness);

        features.push({
          type: 'Feature',
          properties: {
            ...(feature.properties ?? {}),
            elevation: rawMidZ,
            base,
            height
          },
          geometry: {
            type: 'Polygon',
            coordinates: [segmentFootprint(start[0], start[1], end[0], end[1], widthMeters)]
          }
        });
      }
    }
  }

  return { type: 'FeatureCollection', features };
}

export function lowestPositiveLineHeight(featureCollections: readonly FeatureCollection[]): number {
  let minimum = Number.POSITIVE_INFINITY;

  for (const featureCollection of featureCollections) {
    for (const feature of featureCollection.features) {
      for (const coordinates of lineCoordinateSets(feature)) {
        for (const position of coordinates) {
          const z = position[2];
          if (typeof z === 'number' && Number.isFinite(z) && z > 0) {
            minimum = Math.min(minimum, z);
          }
        }
      }
    }
  }

  return Number.isFinite(minimum) ? minimum : 0;
}

export function buildingExtrusionHeightExpression(floorHeightM = FLOOR_HEIGHT_M): ExpressionSpecification {
  return ['*', ['to-number', ['coalesce', ['get', 'floors'], 1]], floorHeightM];
}

export const HEIGHT_COLOR_MAX_M = 300;

/** Two-stack 3D opacity: translucent shaft + opaque top cap (≤ this many meters). */
export const EXTRUSION_TOP_CAP_M = 5;
export const EXTRUSION_OPACITY_MIN = 0.35;
export const EXTRUSION_OPACITY_MAX = 0.9;

/** Top of the translucent shaft / base of the opaque cap. */
export function extrusionShaftTopExpression(heightExpression: ExpressionSpecification): ExpressionSpecification {
  return ['max', 0, ['-', heightExpression, EXTRUSION_TOP_CAP_M]];
}

/** Max finite Z from a LineString coordinate array (meters). */
export function maxCoordinateHeight(coordinates: Position[]): number {
  let maxHeight = 0;
  for (const position of coordinates) {
    const z = position[2];
    if (typeof z === 'number' && Number.isFinite(z)) {
      maxHeight = Math.max(maxHeight, z);
    }
  }
  return maxHeight;
}

/** Blue at 0 m → red at {@link HEIGHT_COLOR_MAX_M} m (and above) via HSL hue. */
export function heightColorExpression(
  heightExpression: ExpressionSpecification = ['to-number', ['coalesce', ['get', 'height'], 0]]
): ExpressionSpecification {
  return [
    'interpolate',
    ['linear'],
    ['max', 0, ['min', heightExpression, HEIGHT_COLOR_MAX_M]],
    0,
    'hsl(240, 85%, 45%)',
    60,
    'hsl(192, 85%, 45%)',
    120,
    'hsl(144, 85%, 45%)',
    180,
    'hsl(96, 85%, 45%)',
    240,
    'hsl(48, 85%, 45%)',
    HEIGHT_COLOR_MAX_M,
    'hsl(0, 85%, 45%)'
  ];
}

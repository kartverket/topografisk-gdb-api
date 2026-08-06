import type { ExpressionSpecification } from 'maplibre-gl'
import type { Feature, FeatureCollection, Position } from './geojson'

export const platformEdgesExtrusionSourceId = 'bane-platform-edges-3d'
export const trackCentresExtrusionSourceId = 'bane-track-centres-3d'
export const platformEdgesExtrusionLayerId = 'bane-platform-edges-extrusion'
export const trackCentresExtrusionLayerId = 'bane-track-centres-extrusion'
export const buildingsExtrusionLayerId = 'buildings-extrusion'

export const DEFAULT_3D_PITCH = 60
export const FLOOR_HEIGHT_M = 3
export const ELEVATED_LINE_WIDTH_M = 3
const MIN_EXTRUSION_HEIGHT_M = 0.5

function segmentFootprint(
  lon1: number,
  lat1: number,
  lon2: number,
  lat2: number,
  widthMeters: number,
): Position[] {
  const midLat = (((lat1 + lat2) / 2) * Math.PI) / 180
  const metersPerDegLat = 110_540
  const metersPerDegLon = 111_320 * Math.cos(midLat)
  const dx = (lon2 - lon1) * metersPerDegLon
  const dy = (lat2 - lat1) * metersPerDegLat
  const length = Math.hypot(dx, dy) || 1
  const offsetX = (-dy / length) * (widthMeters / 2)
  const offsetY = (dx / length) * (widthMeters / 2)
  const dLon = offsetX / metersPerDegLon
  const dLat = offsetY / metersPerDegLat

  return [
    [lon1 + dLon, lat1 + dLat],
    [lon2 + dLon, lat2 + dLat],
    [lon2 - dLon, lat2 - dLat],
    [lon1 - dLon, lat1 - dLat],
    [lon1 + dLon, lat1 + dLat],
  ]
}

/** Approximate elevated LineStrings as thin fill-extrusion footprints. */
export function elevatedLineSegments(
  featureCollection: FeatureCollection,
  widthMeters = ELEVATED_LINE_WIDTH_M,
): FeatureCollection {
  const features: Feature[] = []

  for (const feature of featureCollection.features) {
    if (
      feature.geometry?.type !== 'LineString' ||
      !Array.isArray(feature.geometry.coordinates)
    ) {
      continue
    }

    const coordinates = feature.geometry.coordinates as Position[]
    for (let index = 0; index < coordinates.length - 1; index += 1) {
      const start = coordinates[index]
      const end = coordinates[index + 1]
      if (!start || !end) continue

      const z1 =
        typeof start[2] === 'number' && Number.isFinite(start[2]) ? start[2] : 0
      const z2 =
        typeof end[2] === 'number' && Number.isFinite(end[2]) ? end[2] : 0
      const height = Math.max(z1, z2, MIN_EXTRUSION_HEIGHT_M)

      features.push({
        type: 'Feature',
        properties: {
          ...(feature.properties ?? {}),
          height,
          base: 0,
        },
        geometry: {
          type: 'Polygon',
          coordinates: [
            segmentFootprint(start[0], start[1], end[0], end[1], widthMeters),
          ],
        },
      })
    }
  }

  return { type: 'FeatureCollection', features }
}

export function buildingExtrusionHeightExpression(
  floorHeightM = FLOOR_HEIGHT_M,
): ExpressionSpecification {
  return [
    '*',
    ['to-number', ['coalesce', ['get', 'floors'], 1]],
    floorHeightM,
  ]
}

export const HEIGHT_COLOR_MAX_M = 300

/** Max finite Z from a LineString coordinate array (meters). */
export function maxCoordinateHeight(coordinates: Position[]): number {
  let maxHeight = 0
  for (const position of coordinates) {
    const z = position[2]
    if (typeof z === 'number' && Number.isFinite(z)) {
      maxHeight = Math.max(maxHeight, z)
    }
  }
  return maxHeight
}

/** Blue at 0 m → red at {@link HEIGHT_COLOR_MAX_M} m (and above) via HSL hue. */
export function heightColorExpression(
  heightExpression: ExpressionSpecification = [
    'to-number',
    ['coalesce', ['get', 'height'], 0],
  ],
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
    'hsl(0, 85%, 45%)',
  ]
}

import * as maplibregl from 'maplibre-gl';
import type { CollectionId } from '../../api/geocomponentsApi';
import type { InspectedFeature } from '../../map/featureInspect';
import type { Position } from '../../map/geojson';

type HoverOverlayTransform = {
  coordinatePoint?: (
    coord: maplibregl.MercatorCoordinate,
    elevation?: number,
    pixelMatrix?: unknown
  ) => maplibregl.Point;
  _pixelMatrix3D?: unknown;
};

const BANE_TERRAIN_CLEARANCE_M = 2;

function numericFeatureProperty(properties: Record<string, unknown>, propertyName: string): number | undefined {
  const value = properties[propertyName];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function terrainClearanceMeters(collectionId: CollectionId | undefined) {
  return collectionId === 'jernbaneplattformkant' || collectionId === 'spormidt' ? BANE_TERRAIN_CLEARANCE_M : 0;
}

function featurePositionAltitudeMeters(
  map: maplibregl.Map,
  feature: InspectedFeature,
  index: number,
  is3d: boolean,
  adjustElevatedHeights: boolean,
  currentSelectedPositionZOffset: () => number
) {
  if (!is3d) {
    return 0;
  }

  const position = feature.mapPositions[index] ?? feature.positions[index];
  const z = position?.[2];
  if (typeof z !== 'number' || !Number.isFinite(z)) {
    return 0;
  }

  if (adjustElevatedHeights) {
    return Math.max(0, z - currentSelectedPositionZOffset());
  }

  const terrainElevation = map.queryTerrainElevation([position[0], position[1]]);
  if (typeof terrainElevation === 'number' && Number.isFinite(terrainElevation)) {
    return Math.max(0, z - terrainElevation + terrainClearanceMeters(feature.collectionId));
  }

  const zOffset = numericFeatureProperty(feature.properties, 'zOffset') ?? 0;
  return zOffset > 0 ? Math.max(0, z - zOffset) : Math.max(0, z);
}

export function projectInspectedFeaturePositionPoint(
  map: maplibregl.Map,
  feature: InspectedFeature,
  index: number,
  position: Position,
  is3d: boolean,
  adjustElevatedHeights: boolean,
  currentSelectedPositionZOffset: () => number
): maplibregl.Point {
  const lngLat = maplibregl.LngLat.convert([position[0], position[1]]);
  const altitudeMeters = featurePositionAltitudeMeters(
    map,
    feature,
    index,
    is3d,
    adjustElevatedHeights,
    currentSelectedPositionZOffset
  );

  if (!is3d || altitudeMeters <= 0) {
    return map.project(lngLat);
  }

  const transform = (map as unknown as { _camera?: { transform?: HoverOverlayTransform } })._camera?.transform;
  const pixelMatrix3D = transform?._pixelMatrix3D;

  if (!transform?.coordinatePoint || !pixelMatrix3D) {
    return map.project(lngLat);
  }

  return transform.coordinatePoint(maplibregl.MercatorCoordinate.fromLngLat(lngLat), altitudeMeters, pixelMatrix3D);
}

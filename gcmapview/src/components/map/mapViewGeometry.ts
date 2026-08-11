import type { Coordinates, Feature, FeatureCollection, Position } from '../../map/geojson';

export function collectPositions(coordinates: Coordinates, positions: Position[]) {
  if (typeof coordinates[0] === 'number') {
    positions.push(coordinates as Position);
    return;
  }

  for (const child of coordinates as Coordinates[]) {
    collectPositions(child, positions);
  }
}

export function featureCentroid(feature: Feature): Position | undefined {
  const positions: Position[] = [];
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) {
    return undefined;
  }

  collectPositions(coordinates, positions);
  if (positions.length === 0) {
    return undefined;
  }

  const [lngSum, latSum] = positions.reduce(
    ([lng, lat], [positionLng, positionLat]) => [lng + positionLng, lat + positionLat],
    [0, 0]
  );

  return [lngSum / positions.length, latSum / positions.length];
}

export function buildingCentroidsFeatureCollection(buildings: FeatureCollection): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: buildings.features.flatMap(building => {
      const centroid = featureCentroid(building);
      if (!centroid) {
        return [];
      }

      return [
        {
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: centroid
          },
          properties: building.properties
        }
      ];
    })
  };
}

function coordinateDebugSummary(featureCollection: FeatureCollection) {
  const positions: Position[] = [];
  const geometryTypes: Record<string, number> = {};

  for (const feature of featureCollection.features) {
    const geometry = feature.geometry;
    if (!geometry) {
      geometryTypes.null = (geometryTypes.null ?? 0) + 1;
      continue;
    }

    geometryTypes[geometry.type] = (geometryTypes[geometry.type] ?? 0) + 1;
    if (geometry.coordinates) {
      collectPositions(geometry.coordinates, positions);
    }
  }

  const lngs = positions.map(([lng]) => lng);
  const lats = positions.map(([, lat]) => lat);

  return {
    featureCount: featureCollection.features.length,
    geometryTypes,
    coordinateCount: positions.length,
    lngRange: lngs.length > 0 ? [Math.min(...lngs), Math.max(...lngs)] : undefined,
    latRange: lats.length > 0 ? [Math.min(...lats), Math.max(...lats)] : undefined,
    firstFeatureCoordinates: featureCollection.features[0]?.geometry?.coordinates ?? undefined
  };
}

export function logLoadedCoordinates(label: string, featureCollection: FeatureCollection) {
  console.info(`[gcmapview] loaded ${label} coordinates`, coordinateDebugSummary(featureCollection));
}

function signedRingArea(ring: Position[]) {
  return ring.reduce((sum, [x1, y1], index) => {
    const [x2, y2] = ring[(index + 1) % ring.length];
    return sum + x1 * y2 - x2 * y1;
  }, 0);
}

function normalizeRings(rings: Position[][]) {
  return rings.map((ring, index) => {
    const shouldBeCounterClockwise = index === 0;
    const isCounterClockwise = signedRingArea(ring) > 0;
    return shouldBeCounterClockwise === isCounterClockwise ? ring : [...ring].reverse();
  });
}

export function normalizePolygonFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map(feature => {
      const geometry = feature.geometry;
      if (!geometry?.coordinates) {
        return feature;
      }

      if (geometry.type === 'Polygon') {
        return {
          ...feature,
          geometry: {
            type: 'Polygon',
            coordinates: normalizeRings(geometry.coordinates as Position[][])
          }
        };
      }

      if (geometry.type === 'MultiPolygon') {
        const polygons = geometry.coordinates as Position[][][];
        if (polygons.length === 1) {
          return {
            ...feature,
            geometry: {
              type: 'Polygon',
              coordinates: normalizeRings(polygons[0])
            }
          };
        }

        return {
          ...feature,
          geometry: {
            type: 'MultiPolygon',
            coordinates: polygons.map(normalizeRings)
          }
        };
      }

      return feature;
    })
  };
}

export function sourcePositions(feature: Feature): Position[] {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) {
    return [];
  }

  const positions: Position[] = [];
  collectPositions(coordinates, positions);
  return positions;
}

export type FeatureRectangle = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export function featureRectangle(feature: Feature): FeatureRectangle | undefined {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) {
    return undefined;
  }

  const positions: Position[] = [];
  collectPositions(coordinates as Coordinates, positions);
  if (positions.length === 0) {
    return undefined;
  }

  const longitudes = positions.map(([longitude]) => longitude);
  const latitudes = positions.map(([, latitude]) => latitude);
  return {
    west: Math.min(...longitudes),
    south: Math.min(...latitudes),
    east: Math.max(...longitudes),
    north: Math.max(...latitudes)
  };
}

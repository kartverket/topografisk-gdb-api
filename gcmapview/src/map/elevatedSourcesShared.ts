import type { LayerVisibility } from '../store/layerVisibilityStore';
import type { Coordinates, Feature, FeatureCollection, Position } from './geojson';

export type ElevatedSourceVisibility = Pick<
  LayerVisibility,
  'platformEdges' | 'trackCentres' | 'bygning' | 'bygningSenterlinje' | 'bygningOmrade'
>;

export type TerrainSampleMap = Record<string, number>;

export type ElevatedSourcesWorkerRequest = {
  requestId: number;
  platformEdges: FeatureCollection;
  trackCentres: FeatureCollection;
  bygning: FeatureCollection;
  bygningSenterlinje: FeatureCollection;
  bygningOmrade: FeatureCollection;
  visibility: ElevatedSourceVisibility;
  adjustHeights: boolean;
  terrainEnabled: boolean;
  baneTerrainClearanceMeters: number;
  terrainSamples: TerrainSampleMap;
};

export type ElevatedSourcesWorkerResponse = {
  requestId: number;
  platformData: FeatureCollection;
  trackData: FeatureCollection;
  bygningData: FeatureCollection;
  bygningSenterlinjeData: FeatureCollection;
  bygningOmradeData: FeatureCollection;
};

export function terrainSampleKey(longitude: number, latitude: number) {
  return `${longitude.toFixed(5)}:${latitude.toFixed(5)}`;
}

function collectPositions(coordinates: Coordinates, positions: Position[]) {
  if (typeof coordinates[0] === 'number') {
    positions.push(coordinates as Position);
    return;
  }

  for (const child of coordinates as Coordinates[]) {
    collectPositions(child, positions);
  }
}

function polygonCenter(coordinates: Position[]): [number, number] | undefined {
  if (coordinates.length === 0) {
    return undefined;
  }

  const [xSum, ySum] = coordinates.reduce(([x, y], [positionX, positionY]) => [x + positionX, y + positionY], [0, 0]);
  return [xSum / coordinates.length, ySum / coordinates.length];
}

function featureCenter(feature: Feature): [number, number] | undefined {
  const geometry = feature.geometry;
  const coordinates = geometry?.coordinates;
  if (!geometry || !coordinates || !Array.isArray(coordinates)) {
    return undefined;
  }

  const centers: Array<[number, number]> = [];

  if (geometry.type === 'Polygon') {
    for (const ring of coordinates as Position[][]) {
      const center = polygonCenter(ring);
      if (center) {
        centers.push(center);
      }
    }
  }

  if (geometry.type === 'MultiPolygon') {
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

function addCollectionCoordinates(points: Map<string, [number, number]>, featureCollection: FeatureCollection) {
  for (const feature of featureCollection.features) {
    const coordinates = feature.geometry?.coordinates;
    if (!coordinates) {
      continue;
    }

    const positions: Position[] = [];
    collectPositions(coordinates, positions);
    for (const [longitude, latitude] of positions) {
      points.set(terrainSampleKey(longitude, latitude), [longitude, latitude]);
    }
  }
}

function addFeatureCenters(points: Map<string, [number, number]>, featureCollection: FeatureCollection) {
  for (const feature of featureCollection.features) {
    const center = featureCenter(feature);
    if (!center) {
      continue;
    }

    points.set(terrainSampleKey(center[0], center[1]), center);
  }
}

export function terrainSamplePointsForFeatureCollections(
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningOmrade: FeatureCollection,
  visibility: ElevatedSourceVisibility
): Array<[number, number]> {
  const points = new Map<string, [number, number]>();

  if (visibility.platformEdges) {
    addCollectionCoordinates(points, platformEdges);
  }
  if (visibility.trackCentres) {
    addCollectionCoordinates(points, trackCentres);
  }
  if (visibility.bygning) {
    addCollectionCoordinates(points, bygning);
  }
  if (visibility.bygningSenterlinje) {
    addCollectionCoordinates(points, bygningSenterlinje);
  }
  if (visibility.bygningOmrade) {
    addFeatureCenters(points, bygningOmrade);
  }

  return [...points.values()];
}
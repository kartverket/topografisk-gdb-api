import type * as maplibregl from 'maplibre-gl';
import type { FeatureCollection, Position } from '../../map/geojson';
import { featureRectangle } from './mapViewGeometry';

export type BuildingFeature = {
  type: 'Feature';
  geometry: {
    type: 'MultiPolygon';
    coordinates: Position[][][];
  };
  properties: {
    use: string;
    floors: number;
    parcel_id?: string;
  };
};

export type ParcelFeature = {
  type: 'Feature';
  geometry: {
    type: 'MultiPolygon';
    coordinates: Position[][][];
  };
  properties: {
    label: string;
    source: string;
    area_m2: number;
  };
};

function randomBetween(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function randomInt(min: number, max: number) {
  return Math.floor(randomBetween(min, max + 1));
}

type Offset = [number, number];

function offsetPolygonArea(offsets: Offset[]) {
  const doubledArea = offsets.reduce((sum, [x1, y1], index) => {
    const [x2, y2] = offsets[(index + 1) % offsets.length];
    return sum + x1 * y2 - x2 * y1;
  }, 0);

  return Math.abs(doubledArea) / 2;
}

function scaleOffsetsToArea(offsets: Offset[], targetAreaM2: number) {
  const currentArea = offsetPolygonArea(offsets);
  const scale = currentArea > 0 ? Math.sqrt(targetAreaM2 / currentArea) : 1;
  return offsets.map(([x, y]): Offset => [x * scale, y * scale]);
}

function rotateOffsets(offsets: Offset[], angle: number) {
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  return offsets.map(([x, y]): Offset => [x * cosine - y * sine, x * sine + y * cosine]);
}

function parcelOffsets(targetAreaM2: number) {
  const minPoints = 7;
  const maxPoints = 16;
  const pointCount = randomInt(minPoints, maxPoints);
  const baseRadius = Math.sqrt(targetAreaM2 / Math.PI);
  const aspectRatio = randomBetween(0.7, 1.5);
  const offsets = Array.from({ length: pointCount }, (_, index): Offset => {
    const angle =
      (index / pointCount) * Math.PI * 2 + randomBetween(-Math.PI / pointCount / 3, Math.PI / pointCount / 3);
    const radius = baseRadius * randomBetween(0.82, 1.18);
    return [Math.cos(angle) * radius * aspectRatio, Math.sin(angle) * radius];
  }).sort(([xA, yA], [xB, yB]) => Math.atan2(yA, xA) - Math.atan2(yB, xB));

  return rotateOffsets(scaleOffsetsToArea(offsets, targetAreaM2), randomBetween(0, Math.PI));
}

function buildingOffsets(targetAreaM2: number) {
  const aspectRatio = randomBetween(1.2, 2.4);
  const width = Math.sqrt(targetAreaM2 * aspectRatio);
  const height = targetAreaM2 / width;
  let offsets: Offset[];

  if (Math.random() < 0.45) {
    offsets = [
      [-width / 2, -height / 2],
      [width / 2, -height / 2],
      [width / 2, -height * 0.05],
      [width * 0.15, -height * 0.05],
      [width * 0.15, height / 2],
      [-width / 2, height / 2]
    ];
  } else {
    const chamfer = Math.min(width, height) * randomBetween(0.12, 0.24);
    offsets = [
      [-width / 2 + chamfer, -height / 2],
      [width / 2 - chamfer, -height / 2],
      [width / 2, -height / 2 + chamfer],
      [width / 2, height / 2 - chamfer],
      [width / 2 - chamfer, height / 2],
      [-width / 2 + chamfer, height / 2],
      [-width / 2, height / 2 - chamfer],
      [-width / 2, -height / 2 + chamfer]
    ];
  }

  return rotateOffsets(scaleOffsetsToArea(offsets, targetAreaM2), randomBetween(0, Math.PI));
}

function offsetsToRing(
  offsets: Offset[],
  lng: number,
  lat: number,
  metersPerDegreeLng: number,
  metersPerDegreeLat: number
) {
  const ring = offsets.map(
    ([x, y]): Position => [lng + x / metersPerDegreeLng, lat + y / metersPerDegreeLat]
  );

  return [...ring, ring[0]];
}

function randomBuildingAndParcelInView(map: maplibregl.Map): {
  area: number;
  building: BuildingFeature;
  secondaryBuilding?: {
    area: number;
    feature: BuildingFeature;
  };
  parcel: ParcelFeature;
} {
  const bounds = map.getBounds();
  const west = bounds.getWest();
  const east = bounds.getEast();
  const south = bounds.getSouth();
  const north = bounds.getNorth();
  const lng = randomBetween(west, east);
  const lat = randomBetween(south, north);
  const area = Math.round(randomBetween(20, 200));
  const parcelArea = area * 15;
  const metersPerDegreeLat = 111_320;
  const metersPerDegreeLng = Math.max(metersPerDegreeLat * Math.cos((lat * Math.PI) / 180), 1);
  const buildingRing = offsetsToRing(buildingOffsets(area), lng, lat, metersPerDegreeLng, metersPerDegreeLat);
  const parcelRing = offsetsToRing(parcelOffsets(parcelArea), lng, lat, metersPerDegreeLng, metersPerDegreeLat);
  const shouldAddSecondaryBuilding = Math.random() < 0.55;
  const secondaryArea = Math.max(10, Math.round(area * randomBetween(0.2, 0.5)));
  const parcelRadius = Math.sqrt(parcelArea / Math.PI);
  const secondaryAngle = randomBetween(0, Math.PI * 2);
  const secondaryDistance = parcelRadius * randomBetween(0.3, 0.48);
  const secondaryLng = lng + (Math.cos(secondaryAngle) * secondaryDistance) / metersPerDegreeLng;
  const secondaryLat = lat + (Math.sin(secondaryAngle) * secondaryDistance) / metersPerDegreeLat;
  const secondaryRing = offsetsToRing(
    buildingOffsets(secondaryArea),
    secondaryLng,
    secondaryLat,
    metersPerDegreeLng,
    metersPerDegreeLat
  );

  return {
    area,
    building: {
      type: 'Feature',
      geometry: {
        type: 'MultiPolygon',
        coordinates: [[buildingRing]]
      },
      properties: {
        use: 'random',
        floors: Math.floor(randomBetween(1, 5))
      }
    },
    secondaryBuilding: shouldAddSecondaryBuilding
      ? {
          area: secondaryArea,
          feature: {
            type: 'Feature',
            geometry: {
              type: 'MultiPolygon',
              coordinates: [[secondaryRing]]
            },
            properties: {
              use: 'outbuilding',
              floors: 1
            }
          }
        }
      : undefined,
    parcel: {
      type: 'Feature',
      geometry: {
        type: 'MultiPolygon',
        coordinates: [[parcelRing]]
      },
      properties: {
        label: `Parcel ${Date.now()}`,
        source: 'gcmapview',
        area_m2: parcelArea
      }
    }
  };
}

function rectanglesOverlap(first: { west: number; south: number; east: number; north: number }, second: { west: number; south: number; east: number; north: number }) {
  return !(
    first.east <= second.west ||
    first.west >= second.east ||
    first.north <= second.south ||
    first.south >= second.north
  );
}

export function randomNonOverlappingBuildingAndParcel(map: maplibregl.Map, existingParcels: FeatureCollection) {
  const existingRectangles = existingParcels.features
    .map(featureRectangle)
    .filter((rectangle): rectangle is NonNullable<ReturnType<typeof featureRectangle>> => Boolean(rectangle));

  for (let attempt = 1; attempt <= 80; attempt += 1) {
    const candidate = randomBuildingAndParcelInView(map);
    const candidateRectangle = featureRectangle(candidate.parcel);
    if (
      candidateRectangle &&
      existingRectangles.every(existingRectangle => !rectanglesOverlap(candidateRectangle, existingRectangle))
    ) {
      return { ...candidate, placementAttempts: attempt };
    }
  }

  throw new Error('No non-overlapping parcel placement found in the current map view');
}
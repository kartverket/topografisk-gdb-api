import type * as maplibregl from 'maplibre-gl';
import type { CollectionId } from '../api/geocomponentsApi';
import {
  buildingsExtrusionLayerId,
  bygningExtrusionLayerId,
  bygningExtrusionSourceId,
  platformEdgesExtrusionLayerId,
  platformEdgesExtrusionSourceId,
  trackCentresExtrusionLayerId,
  trackCentresExtrusionSourceId
} from './map3d';
import { platformEdgesLayerId, platformEdgesSourceId, trackCentresLayerId, trackCentresSourceId } from './baneLayers';
import { bygningLayerId, bygningSourceId } from './bygningLayers';
import { bygningPosisjonLayerId } from './bygningPosisjonLayers';
import { bygningSenterlinjeLayerId, bygningSenterlinjeSourceId } from './bygningSenterlinjeLayers';
import {
  bygningOmradeExtrusionLayerId,
  bygningOmradeExtrusionSourceId,
  bygningOmradeFillLayerId,
  bygningOmradeSourceId
} from './bygningOmradeLayers';
import { bygningSenterlinjeExtrusionLayerId, bygningSenterlinjeExtrusionSourceId } from './map3d';
import type { Coordinates, Feature, FeatureCollection, Position } from './geojson';

/** Layers queried on click (topmost first). Outlines/centroids omitted to reduce duplicates. */
export const INSPECTABLE_LAYER_IDS = [
  `${buildingsExtrusionLayerId}-cap`,
  `${buildingsExtrusionLayerId}-shaft`,
  `${platformEdgesExtrusionLayerId}-solid`,
  `${platformEdgesExtrusionLayerId}-shadow`,
  `${trackCentresExtrusionLayerId}-solid`,
  `${trackCentresExtrusionLayerId}-shadow`,
  `${bygningExtrusionLayerId}-solid`,
  `${bygningExtrusionLayerId}-shadow`,
  `${bygningSenterlinjeExtrusionLayerId}-solid`,
  `${bygningSenterlinjeExtrusionLayerId}-shadow`,
  `${bygningOmradeExtrusionLayerId}-cap`,
  `${bygningOmradeExtrusionLayerId}-shaft`,
  bygningOmradeFillLayerId,
  'buildings-fill',
  'parcels-fill',
  platformEdgesLayerId,
  trackCentresLayerId,
  bygningLayerId,
  bygningSenterlinjeLayerId,
  bygningPosisjonLayerId
] as const;

const LAYER_LABELS: Record<string, string> = {
  [`${buildingsExtrusionLayerId}-cap`]: 'Cadastre building',
  [`${buildingsExtrusionLayerId}-shaft`]: 'Cadastre building',
  [`${platformEdgesExtrusionLayerId}-solid`]: 'Bane platform edge',
  [`${platformEdgesExtrusionLayerId}-shadow`]: 'Bane platform edge',
  [`${trackCentresExtrusionLayerId}-solid`]: 'Bane track centre',
  [`${trackCentresExtrusionLayerId}-shadow`]: 'Bane track centre',
  [`${bygningExtrusionLayerId}-solid`]: 'Bygning linework',
  [`${bygningExtrusionLayerId}-shadow`]: 'Bygning linework',
  [`${bygningSenterlinjeExtrusionLayerId}-solid`]: 'Bygning centerline',
  [`${bygningSenterlinjeExtrusionLayerId}-shadow`]: 'Bygning centerline',
  [`${bygningOmradeExtrusionLayerId}-cap`]: 'Bygning area',
  [`${bygningOmradeExtrusionLayerId}-shaft`]: 'Bygning area',
  [bygningOmradeFillLayerId]: 'Bygning area',
  'buildings-fill': 'Cadastre building',
  'parcels-fill': 'Cadastre parcel',
  [platformEdgesLayerId]: 'Bane platform edge',
  [trackCentresLayerId]: 'Bane track centre',
  [bygningLayerId]: 'Bygning linework',
  [bygningSenterlinjeLayerId]: 'Bygning centerline',
  [bygningPosisjonLayerId]: 'Bygning position'
};

const LAYER_COLLECTION_IDS: Record<string, CollectionId> = {
  [`${buildingsExtrusionLayerId}-cap`]: 'buildings',
  [`${buildingsExtrusionLayerId}-shaft`]: 'buildings',
  [`${platformEdgesExtrusionLayerId}-solid`]: 'jernbaneplattformkant',
  [`${platformEdgesExtrusionLayerId}-shadow`]: 'jernbaneplattformkant',
  [`${trackCentresExtrusionLayerId}-solid`]: 'spormidt',
  [`${trackCentresExtrusionLayerId}-shadow`]: 'spormidt',
  [`${bygningExtrusionLayerId}-solid`]: 'bygning',
  [`${bygningExtrusionLayerId}-shadow`]: 'bygning',
  [`${bygningSenterlinjeExtrusionLayerId}-solid`]: 'bygning_senterlinje',
  [`${bygningSenterlinjeExtrusionLayerId}-shadow`]: 'bygning_senterlinje',
  [`${bygningOmradeExtrusionLayerId}-cap`]: 'bygning_omrade',
  [`${bygningOmradeExtrusionLayerId}-shaft`]: 'bygning_omrade',
  [bygningOmradeFillLayerId]: 'bygning_omrade',
  'buildings-fill': 'buildings',
  'parcels-fill': 'parcels',
  [platformEdgesLayerId]: 'jernbaneplattformkant',
  [trackCentresLayerId]: 'spormidt',
  [bygningLayerId]: 'bygning',
  [bygningSenterlinjeLayerId]: 'bygning_senterlinje',
  [bygningPosisjonLayerId]: 'bygning_posisjon'
};

const INTERNAL_PROPERTY_PREFIX = '__gcmapview';
const INSPECTABLE_FEATURE_KEY = `${INTERNAL_PROPERTY_PREFIX}InspectKey`;
const SOURCE_ID_ALIASES: Record<string, string> = {
  [platformEdgesExtrusionSourceId]: platformEdgesSourceId,
  [trackCentresExtrusionSourceId]: trackCentresSourceId,
  [bygningExtrusionSourceId]: bygningSourceId,
  [bygningSenterlinjeExtrusionSourceId]: bygningSenterlinjeSourceId,
  [bygningOmradeExtrusionSourceId]: bygningOmradeSourceId
};
const inspectableSourceData = new Map<string, FeatureCollection>();

export type InspectedFeature = {
  layerId: string;
  layerLabel: string;
  collectionId?: CollectionId;
  featureId?: string | number;
  properties: Record<string, unknown>;
  positions: Position[];
  positionsCoordinateSystem?: string;
  positionsLoading?: boolean;
};

function stripInternalProperties(properties: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(properties).filter(([key]) => !key.startsWith(INTERNAL_PROPERTY_PREFIX)));
}

function inspectableFeatureKey(sourceId: string, index: number) {
  return `${sourceId}:${index}`;
}

export function registerInspectableSourceData(sourceId: string, featureCollection: FeatureCollection): FeatureCollection {
  const registered: FeatureCollection = {
    type: 'FeatureCollection',
    features: featureCollection.features.map((feature, index) => ({
      ...feature,
      properties: {
        ...(feature.properties ?? {}),
        [INSPECTABLE_FEATURE_KEY]: inspectableFeatureKey(sourceId, index)
      }
    }))
  };

  inspectableSourceData.set(sourceId, registered);
  return registered;
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

function positionsFromCoordinates(coordinates: Coordinates | undefined): Position[] {
  if (!coordinates) {
    return [];
  }

  const positions: Position[] = [];
  collectPositions(coordinates, positions);
  return positions;
}

function featurePositions(feature: Pick<Feature, 'geometry'> | maplibregl.MapGeoJSONFeature): Position[] {
  return positionsFromCoordinates(feature.geometry?.coordinates as Coordinates | undefined);
}

function renderedFeatureSourceId(feature: maplibregl.MapGeoJSONFeature): string | undefined {
  const sourceId = typeof feature.source === 'string' ? feature.source : undefined;
  if (!sourceId) {
    return undefined;
  }

  return SOURCE_ID_ALIASES[sourceId] ?? sourceId;
}

function matchingSourceFeature(sourceId: string, renderedFeature: maplibregl.MapGeoJSONFeature): Feature | undefined {
  const sourceFeatureCollection = inspectableSourceData.get(sourceId);
  if (!sourceFeatureCollection) {
    return undefined;
  }

  const renderedProperties = (renderedFeature.properties ?? {}) as Record<string, unknown>;
  const renderedKey = renderedProperties[INSPECTABLE_FEATURE_KEY];
  if (typeof renderedKey === 'string') {
    return sourceFeatureCollection.features.find(sourceFeature => sourceFeature.properties?.[INSPECTABLE_FEATURE_KEY] === renderedKey);
  }

  if (renderedFeature.id !== undefined) {
    return sourceFeatureCollection.features.find(sourceFeature => sourceFeature.id === renderedFeature.id);
  }

  return undefined;
}

function presentLayerIds(map: maplibregl.Map): string[] {
  return INSPECTABLE_LAYER_IDS.filter(layerId => Boolean(map.getLayer(layerId)));
}

export function inspectFeaturesAtPoint(map: maplibregl.Map, point: maplibregl.PointLike): InspectedFeature | undefined {
  const layers = presentLayerIds(map);
  if (layers.length === 0) {
    return undefined;
  }

  const [feature] = map.queryRenderedFeatures(point, { layers });
  if (!feature) {
    return undefined;
  }

  const properties = stripInternalProperties({ ...(feature.properties ?? {}) } as Record<string, unknown>);
  const originalFeature = renderedFeatureSourceId(feature)
    ? matchingSourceFeature(renderedFeatureSourceId(feature) as string, feature)
    : undefined;
  const featureId =
    originalFeature?.id ??
    feature.id ??
    (typeof properties.id === 'string' || typeof properties.id === 'number' ? properties.id : undefined);
  const collectionId = LAYER_COLLECTION_IDS[feature.layer.id];

  return {
    layerId: feature.layer.id,
    layerLabel: LAYER_LABELS[feature.layer.id] ?? feature.layer.id,
    collectionId,
    featureId,
    properties,
    positions: originalFeature ? featurePositions(originalFeature) : featurePositions(feature),
    positionsLoading: Boolean(collectionId && featureId !== undefined)
  };
}

export function hasInspectableFeatureAtPoint(map: maplibregl.Map, point: maplibregl.PointLike): boolean {
  const layers = presentLayerIds(map);
  if (layers.length === 0) {
    return false;
  }
  return map.queryRenderedFeatures(point, { layers }).length > 0;
}

export function formatPropertyValue(value: unknown): string {
  if (value === null || value === undefined) {
    return '—';
  }
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

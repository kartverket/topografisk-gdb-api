import type * as maplibregl from 'maplibre-gl';
import {
  buildingsExtrusionLayerId,
  bygningExtrusionLayerId,
  platformEdgesExtrusionLayerId,
  trackCentresExtrusionLayerId
} from './map3d';
import { platformEdgesLayerId, trackCentresLayerId } from './baneLayers';
import { bygningLayerId } from './bygningLayers';
import { bygningOmradeExtrusionLayerId, bygningOmradeFillLayerId } from './bygningOmradeLayers';

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
  `${bygningOmradeExtrusionLayerId}-cap`,
  `${bygningOmradeExtrusionLayerId}-shaft`,
  bygningOmradeFillLayerId,
  'buildings-fill',
  'parcels-fill',
  platformEdgesLayerId,
  trackCentresLayerId,
  bygningLayerId
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
  [`${bygningOmradeExtrusionLayerId}-cap`]: 'Bygning area',
  [`${bygningOmradeExtrusionLayerId}-shaft`]: 'Bygning area',
  [bygningOmradeFillLayerId]: 'Bygning area',
  'buildings-fill': 'Cadastre building',
  'parcels-fill': 'Cadastre parcel',
  [platformEdgesLayerId]: 'Bane platform edge',
  [trackCentresLayerId]: 'Bane track centre',
  [bygningLayerId]: 'Bygning linework'
};

export type InspectedFeature = {
  layerId: string;
  layerLabel: string;
  featureId?: string | number;
  properties: Record<string, unknown>;
};

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

  const properties = { ...(feature.properties ?? {}) } as Record<string, unknown>;
  const featureId =
    feature.id ?? (typeof properties.id === 'string' || typeof properties.id === 'number' ? properties.id : undefined);

  return {
    layerId: feature.layer.id,
    layerLabel: LAYER_LABELS[feature.layer.id] ?? feature.layer.id,
    featureId,
    properties
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

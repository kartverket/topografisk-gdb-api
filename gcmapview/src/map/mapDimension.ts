import type * as maplibregl from 'maplibre-gl';
import type { ExpressionSpecification } from 'maplibre-gl';
import type { FeatureCollection } from './geojson';
import type { LayerVisibility } from '../store/layerVisibilityStore';
import {
  buildingExtrusionHeightExpression,
  bygningExtrusionLayerId,
  bygningExtrusionSourceId,
  bygningSenterlinjeExtrusionLayerId,
  bygningSenterlinjeExtrusionSourceId,
  buildingsExtrusionLayerId,
  DEFAULT_3D_PITCH,
  extrusionShaftTopExpression,
  EXTRUSION_OPACITY_MAX,
  EXTRUSION_OPACITY_MIN,
  EXTRUSION_TOP_CAP_M,
  heightColorExpression,
  platformEdgesExtrusionLayerId,
  platformEdgesExtrusionSourceId,
  trackCentresExtrusionLayerId,
  trackCentresExtrusionSourceId
} from './map3d';
import { platformEdgesLayerId, trackCentresLayerId } from './baneLayers';
import { bygningLayerId } from './bygningLayers';
import { bygningPosisjonLayerId } from './bygningPosisjonLayers';
import { bygningSenterlinjeColor, bygningSenterlinjeLayerId } from './bygningSenterlinjeLayers';
import {
  bygningOmradeFillColor,
  bygningOmradeExtrusionLayerId,
  bygningOmradeExtrusionSourceId,
  bygningOmradeFillLayerId,
  bygningOmradeOutlineLayerId
} from './bygningOmradeLayers';
import {
  terrainSampleKey,
  terrainSamplePointsForFeatureCollections,
  type ElevatedSourcesWorkerRequest,
  type ElevatedSourcesWorkerResponse,
  type ElevatedSourceVisibility,
  type TerrainSampleMap
} from './elevatedSourcesShared';

export const terrainSourceId = 'terrain-dem';
const TERRAIN_EXAGGERATION = 1;
const BANE_TERRAIN_CLEARANCE_M = 2;
const emptyFeatureCollection: FeatureCollection = { type: 'FeatureCollection', features: [] };
let activeElevatedSourcesWorker: Worker | undefined;
let latestElevatedSourcesRequestId = 0;

function terrainElevationAt(map: maplibregl.Map, longitude: number, latitude: number): number | undefined {
  const terrainElevation = map.queryTerrainElevation([longitude, latitude]);
  return typeof terrainElevation === 'number' && Number.isFinite(terrainElevation) ? terrainElevation : undefined;
}

const buildingFlatLayerIds = ['building-centroids-circle', 'buildings-fill', 'buildings-outline'] as const;

const buildingExtrusionLayerIds = [`${buildingsExtrusionLayerId}-shaft`, `${buildingsExtrusionLayerId}-cap`] as const;

const platformEdgesFlatLayerIds = [platformEdgesLayerId] as const;

const trackCentresFlatLayerIds = [trackCentresLayerId] as const;

const bygningFlatLayerIds = [bygningLayerId] as const;
const bygningSenterlinjeFlatLayerIds = [bygningSenterlinjeLayerId] as const;
const bygningOmradeLayerIds = [bygningOmradeFillLayerId, bygningOmradeOutlineLayerId] as const;
const bygningOmrade3dLayerIds = [`${bygningOmradeExtrusionLayerId}-shaft`, `${bygningOmradeExtrusionLayerId}-cap`] as const;
const bygningPosisjonLayerIds = [bygningPosisjonLayerId] as const;

type OpacityBandedExtrusion = {
  baseLayerId: string;
  source: string;
  heightExpression: ExpressionSpecification;
  baseExpression?: ExpressionSpecification;
  filter?: maplibregl.FilterSpecification;
  color?: string | ExpressionSpecification;
};

function numericPropertyExpression(propertyName: string, fallback = 0): ExpressionSpecification {
  return ['to-number', ['coalesce', ['get', propertyName], fallback]];
}

function offsetBaseExpression(
  baseExpression: ExpressionSpecification,
  zOffsetExpression: ExpressionSpecification
): ExpressionSpecification {
  return ['max', 0, ['-', baseExpression, zOffsetExpression]];
}

function offsetHeightExpression(
  baseExpression: ExpressionSpecification,
  topExpression: ExpressionSpecification,
  zOffsetExpression: ExpressionSpecification
): ExpressionSpecification {
  const adjustedBase = offsetBaseExpression(baseExpression, zOffsetExpression);
  return ['case', ['<=', topExpression, zOffsetExpression], 0, ['max', adjustedBase, ['-', topExpression, zOffsetExpression]]];
}

function setLayerVisibility(map: maplibregl.Map, layerId: string, visible: boolean) {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
}

function setLayersVisibility(map: maplibregl.Map, layerIds: readonly string[], visible: boolean) {
  for (const layerId of layerIds) {
    setLayerVisibility(map, layerId, visible);
  }
}

function upsertGeoJsonSourceData(map: maplibregl.Map, sourceId: string, data: FeatureCollection) {
  const source = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined;

  if (source) {
    source.setData(data);
    return;
  }

  map.addSource(sourceId, {
    type: 'geojson',
    data
  });
}

function setElevatedSourceData(
  map: maplibregl.Map,
  elevatedSources: Pick<
    ElevatedSourcesWorkerResponse,
    'platformData' | 'trackData' | 'bygningData' | 'bygningSenterlinjeData' | 'bygningOmradeData'
  >
) {
  upsertGeoJsonSourceData(map, platformEdgesExtrusionSourceId, elevatedSources.platformData);
  upsertGeoJsonSourceData(map, trackCentresExtrusionSourceId, elevatedSources.trackData);
  upsertGeoJsonSourceData(map, bygningExtrusionSourceId, elevatedSources.bygningData);
  upsertGeoJsonSourceData(map, bygningSenterlinjeExtrusionSourceId, elevatedSources.bygningSenterlinjeData);
  upsertGeoJsonSourceData(map, bygningOmradeExtrusionSourceId, elevatedSources.bygningOmradeData);
}

function clearElevatedSourceData(map: maplibregl.Map) {
  setElevatedSourceData(map, {
    platformData: emptyFeatureCollection,
    trackData: emptyFeatureCollection,
    bygningData: emptyFeatureCollection,
    bygningSenterlinjeData: emptyFeatureCollection,
    bygningOmradeData: emptyFeatureCollection
  });
}

function collectTerrainSamples(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningOmrade: FeatureCollection,
  visibility: ElevatedSourceVisibility
): TerrainSampleMap {
  const terrainSamples: TerrainSampleMap = {};

  for (const [longitude, latitude] of terrainSamplePointsForFeatureCollections(
    platformEdges,
    trackCentres,
    bygning,
    bygningSenterlinje,
    bygningOmrade,
    visibility
  )) {
    const terrainElevation = terrainElevationAt(map, longitude, latitude);
    if (typeof terrainElevation === 'number') {
      terrainSamples[terrainSampleKey(longitude, latitude)] = terrainElevation;
    }
  }

  return terrainSamples;
}

function addExtrusionShaft(map: maplibregl.Map, options: OpacityBandedExtrusion) {
  const {
    baseLayerId,
    source,
    heightExpression,
    baseExpression = 0,
    filter,
    color = heightColorExpression(heightExpression)
  } = options;
  const tallerThanCap: ExpressionSpecification = ['>', heightExpression, EXTRUSION_TOP_CAP_M];
  const shaftFilter: maplibregl.FilterSpecification = filter
    ? (['all', filter, tallerThanCap] as maplibregl.FilterSpecification)
    : tallerThanCap;
  const shaftTop = extrusionShaftTopExpression(heightExpression, baseExpression);

  map.addLayer({
    id: `${baseLayerId}-shaft`,
    type: 'fill-extrusion',
    source,
    filter: shaftFilter,
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': color,
      'fill-extrusion-opacity': EXTRUSION_OPACITY_MIN,
      'fill-extrusion-base': baseExpression,
      'fill-extrusion-height': shaftTop,
      'fill-extrusion-vertical-gradient': false
    }
  });
}

function addExtrusionCap(map: maplibregl.Map, options: OpacityBandedExtrusion) {
  const {
    baseLayerId,
    source,
    heightExpression,
    baseExpression = 0,
    filter,
    color = heightColorExpression(heightExpression)
  } = options;
  const shaftTop = extrusionShaftTopExpression(heightExpression, baseExpression);

  map.addLayer({
    id: `${baseLayerId}-cap`,
    type: 'fill-extrusion',
    source,
    ...(filter ? { filter } : {}),
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': color,
      'fill-extrusion-opacity': EXTRUSION_OPACITY_MAX,
      'fill-extrusion-base': shaftTop,
      'fill-extrusion-height': heightExpression,
      'fill-extrusion-vertical-gradient': false
    }
  });
}

const elevatedLineElevationExpression: ExpressionSpecification = [
  'case',
  ['has', 'sourceHeight'],
  ['to-number', ['get', 'sourceHeight']],
  ['has', 'elevation'],
  ['to-number', ['get', 'elevation']],
  0
];

/**
 * Flat footprint on the ground plane (z=0). Uses fill, not fill-extrusion, so
 * overlapping shadows composite instead of punching holes.
 */
function addElevatedLineGroundShadow(
  map: maplibregl.Map,
  baseLayerId: string,
  source: string,
  color: string | ExpressionSpecification = heightColorExpression(elevatedLineElevationExpression)
) {
  map.addLayer({
    id: `${baseLayerId}-shadow`,
    type: 'fill',
    source,
    layout: { visibility: 'none' },
    paint: {
      'fill-color': color,
      'fill-opacity': EXTRUSION_OPACITY_MIN
    }
  });
}

/** Opaque beam at Z elevation (avoids translucent overlap cropping). */
function addOpaqueElevatedLineExtrusion(
  map: maplibregl.Map,
  baseLayerId: string,
  source: string,
  color: string | ExpressionSpecification = heightColorExpression(elevatedLineElevationExpression)
) {
  const rawBaseExpression = numericPropertyExpression('base');
  const rawHeightExpression = numericPropertyExpression('height');
  const zOffsetExpression = numericPropertyExpression('zOffset');
  const baseExpression = offsetBaseExpression(rawBaseExpression, zOffsetExpression);
  const heightExpression = offsetHeightExpression(rawBaseExpression, rawHeightExpression, zOffsetExpression);

  map.addLayer({
    id: `${baseLayerId}-solid`,
    type: 'fill-extrusion',
    source,
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': color,
      // Opacity must stay 1: translucent fill-extrusion crops overlapping footprints.
      'fill-extrusion-opacity': 1,
      'fill-extrusion-base': baseExpression,
      'fill-extrusion-height': heightExpression,
      'fill-extrusion-vertical-gradient': false
    }
  });
}

export function addExtrusionLayers(map: maplibregl.Map) {
  map.addSource(platformEdgesExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  map.addSource(trackCentresExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  map.addSource(bygningExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  map.addSource(bygningSenterlinjeExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  map.addSource(bygningOmradeExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });

  const buildingHeight = buildingExtrusionHeightExpression();
  const buildingBand: OpacityBandedExtrusion = {
    baseLayerId: buildingsExtrusionLayerId,
    source: 'buildings',
    heightExpression: buildingHeight,
    filter: ['==', ['geometry-type'], 'Polygon'],
    color: '#000000'
  };

  addExtrusionShaft(map, buildingBand);
  addExtrusionCap(map, buildingBand);

  const bygningOmradeRawBaseExpression = numericPropertyExpression('base');
  const bygningOmradeRawHeightExpression = numericPropertyExpression('height');
  const bygningOmradeZOffsetExpression = numericPropertyExpression('zOffset');

  const bygningOmradeBand: OpacityBandedExtrusion = {
    baseLayerId: bygningOmradeExtrusionLayerId,
    source: bygningOmradeExtrusionSourceId,
    baseExpression: offsetBaseExpression(bygningOmradeRawBaseExpression, bygningOmradeZOffsetExpression),
    heightExpression: offsetHeightExpression(
      bygningOmradeRawBaseExpression,
      bygningOmradeRawHeightExpression,
      bygningOmradeZOffsetExpression
    ),
    filter: ['==', ['geometry-type'], 'Polygon'],
    color: bygningOmradeFillColor
  };

  addExtrusionShaft(map, bygningOmradeBand);
  addExtrusionCap(map, bygningOmradeBand);

  // Ground shadows before opaque beams so fills sit under extrusions.
  addElevatedLineGroundShadow(map, platformEdgesExtrusionLayerId, platformEdgesExtrusionSourceId, '#000000');
  addElevatedLineGroundShadow(map, trackCentresExtrusionLayerId, trackCentresExtrusionSourceId);
  addElevatedLineGroundShadow(map, bygningExtrusionLayerId, bygningExtrusionSourceId, '#000000');
  addElevatedLineGroundShadow(
    map,
    bygningSenterlinjeExtrusionLayerId,
    bygningSenterlinjeExtrusionSourceId,
    bygningSenterlinjeColor
  );
  addOpaqueElevatedLineExtrusion(map, platformEdgesExtrusionLayerId, platformEdgesExtrusionSourceId, '#000000');
  addOpaqueElevatedLineExtrusion(map, trackCentresExtrusionLayerId, trackCentresExtrusionSourceId);
  addOpaqueElevatedLineExtrusion(map, bygningExtrusionLayerId, bygningExtrusionSourceId, '#000000');
  addOpaqueElevatedLineExtrusion(
    map,
    bygningSenterlinjeExtrusionLayerId,
    bygningSenterlinjeExtrusionSourceId,
    bygningSenterlinjeColor
  );
}

export function upsertElevatedSources(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningOmrade: FeatureCollection,
  visibility: Pick<
    LayerVisibility,
    'platformEdges' | 'trackCentres' | 'bygning' | 'bygningSenterlinje' | 'bygningOmrade'
  >,
  adjustHeights: boolean,
  renderElevatedSources = true
) {
  latestElevatedSourcesRequestId += 1;
  const requestId = latestElevatedSourcesRequestId;

  if (activeElevatedSourcesWorker) {
    activeElevatedSourcesWorker.terminate();
    activeElevatedSourcesWorker = undefined;
  }

  clearElevatedSourceData(map);

  if (!renderElevatedSources) {
    return;
  }

  const terrainEnabled = Boolean(map.getTerrain()) && !adjustHeights;
  const workerRequest: ElevatedSourcesWorkerRequest = {
    requestId,
    platformEdges,
    trackCentres,
    bygning,
    bygningSenterlinje,
    bygningOmrade,
    visibility,
    adjustHeights,
    terrainEnabled,
    baneTerrainClearanceMeters: BANE_TERRAIN_CLEARANCE_M,
    terrainSamples: terrainEnabled
      ? collectTerrainSamples(map, platformEdges, trackCentres, bygning, bygningSenterlinje, bygningOmrade, visibility)
      : {}
  };

  const worker = new Worker(new URL('../workers/elevatedSourcesWorker.ts', import.meta.url), { type: 'module' });
  activeElevatedSourcesWorker = worker;

  worker.onmessage = event => {
    const response = event.data as ElevatedSourcesWorkerResponse;
    if (response.requestId !== latestElevatedSourcesRequestId) {
      worker.terminate();
      if (activeElevatedSourcesWorker === worker) {
        activeElevatedSourcesWorker = undefined;
      }
      return;
    }

    setElevatedSourceData(map, response);
    worker.terminate();
    if (activeElevatedSourcesWorker === worker) {
      activeElevatedSourcesWorker = undefined;
    }
  };

  worker.onerror = error => {
    console.error('[gcmapview] elevated sources worker failed', error);
    worker.terminate();
    if (activeElevatedSourcesWorker === worker) {
      activeElevatedSourcesWorker = undefined;
    }
  };

  worker.postMessage(workerRequest);
}

/** Apply 2D/3D layer set, gated by user layer toggles. */
export function applyMapLayerVisibility(
  map: maplibregl.Map,
  is3d: boolean,
  visibility: LayerVisibility,
  enableTerrain = false
) {
  const showElevatedLineShadows = is3d && !enableTerrain;

  setLayersVisibility(map, ['parcels-fill', 'parcels-outline'], visibility.parcels);

  setLayersVisibility(map, buildingFlatLayerIds, visibility.buildings && !is3d);
  setLayersVisibility(map, buildingExtrusionLayerIds, visibility.buildings && is3d);

  setLayersVisibility(map, platformEdgesFlatLayerIds, visibility.platformEdges && !is3d);
  setLayerVisibility(map, `${platformEdgesExtrusionLayerId}-shadow`, visibility.platformEdges && showElevatedLineShadows);
  setLayerVisibility(map, `${platformEdgesExtrusionLayerId}-solid`, visibility.platformEdges && is3d);

  setLayersVisibility(map, trackCentresFlatLayerIds, visibility.trackCentres && !is3d);
  setLayerVisibility(map, `${trackCentresExtrusionLayerId}-shadow`, visibility.trackCentres && showElevatedLineShadows);
  setLayerVisibility(map, `${trackCentresExtrusionLayerId}-solid`, visibility.trackCentres && is3d);

  setLayersVisibility(map, bygningFlatLayerIds, visibility.bygning && !is3d);
  setLayerVisibility(map, `${bygningExtrusionLayerId}-shadow`, visibility.bygning && showElevatedLineShadows);
  setLayerVisibility(map, `${bygningExtrusionLayerId}-solid`, visibility.bygning && is3d);
  setLayersVisibility(map, bygningSenterlinjeFlatLayerIds, visibility.bygningSenterlinje && !is3d);
  setLayerVisibility(
    map,
    `${bygningSenterlinjeExtrusionLayerId}-shadow`,
    visibility.bygningSenterlinje && showElevatedLineShadows
  );
  setLayerVisibility(map, `${bygningSenterlinjeExtrusionLayerId}-solid`, visibility.bygningSenterlinje && is3d);
  setLayersVisibility(map, bygningOmradeLayerIds, visibility.bygningOmrade && !is3d);
  setLayersVisibility(map, bygningOmrade3dLayerIds, visibility.bygningOmrade && is3d);
  setLayersVisibility(map, bygningPosisjonLayerIds, visibility.bygningPosisjon);
}

/** Switch camera + layer visibility for the global 2D/3D mode. */
export function applyMapDimensionMode(map: maplibregl.Map, is3d: boolean, visibility: LayerVisibility, enableTerrain: boolean) {
  applyMapLayerVisibility(map, is3d, visibility, enableTerrain);

  if (is3d) {
    if (enableTerrain && map.getSource(terrainSourceId)) {
      map.setTerrain({ source: terrainSourceId, exaggeration: TERRAIN_EXAGGERATION });
    } else {
      map.setTerrain(null);
    }
    map.setMaxPitch(85);
    map.dragRotate.enable();
    map.touchPitch.enable();
    if (map.getPitch() < 20) {
      map.easeTo({ pitch: DEFAULT_3D_PITCH, duration: 700 });
    }
    return;
  }

  if (map.getPitch() === 0) {
    map.setTerrain(null);
    map.setMaxPitch(0);
    return;
  }

  map.setTerrain(null);
  map.easeTo({ pitch: 0, duration: 500 });
  map.once('moveend', () => {
    if (map.getPitch() === 0) {
      map.setMaxPitch(0);
    }
  });
}

export function configureInitialMapInteraction(map: maplibregl.Map) {
  map.setMaxPitch(0);
  map.dragRotate.disable();
  map.touchPitch.disable();
}

import type * as maplibregl from 'maplibre-gl';
import type { ExpressionSpecification } from 'maplibre-gl';
import type { FeatureCollection } from './geojson';
import type { LayerVisibility } from '../store/layerVisibilityStore';
import {
  buildingExtrusionHeightExpression,
  buildingsExtrusionLayerId,
  DEFAULT_3D_PITCH,
  elevatedLineSegments,
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

const buildingFlatLayerIds = ['building-centroids-circle', 'buildings-fill', 'buildings-outline'] as const;

const buildingExtrusionLayerIds = [`${buildingsExtrusionLayerId}-shaft`, `${buildingsExtrusionLayerId}-cap`] as const;

const platformEdgesFlatLayerIds = [platformEdgesLayerId] as const;
const platformEdges3dLayerIds = [
  `${platformEdgesExtrusionLayerId}-shadow`,
  `${platformEdgesExtrusionLayerId}-solid`
] as const;

const trackCentresFlatLayerIds = [trackCentresLayerId] as const;
const trackCentres3dLayerIds = [
  `${trackCentresExtrusionLayerId}-shadow`,
  `${trackCentresExtrusionLayerId}-solid`
] as const;

type OpacityBandedExtrusion = {
  baseLayerId: string;
  source: string;
  heightExpression: ExpressionSpecification;
  filter?: maplibregl.FilterSpecification;
};

function setLayerVisibility(map: maplibregl.Map, layerId: string, visible: boolean) {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
}

function setLayersVisibility(map: maplibregl.Map, layerIds: readonly string[], visible: boolean) {
  for (const layerId of layerIds) {
    setLayerVisibility(map, layerId, visible);
  }
}

function addExtrusionShaft(map: maplibregl.Map, options: OpacityBandedExtrusion) {
  const { baseLayerId, source, heightExpression, filter } = options;
  const tallerThanCap: ExpressionSpecification = ['>', heightExpression, EXTRUSION_TOP_CAP_M];
  const shaftFilter: maplibregl.FilterSpecification = filter
    ? (['all', filter, tallerThanCap] as maplibregl.FilterSpecification)
    : tallerThanCap;

  map.addLayer({
    id: `${baseLayerId}-shaft`,
    type: 'fill-extrusion',
    source,
    filter: shaftFilter,
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': heightColorExpression(heightExpression),
      'fill-extrusion-opacity': EXTRUSION_OPACITY_MIN,
      'fill-extrusion-base': 0,
      'fill-extrusion-height': extrusionShaftTopExpression(heightExpression),
      'fill-extrusion-vertical-gradient': false
    }
  });
}

function addExtrusionCap(map: maplibregl.Map, options: OpacityBandedExtrusion) {
  const { baseLayerId, source, heightExpression, filter } = options;
  const shaftTop = extrusionShaftTopExpression(heightExpression);

  map.addLayer({
    id: `${baseLayerId}-cap`,
    type: 'fill-extrusion',
    source,
    ...(filter ? { filter } : {}),
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': heightColorExpression(heightExpression),
      'fill-extrusion-opacity': EXTRUSION_OPACITY_MAX,
      'fill-extrusion-base': shaftTop,
      'fill-extrusion-height': heightExpression,
      'fill-extrusion-vertical-gradient': false
    }
  });
}

const elevatedLineElevationExpression: ExpressionSpecification = [
  'to-number',
  ['coalesce', ['get', 'elevation'], ['get', 'height'], 0]
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
  const baseExpression: ExpressionSpecification = ['to-number', ['coalesce', ['get', 'base'], 0]];
  const heightExpression: ExpressionSpecification = ['to-number', ['coalesce', ['get', 'height'], 1]];

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

  const buildingHeight = buildingExtrusionHeightExpression();
  const buildingBand: OpacityBandedExtrusion = {
    baseLayerId: buildingsExtrusionLayerId,
    source: 'buildings',
    heightExpression: buildingHeight,
    filter: ['==', '$type', 'Polygon']
  };

  addExtrusionShaft(map, buildingBand);
  addExtrusionCap(map, buildingBand);

  // Ground shadows before opaque beams so fills sit under extrusions.
  addElevatedLineGroundShadow(map, platformEdgesExtrusionLayerId, platformEdgesExtrusionSourceId, '#000000');
  addElevatedLineGroundShadow(map, trackCentresExtrusionLayerId, trackCentresExtrusionSourceId);
  addOpaqueElevatedLineExtrusion(map, platformEdgesExtrusionLayerId, platformEdgesExtrusionSourceId, '#000000');
  addOpaqueElevatedLineExtrusion(map, trackCentresExtrusionLayerId, trackCentresExtrusionSourceId);
}

export function upsertElevatedLineSources(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection
) {
  const platformSource = map.getSource(platformEdgesExtrusionSourceId) as maplibregl.GeoJSONSource | undefined;
  const trackSource = map.getSource(trackCentresExtrusionSourceId) as maplibregl.GeoJSONSource | undefined;

  const platformData = elevatedLineSegments(platformEdges);
  const trackData = elevatedLineSegments(trackCentres);

  if (platformSource) {
    platformSource.setData(platformData);
  } else {
    map.addSource(platformEdgesExtrusionSourceId, {
      type: 'geojson',
      data: platformData
    });
  }

  if (trackSource) {
    trackSource.setData(trackData);
  } else {
    map.addSource(trackCentresExtrusionSourceId, {
      type: 'geojson',
      data: trackData
    });
  }
}

/** Apply 2D/3D layer set, gated by user layer toggles. */
export function applyMapLayerVisibility(map: maplibregl.Map, is3d: boolean, visibility: LayerVisibility) {
  setLayersVisibility(map, ['parcels-fill', 'parcels-outline'], visibility.parcels);

  setLayersVisibility(map, buildingFlatLayerIds, visibility.buildings && !is3d);
  setLayersVisibility(map, buildingExtrusionLayerIds, visibility.buildings && is3d);

  setLayersVisibility(map, platformEdgesFlatLayerIds, visibility.platformEdges && !is3d);
  setLayersVisibility(map, platformEdges3dLayerIds, visibility.platformEdges && is3d);

  setLayersVisibility(map, trackCentresFlatLayerIds, visibility.trackCentres && !is3d);
  setLayersVisibility(map, trackCentres3dLayerIds, visibility.trackCentres && is3d);
}

/** Switch camera + layer visibility for the global 2D/3D mode. */
export function applyMapDimensionMode(map: maplibregl.Map, is3d: boolean, visibility: LayerVisibility) {
  applyMapLayerVisibility(map, is3d, visibility);

  if (is3d) {
    map.setMaxPitch(85);
    map.dragRotate.enable();
    map.touchPitch.enable();
    if (map.getPitch() < 20) {
      map.easeTo({ pitch: DEFAULT_3D_PITCH, duration: 700 });
    }
    return;
  }

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

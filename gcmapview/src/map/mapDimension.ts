import type * as maplibregl from 'maplibre-gl';
import type { ExpressionSpecification } from 'maplibre-gl';
import type { FeatureCollection } from './geojson';
import type { LayerVisibility } from '../store/layerVisibilityStore';
import {
  BYGNING_ELEVATED_LINE_WIDTH_M,
  buildingExtrusionHeightExpression,
  bygningExtrusionLayerId,
  bygningExtrusionSourceId,
  bygningSenterlinjeExtrusionLayerId,
  bygningSenterlinjeExtrusionSourceId,
  buildingsExtrusionLayerId,
  DEFAULT_3D_PITCH,
  elevatedLineSegments,
  extrusionShaftTopExpression,
  EXTRUSION_OPACITY_MAX,
  EXTRUSION_OPACITY_MIN,
  EXTRUSION_TOP_CAP_M,
  heightColorExpression,
  lowestPositiveLineHeight,
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
  bygningOmradeExtrusionFeatureCollection,
  bygningOmradeFillColor,
  bygningOmradeExtrusionLayerId,
  bygningOmradeExtrusionSourceId,
  bygningOmradeFillLayerId,
  bygningOmradeOutlineLayerId,
  lowestPositiveBygningOmradeHeight
} from './bygningOmradeLayers';

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

const bygningFlatLayerIds = [bygningLayerId] as const;
const bygning3dLayerIds = [`${bygningExtrusionLayerId}-shadow`, `${bygningExtrusionLayerId}-solid`] as const;
const bygningSenterlinjeFlatLayerIds = [bygningSenterlinjeLayerId] as const;
const bygningSenterlinje3dLayerIds = [
  `${bygningSenterlinjeExtrusionLayerId}-shadow`,
  `${bygningSenterlinjeExtrusionLayerId}-solid`
] as const;
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
    filter: ['==', '$type', 'Polygon'],
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
    filter: ['==', '$type', 'Polygon'],
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
  adjustHeights: boolean
) {
  const platformSource = map.getSource(platformEdgesExtrusionSourceId) as maplibregl.GeoJSONSource | undefined;
  const trackSource = map.getSource(trackCentresExtrusionSourceId) as maplibregl.GeoJSONSource | undefined;
  const bygningSource = map.getSource(bygningExtrusionSourceId) as maplibregl.GeoJSONSource | undefined;
  const bygningSenterlinjeSource = map.getSource(bygningSenterlinjeExtrusionSourceId) as
    | maplibregl.GeoJSONSource
    | undefined;
  const bygningOmradeSource = map.getSource(bygningOmradeExtrusionSourceId) as maplibregl.GeoJSONSource | undefined;

  const heightSamples = [
    ...(visibility.platformEdges ? [lowestPositiveLineHeight([platformEdges])] : []),
    ...(visibility.trackCentres ? [lowestPositiveLineHeight([trackCentres])] : []),
    ...(visibility.bygning ? [lowestPositiveLineHeight([bygning])] : []),
    ...(visibility.bygningSenterlinje ? [lowestPositiveLineHeight([bygningSenterlinje])] : []),
    ...(visibility.bygningOmrade ? [lowestPositiveBygningOmradeHeight(bygningOmrade)] : [])
  ].filter(height => height > 0);

  const heightOffset = adjustHeights && heightSamples.length > 0 ? Math.min(...heightSamples) : 0;

  const platformData = elevatedLineSegments(platformEdges, undefined, undefined, heightOffset);
  const trackData = elevatedLineSegments(trackCentres, undefined, undefined, heightOffset);
  const bygningData = elevatedLineSegments(
    bygning,
    BYGNING_ELEVATED_LINE_WIDTH_M,
    undefined,
    heightOffset
  );
  const bygningSenterlinjeData = elevatedLineSegments(
    bygningSenterlinje,
    BYGNING_ELEVATED_LINE_WIDTH_M,
    undefined,
    heightOffset
  );
  const bygningOmradeData = bygningOmradeExtrusionFeatureCollection(bygningOmrade, heightOffset);

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

  if (bygningSource) {
    bygningSource.setData(bygningData);
  } else {
    map.addSource(bygningExtrusionSourceId, {
      type: 'geojson',
      data: bygningData
    });
  }

  if (bygningSenterlinjeSource) {
    bygningSenterlinjeSource.setData(bygningSenterlinjeData);
  } else {
    map.addSource(bygningSenterlinjeExtrusionSourceId, {
      type: 'geojson',
      data: bygningSenterlinjeData
    });
  }

  if (bygningOmradeSource) {
    bygningOmradeSource.setData(bygningOmradeData);
  } else {
    map.addSource(bygningOmradeExtrusionSourceId, {
      type: 'geojson',
      data: bygningOmradeData
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

  setLayersVisibility(map, bygningFlatLayerIds, visibility.bygning && !is3d);
  setLayersVisibility(map, bygning3dLayerIds, visibility.bygning && is3d);
  setLayersVisibility(map, bygningSenterlinjeFlatLayerIds, visibility.bygningSenterlinje && !is3d);
  setLayersVisibility(map, bygningSenterlinje3dLayerIds, visibility.bygningSenterlinje && is3d);
  setLayersVisibility(map, bygningOmradeLayerIds, visibility.bygningOmrade && !is3d);
  setLayersVisibility(map, bygningOmrade3dLayerIds, visibility.bygningOmrade && is3d);
  setLayersVisibility(map, bygningPosisjonLayerIds, visibility.bygningPosisjon);
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

  if (map.getPitch() === 0) {
    map.setMaxPitch(0);
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

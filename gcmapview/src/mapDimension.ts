import type * as maplibregl from 'maplibre-gl'
import type { ExpressionSpecification } from 'maplibre-gl'
import type { FeatureCollection } from './geojson'
import {
  buildingExtrusionHeightExpression,
  buildingsExtrusionLayerId,
  DEFAULT_3D_PITCH,
  elevatedLineSegments,
  extrusionBandLayerIds,
  extrusionShaftTopExpression,
  EXTRUSION_OPACITY_MAX,
  EXTRUSION_OPACITY_MIN,
  EXTRUSION_TOP_CAP_M,
  heightColorExpression,
  platformEdgesExtrusionLayerId,
  platformEdgesExtrusionSourceId,
  trackCentresExtrusionLayerId,
  trackCentresExtrusionSourceId,
} from './map3d'
import { platformEdgesLayerId, trackCentresLayerId } from './baneLayers'

const flatOnlyLayerIds = [
  'building-centroids-circle',
  'buildings-fill',
  'buildings-outline',
  platformEdgesLayerId,
  trackCentresLayerId,
] as const

const extrusionLayerIds = [
  ...extrusionBandLayerIds(buildingsExtrusionLayerId),
  ...extrusionBandLayerIds(platformEdgesExtrusionLayerId),
  ...extrusionBandLayerIds(trackCentresExtrusionLayerId),
]

function setLayerVisibility(
  map: maplibregl.Map,
  layerId: string,
  visible: boolean,
) {
  if (!map.getLayer(layerId)) return
  map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
}

function addOpacityBandedExtrusion(options: {
  map: maplibregl.Map
  baseLayerId: string
  source: string
  heightExpression: ExpressionSpecification
  filter?: maplibregl.FilterSpecification
}) {
  const { map, baseLayerId, source, heightExpression, filter } = options
  const color = heightColorExpression(heightExpression)
  const shaftTop = extrusionShaftTopExpression(heightExpression)
  const tallerThanCap: ExpressionSpecification = [
    '>',
    heightExpression,
    EXTRUSION_TOP_CAP_M,
  ]
  const shaftFilter: maplibregl.FilterSpecification = filter
    ? (['all', filter, tallerThanCap] as maplibregl.FilterSpecification)
    : tallerThanCap

  // Translucent shaft: only when feature is taller than the top cap.
  map.addLayer({
    id: `${baseLayerId}-shaft`,
    type: 'fill-extrusion',
    source,
    filter: shaftFilter,
    layout: { visibility: 'none' },
    paint: {
      'fill-extrusion-color': color,
      'fill-extrusion-opacity': EXTRUSION_OPACITY_MIN,
      'fill-extrusion-base': 0,
      'fill-extrusion-height': shaftTop,
      'fill-extrusion-vertical-gradient': false,
    },
  })
  // Opaque top cap of at most EXTRUSION_TOP_CAP_M meters.
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
      'fill-extrusion-vertical-gradient': false,
    },
  })
}

export function addExtrusionLayers(map: maplibregl.Map) {
  map.addSource(platformEdgesExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })
  map.addSource(trackCentresExtrusionSourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
  })

  const buildingHeight = buildingExtrusionHeightExpression()
  const lineHeight: ExpressionSpecification = [
    'to-number',
    ['coalesce', ['get', 'height'], 1],
  ]

  addOpacityBandedExtrusion({
    map,
    baseLayerId: buildingsExtrusionLayerId,
    source: 'buildings',
    heightExpression: buildingHeight,
    filter: ['==', '$type', 'Polygon'],
  })
  addOpacityBandedExtrusion({
    map,
    baseLayerId: platformEdgesExtrusionLayerId,
    source: platformEdgesExtrusionSourceId,
    heightExpression: lineHeight,
  })
  addOpacityBandedExtrusion({
    map,
    baseLayerId: trackCentresExtrusionLayerId,
    source: trackCentresExtrusionSourceId,
    heightExpression: lineHeight,
  })
}

export function upsertElevatedLineSources(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
) {
  const platformSource = map.getSource(platformEdgesExtrusionSourceId) as
    | maplibregl.GeoJSONSource
    | undefined
  const trackSource = map.getSource(trackCentresExtrusionSourceId) as
    | maplibregl.GeoJSONSource
    | undefined

  const platformData = elevatedLineSegments(platformEdges)
  const trackData = elevatedLineSegments(trackCentres)

  if (platformSource) {
    platformSource.setData(platformData)
  } else {
    map.addSource(platformEdgesExtrusionSourceId, {
      type: 'geojson',
      data: platformData,
    })
  }

  if (trackSource) {
    trackSource.setData(trackData)
  } else {
    map.addSource(trackCentresExtrusionSourceId, {
      type: 'geojson',
      data: trackData,
    })
  }
}

/** Switch camera + layer visibility for the global 2D/3D mode. */
export function applyMapDimensionMode(map: maplibregl.Map, is3d: boolean) {
  for (const layerId of flatOnlyLayerIds) {
    setLayerVisibility(map, layerId, !is3d)
  }
  for (const layerId of extrusionLayerIds) {
    setLayerVisibility(map, layerId, is3d)
  }

  setLayerVisibility(map, 'parcels-fill', true)
  setLayerVisibility(map, 'parcels-outline', true)

  if (is3d) {
    map.setMaxPitch(85)
    map.dragRotate.enable()
    map.touchPitch.enable()
    if (map.getPitch() < 20) {
      map.easeTo({ pitch: DEFAULT_3D_PITCH, duration: 700 })
    }
    return
  }

  map.easeTo({ pitch: 0, duration: 500 })
  map.once('moveend', () => {
    if (map.getPitch() === 0) {
      map.setMaxPitch(0)
    }
  })
}

export function configureInitialMapInteraction(map: maplibregl.Map) {
  map.setMaxPitch(0)
  map.dragRotate.disable()
  map.touchPitch.disable()
}

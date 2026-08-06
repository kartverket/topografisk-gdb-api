import type * as maplibregl from "maplibre-gl";
import type { FeatureCollection } from "./geojson";
import {
  buildingExtrusionHeightExpression,
  buildingsExtrusionLayerId,
  DEFAULT_3D_PITCH,
  elevatedLineSegments,
  heightColorExpression,
  platformEdgesExtrusionLayerId,
  platformEdgesExtrusionSourceId,
  trackCentresExtrusionLayerId,
  trackCentresExtrusionSourceId,
} from "./map3d";
import { platformEdgesLayerId, trackCentresLayerId } from "./baneLayers";

const flatOnlyLayerIds = [
  "building-centroids-circle",
  "buildings-fill",
  "buildings-outline",
  platformEdgesLayerId,
  trackCentresLayerId,
] as const;

const extrusionLayerIds = [
  buildingsExtrusionLayerId,
  platformEdgesExtrusionLayerId,
  trackCentresExtrusionLayerId,
] as const;

function setLayerVisibility(
  map: maplibregl.Map,
  layerId: string,
  visible: boolean,
) {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
}

export function addExtrusionLayers(map: maplibregl.Map) {
  map.addSource(platformEdgesExtrusionSourceId, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });
  map.addSource(trackCentresExtrusionSourceId, {
    type: "geojson",
    data: { type: "FeatureCollection", features: [] },
  });

  const buildingHeight = buildingExtrusionHeightExpression();
  const lineHeight: maplibregl.ExpressionSpecification = [
    "to-number",
    ["coalesce", ["get", "height"], 1],
  ];

  map.addLayer({
    id: buildingsExtrusionLayerId,
    type: "fill-extrusion",
    source: "buildings",
    filter: ["==", "$type", "Polygon"],
    layout: { visibility: "none" },
    paint: {
      "fill-extrusion-color": heightColorExpression(buildingHeight),
      "fill-extrusion-opacity": 0.75,
      "fill-extrusion-height": buildingHeight,
      "fill-extrusion-base": 0,
    },
  });
  map.addLayer({
    id: platformEdgesExtrusionLayerId,
    type: "fill-extrusion",
    source: platformEdgesExtrusionSourceId,
    layout: { visibility: "none" },
    paint: {
      "fill-extrusion-color": heightColorExpression(lineHeight),
      "fill-extrusion-opacity": 0.75,
      "fill-extrusion-height": lineHeight,
      "fill-extrusion-base": ["coalesce", ["get", "base"], 0],
    },
  });
  map.addLayer({
    id: trackCentresExtrusionLayerId,
    type: "fill-extrusion",
    source: trackCentresExtrusionSourceId,
    layout: { visibility: "none" },
    paint: {
      "fill-extrusion-color": heightColorExpression(lineHeight),
      "fill-extrusion-opacity": 0.75,
      "fill-extrusion-height": lineHeight,
      "fill-extrusion-base": ["coalesce", ["get", "base"], 0],
    },
  });
}

export function upsertElevatedLineSources(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
) {
  const platformSource = map.getSource(platformEdgesExtrusionSourceId) as
    | maplibregl.GeoJSONSource
    | undefined;
  const trackSource = map.getSource(trackCentresExtrusionSourceId) as
    | maplibregl.GeoJSONSource
    | undefined;

  const platformData = elevatedLineSegments(platformEdges);
  const trackData = elevatedLineSegments(trackCentres);

  if (platformSource) {
    platformSource.setData(platformData);
  } else {
    map.addSource(platformEdgesExtrusionSourceId, {
      type: "geojson",
      data: platformData,
    });
  }

  if (trackSource) {
    trackSource.setData(trackData);
  } else {
    map.addSource(trackCentresExtrusionSourceId, {
      type: "geojson",
      data: trackData,
    });
  }
}

/** Switch camera + layer visibility for the global 2D/3D mode. */
export function applyMapDimensionMode(map: maplibregl.Map, is3d: boolean) {
  for (const layerId of flatOnlyLayerIds) {
    setLayerVisibility(map, layerId, !is3d);
  }
  for (const layerId of extrusionLayerIds) {
    setLayerVisibility(map, layerId, is3d);
  }

  setLayerVisibility(map, "parcels-fill", true);
  setLayerVisibility(map, "parcels-outline", true);

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
  map.once("moveend", () => {
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

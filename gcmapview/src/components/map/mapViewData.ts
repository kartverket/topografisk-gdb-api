import * as maplibregl from 'maplibre-gl';
import {
  bygningItemsInBboxUrl,
  bygningOmradeItemsInBboxUrl,
  bygningPosisjonItemsInBboxUrl,
  bygningSenterlinjeItemsInBboxUrl,
  buildingsItemsInBboxUrl,
  parcelsItemsInBboxUrl,
  platformEdgesItemsInBboxUrl,
  trackCentresItemsInBboxUrl,
  type OgcBbox
} from '../../api/geocomponentsApi';
import { addBaneSourcesAndLayers, normalizeBaneFeatureCollection, platformEdgesSourceId, trackCentresSourceId } from '../../map/baneLayers';
import { addBygningSourcesAndLayers, bygningSourceId, normalizeBygningFeatureCollection } from '../../map/bygningLayers';
import {
  addBygningPosisjonSourceAndLayer,
  bygningPosisjonSourceId,
  normalizeBygningPosisjonFeatureCollection
} from '../../map/bygningPosisjonLayers';
import {
  addBygningSenterlinjeSourceAndLayer,
  bygningSenterlinjeSourceId,
  normalizeBygningSenterlinjeFeatureCollection
} from '../../map/bygningSenterlinjeLayers';
import { addBygningOmradeSourceAndLayers, bygningOmradeSourceId } from '../../map/bygningOmradeLayers';
import {
  addExtrusionLayers,
  upsertElevatedSources
} from '../../map/mapDimension';
import { registerInspectableSourceData } from '../../map/featureInspect';
import type { Coordinates, Feature, FeatureCollection, Position } from '../../map/geojson';
import { type LayerVisibility, useLayerVisibilityStore } from '../../store/layerVisibilityStore';
import {
  buildingCentroidsFeatureCollection,
  normalizePolygonFeatureCollection
} from './mapViewGeometry';

export const emptyFeatureCollection: FeatureCollection = {
  type: 'FeatureCollection',
  features: []
};

export type VisibleFeatureCollections = {
  parcels: FeatureCollection;
  buildings: FeatureCollection;
  platformEdges: FeatureCollection;
  trackCentres: FeatureCollection;
  bygning: FeatureCollection;
  bygningOmrade: FeatureCollection;
  bygningSenterlinje: FeatureCollection;
  bygningPosisjon: FeatureCollection;
};

export const emptyVisibleFeatureCollections: VisibleFeatureCollections = {
  parcels: emptyFeatureCollection,
  buildings: emptyFeatureCollection,
  platformEdges: emptyFeatureCollection,
  trackCentres: emptyFeatureCollection,
  bygning: emptyFeatureCollection,
  bygningOmrade: emptyFeatureCollection,
  bygningSenterlinje: emptyFeatureCollection,
  bygningPosisjon: emptyFeatureCollection
};

export const MIN_VECTOR_ZOOM = 10;
export const MIN_BUILDING_ZOOM = 15;

const BUILDING_COLOR = '#000000';
const BUILDING_FILL_COLOR = '#a541c3';
const MISSING_HEIGHT_Z = -99_999;

export function isVectorZoom(map: maplibregl.Map) {
  return map.getZoom() > MIN_VECTOR_ZOOM;
}

export function isBuildingZoom(map: maplibregl.Map) {
  return map.getZoom() >= MIN_BUILDING_ZOOM;
}

function sanitizeMissingHeightPosition(position: Position): Position {
  return position[2] === MISSING_HEIGHT_Z ? ([position[0], position[1]] as Position) : position;
}

function sanitizeMissingHeightCoordinates(coordinates: Coordinates): Coordinates {
  if (typeof coordinates[0] === 'number') {
    return sanitizeMissingHeightPosition(coordinates as Position);
  }

  return (coordinates as Coordinates[]).map(child => sanitizeMissingHeightCoordinates(child));
}

function sanitizeMissingHeightFeature(feature: Feature): Feature {
  const geometry = feature.geometry;
  if (!geometry?.coordinates) {
    return feature;
  }

  return {
    ...feature,
    geometry: {
      ...geometry,
      coordinates: sanitizeMissingHeightCoordinates(geometry.coordinates)
    }
  };
}

function sanitizeMissingHeights(featureCollection: FeatureCollection): FeatureCollection {
  return {
    ...featureCollection,
    features: featureCollection.features.map(sanitizeMissingHeightFeature)
  };
}

function visibleCollectionPromise(visible: boolean, url: string) {
  return visible ? getFeatureCollection(url) : Promise.resolve(emptyFeatureCollection);
}

export function visibleOgcBbox(map: maplibregl.Map): OgcBbox {
  const container = map.getContainer();
  const width = container.clientWidth;
  const height = container.clientHeight;
  const screenPoints: Array<[number, number]> = [
    [0, 0],
    [width / 2, 0],
    [width, 0],
    [width, height / 2],
    [width, height],
    [width / 2, height],
    [0, height],
    [0, height / 2]
  ];
  const coordinates = screenPoints.map(([x, y]) => map.unproject([x, y]));
  const longitudes = coordinates.map(({ lng }) => lng);
  const latitudes = coordinates.map(({ lat }) => lat);

  return [
    Math.min(...longitudes),
    Math.max(-90, Math.min(...latitudes)),
    Math.max(...longitudes),
    Math.min(90, Math.max(...latitudes))
  ];
}

function idFromLocation(location: string | null) {
  if (!location) {
    return undefined;
  }

  return decodeURIComponent(location.split('/').filter(Boolean).at(-1) ?? '');
}

function prepareNativeSources(
  parcels: FeatureCollection,
  buildings: FeatureCollection,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningOmrade: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningPosisjon: FeatureCollection
) {
  const inspectableParcels = registerInspectableSourceData('parcels', parcels);
  const inspectableBuildings = registerInspectableSourceData('buildings', buildings);
  const inspectablePlatformEdges = registerInspectableSourceData(platformEdgesSourceId, platformEdges);
  const inspectableTrackCentres = registerInspectableSourceData(trackCentresSourceId, trackCentres);
  const inspectableBygning = registerInspectableSourceData(bygningSourceId, bygning);
  const inspectableBygningOmrade = registerInspectableSourceData(bygningOmradeSourceId, bygningOmrade);
  const inspectableBygningSenterlinje = registerInspectableSourceData(bygningSenterlinjeSourceId, bygningSenterlinje);
  const inspectableBygningPosisjon = registerInspectableSourceData(bygningPosisjonSourceId, bygningPosisjon);

  return {
    normalizedParcels: normalizePolygonFeatureCollection(inspectableParcels),
    normalizedBuildings: normalizePolygonFeatureCollection(inspectableBuildings),
    normalizedPlatformEdges: normalizeBaneFeatureCollection(inspectablePlatformEdges),
    normalizedTrackCentres: normalizeBaneFeatureCollection(inspectableTrackCentres),
    normalizedBygning: normalizeBygningFeatureCollection(inspectableBygning),
    normalizedBygningOmrade: normalizePolygonFeatureCollection(inspectableBygningOmrade),
    normalizedBygningSenterlinje: normalizeBygningSenterlinjeFeatureCollection(inspectableBygningSenterlinje),
    normalizedBygningPosisjon: normalizeBygningPosisjonFeatureCollection(inspectableBygningPosisjon),
    inspectableBygning,
    inspectablePlatformEdges,
    inspectableTrackCentres
  };
}

export function addNativeFeatureSourcesAndLayers(
  map: maplibregl.Map,
  parcels: FeatureCollection,
  buildings: FeatureCollection,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningOmrade: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningPosisjon: FeatureCollection,
  visibility: LayerVisibility,
  adjustElevatedHeights: boolean
) {
  const {
    normalizedParcels,
    normalizedBuildings,
    normalizedPlatformEdges,
    normalizedTrackCentres,
    normalizedBygning,
    normalizedBygningOmrade,
    normalizedBygningSenterlinje,
    normalizedBygningPosisjon,
    inspectableBygning,
    inspectablePlatformEdges,
    inspectableTrackCentres
  } = prepareNativeSources(
    parcels,
    buildings,
    platformEdges,
    trackCentres,
    bygning,
    bygningOmrade,
    bygningSenterlinje,
    bygningPosisjon
  );

  map.addSource('parcels', {
    type: 'geojson',
    data: normalizedParcels
  });
  map.addSource('buildings', {
    type: 'geojson',
    data: normalizedBuildings
  });
  map.addSource('building-centroids', {
    type: 'geojson',
    data: buildingCentroidsFeatureCollection(normalizedBuildings)
  });

  map.addLayer({
    id: 'building-centroids-circle',
    type: 'circle',
    source: 'building-centroids',
    paint: {
      'circle-color': BUILDING_COLOR,
      'circle-opacity': 0.8,
      'circle-radius': 3,
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1
    }
  });
  map.addLayer({
    id: 'parcels-fill',
    type: 'fill',
    source: 'parcels',
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: {
      'fill-color': '#ffc040',
      'fill-opacity': 0.32,
      'fill-outline-color': '#005cff'
    }
  });
  map.addLayer({
    id: 'parcels-outline',
    type: 'line',
    source: 'parcels',
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: {
      'line-color': '#ffc040',
      'line-opacity': 1,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 2, 14, 4]
    }
  });
  map.addLayer({
    id: 'buildings-fill',
    type: 'fill',
    source: 'buildings',
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: {
      'fill-color': BUILDING_FILL_COLOR,
      'fill-opacity': 0.55,
      'fill-outline-color': BUILDING_COLOR
    }
  });
  map.addLayer({
    id: 'buildings-outline',
    type: 'line',
    source: 'buildings',
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: {
      'line-color': BUILDING_COLOR,
      'line-opacity': 1,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 2, 14, 4]
    }
  });

  addBaneSourcesAndLayers(map, inspectablePlatformEdges, inspectableTrackCentres);
  addBygningSourcesAndLayers(map, inspectableBygning);
  addBygningOmradeSourceAndLayers(map, normalizedBygningOmrade);
  addBygningSenterlinjeSourceAndLayer(map, normalizedBygningSenterlinje);
  addBygningPosisjonSourceAndLayer(map, normalizedBygningPosisjon);
  addExtrusionLayers(map);
  upsertElevatedSources(
    map,
    normalizedPlatformEdges,
    normalizedTrackCentres,
    normalizedBygning,
    normalizedBygningSenterlinje,
    normalizedBygningOmrade,
    visibility,
    adjustElevatedHeights
  );
}

export async function getFeatureCollection(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return sanitizeMissingHeights((await response.json()) as FeatureCollection);
}

export async function getVisibleFeatureCollections(map: maplibregl.Map, visibility: LayerVisibility) {
  const bbox = visibleOgcBbox(map);
  const buildingZoomActive = isBuildingZoom(map);
  const [parcels, buildings, platformEdges, trackCentres, bygning, bygningOmrade, bygningSenterlinje, bygningPosisjon] =
    await Promise.all([
      visibleCollectionPromise(visibility.parcels, parcelsItemsInBboxUrl(bbox)),
      visibleCollectionPromise(visibility.buildings && buildingZoomActive, buildingsItemsInBboxUrl(bbox)),
      visibleCollectionPromise(visibility.platformEdges, platformEdgesItemsInBboxUrl(bbox)),
      visibleCollectionPromise(visibility.trackCentres, trackCentresItemsInBboxUrl(bbox)),
      visibleCollectionPromise(visibility.bygning && buildingZoomActive, bygningItemsInBboxUrl(bbox)),
      visibleCollectionPromise(visibility.bygningOmrade && buildingZoomActive, bygningOmradeItemsInBboxUrl(bbox)),
      visibleCollectionPromise(
        visibility.bygningSenterlinje && buildingZoomActive,
        bygningSenterlinjeItemsInBboxUrl(bbox)
      ),
      visibleCollectionPromise(visibility.bygningPosisjon && buildingZoomActive, bygningPosisjonItemsInBboxUrl(bbox))
    ]);

  return {
    bbox,
    parcels,
    buildings,
    platformEdges,
    trackCentres,
    bygning,
    bygningOmrade,
    bygningSenterlinje,
    bygningPosisjon
  };
}

export function layerVisibilityChanged(previous: LayerVisibility, current: LayerVisibility) {
  return (
    previous.parcels !== current.parcels ||
    previous.buildings !== current.buildings ||
    previous.platformEdges !== current.platformEdges ||
    previous.trackCentres !== current.trackCentres ||
    previous.bygning !== current.bygning ||
    previous.bygningOmrade !== current.bygningOmrade ||
    previous.bygningSenterlinje !== current.bygningSenterlinje ||
    previous.bygningPosisjon !== current.bygningPosisjon
  );
}

export async function createFeature(url: string, feature: unknown) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/geo+json'
    },
    body: JSON.stringify(feature)
  });

  if (!response.ok) {
    throw new Error(`Create failed with ${response.status}`);
  }

  const locationId = idFromLocation(response.headers.get('location'));
  if (locationId) {
    return locationId;
  }

  const body = (await response.text()).trim();
  if (!body) {
    return undefined;
  }

  try {
    const parsed = JSON.parse(body) as unknown;
    if (typeof parsed === 'string') {
      return parsed;
    }
    if (parsed && typeof parsed === 'object' && 'id' in parsed) {
      return String((parsed as { id: unknown }).id);
    }
  } catch {
    return body.replace(/^"|"$/g, '');
  }

  return undefined;
}

export async function deleteFeature(url: string) {
  const response = await fetch(url, { method: 'DELETE' });
  if (!response.ok && response.status !== 404) {
    throw new Error(`Delete failed with ${response.status}`);
  }
}

export async function upsertGeoJsonSource(map: maplibregl.Map, sourceId: string, data: FeatureCollection) {
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

export async function setNativeFeatureSources(
  map: maplibregl.Map,
  parcels: FeatureCollection,
  buildings: FeatureCollection,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningOmrade: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningPosisjon: FeatureCollection,
  visibility: LayerVisibility,
  adjustElevatedHeights: boolean
) {
  const {
    normalizedParcels,
    normalizedBuildings,
    normalizedPlatformEdges,
    normalizedTrackCentres,
    normalizedBygning,
    normalizedBygningOmrade,
    normalizedBygningSenterlinje,
    normalizedBygningPosisjon
  } = prepareNativeSources(
    parcels,
    buildings,
    platformEdges,
    trackCentres,
    bygning,
    bygningOmrade,
    bygningSenterlinje,
    bygningPosisjon
  );

  await Promise.all([
    upsertGeoJsonSource(map, 'parcels', normalizedParcels),
    upsertGeoJsonSource(map, 'buildings', normalizedBuildings),
    upsertGeoJsonSource(map, 'bane-platform-edges', normalizedPlatformEdges),
    upsertGeoJsonSource(map, 'bane-track-centres', normalizedTrackCentres),
    upsertGeoJsonSource(map, 'bygning-linework', normalizedBygning),
    upsertGeoJsonSource(map, bygningOmradeSourceId, normalizedBygningOmrade),
    upsertGeoJsonSource(map, bygningSenterlinjeSourceId, normalizedBygningSenterlinje),
    upsertGeoJsonSource(map, bygningPosisjonSourceId, normalizedBygningPosisjon)
  ]);

  updateElevatedFeatureSources(
    map,
    platformEdges,
    trackCentres,
    bygning,
    bygningSenterlinje,
    bygningOmrade,
    visibility,
    adjustElevatedHeights
  );
}

export function updateElevatedFeatureSources(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
  bygning: FeatureCollection,
  bygningSenterlinje: FeatureCollection,
  bygningOmrade: FeatureCollection,
  visibility: LayerVisibility,
  adjustElevatedHeights: boolean
) {
  const inspectablePlatformEdges = registerInspectableSourceData(platformEdgesSourceId, platformEdges);
  const inspectableTrackCentres = registerInspectableSourceData(trackCentresSourceId, trackCentres);
  const inspectableBygning = registerInspectableSourceData(bygningSourceId, bygning);
  const inspectableBygningOmrade = registerInspectableSourceData(bygningOmradeSourceId, bygningOmrade);
  const inspectableBygningSenterlinje = registerInspectableSourceData(bygningSenterlinjeSourceId, bygningSenterlinje);

  upsertElevatedSources(
    map,
    normalizeBaneFeatureCollection(inspectablePlatformEdges),
    normalizeBaneFeatureCollection(inspectableTrackCentres),
    normalizeBygningFeatureCollection(inspectableBygning),
    normalizeBygningSenterlinjeFeatureCollection(inspectableBygningSenterlinje),
    normalizePolygonFeatureCollection(inspectableBygningOmrade),
    visibility,
    adjustElevatedHeights
  );
}

export async function clearVectorSources(map: maplibregl.Map) {
  await setNativeFeatureSources(
    map,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    useLayerVisibilityStore.getState().visibility,
    false
  );
  await upsertGeoJsonSource(map, 'building-centroids', emptyFeatureCollection);
}

export function logNativeRenderingState(map: maplibregl.Map) {
  const state = {
    parcelsSourceLoaded: map.isSourceLoaded('parcels'),
    buildingsSourceLoaded: map.isSourceLoaded('buildings'),
    parcelSourceFeatures: map.querySourceFeatures('parcels').length,
    buildingSourceFeatures: map.querySourceFeatures('buildings').length,
    parcelRenderedFeatures: map.queryRenderedFeatures({
      layers: ['parcels-fill', 'parcels-outline']
    }).length,
    buildingRenderedFeatures: map.queryRenderedFeatures({
      layers: ['buildings-fill', 'buildings-outline']
    }).length
  };

  console.info('[gcmapview] native MapLibre rendering state', JSON.stringify(state));
  return state;
}
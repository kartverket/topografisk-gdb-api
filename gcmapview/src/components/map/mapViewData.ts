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
import {
  addBaneSourcesAndLayers,
  normalizeBaneFeatureCollection,
  platformEdgesSourceId,
  trackCentresSourceId
} from '../../map/baneLayers';
import {
  addBygningSourcesAndLayers,
  bygningSourceId,
  normalizeBygningFeatureCollection
} from '../../map/bygningLayers';
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
import { addExtrusionLayers, upsertElevatedSources } from '../../map/mapDimension';
import {
  filterableFeaturePropertyValue,
  registerInspectableSourceData,
  type ActiveFeatureFilter
} from '../../map/featureInspect';
import type { Coordinates, Feature, FeatureCollection, Position } from '../../map/geojson';
import { type LayerVisibility, useLayerVisibilityStore } from '../../store/layerVisibilityStore';
import { buildingCentroidsFeatureCollection, normalizePolygonFeatureCollection } from './mapViewGeometry';

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
const FEATURE_PAGE_LIMIT = 1000;
const MAX_FEATURE_PAGE_REQUESTS = 100;

const BUILDING_COLOR = '#ff0000';
const BUILDING_FILL_COLOR = '#9914d2';
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

export type VisibleFeatureCollectionKey = keyof VisibleFeatureCollections;

function visibleCollectionPromise(
  visible: boolean,
  url: string,
  onProgress?: (featureCollection: FeatureCollection) => Promise<void> | void
) {
  return visible ? getFeatureCollection(url, onProgress) : Promise.resolve(emptyFeatureCollection);
}

function normalizedFilterValue(value: string | undefined): string | undefined {
  if (!value) {
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed.toLowerCase() : undefined;
}

function filterFeatureCollectionByProperty(
  featureCollection: FeatureCollection,
  activeFeatureFilter?: ActiveFeatureFilter
): FeatureCollection {
  const normalizedFilterValueToMatch = normalizedFilterValue(activeFeatureFilter?.value);
  if (!activeFeatureFilter?.propertyKey || !normalizedFilterValueToMatch) {
    return featureCollection;
  }

  return {
    ...featureCollection,
    features: featureCollection.features.filter(feature => {
      const featureValue = filterableFeaturePropertyValue(
        (feature.properties ?? {}) as Record<string, unknown>,
        activeFeatureFilter.propertyKey
      );
      return normalizedFilterValue(featureValue) === normalizedFilterValueToMatch;
    })
  };
}

export function filterVisibleFeatureCollectionsByProperty(
  visibleFeatureCollections: VisibleFeatureCollections,
  activeFeatureFilter?: ActiveFeatureFilter
): VisibleFeatureCollections {
  if (!activeFeatureFilter) {
    return visibleFeatureCollections;
  }

  return {
    parcels: filterFeatureCollectionByProperty(visibleFeatureCollections.parcels, activeFeatureFilter),
    buildings: filterFeatureCollectionByProperty(visibleFeatureCollections.buildings, activeFeatureFilter),
    platformEdges: filterFeatureCollectionByProperty(visibleFeatureCollections.platformEdges, activeFeatureFilter),
    trackCentres: filterFeatureCollectionByProperty(visibleFeatureCollections.trackCentres, activeFeatureFilter),
    bygning: filterFeatureCollectionByProperty(visibleFeatureCollections.bygning, activeFeatureFilter),
    bygningOmrade: filterFeatureCollectionByProperty(visibleFeatureCollections.bygningOmrade, activeFeatureFilter),
    bygningSenterlinje: filterFeatureCollectionByProperty(
      visibleFeatureCollections.bygningSenterlinje,
      activeFeatureFilter
    ),
    bygningPosisjon: filterFeatureCollectionByProperty(visibleFeatureCollections.bygningPosisjon, activeFeatureFilter)
  };
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
  adjustElevatedHeights: boolean,
  renderElevatedSources: boolean
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
      'fill-opacity': 0.9,
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
    adjustElevatedHeights,
    renderElevatedSources
  );
}

export async function getFeatureCollection(
  url: string,
  onProgress?: (featureCollection: FeatureCollection) => Promise<void> | void
) {
  return getPagedFeatureCollection(url, onProgress);
}

type FeatureCollectionLink = {
  rel?: unknown;
  href?: unknown;
};

type FeatureCollectionPage = FeatureCollection & {
  links?: FeatureCollectionLink[];
};

function pagedFeatureCollectionUrl(url: string, offset = 0) {
  const nextUrl = new URL(url, window.location.origin);
  nextUrl.searchParams.set('limit', String(FEATURE_PAGE_LIMIT));
  if (offset > 0) {
    nextUrl.searchParams.set('offset', String(offset));
  } else {
    nextUrl.searchParams.delete('offset');
  }
  return nextUrl.toString();
}

function nextFeatureCollectionUrl(payload: FeatureCollectionPage) {
  const nextLink = payload.links?.find(link => link.rel === 'next' && typeof link.href === 'string');
  return typeof nextLink?.href === 'string' && nextLink.href ? nextLink.href : null;
}

function mergedFeatureCollection(current: FeatureCollection, nextPage: FeatureCollection) {
  if (current.features.length === 0) {
    return nextPage;
  }

  return {
    ...nextPage,
    features: [...current.features, ...nextPage.features]
  };
}

function featurePageSignature(featureCollection: FeatureCollection) {
  const firstId = featureCollection.features[0]?.id;
  const lastId = featureCollection.features.at(-1)?.id;
  return `${String(firstId ?? '')}:${String(lastId ?? '')}:${featureCollection.features.length}`;
}

async function getPagedFeatureCollection(
  url: string,
  onProgress?: (featureCollection: FeatureCollection) => Promise<void> | void
) {
  let aggregated = emptyFeatureCollection;
  let nextUrl: string | null = pagedFeatureCollectionUrl(url);
  let offset = 0;
  let requestCount = 0;
  let previousSignature: string | null = null;

  while (nextUrl !== null && requestCount < MAX_FEATURE_PAGE_REQUESTS) {
    requestCount += 1;

    const response = await fetch(nextUrl);
    if (!response.ok) {
      throw new Error(`Request failed with ${response.status}`);
    }

    const payload = (await response.json()) as FeatureCollectionPage;
    const page = sanitizeMissingHeights(payload);
    aggregated = mergedFeatureCollection(aggregated, page);
    await onProgress?.(aggregated);

    const linkedNextUrl = nextFeatureCollectionUrl(payload);
    if (linkedNextUrl) {
      nextUrl = linkedNextUrl;
      offset = aggregated.features.length;
      previousSignature = null;
      continue;
    }

    if (page.features.length < FEATURE_PAGE_LIMIT) {
      break;
    }

    const currentSignature = featurePageSignature(page);
    if (currentSignature === previousSignature) {
      break;
    }

    previousSignature = currentSignature;
    offset += page.features.length;
    nextUrl = pagedFeatureCollectionUrl(url, offset);
  }

  return aggregated;
}

export async function getVisibleFeatureCollections(
  map: maplibregl.Map,
  visibility: LayerVisibility,
  onProgress?: (collections: VisibleFeatureCollections, layerId: VisibleFeatureCollectionKey) => Promise<void> | void
) {
  const bbox = visibleOgcBbox(map);
  const buildingZoomActive = isBuildingZoom(map);

  let currentCollections: VisibleFeatureCollections = emptyVisibleFeatureCollections;
  async function updateCollection(layerId: VisibleFeatureCollectionKey, featureCollection: FeatureCollection) {
    currentCollections = {
      ...currentCollections,
      [layerId]: featureCollection
    };
    await onProgress?.(currentCollections, layerId);
  }

  const [parcels, buildings, platformEdges, trackCentres, bygning, bygningOmrade, bygningSenterlinje, bygningPosisjon] =
    await Promise.all([
      visibleCollectionPromise(visibility.parcels, parcelsItemsInBboxUrl(bbox), featureCollection =>
        updateCollection('parcels', featureCollection)
      ),
      visibleCollectionPromise(
        visibility.buildings && buildingZoomActive,
        buildingsItemsInBboxUrl(bbox),
        featureCollection => updateCollection('buildings', featureCollection)
      ),
      visibleCollectionPromise(visibility.platformEdges, platformEdgesItemsInBboxUrl(bbox), featureCollection =>
        updateCollection('platformEdges', featureCollection)
      ),
      visibleCollectionPromise(visibility.trackCentres, trackCentresItemsInBboxUrl(bbox), featureCollection =>
        updateCollection('trackCentres', featureCollection)
      ),
      visibleCollectionPromise(
        visibility.bygning && buildingZoomActive,
        bygningItemsInBboxUrl(bbox),
        featureCollection => updateCollection('bygning', featureCollection)
      ),
      visibleCollectionPromise(
        visibility.bygningOmrade && buildingZoomActive,
        bygningOmradeItemsInBboxUrl(bbox),
        featureCollection => updateCollection('bygningOmrade', featureCollection)
      ),
      visibleCollectionPromise(
        visibility.bygningSenterlinje && buildingZoomActive,
        bygningSenterlinjeItemsInBboxUrl(bbox),
        featureCollection => updateCollection('bygningSenterlinje', featureCollection)
      ),
      visibleCollectionPromise(
        visibility.bygningPosisjon && buildingZoomActive,
        bygningPosisjonItemsInBboxUrl(bbox),
        featureCollection => updateCollection('bygningPosisjon', featureCollection)
      )
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

export async function replaceFeature(url: string, feature: unknown) {
  const response = await fetch(url, {
    method: 'PUT',
    headers: {
      'content-type': 'application/geo+json'
    },
    body: JSON.stringify(feature)
  });

  if (!response.ok) {
    throw new Error(`Replace failed with ${response.status}`);
  }
}

export async function getFeature(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return sanitizeMissingHeightFeature((await response.json()) as Feature);
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

export async function setVisibleFeatureCollectionSource(
  map: maplibregl.Map,
  layerId: VisibleFeatureCollectionKey,
  featureCollection: FeatureCollection
) {
  switch (layerId) {
    case 'parcels':
      await upsertGeoJsonSource(map, 'parcels', normalizePolygonFeatureCollection(featureCollection));
      return;
    case 'buildings': {
      const normalizedBuildings = normalizePolygonFeatureCollection(featureCollection);
      await Promise.all([
        upsertGeoJsonSource(map, 'buildings', normalizedBuildings),
        upsertGeoJsonSource(map, 'building-centroids', buildingCentroidsFeatureCollection(normalizedBuildings))
      ]);
      return;
    }
    case 'platformEdges':
      await upsertGeoJsonSource(map, platformEdgesSourceId, normalizeBaneFeatureCollection(featureCollection));
      return;
    case 'trackCentres':
      await upsertGeoJsonSource(map, trackCentresSourceId, normalizeBaneFeatureCollection(featureCollection));
      return;
    case 'bygning':
      await upsertGeoJsonSource(map, bygningSourceId, normalizeBygningFeatureCollection(featureCollection));
      return;
    case 'bygningOmrade':
      await upsertGeoJsonSource(map, bygningOmradeSourceId, normalizePolygonFeatureCollection(featureCollection));
      return;
    case 'bygningSenterlinje':
      await upsertGeoJsonSource(
        map,
        bygningSenterlinjeSourceId,
        normalizeBygningSenterlinjeFeatureCollection(featureCollection)
      );
      return;
    case 'bygningPosisjon':
      await upsertGeoJsonSource(
        map,
        bygningPosisjonSourceId,
        normalizeBygningPosisjonFeatureCollection(featureCollection)
      );
      return;
  }
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
  adjustElevatedHeights: boolean,
  renderElevatedSources: boolean
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
    adjustElevatedHeights,
    renderElevatedSources
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
  adjustElevatedHeights: boolean,
  renderElevatedSources: boolean
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
    adjustElevatedHeights,
    renderElevatedSources
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
    false,
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

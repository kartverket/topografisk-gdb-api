import { gcapiRuntimeApiUrl, resolveApiBaseUrl } from './runtimeConfig';

export const gcapiApiBaseUrl = resolveApiBaseUrl(
  gcapiRuntimeApiUrl(),
  import.meta.env.GCAPI_API_URL,
  'GCAPI_API_URL',
  'http://localhost:8004'
);

export type CollectionId =
  | 'parcels'
  | 'buildings'
  | 'jernbaneplattformkant'
  | 'spormidt'
  | 'bygning'
  | 'bygning_omrade'
  | 'bygning_senterlinje'
  | 'bygning_posisjon';

export type CollectionMetadata = {
  id: CollectionId;
  storageCrs?: string;
  crs?: string[];
};

type CollectionRoute = {
  datasetId: string;
  collectionId: string;
};

const collectionRoutes: Record<CollectionId, CollectionRoute> = {
  parcels: { datasetId: 'cadastre', collectionId: 'parcels' },
  buildings: { datasetId: 'cadastre', collectionId: 'buildings' },
  jernbaneplattformkant: { datasetId: 'fkb_bane', collectionId: 'jernbaneplattformkant' },
  spormidt: { datasetId: 'fkb_bane', collectionId: 'spormidt' },
  bygning: { datasetId: 'bygning', collectionId: 'bygning' },
  bygning_omrade: { datasetId: 'bygning', collectionId: 'bygning_omrade' },
  bygning_senterlinje: { datasetId: 'bygning', collectionId: 'bygning_senterlinje' },
  bygning_posisjon: { datasetId: 'bygning', collectionId: 'bygning_posisjon' }
};

const collectionIds = Object.keys(collectionRoutes) as CollectionId[];

function isCollectionId(value: string): value is CollectionId {
  return collectionIds.includes(value as CollectionId);
}

function datasetOgcApiBaseUrl(datasetId: string) {
  return `${gcapiApiBaseUrl}/datasets/${datasetId}/ogc_api`;
}

function collectionBaseUrl(collectionId: CollectionId) {
  const route = collectionRoutes[collectionId];
  return `${datasetOgcApiBaseUrl(route.datasetId)}/collections/${route.collectionId}`;
}

function collectionItemsUrl(collectionId: CollectionId) {
  return `${collectionBaseUrl(collectionId)}/items?f=json&limit=10000`;
}

export function deleteCollectionItemsExecutionUrl(collectionId: CollectionId) {
  const route = collectionRoutes[collectionId];
  return `${datasetOgcApiBaseUrl(route.datasetId)}/processes/delete-collection-items/execution`;
}

export function collectionMetadataUrl(collectionId: CollectionId) {
  return `${collectionBaseUrl(collectionId)}?f=json`;
}

export function collectionItemUrl(collectionId: CollectionId, id: string | number, crs?: string) {
  return `${collectionBaseUrl(collectionId)}/items/${encodeURIComponent(String(id))}?f=json${crs ? `&crs=${encodeURIComponent(crs)}` : ''}`;
}

export const parcelsItemsUrl = collectionItemsUrl('parcels');
export const parcelsCreateUrl = `${collectionBaseUrl('parcels')}/items`;
export const buildingsItemsUrl = collectionItemsUrl('buildings');
export const buildingsCreateUrl = `${collectionBaseUrl('buildings')}/items`;
export const platformEdgesItemsUrl = collectionItemsUrl('jernbaneplattformkant');
export const trackCentresItemsUrl = collectionItemsUrl('spormidt');
export const bygningItemsUrl = collectionItemsUrl('bygning');
export const bygningOmradeItemsUrl = collectionItemsUrl('bygning_omrade');
export const bygningSenterlinjeItemsUrl = collectionItemsUrl('bygning_senterlinje');
export const bygningPosisjonItemsUrl = collectionItemsUrl('bygning_posisjon');

export type OgcBbox = [number, number, number, number];

function withBbox(url: string, bbox: OgcBbox) {
  return `${url}&bbox=${bbox.join(',')}`;
}

export function collectionItemsInBboxUrl(collectionId: CollectionId, bbox: OgcBbox) {
  return withBbox(collectionItemsUrl(collectionId), bbox);
}

export function parcelsItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('parcels', bbox);
}

export function buildingsItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('buildings', bbox);
}

export function platformEdgesItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('jernbaneplattformkant', bbox);
}

export function trackCentresItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('spormidt', bbox);
}

export function bygningItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('bygning', bbox);
}

export function bygningOmradeItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('bygning_omrade', bbox);
}

export function bygningSenterlinjeItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('bygning_senterlinje', bbox);
}

export function bygningPosisjonItemsInBboxUrl(bbox: OgcBbox) {
  return collectionItemsInBboxUrl('bygning_posisjon', bbox);
}

export function parcelItemUrl(id: string | number) {
  return `${collectionBaseUrl('parcels')}/items/${id}`;
}

export function buildingItemUrl(id: string | number) {
  return `${collectionBaseUrl('buildings')}/items/${id}`;
}

export async function getDatasetCollectionIds() {
  const response = await fetch(`${gcapiApiBaseUrl}/datasets`);
  if (!response.ok) {
    throw new Error(`Datasets request failed with ${response.status}`);
  }

  const body = (await response.json()) as {
    datasets?: Array<{
      id?: unknown;
      collections?: unknown;
    }>;
  };
  const availableCollectionIds = new Set<CollectionId>();
  const routeToLocal = new Map<string, CollectionId>(
    collectionIds.map(collectionId => {
      const route = collectionRoutes[collectionId];
      return [`${route.datasetId}.${route.collectionId}`, collectionId];
    })
  );

  for (const dataset of body.datasets ?? []) {
    const datasetId = typeof dataset.id === 'string' ? dataset.id : null;
    if (datasetId === null || !Array.isArray(dataset.collections)) {
      continue;
    }
    for (const collectionId of dataset.collections) {
      if (typeof collectionId !== 'string') {
        continue;
      }
      const localId = routeToLocal.get(`${datasetId}.${collectionId}`);
      if (localId && isCollectionId(localId)) {
        availableCollectionIds.add(localId);
      }
    }
  }

  return availableCollectionIds;
}

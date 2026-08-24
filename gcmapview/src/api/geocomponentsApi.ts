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

const collectionPublicIds: Record<CollectionId, string> = {
  parcels: 'cadastre.parcels',
  buildings: 'cadastre.buildings',
  jernbaneplattformkant: 'fkb_bane.jernbaneplattformkant',
  spormidt: 'fkb_bane.spormidt',
  bygning: 'bygning.bygning',
  bygning_omrade: 'bygning.bygning_omrade',
  bygning_senterlinje: 'bygning.bygning_senterlinje',
  bygning_posisjon: 'bygning.bygning_posisjon'
};

const collectionIds = Object.keys(collectionPublicIds) as CollectionId[];

type CollectionsResponse = {
  collections?: Array<{
    id?: string;
  }>;
};

function isCollectionId(value: string): value is CollectionId {
  return collectionIds.includes(value as CollectionId);
}

function collectionBaseUrl(collectionId: CollectionId) {
  return `${gcapiApiBaseUrl}/collections/${collectionPublicIds[collectionId]}`;
}

function collectionItemsUrl(collectionId: CollectionId) {
  return `${collectionBaseUrl(collectionId)}/items?f=json&limit=10000`;
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
  const response = await fetch(`${gcapiApiBaseUrl}/collections`);
  if (!response.ok) {
    throw new Error(`Collections request failed with ${response.status}`);
  }

  const body = (await response.json()) as CollectionsResponse;
  const availableCollectionIds = new Set<CollectionId>();
  const publicToLocal = new Map<string, CollectionId>(
    collectionIds.map(collectionId => [collectionPublicIds[collectionId], collectionId])
  );

  for (const collection of body.collections ?? []) {
    const publicId = collection.id;
    if (typeof publicId !== 'string') {
      continue;
    }
    const localId = publicToLocal.get(publicId);
    if (localId && isCollectionId(localId)) {
      availableCollectionIds.add(localId);
    }
  }

  return availableCollectionIds;
}

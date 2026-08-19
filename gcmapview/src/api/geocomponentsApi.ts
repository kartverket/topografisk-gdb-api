import { geocomponentsRuntimeApiUrl, resolveApiBaseUrl } from './runtimeConfig';

export const geocomponentsApiBaseUrl = resolveApiBaseUrl(
  geocomponentsRuntimeApiUrl(),
  import.meta.env.GEOCOMPONENTS_API_URL,
  'GEOCOMPONENTS_API_URL',
  'http://localhost:8000'
);

const cadastreApiUrl = `${geocomponentsApiBaseUrl}/datasets/cadastre/ogc_api`;
const fkbBaneApiUrl = `${geocomponentsApiBaseUrl}/datasets/fkb_bane/ogc_api`;
const bygningApiUrl = `${geocomponentsApiBaseUrl}/datasets/bygning/ogc_api`;

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

const collectionApiUrls: Record<CollectionId, string> = {
  parcels: cadastreApiUrl,
  buildings: cadastreApiUrl,
  jernbaneplattformkant: fkbBaneApiUrl,
  spormidt: fkbBaneApiUrl,
  bygning: bygningApiUrl,
  bygning_omrade: bygningApiUrl,
  bygning_senterlinje: bygningApiUrl,
  bygning_posisjon: bygningApiUrl
};

const collectionIds = Object.keys(collectionApiUrls) as CollectionId[];

type DatasetIndexResponse = {
  datasets?: Array<{
    collections?: string[];
  }>;
};

function isCollectionId(value: string): value is CollectionId {
  return collectionIds.includes(value as CollectionId);
}

function collectionBaseUrl(collectionId: CollectionId) {
  return `${collectionApiUrls[collectionId]}/collections/${collectionId}`;
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
export const parcelsCreateUrl = `${cadastreApiUrl}/collections/parcels/items`;
export const buildingsItemsUrl = collectionItemsUrl('buildings');
export const buildingsCreateUrl = `${cadastreApiUrl}/collections/buildings/items`;
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

export function parcelsItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(parcelsItemsUrl, bbox);
}

export function buildingsItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(buildingsItemsUrl, bbox);
}

export function platformEdgesItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(platformEdgesItemsUrl, bbox);
}

export function trackCentresItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(trackCentresItemsUrl, bbox);
}

export function bygningItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(bygningItemsUrl, bbox);
}

export function bygningOmradeItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(bygningOmradeItemsUrl, bbox);
}

export function bygningSenterlinjeItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(bygningSenterlinjeItemsUrl, bbox);
}

export function bygningPosisjonItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(bygningPosisjonItemsUrl, bbox);
}

export function parcelItemUrl(id: string | number) {
  return `${cadastreApiUrl}/collections/parcels/items/${id}`;
}

export function buildingItemUrl(id: string | number) {
  return `${cadastreApiUrl}/collections/buildings/items/${id}`;
}

export async function getDatasetCollectionIds() {
  const response = await fetch(`${geocomponentsApiBaseUrl}/datasets`);
  if (!response.ok) {
    throw new Error(`Dataset index request failed with ${response.status}`);
  }

  const body = (await response.json()) as DatasetIndexResponse;
  const availableCollectionIds = new Set<CollectionId>();

  for (const dataset of body.datasets ?? []) {
    for (const collectionId of dataset.collections ?? []) {
      if (isCollectionId(collectionId)) {
        availableCollectionIds.add(collectionId);
      }
    }
  }

  return availableCollectionIds;
}

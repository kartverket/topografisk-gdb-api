const defaultApiBaseUrl = '/geocomponents-api';

export const geocomponentsApiBaseUrl = (import.meta.env.VITE_GEOCOMPONENTS_API_URL ?? defaultApiBaseUrl).replace(
  /\/$/,
  ''
);

const cadastreApiUrl = `${geocomponentsApiBaseUrl}/datasets/cadastre/ogc_api`;
const baneApiUrl = `${geocomponentsApiBaseUrl}/datasets/bane/ogc_api`;
const bygningApiUrl = `${geocomponentsApiBaseUrl}/datasets/bygning/ogc_api`;

export const parcelsItemsUrl = `${cadastreApiUrl}/collections/parcels/items?f=json&limit=10000`;
export const parcelsCreateUrl = `${cadastreApiUrl}/collections/parcels/items`;
export const buildingsItemsUrl = `${cadastreApiUrl}/collections/buildings/items?f=json&limit=10000`;
export const buildingsCreateUrl = `${cadastreApiUrl}/collections/buildings/items`;
export const platformEdgesItemsUrl = `${baneApiUrl}/collections/jernbaneplattformkant/items?f=json&limit=10000`;
export const trackCentresItemsUrl = `${baneApiUrl}/collections/spormidt/items?f=json&limit=10000`;
export const bygningItemsUrl = `${bygningApiUrl}/collections/bygning/items?f=json&limit=10000`;
export const bygningOmradeItemsUrl = `${bygningApiUrl}/collections/bygning_omrade/items?f=json&limit=10000`;

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

export function parcelItemUrl(id: string | number) {
  return `${cadastreApiUrl}/collections/parcels/items/${id}`;
}

export function buildingItemUrl(id: string | number) {
  return `${cadastreApiUrl}/collections/buildings/items/${id}`;
}

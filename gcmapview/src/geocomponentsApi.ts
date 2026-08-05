const defaultApiBaseUrl = '/geocomponents-api'

export const geocomponentsApiBaseUrl = (
  import.meta.env.VITE_GEOCOMPONENTS_API_URL ?? defaultApiBaseUrl
).replace(/\/$/, '')

const cadastreApiUrl = `${geocomponentsApiBaseUrl}/datasets/cadastre/ogc_api`

export const parcelsItemsUrl = `${cadastreApiUrl}/collections/parcels/items?f=json&limit=1000`
export const parcelsCreateUrl = `${cadastreApiUrl}/collections/parcels/items`
export const buildingsItemsUrl = `${cadastreApiUrl}/collections/buildings/items?f=json&limit=1000`
export const buildingsCreateUrl = `${cadastreApiUrl}/collections/buildings/items`

export type OgcBbox = [number, number, number, number]

function withBbox(url: string, bbox: OgcBbox) {
  return `${url}&bbox=${bbox.join(',')}`
}

export function parcelsItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(parcelsItemsUrl, bbox)
}

export function buildingsItemsInBboxUrl(bbox: OgcBbox) {
  return withBbox(buildingsItemsUrl, bbox)
}

export function parcelItemUrl(id: string | number) {
  return `${cadastreApiUrl}/collections/parcels/items/${id}`
}

export function buildingItemUrl(id: string | number) {
  return `${cadastreApiUrl}/collections/buildings/items/${id}`
}

import * as maplibregl from 'maplibre-gl'
import proj4 from 'proj4'
import type { FeatureCollection, Position } from './geojson'
import { heightColorExpression, maxCoordinateHeight } from './map3d'

export const platformEdgesSourceId = 'bane-platform-edges'
export const trackCentresSourceId = 'bane-track-centres'

export const platformEdgesLayerId = 'bane-platform-edges-line'
export const trackCentresLayerId = 'bane-track-centres-line'

// EPSG:5973 is ETRS89 / UTM zone 33N with NN2000 height. MapLibre maps use
// WGS84 horizontally; Z is preserved and also copied to properties.height for
// shared 2D/3D colouring.
proj4.defs(
  'EPSG:5973',
  '+proj=utm +zone=33 +ellps=GRS80 +units=m +no_defs +type=crs',
)

function toWgs84(position: Position): Position {
  const [longitude, latitude] = proj4('EPSG:5973', 'EPSG:4326', [
    position[0],
    position[1],
  ])
  return [longitude, latitude, ...position.slice(2)]
}

export function wgs84BboxToBaneBbox(
  bbox: [number, number, number, number],
): [number, number, number, number] {
  const [minLongitude, minLatitude, maxLongitude, maxLatitude] = bbox
  const corners = [
    [minLongitude, minLatitude],
    [minLongitude, maxLatitude],
    [maxLongitude, minLatitude],
    [maxLongitude, maxLatitude],
  ].map((position) => proj4('EPSG:4326', 'EPSG:5973', position))
  const eastings = corners.map(([easting]) => easting)
  const northings = corners.map(([, northing]) => northing)
  return [
    Math.min(...eastings),
    Math.min(...northings),
    Math.max(...eastings),
    Math.max(...northings),
  ]
}

export function normalizeBaneFeatureCollection(
  featureCollection: FeatureCollection,
): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map((feature) => {
      if (
        feature.geometry?.type !== 'LineString' ||
        !Array.isArray(feature.geometry.coordinates)
      ) {
        return feature
      }
      const coordinates = (feature.geometry.coordinates as Position[]).map(
        toWgs84,
      )
      return {
        ...feature,
        properties: {
          ...(feature.properties ?? {}),
          height: maxCoordinateHeight(coordinates),
        },
        geometry: {
          type: 'LineString',
          coordinates,
        },
      }
    }),
  }
}

export function addBaneSourcesAndLayers(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
) {
  map.addSource(platformEdgesSourceId, {
    type: 'geojson',
    data: normalizeBaneFeatureCollection(platformEdges),
  })
  map.addSource(trackCentresSourceId, {
    type: 'geojson',
    data: normalizeBaneFeatureCollection(trackCentres),
  })
  map.addLayer({
    id: platformEdgesLayerId,
    type: 'line',
    source: platformEdgesSourceId,
    paint: {
      'line-color': '#000000',
      'line-opacity': 0.9,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 14, 4],
    },
  })
  map.addLayer({
    id: trackCentresLayerId,
    type: 'line',
    source: trackCentresSourceId,
    paint: {
      'line-color': heightColorExpression(),
      'line-opacity': 0.95,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 14, 5],
    },
  })
}

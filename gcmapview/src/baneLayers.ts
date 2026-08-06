import * as maplibregl from 'maplibre-gl';
import proj4 from 'proj4';
import type { FeatureCollection, Position } from './geojson';

export const platformEdgesSourceId = 'bane-platform-edges';
export const trackCentresSourceId = 'bane-track-centres';

export const platformEdgesLayerId = 'bane-platform-edges-line';
export const trackCentresLayerId = 'bane-track-centres-line';

// EPSG:5973 is ETRS89 / UTM zone 33N with NN2000 height. MapLibre maps use
// WGS84 horizontally; Z is preserved for 3D extrusion when that mode is on.
proj4.defs('EPSG:5973', '+proj=utm +zone=33 +ellps=GRS80 +units=m +no_defs +type=crs');

function toWgs84(position: Position): Position {
  const [longitude, latitude] = proj4('EPSG:5973', 'EPSG:4326', [position[0], position[1]]);
  return [longitude, latitude, ...position.slice(2)];
}

export function wgs84BboxToBaneBbox(bbox: [number, number, number, number]): [number, number, number, number] {
  const [minLongitude, minLatitude, maxLongitude, maxLatitude] = bbox;
  const corners = [
    [minLongitude, minLatitude],
    [minLongitude, maxLatitude],
    [maxLongitude, minLatitude],
    [maxLongitude, maxLatitude]
  ].map(position => proj4('EPSG:4326', 'EPSG:5973', position));
  const eastings = corners.map(([easting]) => easting);
  const northings = corners.map(([, northing]) => northing);
  return [Math.min(...eastings), Math.min(...northings), Math.max(...eastings), Math.max(...northings)];
}

export function normalizeBaneFeatureCollection(featureCollection: FeatureCollection): FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: featureCollection.features.map(feature => {
      if (feature.geometry?.type !== 'LineString' || !Array.isArray(feature.geometry.coordinates)) {
        return feature;
      }
      return {
        ...feature,
        geometry: {
          type: 'LineString',
          coordinates: (feature.geometry.coordinates as Position[]).map(toWgs84)
        }
      };
    })
  };
}

export function addBaneSourcesAndLayers(
  map: maplibregl.Map,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection
) {
  map.addSource(platformEdgesSourceId, {
    type: 'geojson',
    data: normalizeBaneFeatureCollection(platformEdges)
  });
  map.addSource(trackCentresSourceId, {
    type: 'geojson',
    data: normalizeBaneFeatureCollection(trackCentres)
  });
  map.addLayer({
    id: platformEdgesLayerId,
    type: 'line',
    source: platformEdgesSourceId,
    paint: {
      'line-color': '#e11d48',
      'line-opacity': 0.9,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 14, 4]
    }
  });
  map.addLayer({
    id: trackCentresLayerId,
    type: 'line',
    source: trackCentresSourceId,
    paint: {
      'line-color': '#7c3aed',
      'line-opacity': 0.95,
      'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 14, 5]
    }
  });
}

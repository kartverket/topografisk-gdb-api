import * as maplibregl from 'maplibre-gl';
import type { Feature, FeatureCollection, Position } from '../../map/geojson';
import type { LayerVisibility } from '../../store/layerVisibilityStore';
import type { VisibleFeatureCollections } from './mapViewData';
import { featureCentroid, featureRectangle } from './mapViewGeometry';

export const OBJTYPE_LABEL_SOURCE_ID = 'objtype-label-source';
export const OBJTYPE_LABEL_LAYER_ID = 'objtype-label-layer';
export const OBJTYPE_LABEL_MIN_ZOOM = 18;

const OBJTYPE_LABEL_LIMIT = 40;
const OBJTYPE_LABEL_FONT_SIZE = 20;
const OBJTYPE_LABEL_PADDING_PX = 8;
const importedLayerIds = [
  'platformEdges',
  'trackCentres',
  'bygning',
  'bygningOmrade',
  'bygningSenterlinje',
  'bygningPosisjon'
] as const;

type LabelAnchor = {
  position: Position;
  angle: number;
};

type LabelBounds = {
  left: number;
  top: number;
  right: number;
  bottom: number;
};

function objtypeLabelFeatureCollection(
  map: maplibregl.Map,
  visibleFeatureCollections: VisibleFeatureCollections,
  visibility: LayerVisibility
): FeatureCollection {
  const placedBounds: LabelBounds[] = [];

  const features = importedLayerIds.flatMap(layerId => {
    if (!visibility[layerId]) {
      return [];
    }

    return visibleFeatureCollections[layerId].features.flatMap(feature => {
      const objtype = feature.properties?.objtype;
      const label = typeof objtype === 'string' && objtype.trim() ? objtype.trim() : String(layerId);
      const anchor = chooseLabelAnchor(map, feature, label, placedBounds);
      if (!anchor) {
        return [];
      }

      placedBounds.push(labelBounds(map, anchor, label));

      return [
        {
          type: 'Feature' as const,
          geometry: {
            type: 'Point' as const,
            coordinates: anchor.position
          },
          properties: {
            label,
            angle: anchor.angle
          }
        }
      ];
    });
  });

  return {
    type: 'FeatureCollection',
    features: features.slice(0, OBJTYPE_LABEL_LIMIT)
  };
}

function lineCoordinateSets(feature: Feature): Position[][] {
  const geometry = feature.geometry;
  if (!geometry?.coordinates || !Array.isArray(geometry.coordinates)) {
    return [];
  }

  if (geometry.type === 'LineString') {
    return [geometry.coordinates as Position[]];
  }

  if (geometry.type === 'MultiLineString') {
    return geometry.coordinates as Position[][];
  }

  return [];
}

function segmentMetrics(start: Position, end: Position) {
  const averageLatitudeRadians = (((start[1] + end[1]) / 2) * Math.PI) / 180;
  const longitudeScale = Math.cos(averageLatitudeRadians);
  const deltaLongitude = (end[0] - start[0]) * longitudeScale;
  const deltaLatitude = end[1] - start[1];

  return {
    length: Math.hypot(deltaLongitude, deltaLatitude),
    angle: (Math.atan2(deltaLatitude, deltaLongitude) * 180) / Math.PI
  };
}

function uprightTextAngle(rawAngle: number) {
  const clockwiseAngle = -rawAngle;

  if (clockwiseAngle > 90) {
    return clockwiseAngle - 180;
  }

  if (clockwiseAngle < -90) {
    return clockwiseAngle + 180;
  }

  return clockwiseAngle;
}

function lineLabelAnchor(feature: Feature, fraction = 0.5): LabelAnchor | undefined {
  const lineSets = lineCoordinateSets(feature);
  if (lineSets.length === 0) {
    return undefined;
  }

  const segments = lineSets.flatMap(coordinates =>
    coordinates.slice(0, -1).flatMap((start, index) => {
      const end = coordinates[index + 1];
      if (!end) {
        return [];
      }

      const { length, angle } = segmentMetrics(start, end);
      if (length === 0) {
        return [];
      }

      return [{ start, end, length, angle: uprightTextAngle(angle) }];
    })
  );

  if (segments.length === 0) {
    const centroid = featureCentroid(feature);
    return centroid ? { position: centroid, angle: 0 } : undefined;
  }

  const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0);
  const targetLength = totalLength * Math.max(0, Math.min(1, fraction));
  let traversedLength = 0;

  for (const segment of segments) {
    if (traversedLength + segment.length >= targetLength) {
      const remainingLength = targetLength - traversedLength;
      const ratio = segment.length === 0 ? 0 : remainingLength / segment.length;

      return {
        position: [
          segment.start[0] + (segment.end[0] - segment.start[0]) * ratio,
          segment.start[1] + (segment.end[1] - segment.start[1]) * ratio
        ] as Position,
        angle: segment.angle
      };
    }

    traversedLength += segment.length;
  }

  const lastSegment = segments[segments.length - 1];
  return {
    position: lastSegment.end,
    angle: lastSegment.angle
  };
}

function featureLabelAnchors(feature: Feature): LabelAnchor[] {
  const lineFractions = [0.5, 0.35, 0.65, 0.2, 0.8];
  const lineAnchors = lineFractions.flatMap(fraction => {
    const anchor = lineLabelAnchor(feature, fraction);
    return anchor ? [anchor] : [];
  });
  if (lineAnchors.length > 0) {
    return lineAnchors;
  }

  const rectangle = featureRectangle(feature);
  const centroid = featureCentroid(feature);
  if (!rectangle || !centroid) {
    return centroid ? [{ position: centroid, angle: 0 }] : [];
  }

  return [
    { position: centroid, angle: 0 },
    {
      position: [centroid[0], rectangle.south + (rectangle.north - rectangle.south) * 0.7] as Position,
      angle: 0
    },
    {
      position: [centroid[0], rectangle.south + (rectangle.north - rectangle.south) * 0.3] as Position,
      angle: 0
    },
    {
      position: [rectangle.west + (rectangle.east - rectangle.west) * 0.35, centroid[1]] as Position,
      angle: 0
    },
    {
      position: [rectangle.west + (rectangle.east - rectangle.west) * 0.65, centroid[1]] as Position,
      angle: 0
    }
  ];
}

function labelBounds(map: maplibregl.Map, anchor: LabelAnchor, label: string): LabelBounds {
  const projected = map.project([anchor.position[0], anchor.position[1]]);
  const approximateWidth = label.length * OBJTYPE_LABEL_FONT_SIZE * 0.55 + OBJTYPE_LABEL_PADDING_PX * 2;
  const approximateHeight = OBJTYPE_LABEL_FONT_SIZE * 1.3 + OBJTYPE_LABEL_PADDING_PX * 2;
  const radius = Math.hypot(approximateWidth / 2, approximateHeight / 2);

  return {
    left: projected.x - radius,
    top: projected.y - radius,
    right: projected.x + radius,
    bottom: projected.y + radius
  };
}

function boundsOverlap(a: LabelBounds, b: LabelBounds) {
  return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
}

function chooseLabelAnchor(
  map: maplibregl.Map,
  feature: Feature,
  label: string,
  placedBounds: LabelBounds[]
): LabelAnchor | undefined {
  const candidates = featureLabelAnchors(feature);

  for (const candidate of candidates) {
    const candidateBounds = labelBounds(map, candidate, label);
    if (!placedBounds.some(bounds => boundsOverlap(bounds, candidateBounds))) {
      return candidate;
    }
  }

  return candidates[0];
}

export function upsertObjtypeLabelLayer(
  map: maplibregl.Map,
  visibleFeatureCollections: VisibleFeatureCollections,
  visibility: LayerVisibility
) {
  const data = objtypeLabelFeatureCollection(map, visibleFeatureCollections, visibility);
  const source = map.getSource(OBJTYPE_LABEL_SOURCE_ID) as maplibregl.GeoJSONSource | undefined;

  if (source) {
    source.setData(data);
  } else {
    map.addSource(OBJTYPE_LABEL_SOURCE_ID, {
      type: 'geojson',
      data
    });
  }

  if (!map.getLayer(OBJTYPE_LABEL_LAYER_ID)) {
    map.addLayer({
      id: OBJTYPE_LABEL_LAYER_ID,
      type: 'symbol',
      source: OBJTYPE_LABEL_SOURCE_ID,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'label'],
        'text-font': ['Roboto Variable'],
        'text-size': OBJTYPE_LABEL_FONT_SIZE,
        'text-anchor': 'center',
        'text-rotation-alignment': 'map',
        'text-rotate': ['coalesce', ['get', 'angle'], 0],
        'text-allow-overlap': false,
        'text-ignore-placement': false
      },
      paint: {
        'text-color': '#005cff',
        'text-halo-color': '#ffffff',
        'text-halo-width': 1.8
      }
    });
  }
}

export function applyObjtypeLabelVisibility(map: maplibregl.Map, visible: boolean) {
  if (!map.getLayer(OBJTYPE_LABEL_LAYER_ID)) {
    return;
  }

  map.setLayoutProperty(OBJTYPE_LABEL_LAYER_ID, 'visibility', visible ? 'visible' : 'none');
}

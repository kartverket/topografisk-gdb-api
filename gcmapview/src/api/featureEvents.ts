import proj4 from 'proj4';
import { featureEventsRuntimeUrl } from './runtimeConfig';
import type { OgcBbox } from './geocomponentsApi';

const DISPLAY_CRS = 'EPSG:4326';
const CRS_DEFINITIONS = {
  'EPSG:5972': '+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs',
  'EPSG:5973': '+proj=utm +zone=33 +ellps=GRS80 +units=m +no_defs'
};

for (const [code, definition] of Object.entries(CRS_DEFINITIONS)) {
  proj4.defs(code, definition);
}

export type FeatureChangeEvent = {
  id: string;
  type: 'features.changed';
  dataset: string;
  maplayer: string;
  localids: string[];
  operations: string[];
  bbox: [number, number, number, number] | null;
  crs: string;
  occurred_at: string;
};

type FeatureChangeSubscriptionOptions = {
  onOpen?: () => void;
  onError?: () => void;
};

function featureEventsUrl() {
  const runtimeUrl = featureEventsRuntimeUrl();
  if (typeof runtimeUrl === 'string' && runtimeUrl.trim()) {
    return runtimeUrl;
  }
  if (import.meta.env.DEV) {
    return import.meta.env.VITE_FEATURE_EVENTS_URL ?? 'http://localhost:8080/feature-events';
  }
  throw new Error('Feature event subscription URL must be configured');
}

function parseFeatureChangeEvent(data: string): FeatureChangeEvent | null {
  try {
    const value = JSON.parse(data) as Partial<FeatureChangeEvent>;
    if (
      value.type !== 'features.changed' ||
      typeof value.id !== 'string' ||
      typeof value.dataset !== 'string' ||
      typeof value.maplayer !== 'string' ||
      !Array.isArray(value.localids) ||
      !Array.isArray(value.operations)
    ) {
      return null;
    }
    return value as FeatureChangeEvent;
  } catch {
    return null;
  }
}

function eventCrsCode(crs: string) {
  const epsgCode = crs.match(/EPSG(?:\/0\/|:)(\d+)$/i)?.[1];
  return epsgCode ? `EPSG:${epsgCode}` : null;
}

export function featureChangeIntersectsBbox(event: FeatureChangeEvent, viewport: OgcBbox) {
  if (event.bbox === null) {
    return true;
  }
  const sourceCrs = eventCrsCode(event.crs);
  if (sourceCrs === null) {
    return true;
  }

  try {
    const [minX, minY, maxX, maxY] = event.bbox;
    const corners = [
      [minX, minY],
      [minX, maxY],
      [maxX, minY],
      [maxX, maxY]
    ].map(coordinate => proj4(sourceCrs, DISPLAY_CRS, coordinate));
    const eventBbox: OgcBbox = [
      Math.min(...corners.map(([longitude]) => longitude)),
      Math.min(...corners.map(([, latitude]) => latitude)),
      Math.max(...corners.map(([longitude]) => longitude)),
      Math.max(...corners.map(([, latitude]) => latitude))
    ];
    return !(
      eventBbox[2] < viewport[0] ||
      eventBbox[0] > viewport[2] ||
      eventBbox[3] < viewport[1] ||
      eventBbox[1] > viewport[3]
    );
  } catch {
    return true;
  }
}

export function subscribeToFeatureChanges(
  onChange: (event: FeatureChangeEvent) => void,
  options: FeatureChangeSubscriptionOptions = {}
) {
  const eventSource = new EventSource(featureEventsUrl());
  eventSource.onopen = () => options.onOpen?.();
  eventSource.onmessage = message => {
    const event = parseFeatureChangeEvent(message.data);
    if (event) {
      onChange(event);
    }
  };
  eventSource.onerror = () => {
    options.onError?.();
    console.warn('[gcmapview] Feature event subscription interrupted; reconnecting');
  };
  return () => eventSource.close();
}

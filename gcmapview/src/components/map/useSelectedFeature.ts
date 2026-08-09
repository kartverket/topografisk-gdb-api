import { useEffect, useRef, useState, type RefObject } from 'react';
import * as maplibregl from 'maplibre-gl';
import { collectionItemUrl, collectionMetadataUrl, type CollectionId } from '../../api/geocomponentsApi';
import { FLOOR_HEIGHT_M } from '../../map/map3d';
import { type InspectedFeature } from '../../map/featureInspect';
import type { Coordinates, Feature, Position } from '../../map/geojson';
import { sourcePositions } from './mapViewGeometry';

const MISSING_HEIGHT_Z = -99_999;

type HoverOverlayTransform = {
  coordinatePoint?: (coord: maplibregl.MercatorCoordinate, elevation?: number, pixelMatrix?: unknown) => maplibregl.Point;
  _pixelMatrix3D?: unknown;
};

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

function featureSelectionKey(feature: Pick<InspectedFeature, 'collectionId' | 'featureId' | 'layerId'>) {
  return `${feature.collectionId ?? 'unknown'}:${String(feature.featureId ?? 'missing')}:${feature.layerId}`;
}

function displayCoordinateSystemName(crs: string) {
  const epsgMatch = crs.match(/\/EPSG\/0\/(\d+)$/i);
  if (epsgMatch) {
    return `EPSG:${epsgMatch[1]}`;
  }

  const crs84Match = crs.match(/\/OGC\/1\.3\/(CRS84)$/i);
  if (crs84Match) {
    return crs84Match[1];
  }

  return crs;
}

function numericFeatureProperty(properties: Record<string, unknown>, propertyName: string): number | undefined {
  const value = properties[propertyName];
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function publicFeatureProperties(feature: Feature): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(feature.properties ?? {}).filter(([key]) => !key.startsWith('__gcmapview'))
  );
}

function adjustedHoverAltitude(height: number | undefined, zOffset = 0): number {
  if (typeof height !== 'number' || !Number.isFinite(height) || height <= 0) {
    return 0;
  }

  return Math.max(0, height - zOffset);
}

function hoveredPositionAltitudeMeters(feature: InspectedFeature, positionIndex: number, is3d: boolean): number {
  if (!is3d) {
    return 0;
  }

  const zOffset = numericFeatureProperty(feature.properties, 'zOffset') ?? 0;
  const displayedZ = feature.positions[positionIndex]?.[2];
  const mapZ = feature.mapPositions[positionIndex]?.[2];
  const floors = numericFeatureProperty(feature.properties, 'floors');
  const calculatedHeight =
    numericFeatureProperty(feature.properties, 'elevation') ??
    numericFeatureProperty(feature.properties, 'height') ??
    (typeof floors === 'number' && floors > 0 ? floors * FLOOR_HEIGHT_M : undefined) ??
    numericFeatureProperty(feature.properties, 'base');

  return (
    adjustedHoverAltitude(
      typeof displayedZ === 'number' && Number.isFinite(displayedZ) ? displayedZ : undefined,
      zOffset
    ) ||
    adjustedHoverAltitude(typeof mapZ === 'number' && Number.isFinite(mapZ) ? mapZ : undefined, zOffset) ||
    adjustedHoverAltitude(calculatedHeight, zOffset)
  );
}

function projectHoverOverlayPoint(map: maplibregl.Map, lngLat: maplibregl.LngLat, altitudeMeters: number): maplibregl.Point {
  if (altitudeMeters <= 0) {
    return map.project(lngLat);
  }

  const transform = (map as unknown as { _camera?: { transform?: HoverOverlayTransform } })._camera?.transform;
  const pixelMatrix3D = transform?._pixelMatrix3D;

  if (!transform?.coordinatePoint || !pixelMatrix3D) {
    return map.project(lngLat);
  }

  return transform.coordinatePoint(maplibregl.MercatorCoordinate.fromLngLat(lngLat), altitudeMeters, pixelMatrix3D);
}

async function getFeature(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return sanitizeMissingHeightFeature((await response.json()) as Feature);
}

type UseSelectedFeatureOptions = {
  mapRef: RefObject<maplibregl.Map | null>;
  is3d: boolean;
};

export function useSelectedFeature({ mapRef, is3d }: UseSelectedFeatureOptions) {
  const [selectedFeature, setSelectedFeature] = useState<InspectedFeature>();
  const [hoveredPositionIndex, setHoveredPositionIndex] = useState<number>();
  const collectionStorageCrsRef = useRef(new Map<CollectionId, string>());
  const hoveredPositionOverlayRef = useRef<HTMLDivElement | undefined>(undefined);

  useEffect(() => {
    if (!selectedFeature?.positionsLoading || !selectedFeature.collectionId || selectedFeature.featureId === undefined) {
      return;
    }

    let cancelled = false;
    const selectionKey = featureSelectionKey(selectedFeature);
    const { collectionId, featureId } = selectedFeature;

    async function loadStoredPositions() {
      try {
        let storageCrs = collectionStorageCrsRef.current.get(collectionId);
        if (!storageCrs) {
          const response = await fetch(collectionMetadataUrl(collectionId));
          if (!response.ok) {
            throw new Error(`Request failed with ${response.status}`);
          }

          const metadata = (await response.json()) as { storageCrs?: string };
          storageCrs = metadata.storageCrs;
          if (storageCrs) {
            collectionStorageCrsRef.current.set(collectionId, storageCrs);
          }
        }

        if (!storageCrs) {
          if (!cancelled) {
            setSelectedFeature(current =>
              current && featureSelectionKey(current) === selectionKey
                ? { ...current, positionsLoading: false }
                : current
            );
          }
          return;
        }

        const storedFeature = await getFeature(collectionItemUrl(collectionId, featureId, storageCrs));
        if (cancelled) {
          return;
        }

        setSelectedFeature(current =>
          current && featureSelectionKey(current) === selectionKey
            ? {
                ...current,
                properties: publicFeatureProperties(storedFeature),
                positions: sourcePositions(storedFeature),
                positionsCoordinateSystem: displayCoordinateSystemName(storageCrs),
                positionsLoading: false
              }
            : current
        );
      } catch (cause) {
        console.error('[gcmapview] failed to load stored coordinate positions', cause);
        if (!cancelled) {
          setSelectedFeature(current =>
            current && featureSelectionKey(current) === selectionKey
              ? { ...current, positionsLoading: false }
              : current
          );
        }
      }
    }

    void loadStoredPositions();

    return () => {
      cancelled = true;
    };
  }, [selectedFeature]);

  useEffect(() => {
    setHoveredPositionIndex(undefined);
  }, [selectedFeature?.collectionId, selectedFeature?.featureId, selectedFeature?.layerId]);

  useEffect(() => {
    const map = mapRef.current;
    const hoveredIndex = hoveredPositionIndex;
    const hoveredPosition = hoveredIndex === undefined ? undefined : selectedFeature?.mapPositions[hoveredIndex];

    if (!map || hoveredIndex === undefined || !selectedFeature || !hoveredPosition) {
      hoveredPositionOverlayRef.current?.remove();
      hoveredPositionOverlayRef.current = undefined;
      return;
    }

    const lngLat = maplibregl.LngLat.convert([hoveredPosition[0], hoveredPosition[1]]);
    const altitudeMeters = hoveredPositionAltitudeMeters(selectedFeature, hoveredIndex, is3d);

    let overlay = hoveredPositionOverlayRef.current;
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className =
        'h-3 w-3 rounded-full border-2 border-white bg-amber-500 shadow-[0_0_0_2px_rgb(0_0_0/0.35)]';
      overlay.style.pointerEvents = 'none';
      overlay.style.position = 'absolute';
      overlay.style.top = '0';
      overlay.style.left = '0';
      map.getCanvasContainer().appendChild(overlay);
      hoveredPositionOverlayRef.current = overlay;
    }

    const updateOverlayPosition = () => {
      const point = projectHoverOverlayPoint(map, lngLat, altitudeMeters);
      if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
        overlay.style.display = 'none';
        return;
      }

      overlay.style.display = '';
      overlay.style.transform = `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`;
    };

    updateOverlayPosition();
    map.on('render', updateOverlayPosition);

    return () => {
      map.off('render', updateOverlayPosition);
    };
  }, [hoveredPositionIndex, is3d, mapRef, selectedFeature]);

  useEffect(
    () => () => {
      hoveredPositionOverlayRef.current?.remove();
      hoveredPositionOverlayRef.current = undefined;
    },
    []
  );

  return {
    selectedFeature,
    setHoveredPositionIndex,
    setSelectedFeature
  };
}
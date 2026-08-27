import { useEffect, useRef, useState, type MutableRefObject, type RefObject } from 'react';
import * as maplibregl from 'maplibre-gl';
import { collectionItemUrl, collectionMetadataUrl, type CollectionId } from '../../api/geocomponentsApi';
import { type InspectedFeature } from '../../map/featureInspect';
import type { Feature } from '../../map/geojson';
import { projectInspectedFeaturePositionPoint } from './featurePositionProjection';
import { getFeature } from './mapViewData';
import { sourcePositions } from './mapViewGeometry';

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

function publicFeatureProperties(feature: Feature): Record<string, unknown> {
  return Object.fromEntries(Object.entries(feature.properties ?? {}).filter(([key]) => !key.startsWith('__gcmapview')));
}

type UseSelectedFeatureOptions = {
  mapRef: RefObject<maplibregl.Map | null>;
  is3d: boolean;
  adjustElevatedHeights: boolean;
  currentSelectedPositionZOffset: () => number;
  editedPositionIndicesRef: MutableRefObject<number[]>;
  hoveredPositionIndex: number | undefined;
  setHoveredPositionIndex: (index: number | undefined) => void;
  showSelectedPositionDots: boolean;
};

export function useSelectedFeature({
  mapRef,
  is3d,
  adjustElevatedHeights,
  currentSelectedPositionZOffset,
  editedPositionIndicesRef,
  hoveredPositionIndex,
  setHoveredPositionIndex,
  showSelectedPositionDots
}: UseSelectedFeatureOptions) {
  const [selectedFeature, setSelectedFeature] = useState<InspectedFeature>();
  const collectionStorageCrsRef = useRef(new Map<CollectionId, string>());
  const selectedPositionsOverlayRef = useRef<HTMLDivElement | undefined>(undefined);
  const selectedPositionDotRefs = useRef<HTMLDivElement[]>([]);

  function removeSelectedPositionsOverlay() {
    selectedPositionsOverlayRef.current?.remove();
    selectedPositionsOverlayRef.current = undefined;
    selectedPositionDotRefs.current = [];
  }

  useEffect(() => {
    if (
      !selectedFeature?.positionsLoading ||
      !selectedFeature.collectionId ||
      selectedFeature.featureId === undefined
    ) {
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
                sourceFeature: storedFeature,
                storageCrs,
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
            current && featureSelectionKey(current) === selectionKey ? { ...current, positionsLoading: false } : current
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
  }, [selectedFeature?.collectionId, selectedFeature?.featureId, selectedFeature?.layerId, setHoveredPositionIndex]);

  useEffect(() => {
    const map = mapRef.current;
    const mapPositions = selectedFeature?.mapPositions ?? [];

    if (!map || !selectedFeature || mapPositions.length === 0 || !showSelectedPositionDots) {
      removeSelectedPositionsOverlay();
      return;
    }

    let overlay = selectedPositionsOverlayRef.current;
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'pointer-events-none absolute inset-0';
      overlay.style.pointerEvents = 'none';
      overlay.style.position = 'absolute';
      overlay.style.top = '0';
      overlay.style.left = '0';
      overlay.style.width = '100%';
      overlay.style.height = '100%';
      map.getCanvasContainer().appendChild(overlay);
      selectedPositionsOverlayRef.current = overlay;
    }

    while (selectedPositionDotRefs.current.length > mapPositions.length) {
      selectedPositionDotRefs.current.pop()?.remove();
    }

    while (selectedPositionDotRefs.current.length < mapPositions.length) {
      const dot = document.createElement('div');
      dot.style.pointerEvents = 'none';
      dot.style.position = 'absolute';
      dot.style.top = '0';
      dot.style.left = '0';
      overlay.appendChild(dot);
      selectedPositionDotRefs.current.push(dot);
    }

    const editedPositionIndices = new Set(editedPositionIndicesRef.current);

    const updateDotStyles = () => {
      selectedPositionDotRefs.current.forEach((dot, index) => {
        const isHighlighted = editedPositionIndices.has(index) || hoveredPositionIndex === index;
        dot.className = isHighlighted
          ? 'h-3 w-3 rounded-full border-2 border-white bg-yellow-400 shadow-[0_0_0_2px_rgb(0_0_0/0.35)]'
          : 'h-2 w-2 rounded-full border border-white bg-sky-500 shadow-[0_0_0_1px_rgb(15_23_42/0.35)]';
      });
    };

    const updateOverlayPosition = () => {
      updateDotStyles();
      selectedPositionDotRefs.current.forEach((dot, index) => {
        const position = mapPositions[index];
        if (!position) {
          dot.style.display = 'none';
          return;
        }

        const point = projectInspectedFeaturePositionPoint(
          map,
          selectedFeature,
          index,
          position,
          is3d,
          adjustElevatedHeights,
          currentSelectedPositionZOffset
        );
        if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {
          dot.style.display = 'none';
          return;
        }

        dot.style.display = '';
        dot.style.transform = `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`;
      });
    };

    updateOverlayPosition();
    map.on('render', updateOverlayPosition);

    return () => {
      map.off('render', updateOverlayPosition);
    };
  }, [
    adjustElevatedHeights,
    currentSelectedPositionZOffset,
    editedPositionIndicesRef,
    hoveredPositionIndex,
    is3d,
    mapRef,
    selectedFeature,
    showSelectedPositionDots
  ]);

  useEffect(
    () => () => {
      removeSelectedPositionsOverlay();
    },
    []
  );

  return {
    selectedFeature,
    setSelectedFeature
  };
}

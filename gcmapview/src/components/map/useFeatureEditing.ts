import { useEffect, useMemo, useRef, useState, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';
import * as maplibregl from 'maplibre-gl';
import proj4 from 'proj4';
import { collectionItemUrl, type CollectionId } from '../../api/geocomponentsApi';
import type { InspectedFeature } from '../../map/featureInspect';
import type { Coordinates, Feature, Position } from '../../map/geojson';
import { projectInspectedFeaturePositionPoint } from './featurePositionProjection';
import { deleteFeature, getFeature, replaceFeature, type VisibleFeatureCollections } from './mapViewData';
import { sourcePositions } from './mapViewGeometry';

const collectionVisibleFeatureKeys = {
  parcels: 'parcels',
  buildings: 'buildings',
  jernbaneplattformkant: 'platformEdges',
  spormidt: 'trackCentres',
  bygning: 'bygning',
  bygning_omrade: 'bygningOmrade',
  bygning_senterlinje: 'bygningSenterlinje',
  bygning_posisjon: 'bygningPosisjon'
} as const;

const CRS84_URI = 'http://www.opengis.net/def/crs/OGC/1.3/CRS84';
const DISPLAY_CRS = 'EPSG:4326';
const REGISTERED_CRS_DEFINITIONS = {
  'EPSG:5972': '+proj=utm +zone=32 +ellps=GRS80 +units=m +no_defs',
  'EPSG:5973': '+proj=utm +zone=33 +ellps=GRS80 +units=m +no_defs'
} as const;

for (const [code, definition] of Object.entries(REGISTERED_CRS_DEFINITIONS)) {
  proj4.defs(code, definition);
}

function featureMatchesId(
  feature: { id?: string | number; properties?: Record<string, unknown> | null },
  featureId: string | number
) {
  if (feature.id !== undefined) {
    return String(feature.id) === String(featureId);
  }

  const propertyId = feature.properties?.id;
  return typeof propertyId === 'string' || typeof propertyId === 'number'
    ? String(propertyId) === String(featureId)
    : false;
}

function removeFeatureFromVisibleCollections(
  visibleFeatureCollections: VisibleFeatureCollections,
  collectionId: CollectionId,
  featureId: string | number
): VisibleFeatureCollections {
  const collectionKey = collectionVisibleFeatureKeys[collectionId];
  const featureCollection = visibleFeatureCollections[collectionKey];

  return {
    ...visibleFeatureCollections,
    [collectionKey]: {
      ...featureCollection,
      features: featureCollection.features.filter(feature => !featureMatchesId(feature, featureId))
    }
  };
}

function replaceFeatureInVisibleCollections(
  visibleFeatureCollections: VisibleFeatureCollections,
  collectionId: CollectionId,
  nextFeature: Feature
): VisibleFeatureCollections {
  const collectionKey = collectionVisibleFeatureKeys[collectionId];
  const featureCollection = visibleFeatureCollections[collectionKey];
  const nextFeatureId = nextFeature.id;

  if (nextFeatureId === undefined) {
    throw new Error('Det oppdaterte objektet mangler id.');
  }

  return {
    ...visibleFeatureCollections,
    [collectionKey]: {
      ...featureCollection,
      features: featureCollection.features.map(feature =>
        featureMatchesId(feature, nextFeatureId) ? nextFeature : feature
      )
    }
  };
}

function findFeatureInVisibleCollections(
  visibleFeatureCollections: VisibleFeatureCollections,
  collectionId: CollectionId,
  featureId: string | number
) {
  const collectionKey = collectionVisibleFeatureKeys[collectionId];
  return visibleFeatureCollections[collectionKey].features.find(feature => featureMatchesId(feature, featureId));
}

function clonePosition(position: Position): Position {
  return [...position] as Position;
}

function normalizeCrsForProj4(crs: string | undefined) {
  if (!crs) {
    return undefined;
  }

  if (crs === CRS84_URI || /\/OGC\/1\.3\/CRS84$/i.test(crs) || crs === 'CRS84') {
    return DISPLAY_CRS;
  }

  const epsgMatch = crs.match(/EPSG:(\d+)$/i) ?? crs.match(/\/EPSG\/0\/(\d+)$/i);
  if (epsgMatch) {
    return `EPSG:${epsgMatch[1]}`;
  }

  return crs;
}

function transformPosition(position: Position, fromCrs: string, toCrs: string): Position {
  const [x, y] = proj4(fromCrs, toCrs, [position[0], position[1]]);
  return [x, y, ...position.slice(2)] as Position;
}

function transformCoordinates(coordinates: Coordinates, fromCrs: string, toCrs: string): Coordinates {
  if (typeof coordinates[0] === 'number') {
    return transformPosition(coordinates as Position, fromCrs, toCrs);
  }

  return (coordinates as Coordinates[]).map(child => transformCoordinates(child, fromCrs, toCrs));
}

function featureInDisplayCrs(feature: Feature, storageCrs: string | undefined): Feature {
  const normalizedStorageCrs = normalizeCrsForProj4(storageCrs);
  if (!feature.geometry?.coordinates || !normalizedStorageCrs || normalizedStorageCrs === DISPLAY_CRS) {
    return feature;
  }

  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: transformCoordinates(feature.geometry.coordinates, normalizedStorageCrs, DISPLAY_CRS)
    }
  };
}

function positionsFromMapPositions(
  mapPositions: Position[],
  referencePositions: Position[],
  storageCrs: string | undefined
): Position[] {
  const normalizedStorageCrs = normalizeCrsForProj4(storageCrs);
  return mapPositions.map((position, index) => {
    const [x, y] =
      normalizedStorageCrs && normalizedStorageCrs !== DISPLAY_CRS
        ? proj4(DISPLAY_CRS, normalizedStorageCrs, [position[0], position[1]])
        : [position[0], position[1]];
    const referencePosition = referencePositions[index] ?? position;

    return position[2] === undefined && referencePosition[2] === undefined
      ? ([x, y, ...referencePosition.slice(3)] as Position)
      : ([x, y, referencePosition[2] ?? position[2], ...referencePosition.slice(3)] as Position);
  });
}

function positionsEqualXY(left: Position, right: Position) {
  return left[0] === right[0] && left[1] === right[1];
}

function positionsEqual(left: Position, right: Position) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function collectClosedPositionPairs(coordinates: Coordinates, startIndex = 0, pairs: Array<[number, number]> = []) {
  if (typeof coordinates[0] === 'number') {
    return { nextIndex: startIndex + 1, pairs };
  }

  const childCoordinates = coordinates as Coordinates[];
  if (childCoordinates.length > 0 && typeof childCoordinates[0]?.[0] === 'number') {
    const sequence = childCoordinates as Position[];
    if (sequence.length > 1 && positionsEqualXY(sequence[0], sequence[sequence.length - 1])) {
      pairs.push([startIndex, startIndex + sequence.length - 1]);
    }
  }

  let nextIndex = startIndex;
  for (const child of childCoordinates) {
    const result = collectClosedPositionPairs(child, nextIndex, pairs);
    nextIndex = result.nextIndex;
  }

  return { nextIndex, pairs };
}

function normalizeClosedPositions(feature: Feature, editedPositions: Position[]): Position[] {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) {
    return editedPositions;
  }

  const originalPositions = sourcePositions(feature);
  const nextPositions = editedPositions.map(clonePosition);
  const { pairs } = collectClosedPositionPairs(coordinates);

  for (const [firstIndex, lastIndex] of pairs) {
    const firstPosition = nextPositions[firstIndex];
    const lastPosition = nextPositions[lastIndex];
    const originalFirst = originalPositions[firstIndex];
    const originalLast = originalPositions[lastIndex];

    if (!firstPosition || !lastPosition || !originalFirst || !originalLast) {
      throw new Error('Kunne ikke matche redigerte posisjoner mot geometrien.');
    }

    const firstChanged = !positionsEqualXY(firstPosition, originalFirst);
    const lastChanged = !positionsEqualXY(lastPosition, originalLast);

    if (firstChanged && lastChanged && !positionsEqualXY(firstPosition, lastPosition)) {
      throw new Error('Lukkede ringer må beholde samme første og siste punkt.');
    }

    if (firstChanged && !lastChanged) {
      nextPositions[lastIndex] = clonePosition(firstPosition);
      continue;
    }

    if (!firstChanged && lastChanged) {
      nextPositions[firstIndex] = clonePosition(lastPosition);
      continue;
    }

    nextPositions[lastIndex] = clonePosition(nextPositions[firstIndex]);
  }

  return nextPositions;
}

function replaceCoordinatesFromPositions(
  coordinates: Coordinates,
  positions: Position[],
  nextPositionIndexRef: { current: number }
): Coordinates {
  if (typeof coordinates[0] === 'number') {
    const nextPosition = positions[nextPositionIndexRef.current];
    if (!nextPosition) {
      throw new Error('Kunne ikke matche redigerte posisjoner mot geometrien.');
    }

    nextPositionIndexRef.current += 1;
    return clonePosition(nextPosition);
  }

  return (coordinates as Coordinates[]).map(child =>
    replaceCoordinatesFromPositions(child, positions, nextPositionIndexRef)
  );
}

function featureWithUpdatedPositions(feature: Feature, editedPositions: Position[]): Feature {
  const coordinates = feature.geometry?.coordinates;
  if (!feature.geometry || !coordinates) {
    throw new Error('Det valgte objektet har ingen redigerbar geometri.');
  }

  const normalizedPositions = normalizeClosedPositions(feature, editedPositions);
  const nextPositionIndexRef = { current: 0 };
  const nextCoordinates = replaceCoordinatesFromPositions(coordinates, normalizedPositions, nextPositionIndexRef);

  if (nextPositionIndexRef.current !== normalizedPositions.length) {
    throw new Error('Kunne ikke matche alle redigerte posisjoner mot geometrien.');
  }

  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: nextCoordinates
    }
  };
}

function sameSelectedFeature(
  current: { collectionId?: CollectionId; featureId?: string | number; layerId: string } | undefined,
  expected: { collectionId?: CollectionId; featureId?: string | number; layerId: string }
) {
  return (
    current?.collectionId === expected.collectionId &&
    current?.featureId === expected.featureId &&
    current?.layerId === expected.layerId
  );
}

type FeatureEditSession = {
  selectedFeature: InspectedFeature;
  renderedFeature?: Feature;
};

function structuredCloneFeatureSelection(feature: InspectedFeature): InspectedFeature {
  return {
    ...feature,
    sourceFeature: feature.sourceFeature
      ? ({
          ...feature.sourceFeature,
          geometry: feature.sourceFeature.geometry
            ? {
                ...feature.sourceFeature.geometry,
                coordinates: feature.sourceFeature.geometry.coordinates
              }
            : null,
          properties: feature.sourceFeature.properties
            ? { ...feature.sourceFeature.properties }
            : feature.sourceFeature.properties
        } as Feature)
      : undefined,
    properties: { ...feature.properties },
    positions: feature.positions.map(clonePosition),
    mapPositions: feature.mapPositions.map(clonePosition)
  };
}

type UseFeatureEditingOptions = {
  mapRef: MutableRefObject<maplibregl.Map | null>;
  is3d: boolean;
  adjustElevatedHeights: boolean;
  currentSelectedPositionZOffset: () => number;
  hoveredPositionIndex: number | undefined;
  selectedFeature: InspectedFeature | undefined;
  setSelectedFeature: Dispatch<SetStateAction<InspectedFeature | undefined>>;
  setHoveredPositionIndex: (index: number | undefined) => void;
  setShowSelectedPositionDots: Dispatch<SetStateAction<boolean>>;
  latestVectorDataRef: MutableRefObject<VisibleFeatureCollections>;
  currentFilteredLayerVisibility: () => ReturnType<
    typeof import('../../store/layerVisibilityStore').filterUnavailableLayers
  >;
  applyRenderedVisibleData: (
    map: maplibregl.Map,
    visibleFeatureCollections: VisibleFeatureCollections,
    visibility: ReturnType<typeof import('../../store/layerVisibilityStore').filterUnavailableLayers>
  ) => Promise<void>;
  setError: Dispatch<SetStateAction<string | undefined>>;
  setStatus: Dispatch<SetStateAction<string>>;
};

export function useFeatureEditing({
  mapRef,
  is3d,
  adjustElevatedHeights,
  currentSelectedPositionZOffset,
  hoveredPositionIndex,
  selectedFeature,
  setSelectedFeature,
  setHoveredPositionIndex,
  setShowSelectedPositionDots,
  latestVectorDataRef,
  currentFilteredLayerVisibility,
  applyRenderedVisibleData,
  setError,
  setStatus
}: UseFeatureEditingOptions) {
  const [isDeletingFeature, setIsDeletingFeature] = useState(false);
  const [isSavingFeatureChanges, setIsSavingFeatureChanges] = useState(false);
  const [isEditingFeature, setIsEditingFeature] = useState(false);
  const selectedFeatureRef = useRef(selectedFeature);
  selectedFeatureRef.current = selectedFeature;
  const isEditingFeatureRef = useRef(isEditingFeature);
  isEditingFeatureRef.current = isEditingFeature;
  const hoveredPositionIndexRef = useRef(hoveredPositionIndex);
  hoveredPositionIndexRef.current = hoveredPositionIndex;
  const previewFeaturePositionChangesRef = useRef<(positions: Position[]) => void>(() => {});
  const featureEditSessionRef = useRef<FeatureEditSession | undefined>(undefined);
  const dragPointsOverlayRef = useRef<HTMLDivElement | undefined>(undefined);
  const dragPointRefs = useRef<HTMLButtonElement[]>([]);
  const dragPointerCleanupRef = useRef<(() => void) | undefined>(undefined);
  const activeDragPointIndexRef = useRef<number | undefined>(undefined);

  const projectFeaturePositionPointRef = useRef<
    (feature: InspectedFeature, index: number, position: Position) => maplibregl.Point
  >(() => new maplibregl.Point(0, 0));
  projectFeaturePositionPointRef.current = (feature: InspectedFeature, index: number, position: Position) => {
    const map = mapRef.current;
    if (!map) {
      return new maplibregl.Point(0, 0);
    }

    return projectInspectedFeaturePositionPoint(
      map,
      feature,
      index,
      position,
      is3d,
      adjustElevatedHeights,
      currentSelectedPositionZOffset
    );
  };

  const editedPositionIndices = useMemo(() => {
    const editSessionFeature = featureEditSessionRef.current?.selectedFeature;
    if (
      !isEditingFeature ||
      !selectedFeature ||
      !editSessionFeature ||
      !sameSelectedFeature(selectedFeature, editSessionFeature)
    ) {
      return [];
    }

    return selectedFeature.positions.reduce<number[]>((indices, position, index) => {
      const originalPosition = editSessionFeature.positions[index];
      if (!originalPosition || !positionsEqual(position, originalPosition)) {
        indices.push(index);
      }
      return indices;
    }, []);
  }, [isEditingFeature, selectedFeature]);

  function applyDragMarkerClass(element: HTMLElement, isHighlighted: boolean, isDragging: boolean) {
    element.className = [
      'block h-4 w-4 box-border rounded-full border-2 border-white shadow-[0_0_0_2px_rgb(15_23_42/0.35)]',
      isHighlighted ? 'bg-yellow-400' : 'bg-sky-500',
      isDragging ? 'cursor-grabbing' : 'cursor-grab'
    ].join(' ');
  }

  function removeDragPointsOverlay() {
    dragPointerCleanupRef.current?.();
    dragPointerCleanupRef.current = undefined;
    activeDragPointIndexRef.current = undefined;
    dragPointsOverlayRef.current?.remove();
    dragPointsOverlayRef.current = undefined;
    dragPointRefs.current = [];
  }

  function restoreFeatureEditPreview() {
    const map = mapRef.current;
    const session = featureEditSessionRef.current;
    if (!map || !session?.selectedFeature.collectionId || session.selectedFeature.featureId === undefined) {
      return;
    }

    if (session.renderedFeature) {
      latestVectorDataRef.current = replaceFeatureInVisibleCollections(
        latestVectorDataRef.current,
        session.selectedFeature.collectionId,
        session.renderedFeature
      );
      void applyRenderedVisibleData(map, latestVectorDataRef.current, currentFilteredLayerVisibility());
    }

    setSelectedFeature(current =>
      current && sameSelectedFeature(current, session.selectedFeature)
        ? structuredCloneFeatureSelection(session.selectedFeature)
        : current
    );
  }

  function startSelectedFeatureEditing() {
    if (
      isEditingFeatureRef.current ||
      !selectedFeature?.collectionId ||
      selectedFeature.featureId === undefined ||
      !selectedFeature.sourceFeature
    ) {
      return;
    }

    featureEditSessionRef.current = {
      selectedFeature: structuredCloneFeatureSelection(selectedFeature),
      renderedFeature: findFeatureInVisibleCollections(
        latestVectorDataRef.current,
        selectedFeature.collectionId,
        selectedFeature.featureId
      )
    };
    setHoveredPositionIndex(selectedFeature.mapPositions.length > 0 ? 0 : undefined);
    setShowSelectedPositionDots(false);
    setIsEditingFeature(true);
    setStatus(`Redigerer ${selectedFeature.layerLabel.toLowerCase()} ${String(selectedFeature.featureId)}.`);
  }

  function cancelSelectedFeatureEditing() {
    if (!isEditingFeatureRef.current) {
      return;
    }

    restoreFeatureEditPreview();
    featureEditSessionRef.current = undefined;
    setIsEditingFeature(false);
    setHoveredPositionIndex(undefined);
    setShowSelectedPositionDots(true);
  }

  function previewSelectedFeaturePositionChanges(positions: Position[]) {
    const map = mapRef.current;
    const featureToPreview = selectedFeatureRef.current;
    if (
      !map ||
      !featureToPreview?.collectionId ||
      featureToPreview.featureId === undefined ||
      !featureToPreview.sourceFeature
    ) {
      return;
    }

    const normalizedPositions = normalizeClosedPositions(featureToPreview.sourceFeature, positions);
    const updatedSourceFeature = featureWithUpdatedPositions(featureToPreview.sourceFeature, normalizedPositions);
    const updatedRenderedFeature = featureInDisplayCrs(updatedSourceFeature, featureToPreview.storageCrs);

    latestVectorDataRef.current = replaceFeatureInVisibleCollections(
      latestVectorDataRef.current,
      featureToPreview.collectionId,
      updatedRenderedFeature
    );
    void applyRenderedVisibleData(map, latestVectorDataRef.current, currentFilteredLayerVisibility());
    setSelectedFeature(current => {
      if (!current || !sameSelectedFeature(current, featureToPreview)) {
        return current;
      }

      return {
        ...current,
        positions: normalizedPositions,
        mapPositions: sourcePositions(updatedRenderedFeature)
      };
    });
  }
  previewFeaturePositionChangesRef.current = previewSelectedFeaturePositionChanges;

  async function deleteSelectedFeature() {
    const map = mapRef.current;
    const featureToDelete = selectedFeatureRef.current;

    if (
      !map ||
      !featureToDelete?.collectionId ||
      featureToDelete.featureId === undefined ||
      isDeletingFeature ||
      isSavingFeatureChanges ||
      isEditingFeatureRef.current
    ) {
      return;
    }

    const featureLabel = featureToDelete.layerLabel.toLowerCase();
    const confirmed = window.confirm(
      `Slette ${featureLabel} ${String(featureToDelete.featureId)}? Dette kan ikke angres.`
    );

    if (!confirmed) {
      return;
    }

    setIsDeletingFeature(true);
    setError(undefined);
    setStatus(`Sletter ${featureLabel} ${String(featureToDelete.featureId)}...`);

    try {
      await deleteFeature(collectionItemUrl(featureToDelete.collectionId, featureToDelete.featureId));
      latestVectorDataRef.current = removeFeatureFromVisibleCollections(
        latestVectorDataRef.current,
        featureToDelete.collectionId,
        featureToDelete.featureId
      );
      await applyRenderedVisibleData(map, latestVectorDataRef.current, currentFilteredLayerVisibility());
      setSelectedFeature(undefined);
      setHoveredPositionIndex(undefined);
      setStatus(`Slettet ${featureLabel} ${String(featureToDelete.featureId)}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ukjent feil');
      setStatus(`Kunne ikke slette ${featureLabel} ${String(featureToDelete.featureId)}.`);
    } finally {
      setIsDeletingFeature(false);
    }
  }

  async function commitSelectedFeaturePositionChanges(positions: Position[]) {
    const map = mapRef.current;
    const featureToEdit = selectedFeatureRef.current;

    if (
      !map ||
      !featureToEdit?.collectionId ||
      featureToEdit.featureId === undefined ||
      !featureToEdit.sourceFeature ||
      isSavingFeatureChanges ||
      isDeletingFeature
    ) {
      return;
    }

    const featureLabel = featureToEdit.layerLabel.toLowerCase();
    const updatedSourceFeature = featureWithUpdatedPositions(featureToEdit.sourceFeature, positions);

    setIsSavingFeatureChanges(true);
    setError(undefined);
    setStatus(`Lagrer ${featureLabel} ${String(featureToEdit.featureId)}...`);

    try {
      await replaceFeature(
        collectionItemUrl(featureToEdit.collectionId, featureToEdit.featureId),
        updatedSourceFeature
      );
      featureEditSessionRef.current = undefined;
      setIsEditingFeature(false);
      setHoveredPositionIndex(undefined);
      setShowSelectedPositionDots(true);

      const updatedRenderedFeature = await getFeature(
        collectionItemUrl(featureToEdit.collectionId, featureToEdit.featureId)
      );
      latestVectorDataRef.current = replaceFeatureInVisibleCollections(
        latestVectorDataRef.current,
        featureToEdit.collectionId,
        updatedRenderedFeature
      );
      await applyRenderedVisibleData(map, latestVectorDataRef.current, currentFilteredLayerVisibility());
      setSelectedFeature(current => {
        if (!current || !sameSelectedFeature(current, featureToEdit)) {
          return current;
        }

        return {
          ...current,
          sourceFeature: updatedSourceFeature,
          properties: { ...(updatedSourceFeature.properties ?? {}) },
          positions,
          mapPositions: sourcePositions(updatedRenderedFeature),
          positionsLoading: false
        };
      });
      setStatus(`Oppdaterte ${featureLabel} ${String(featureToEdit.featureId)}.`);
    } catch (cause) {
      const errorMessage = cause instanceof Error ? cause.message : 'Ukjent feil';
      setError(errorMessage);
      setStatus(`Kunne ikke oppdatere ${featureLabel} ${String(featureToEdit.featureId)}.`);
      throw cause instanceof Error ? cause : new Error(errorMessage);
    } finally {
      setIsSavingFeatureChanges(false);
    }
  }

  useEffect(() => {
    const map = mapRef.current;
    const currentSelectedFeature = selectedFeatureRef.current;

    removeDragPointsOverlay();

    if (!map || !isEditingFeature || !currentSelectedFeature) {
      return;
    }

    const overlay = document.createElement('div');
    overlay.className = 'absolute inset-0 pointer-events-none';
    overlay.style.position = 'absolute';
    overlay.style.top = '0';
    overlay.style.left = '0';
    overlay.style.width = '100%';
    overlay.style.height = '100%';
    overlay.style.pointerEvents = 'none';
    map.getCanvasContainer().appendChild(overlay);
    dragPointsOverlayRef.current = overlay;

    const buttonCleanupCallbacks: Array<() => void> = [];
    const activeEditPositionIndex = activeDragPointIndexRef.current ?? hoveredPositionIndexRef.current;
    const updateDraggedPosition = (index: number, lngLat: maplibregl.LngLat) => {
      const currentSelectedFeature = selectedFeatureRef.current;
      if (!currentSelectedFeature) {
        return;
      }

      const nextMapPositions = currentSelectedFeature.mapPositions.map(clonePosition);
      const referencePosition = nextMapPositions[index] ?? currentSelectedFeature.mapPositions[index];
      nextMapPositions[index] =
        referencePosition?.[2] === undefined
          ? ([lngLat.lng, lngLat.lat] as Position)
          : ([lngLat.lng, lngLat.lat, referencePosition[2], ...referencePosition.slice(3)] as Position);
      const nextStoragePositions = positionsFromMapPositions(
        nextMapPositions,
        currentSelectedFeature.positions,
        currentSelectedFeature.storageCrs
      );

      previewFeaturePositionChangesRef.current(nextStoragePositions);
    };

    dragPointRefs.current = currentSelectedFeature.mapPositions.map((position, index) => {
      const element = document.createElement('button');
      applyDragMarkerClass(element, activeEditPositionIndex === index, false);
      element.type = 'button';
      element.setAttribute('aria-label', `Drag point ${index + 1}`);
      element.style.position = 'absolute';
      element.style.top = '0';
      element.style.left = '0';
      element.style.pointerEvents = 'auto';
      element.style.touchAction = 'none';
      overlay.appendChild(element);

      const handlePointerDown = (event: PointerEvent) => {
        if (event.button !== 0) {
          return;
        }

        event.preventDefault();
        event.stopPropagation();
        activeDragPointIndexRef.current = index;
        setHoveredPositionIndex(index);
        const isVerticalDrag = is3d && event.ctrlKey;
        applyDragMarkerClass(element, true, true);
        map.dragPan.disable();

        const startClientY = event.clientY;
        const currentStoragePosition = selectedFeatureRef.current?.positions[index];
        const startZ = currentStoragePosition?.[2] ?? selectedFeatureRef.current?.mapPositions[index]?.[2] ?? 0;

        const handlePointerMove = (moveEvent: PointerEvent) => {
          if (isVerticalDrag) {
            const currentSelectedFeature = selectedFeatureRef.current;
            if (!currentSelectedFeature) {
              return;
            }

            const nextStoragePositions = currentSelectedFeature.positions.map(clonePosition);
            const referencePosition = nextStoragePositions[index] ?? currentSelectedFeature.positions[index];
            if (!referencePosition) {
              return;
            }

            const nextZ = startZ - (moveEvent.clientY - startClientY) * 0.01;
            nextStoragePositions[index] = [
              referencePosition[0],
              referencePosition[1],
              nextZ,
              ...referencePosition.slice(3)
            ] as Position;
            previewFeaturePositionChangesRef.current(nextStoragePositions);
            return;
          }

          const containerRect = map.getCanvasContainer().getBoundingClientRect();
          const lngLat = map.unproject([moveEvent.clientX - containerRect.left, moveEvent.clientY - containerRect.top]);
          updateDraggedPosition(index, lngLat);
        };

        const finishPointerDrag = () => {
          window.removeEventListener('pointermove', handlePointerMove);
          window.removeEventListener('pointerup', finishPointerDrag);
          window.removeEventListener('pointercancel', finishPointerDrag);
          dragPointerCleanupRef.current = undefined;
          activeDragPointIndexRef.current = undefined;
          if (!map.dragPan.isEnabled()) {
            map.dragPan.enable();
          }
          applyDragMarkerClass(element, true, false);
        };

        dragPointerCleanupRef.current = finishPointerDrag;
        window.addEventListener('pointermove', handlePointerMove);
        window.addEventListener('pointerup', finishPointerDrag);
        window.addEventListener('pointercancel', finishPointerDrag);
      };

      element.addEventListener('pointerdown', handlePointerDown);
      buttonCleanupCallbacks.push(() => {
        element.removeEventListener('pointerdown', handlePointerDown);
      });

      const point = projectFeaturePositionPointRef.current(currentSelectedFeature, index, position);
      element.style.transform = `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`;
      return element;
    });

    return () => {
      for (const cleanup of buttonCleanupCallbacks) {
        cleanup();
      }
      removeDragPointsOverlay();
    };
  }, [
    is3d,
    isEditingFeature,
    mapRef,
    selectedFeature?.collectionId,
    selectedFeature?.featureId,
    selectedFeature?.layerId,
    selectedFeature?.mapPositions.length,
    setHoveredPositionIndex
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isEditingFeature) {
      return;
    }

    const updateDragPointPositions = () => {
      const currentSelectedFeature = selectedFeatureRef.current;
      if (!currentSelectedFeature) {
        return;
      }

      const activeEditPositionIndex = activeDragPointIndexRef.current ?? hoveredPositionIndex;
      dragPointRefs.current.forEach((element, index) => {
        const position = currentSelectedFeature.mapPositions[index];
        const isActive = activeEditPositionIndex === index;
        applyDragMarkerClass(element, isActive, element.classList.contains('cursor-grabbing'));

        if (!position) {
          element.style.display = 'none';
          return;
        }

        const point = projectFeaturePositionPointRef.current(currentSelectedFeature, index, position);
        element.style.display = '';
        element.style.transform = `translate(-50%, -50%) translate(${point.x}px, ${point.y}px)`;
      });
    };

    updateDragPointPositions();
    map.on('render', updateDragPointPositions);

    return () => {
      map.off('render', updateDragPointPositions);
    };
  }, [hoveredPositionIndex, isEditingFeature, mapRef, selectedFeature?.mapPositions.length]);

  return {
    editedPositionIndices,
    isDeletingFeature,
    isSavingFeatureChanges,
    isEditingFeature,
    isEditingFeatureRef,
    startSelectedFeatureEditing,
    cancelSelectedFeatureEditing,
    previewSelectedFeaturePositionChanges,
    commitSelectedFeaturePositionChanges,
    deleteSelectedFeature
  };
}

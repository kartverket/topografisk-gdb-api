import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import robotoLatinVariableUrl from '@fontsource-variable/roboto/files/roboto-latin-wght-normal.woff2';
import { AlertCircle, Eraser, Plus } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  buildingItemUrl,
  buildingsCreateUrl,
  buildingsItemsUrl,
  parcelItemUrl,
  parcelsItemsInBboxUrl,
  parcelsCreateUrl,
  parcelsItemsUrl
} from '../../api/geocomponentsApi';
import {
  applyMapDimensionMode,
  applyMapLayerVisibility,
  configureInitialMapInteraction,
  terrainSourceId
} from '../../map/mapDimension';
import {
  hasInspectableFeatureAtPoint,
  inspectFeaturesAtPoint,
  type ActiveFeatureFilter
} from '../../map/featureInspect';
import { useLayerVisibilityStore } from '../../store/layerVisibilityStore';
import { useMapViewStore } from '../../store/mapViewStore';
import {
  clearBuildingDebugMarkers,
  createBuildingDebugMarkerState,
  setBuildingDebugMarkerVisibility,
  updateBuildingDebugMarkers
} from './buildingDebugMarkers';
import { applyObjtypeLabelVisibility, OBJTYPE_LABEL_MIN_ZOOM, upsertObjtypeLabelLayer } from './objtypeLabels';
import { FeaturePropertiesCard } from './FeaturePropertiesCard';
import { MapLayersCard } from './MapLayersCard';
import { useMapDimension } from './useMapDimension';
import { buildingCentroidsFeatureCollection, logLoadedCoordinates } from './mapViewGeometry';
import {
  addNativeFeatureSourcesAndLayers,
  clearVectorSources,
  createFeature,
  deleteFeature,
  emptyFeatureCollection,
  emptyVisibleFeatureCollections,
  filterVisibleFeatureCollectionsByProperty,
  getFeatureCollection,
  getVisibleFeatureCollections,
  isBuildingZoom,
  isVectorZoom,
  layerVisibilityChanged,
  logNativeRenderingState,
  MIN_BUILDING_ZOOM,
  MIN_VECTOR_ZOOM,
  setNativeFeatureSources,
  type VisibleFeatureCollections,
  updateElevatedFeatureSources,
  upsertGeoJsonSource,
  visibleOgcBbox
} from './mapViewData';
import { randomNonOverlappingBuildingAndParcel } from './mapViewRandomFeatures';
import { useSelectedFeature } from './useSelectedFeature';

/** Default initial view when no local favorite view has been saved. */
const OTTA_CENTER: [number, number] = [9.54, 61.77];
const OTTA_ZOOM = 15;
const DEFERRED_ELEVATED_SOURCE_DELAY_MS = 120;

const mapStyle: maplibregl.StyleSpecification = {
  version: 8,
  'font-faces': {
    'Roboto Variable': robotoLatinVariableUrl
  },
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 17,
      attribution: '&copy; OpenStreetMap contributors'
    },
    [terrainSourceId]: {
      type: 'raster-dem',
      tiles: ['https://elevation-tiles-prod.s3.amazonaws.com/terrarium/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 15,
      encoding: 'terrarium',
      attribution: 'Elevation tiles by AWS Terrain Tiles'
    }
  },
  layers: [
    {
      id: 'osm',
      type: 'raster',
      source: 'osm'
    }
  ]
};

function isTerrainEnabled(is3d: boolean, adjustElevatedHeights: boolean) {
  return is3d && !adjustElevatedHeights;
}

export function MapView() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map>(null);
  const buildingMarkerStateRef = useRef(createBuildingDebugMarkerState());
  const pendingReloadTimeoutRef = useRef<number | undefined>(undefined);
  const pendingElevatedRefreshTimeoutRef = useRef<number | undefined>(undefined);
  const reloadVisibleDataRef = useRef<(() => Promise<void>) | undefined>(undefined);
  const { is3d, adjustElevatedHeights, setIs3d, setAdjustElevatedHeights } = useMapDimension();
  const is3dRef = useRef(is3d);
  is3dRef.current = is3d;
  const adjustElevatedHeightsRef = useRef(adjustElevatedHeights);
  adjustElevatedHeightsRef.current = adjustElevatedHeights;
  const [activeFeatureFilter, setActiveFeatureFilter] = useState<ActiveFeatureFilter>();
  const activeFeatureFilterRef = useRef<ActiveFeatureFilter | undefined>(undefined);
  activeFeatureFilterRef.current = activeFeatureFilter;
  const latestVectorDataRef = useRef<VisibleFeatureCollections>(emptyVisibleFeatureCollections);
  const layerVisibility = useLayerVisibilityStore(state => state.visibility);
  const setLayerVisibility = useLayerVisibilityStore(state => state.setVisibility);
  const previousLayerVisibilityRef = useRef(layerVisibility);
  const favoriteViews = useMapViewStore(state => state.favoriteViews);
  const activeFavoriteName = useMapViewStore(state => state.activeFavoriteName);
  const saveFavoriteView = useMapViewStore(state => state.saveFavoriteView);
  const selectFavoriteView = useMapViewStore(state => state.selectFavoriteView);
  const removeFavoriteView = useMapViewStore(state => state.removeFavoriteView);
  const activeFavoriteView =
    favoriteViews.find(favoriteView => favoriteView.name === activeFavoriteName) ?? favoriteViews[0];
  const initialFavoriteViewRef = useRef<{ center: [number, number]; zoom: number }>({
    center: activeFavoriteView?.center ?? OTTA_CENTER,
    zoom: activeFavoriteView?.zoom ?? OTTA_ZOOM
  });
  const [status, setStatus] = useState('Loading map...');
  const [error, setError] = useState<string>();
  const [isMapReady, setIsMapReady] = useState(false);
  const [isVectorZoomActive, setIsVectorZoomActive] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const { selectedFeature, setHoveredPositionIndex, setSelectedFeature } = useSelectedFeature({ mapRef, is3d });
  const closeSelectedFeatureInspectorRef = useRef<() => void>(() => {});
  const setSelectedFeatureRef = useRef(setSelectedFeature);
  setSelectedFeatureRef.current = setSelectedFeature;

  function cancelPendingMapWork() {
    if (pendingReloadTimeoutRef.current !== undefined) {
      window.clearTimeout(pendingReloadTimeoutRef.current);
      pendingReloadTimeoutRef.current = undefined;
    }
    if (pendingElevatedRefreshTimeoutRef.current !== undefined) {
      window.clearTimeout(pendingElevatedRefreshTimeoutRef.current);
      pendingElevatedRefreshTimeoutRef.current = undefined;
    }
  }

  useEffect(() => {
    if (!activeFavoriteView) {
      return;
    }

    if (activeFavoriteView.visibility) {
      setLayerVisibility(activeFavoriteView.visibility);
    }

    if (activeFavoriteView.is3d !== undefined) {
      setIs3d(activeFavoriteView.is3d);
    }

    if (activeFavoriteView.adjustElevatedHeights !== undefined) {
      setAdjustElevatedHeights(activeFavoriteView.adjustElevatedHeights);
    }
  }, [activeFavoriteView, setAdjustElevatedHeights, setIs3d, setLayerVisibility]);

  function applyFavoriteViewSettings(favoriteView: typeof activeFavoriteView) {
    if (!favoriteView) {
      return;
    }

    if (favoriteView.visibility) {
      setLayerVisibility(favoriteView.visibility);
    }

    if (favoriteView.is3d !== undefined) {
      setIs3d(favoriteView.is3d);
    }

    if (favoriteView.adjustElevatedHeights !== undefined) {
      setAdjustElevatedHeights(favoriteView.adjustElevatedHeights);
    }
  }

  function saveCurrentFavoriteView() {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    const suggestedName = activeFavoriteName ?? `Favorite ${favoriteViews.length + 1}`;
    const rawName = window.prompt('Name for favorite location:', suggestedName);
    if (rawName === null) {
      return;
    }

    const favoriteName = rawName.trim();
    if (!favoriteName) {
      setStatus('Favorite location was not saved because no name was provided.');
      return;
    }

    const center = map.getCenter();
    const savedCenter: [number, number] = [Number(center.lng.toFixed(6)), Number(center.lat.toFixed(6))];
    const savedZoom = Number(map.getZoom().toFixed(2));
    const existed = favoriteViews.some(favoriteView => favoriteView.name === favoriteName);
    saveFavoriteView({
      name: favoriteName,
      center: savedCenter,
      zoom: savedZoom,
      visibility: layerVisibility,
      is3d,
      adjustElevatedHeights
    });
    setStatus(
      `${existed ? 'Updated' : 'Saved'} favorite "${favoriteName}" at ${savedCenter[0].toFixed(5)}, ${savedCenter[1].toFixed(5)} (z=${savedZoom.toFixed(2)}) with current layers.`
    );
  }

  function clearStoredFavoriteView() {
    if (!activeFavoriteView) {
      return;
    }

    removeFavoriteView(activeFavoriteView.name);
    setStatus(`Removed favorite "${activeFavoriteView.name}".`);
  }

  function selectStoredFavoriteView(name: string) {
    const map = mapRef.current;
    const selectedFavoriteView = favoriteViews.find(favoriteView => favoriteView.name === name);

    selectFavoriteView(name);

    if (map && selectedFavoriteView) {
      setError(undefined);
      applyFavoriteViewSettings(selectedFavoriteView);
      map.easeTo({ center: selectedFavoriteView.center, zoom: selectedFavoriteView.zoom, duration: 700 });
      setStatus(`Selected favorite "${name}", restored its layers, and moved to it.`);
      return;
    }

    setStatus(`Selected favorite "${name}".`);
  }

  function applyFeatureFilter(featureFilter: ActiveFeatureFilter) {
    const propertyKey = featureFilter.propertyKey.trim();
    const value = featureFilter.value.trim();
    if (!propertyKey || !value) {
      return;
    }

    setError(undefined);
    setActiveFeatureFilter({ propertyKey, value });
    setStatus(`Filtering visible layers by ${propertyKey} "${value}".`);
  }

  function clearFeatureFilter() {
    if (!activeFeatureFilterRef.current) {
      return;
    }

    const clearedFeatureFilter = activeFeatureFilterRef.current;
    setError(undefined);
    setActiveFeatureFilter(undefined);
    setStatus(`Cleared ${clearedFeatureFilter.propertyKey} filter "${clearedFeatureFilter.value}".`);
  }

  function closeSelectedFeatureInspector() {
    if (activeFeatureFilterRef.current) {
      clearFeatureFilter();
    }

    setSelectedFeature(undefined);
  }
  closeSelectedFeatureInspectorRef.current = closeSelectedFeatureInspector;

  async function applyRenderedVisibleData(
    map: maplibregl.Map,
    visibleFeatureCollections: VisibleFeatureCollections,
    visibility: typeof layerVisibility,
    featureFilter = activeFeatureFilterRef.current
  ) {
    const renderedFeatureCollections = filterVisibleFeatureCollectionsByProperty(
      visibleFeatureCollections,
      featureFilter
    );

    await setNativeFeatureSources(
      map,
      renderedFeatureCollections.parcels,
      renderedFeatureCollections.buildings,
      renderedFeatureCollections.platformEdges,
      renderedFeatureCollections.trackCentres,
      renderedFeatureCollections.bygning,
      renderedFeatureCollections.bygningOmrade,
      renderedFeatureCollections.bygningSenterlinje,
      renderedFeatureCollections.bygningPosisjon,
      visibility,
      adjustElevatedHeightsRef.current,
      is3dRef.current
    );
    await upsertGeoJsonSource(
      map,
      'building-centroids',
      buildingCentroidsFeatureCollection(renderedFeatureCollections.buildings)
    );
    upsertObjtypeLabelLayer(map, renderedFeatureCollections, visibility);
    updateBuildingDebugMarkers(
      buildingMarkerStateRef.current,
      map,
      renderedFeatureCollections.buildings,
      !is3dRef.current && useLayerVisibilityStore.getState().visibility.buildings
    );
  }

  useEffect(() => {
    if (!mapContainerRef.current) {
      return;
    }

    let cancelled = false;
    const buildingMarkerState = buildingMarkerStateRef.current;
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapStyle,
      center: initialFavoriteViewRef.current.center,
      zoom: initialFavoriteViewRef.current.zoom
    });
    mapRef.current = map;
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(mapContainerRef.current);

    map.on('error', event => {
      console.error('[gcmapview] MapLibre error', event.error);
      setError(event.error?.message ?? 'Unknown MapLibre error');
      setStatus('MapLibre failed while loading the map style or layers');
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.FullscreenControl(), 'top-right');
    map.addControl(new maplibregl.GlobeControl(), 'top-right');
    configureInitialMapInteraction(map);

    let visibleRequestId = 0;
    async function reloadVisibleData() {
      if (pendingElevatedRefreshTimeoutRef.current !== undefined) {
        window.clearTimeout(pendingElevatedRefreshTimeoutRef.current);
        pendingElevatedRefreshTimeoutRef.current = undefined;
      }

      const requestId = ++visibleRequestId;
      const vectorZoomActive = isVectorZoom(map);
      setIsVectorZoomActive(vectorZoomActive);

      if (!vectorZoomActive) {
        latestVectorDataRef.current = emptyVisibleFeatureCollections;
        await clearVectorSources(map);
        upsertObjtypeLabelLayer(map, emptyVisibleFeatureCollections, useLayerVisibilityStore.getState().visibility);
        updateBuildingDebugMarkers(buildingMarkerStateRef.current, map, emptyFeatureCollection, false);
        if (!cancelled && requestId === visibleRequestId) {
          setError(undefined);
          closeSelectedFeatureInspectorRef.current();
          setStatus(
            `Zoom in above level ${MIN_VECTOR_ZOOM} to load vector data (current z=${map.getZoom().toFixed(1)}).`
          );
        }
        return;
      }

      try {
        const currentVisibility = useLayerVisibilityStore.getState().visibility;
        const {
          bbox,
          parcels,
          buildings,
          platformEdges,
          trackCentres,
          bygning,
          bygningOmrade,
          bygningSenterlinje,
          bygningPosisjon
        } = await getVisibleFeatureCollections(map, currentVisibility);
        if (cancelled || requestId !== visibleRequestId) {
          return;
        }

        latestVectorDataRef.current = {
          parcels,
          buildings,
          platformEdges,
          trackCentres,
          bygning,
          bygningOmrade,
          bygningSenterlinje,
          bygningPosisjon
        };
        await applyRenderedVisibleData(map, latestVectorDataRef.current, currentVisibility);
        setError(undefined);
        setStatus(
          `Loaded ${parcels.features.length} parcels, ${buildings.features.length} buildings, ${platformEdges.features.length} platform edges, ${trackCentres.features.length} track centres, ${bygning.features.length} Bygning line features, ${bygningOmrade.features.length} Bygning area features, ${bygningSenterlinje.features.length} Bygning centerline features, and ${bygningPosisjon.features.length} Bygning position features for bbox ${bbox.map(value => value.toFixed(5)).join(',')}.${activeFeatureFilterRef.current ? ` Rendering only ${activeFeatureFilterRef.current.propertyKey} "${activeFeatureFilterRef.current.value}".` : ''}${isBuildingZoom(map) ? '' : ` Building layers load from zoom ${MIN_BUILDING_ZOOM}.`}`
        );
      } catch (cause) {
        if (!cancelled && requestId === visibleRequestId) {
          setError(cause instanceof Error ? cause.message : 'Unknown error');
          setStatus('Could not reload visible map data');
        }
      }
    }

    reloadVisibleDataRef.current = reloadVisibleData;

    function scheduleVisibleDataReload() {
      if (pendingReloadTimeoutRef.current !== undefined) {
        window.clearTimeout(pendingReloadTimeoutRef.current);
      }

      pendingReloadTimeoutRef.current = window.setTimeout(() => {
        pendingReloadTimeoutRef.current = undefined;
        applyObjtypeLabelVisibility(map, !is3dRef.current && map.getZoom() > OBJTYPE_LABEL_MIN_ZOOM);
        void reloadVisibleData();
      }, 120);
    }

    function handleMoveStart() {
      cancelPendingMapWork();
    }

    map.once('load', () => {
      addNativeFeatureSourcesAndLayers(
        map,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        useLayerVisibilityStore.getState().visibility,
        adjustElevatedHeightsRef.current,
        false
      );
      upsertObjtypeLabelLayer(map, emptyVisibleFeatureCollections, useLayerVisibilityStore.getState().visibility);
      applyObjtypeLabelVisibility(map, !is3dRef.current && map.getZoom() > OBJTYPE_LABEL_MIN_ZOOM);
      updateBuildingDebugMarkers(buildingMarkerState, map, emptyFeatureCollection, false);
      map.on('movestart', handleMoveStart);
      map.on('moveend', scheduleVisibleDataReload);

      map.on('click', event => {
        const inspectedFeature = inspectFeaturesAtPoint(map, event.point);
        if (!inspectedFeature) {
          closeSelectedFeatureInspectorRef.current();
          return;
        }

        setSelectedFeatureRef.current(inspectedFeature);
      });
      map.on('mousemove', event => {
        map.getCanvas().style.cursor = hasInspectableFeatureAtPoint(map, event.point) ? 'pointer' : '';
      });

      setIsMapReady(true);
      setIsVectorZoomActive(isVectorZoom(map));
      setStatus(`Zoom in above level ${MIN_VECTOR_ZOOM} to load vector data.`);
      void reloadVisibleData();
    });

    return () => {
      cancelled = true;
      visibleRequestId += 1;
      reloadVisibleDataRef.current = undefined;
      cancelPendingMapWork();
      map.off('movestart', handleMoveStart);
      map.off('moveend', scheduleVisibleDataReload);
      mapRef.current = null;
      clearBuildingDebugMarkers(buildingMarkerState);
      resizeObserver.disconnect();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyMapDimensionMode(
      map,
      is3d,
      useLayerVisibilityStore.getState().visibility,
      isTerrainEnabled(is3d, adjustElevatedHeights)
    );
    applyObjtypeLabelVisibility(map, !is3d && map.getZoom() > OBJTYPE_LABEL_MIN_ZOOM);
    setBuildingDebugMarkerVisibility(
      buildingMarkerStateRef.current,
      useLayerVisibilityStore.getState().visibility.buildings && !is3d
    );
  }, [adjustElevatedHeights, is3d, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || !isVectorZoom(map)) {
      return;
    }

    void applyRenderedVisibleData(
      map,
      latestVectorDataRef.current,
      useLayerVisibilityStore.getState().visibility,
      activeFeatureFilter
    );
  }, [activeFeatureFilter, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyMapLayerVisibility(map, is3d, layerVisibility, isTerrainEnabled(is3d, adjustElevatedHeights));
    setBuildingDebugMarkerVisibility(buildingMarkerStateRef.current, layerVisibility.buildings && !is3d);

    const visibilityChanged = layerVisibilityChanged(previousLayerVisibilityRef.current, layerVisibility);
    previousLayerVisibilityRef.current = layerVisibility;

    if (pendingElevatedRefreshTimeoutRef.current !== undefined) {
      window.clearTimeout(pendingElevatedRefreshTimeoutRef.current);
      pendingElevatedRefreshTimeoutRef.current = undefined;
    }

    if (visibilityChanged && isVectorZoom(map)) {
      void reloadVisibleDataRef.current?.();
      return;
    }

    if (!is3d) {
      return;
    }

    const latest = filterVisibleFeatureCollectionsByProperty(
      latestVectorDataRef.current,
      activeFeatureFilterRef.current
    );
    pendingElevatedRefreshTimeoutRef.current = window.setTimeout(() => {
      pendingElevatedRefreshTimeoutRef.current = undefined;
      updateElevatedFeatureSources(
        map,
        latest.platformEdges,
        latest.trackCentres,
        latest.bygning,
        latest.bygningSenterlinje,
        latest.bygningOmrade,
        layerVisibility,
        adjustElevatedHeights && is3d,
        is3d
      );
    }, DEFERRED_ELEVATED_SOURCE_DELAY_MS);
  }, [adjustElevatedHeights, layerVisibility, isMapReady, is3d]);

  async function createRandomBuilding() {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    if (!isVectorZoom(map)) {
      setError(`Zoom in above level ${MIN_VECTOR_ZOOM} before creating parcels`);
      return;
    }

    setIsCreating(true);
    setError(undefined);

    try {
      const existingParcels = await getFeatureCollection(parcelsItemsInBboxUrl(visibleOgcBbox(map)));
      const { area, building, secondaryBuilding, parcel, placementAttempts } = randomNonOverlappingBuildingAndParcel(
        map,
        existingParcels
      );
      console.info('[gcmapview] storing generated parcel/building coordinates', {
        placementAttempts,
        existingParcelCount: existingParcels.features.length,
        buildingAreaM2: area,
        secondaryBuildingAreaM2: secondaryBuilding?.area,
        parcelAreaM2: area * 15,
        buildingCoordinates: building.geometry.coordinates,
        secondaryBuildingCoordinates: secondaryBuilding?.feature.geometry.coordinates,
        parcelCoordinates: parcel.geometry.coordinates
      });
      const parcelId = await createFeature(parcelsCreateUrl, parcel);
      const buildingsToCreate = [building];
      if (secondaryBuilding) {
        buildingsToCreate.push(secondaryBuilding.feature);
      }
      await Promise.all(
        buildingsToCreate.map(feature =>
          createFeature(buildingsCreateUrl, {
            ...feature,
            properties: {
              ...feature.properties,
              ...(parcelId ? { parcel_id: parcelId } : {})
            }
          })
        )
      );

      const {
        parcels,
        buildings,
        platformEdges,
        trackCentres,
        bygning,
        bygningOmrade,
        bygningSenterlinje,
        bygningPosisjon
      } = await getVisibleFeatureCollections(map, layerVisibility);
      logLoadedCoordinates('parcels after create', parcels);
      logLoadedCoordinates('buildings after create', buildings);
      latestVectorDataRef.current = {
        parcels,
        buildings,
        platformEdges,
        trackCentres,
        bygning,
        bygningOmrade,
        bygningSenterlinje,
        bygningPosisjon
      };
      await applyRenderedVisibleData(map, latestVectorDataRef.current, layerVisibility);
      const createdStatus = `Created ${buildingsToCreate.length} building${buildingsToCreate.length === 1 ? '' : 's'} with a ${area * 15} m2 parcel after ${placementAttempts} placement attempt${placementAttempts === 1 ? '' : 's'}. ${buildings.features.length} buildings loaded.`;
      setStatus(createdStatus);
      map.once('idle', () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${createdStatus} Native source features P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendered P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`
        );
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unknown error');
      setStatus('Could not create building');
    } finally {
      setIsCreating(false);
    }
  }

  async function clearData() {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    if (!isVectorZoom(map)) {
      setError(`Zoom in above level ${MIN_VECTOR_ZOOM} before clearing data`);
      return;
    }

    setIsClearing(true);
    setError(undefined);

    try {
      const [buildings, parcels] = await Promise.all([
        getFeatureCollection(buildingsItemsUrl),
        getFeatureCollection(parcelsItemsUrl)
      ]);
      logLoadedCoordinates('buildings before clear', buildings);
      logLoadedCoordinates('parcels before clear', parcels);

      await Promise.all(
        buildings.features.map(building =>
          building.id === undefined ? Promise.resolve() : deleteFeature(buildingItemUrl(building.id))
        )
      );
      await Promise.all(
        parcels.features.map(parcel =>
          parcel.id === undefined ? Promise.resolve() : deleteFeature(parcelItemUrl(parcel.id))
        )
      );

      const {
        parcels: reloadedParcels,
        buildings: reloadedBuildings,
        platformEdges: reloadedPlatformEdges,
        trackCentres: reloadedTrackCentres,
        bygning: reloadedBygning,
        bygningOmrade: reloadedBygningOmrade,
        bygningSenterlinje: reloadedBygningSenterlinje,
        bygningPosisjon: reloadedBygningPosisjon
      } = await getVisibleFeatureCollections(map, layerVisibility);
      logLoadedCoordinates('parcels after clear', reloadedParcels);
      logLoadedCoordinates('buildings after clear', reloadedBuildings);
      latestVectorDataRef.current = {
        parcels: reloadedParcels,
        buildings: reloadedBuildings,
        platformEdges: reloadedPlatformEdges,
        trackCentres: reloadedTrackCentres,
        bygning: reloadedBygning,
        bygningOmrade: reloadedBygningOmrade,
        bygningSenterlinje: reloadedBygningSenterlinje,
        bygningPosisjon: reloadedBygningPosisjon
      };
      await applyRenderedVisibleData(map, latestVectorDataRef.current, layerVisibility);
      const clearedStatus = `Cleared ${buildings.features.length} buildings and ${parcels.features.length} parcels.`;
      setStatus(clearedStatus);
      map.once('idle', () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${clearedStatus} Native source features P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendered P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`
        );
      });
      setIsMapReady(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unknown error');
      setStatus('Could not clear data');
    } finally {
      setIsClearing(false);
    }
  }

  return (
    <section
      className="relative min-h-0 w-full overflow-hidden rounded-[min(var(--radius-4xl),24px)] border border-border bg-card shadow-sm"
      aria-label="Cadastre, FKB-Bane, and Bygning map">
      <div
        ref={mapContainerRef}
        className="absolute inset-0 h-full w-full"
      />
      <div className="absolute top-4 left-4 z-[3] flex flex-col items-start gap-2 sm:flex-row">
        <Button
          size="sm"
          disabled={!isMapReady || !isVectorZoomActive || isCreating || isClearing}
          onClick={createRandomBuilding}>
          <Plus data-icon="inline-start" />
          {isCreating ? 'Creating parcel...' : 'Create random parcel'}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          className="border-destructive/30 bg-destructive text-white shadow-md hover:bg-destructive/90 hover:text-white"
          disabled={!isMapReady || !isVectorZoomActive || isCreating || isClearing}
          onClick={clearData}>
          <Eraser data-icon="inline-start" />
          {isClearing ? 'Clearing data...' : 'Clear parcels'}
        </Button>
      </div>
      <MapLayersCard
        is3d={is3d}
        visibility={layerVisibility}
        favoriteViews={favoriteViews}
        activeFavoriteName={activeFavoriteView?.name}
        onSaveFavoriteView={saveCurrentFavoriteView}
        onClearFavoriteView={clearStoredFavoriteView}
        onSelectFavoriteView={selectStoredFavoriteView}
      />
      {selectedFeature ? (
        <FeaturePropertiesCard
          feature={selectedFeature}
          activeFeatureFilter={activeFeatureFilter}
          onApplyFeatureFilter={applyFeatureFilter}
          onClearFeatureFilter={clearFeatureFilter}
          onHoverPositionIndex={setHoveredPositionIndex}
          onClose={closeSelectedFeatureInspector}
        />
      ) : null}
      <div className="absolute bottom-4 left-4 z-[3] max-w-[min(720px,calc(100%-2rem))]">
        {error ? (
          <Alert
            variant="destructive"
            className="bg-card/95 shadow-md">
            <AlertCircle />
            <AlertTitle>{status}</AlertTitle>
            <AlertDescription>
              <code className="text-xs">{error}</code>
            </AlertDescription>
          </Alert>
        ) : (
          <div
            className={cn('rounded-2xl border border-border bg-card/95 px-3 py-2 text-sm text-foreground shadow-md')}>
            {status}
          </div>
        )}
      </div>
    </section>
  );
}

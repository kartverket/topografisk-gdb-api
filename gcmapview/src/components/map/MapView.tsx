import { useEffect, useMemo, useRef, useState } from 'react';
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
import { DEFAULT_3D_PITCH } from '../../map/map3d';
import {
  hasInspectableFeatureAtPoint,
  inspectFeaturesAtPoint,
  type ActiveFeatureFilter
} from '../../map/featureInspect';
import { filterUnavailableLayers, useLayerVisibilityStore } from '../../store/layerVisibilityStore';
import { useMapViewStore } from '../../store/mapViewStore';
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
  setVisibleFeatureCollectionSource,
  setNativeFeatureSources,
  type VisibleFeatureCollectionKey,
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
const backgroundMapLayerIds = ['kartverket-topo', 'kartverket-toporaster', 'kartverket-topograatone'] as const;

export type BackgroundMapId = 'topo' | 'toporaster' | 'topograatone' | 'none';

const mapStyle: maplibregl.StyleSpecification = {
  version: 8,
  'font-faces': {
    'Roboto Variable': robotoLatinVariableUrl
  },
  sources: {
    kartverketTopo: {
      type: 'raster',
      tiles: ['https://cache.kartverket.no/v1/wmts/1.0.0/topo/default/webmercator/{z}/{y}/{x}.png'],
      tileSize: 256,
      maxzoom: 18,
      attribution: '&copy; Kartverket'
    },
    kartverketToporaster: {
      type: 'raster',
      tiles: ['https://cache.kartverket.no/v1/wmts/1.0.0/toporaster/default/webmercator/{z}/{y}/{x}.png'],
      tileSize: 256,
      maxzoom: 18,
      attribution: '&copy; Kartverket'
    },
    kartverketTopograatone: {
      type: 'raster',
      tiles: ['https://cache.kartverket.no/v1/wmts/1.0.0/topograatone/default/webmercator/{z}/{y}/{x}.png'],
      tileSize: 256,
      maxzoom: 18,
      attribution: '&copy; Kartverket'
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
      id: 'kartverket-topo',
      type: 'raster',
      source: 'kartverketTopo'
    },
    {
      id: 'kartverket-toporaster',
      type: 'raster',
      source: 'kartverketToporaster',
      layout: {
        visibility: 'none'
      }
    },
    {
      id: 'kartverket-topograatone',
      type: 'raster',
      source: 'kartverketTopograatone',
      layout: {
        visibility: 'none'
      }
    }
  ]
};

function isTerrainEnabled(is3d: boolean, adjustElevatedHeights: boolean) {
  return is3d && !adjustElevatedHeights;
}

function applyBackgroundMap(map: maplibregl.Map, backgroundMap: BackgroundMapId) {
  for (const layerId of backgroundMapLayerIds) {
    if (!map.getLayer(layerId)) {
      continue;
    }

    const isVisible =
      (backgroundMap === 'topo' && layerId === 'kartverket-topo') ||
      (backgroundMap === 'toporaster' && layerId === 'kartverket-toporaster') ||
      (backgroundMap === 'topograatone' && layerId === 'kartverket-topograatone');
    map.setLayoutProperty(layerId, 'visibility', isVisible ? 'visible' : 'none');
  }
}

export function MapView() {
  const mapSectionRef = useRef<HTMLElement>(null);
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map>(null);
  const mapLayersPanelRef = useRef<HTMLDivElement>(null);
  const featureInspectorPanelRef = useRef<HTMLDivElement>(null);
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
  const availableLayerIds = useLayerVisibilityStore(state => state.availableLayerIds);
  const isLoadingAvailableLayers = useLayerVisibilityStore(state => state.isLoadingAvailableLayers);
  const resolveAvailableLayerIds = useLayerVisibilityStore(state => state.resolveAvailableLayerIds);
  const setLayerVisibility = useLayerVisibilityStore(state => state.setVisibility);
  const filteredLayerVisibility = useMemo(
    () => filterUnavailableLayers(layerVisibility, availableLayerIds),
    [availableLayerIds, layerVisibility]
  );
  const previousLayerVisibilityRef = useRef(filteredLayerVisibility);
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
  const [status, setStatus] = useState('Laster kart...');
  const [error, setError] = useState<string>();
  const [isMapReady, setIsMapReady] = useState(false);
  const [pendingFavoriteNavigationName, setPendingFavoriteNavigationName] = useState<string>();
  const [isVectorZoomActive, setIsVectorZoomActive] = useState(false);
  const [backgroundMap, setBackgroundMap] = useState<BackgroundMapId>('topo');
  const backgroundMapRef = useRef<BackgroundMapId>(backgroundMap);
  backgroundMapRef.current = backgroundMap;
  const [isCreating, setIsCreating] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [placeInspectorLeftOfLayers, setPlaceInspectorLeftOfLayers] = useState(false);
  const { selectedFeature, setHoveredPositionIndex, setSelectedFeature } = useSelectedFeature({ mapRef, is3d });
  const closeSelectedFeatureInspectorRef = useRef<() => void>(() => {});
  const setSelectedFeatureRef = useRef(setSelectedFeature);
  setSelectedFeatureRef.current = setSelectedFeature;

  function toggleMapDimension() {
    if (!is3d) {
      setAdjustElevatedHeights(true);
    }

    setIs3d(value => !value);
  }

  function currentFilteredLayerVisibility() {
    const state = useLayerVisibilityStore.getState();
    return filterUnavailableLayers(state.visibility, state.availableLayerIds);
  }

  useEffect(() => {
    void resolveAvailableLayerIds();
  }, [resolveAvailableLayerIds]);

  useEffect(() => {
    if (!selectedFeature) {
      setPlaceInspectorLeftOfLayers(false);
      return;
    }

    const mapSection = mapSectionRef.current;
    const mapLayersPanel = mapLayersPanelRef.current;
    const featureInspectorPanel = featureInspectorPanelRef.current;

    if (!mapSection || !mapLayersPanel || !featureInspectorPanel) {
      return;
    }

    let frame = 0;

    const updateInspectorPlacement = () => {
      frame = 0;
      const sectionRect = mapSection.getBoundingClientRect();
      const layersRect = mapLayersPanel.getBoundingClientRect();
      const inspectorRect = featureInspectorPanel.getBoundingClientRect();
      const overlapsVertically = inspectorRect.top < layersRect.bottom && layersRect.top < inspectorRect.bottom;
      const availableWidthLeftOfLayers = layersRect.left - sectionRect.left - 16;
      const canMoveLeft = window.innerWidth >= 640 && inspectorRect.width <= availableWidthLeftOfLayers;

      setPlaceInspectorLeftOfLayers(overlapsVertically && canMoveLeft);
    };

    const scheduleInspectorPlacementUpdate = () => {
      if (frame !== 0) {
        return;
      }

      frame = window.requestAnimationFrame(updateInspectorPlacement);
    };

    scheduleInspectorPlacementUpdate();

    const resizeObserver = new ResizeObserver(scheduleInspectorPlacementUpdate);
    resizeObserver.observe(mapSection);
    resizeObserver.observe(mapLayersPanel);
    resizeObserver.observe(featureInspectorPanel);
    window.addEventListener('resize', scheduleInspectorPlacementUpdate);

    return () => {
      if (frame !== 0) {
        window.cancelAnimationFrame(frame);
      }

      resizeObserver.disconnect();
      window.removeEventListener('resize', scheduleInspectorPlacementUpdate);
    };
  }, [selectedFeature]);

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

  useEffect(() => {
    if (!pendingFavoriteNavigationName || activeFavoriteView?.name !== pendingFavoriteNavigationName) {
      return;
    }

    const map = mapRef.current;
    if (!map) {
      return;
    }

    if (activeFavoriteView.is3d !== undefined && activeFavoriteView.is3d !== is3d) {
      return;
    }

    if (
      activeFavoriteView.adjustElevatedHeights !== undefined &&
      activeFavoriteView.adjustElevatedHeights !== adjustElevatedHeights
    ) {
      return;
    }

    const targetPitch = activeFavoriteView.is3d ? Math.max(map.getPitch(), DEFAULT_3D_PITCH) : 0;
    const frame = window.requestAnimationFrame(() => {
      map.easeTo({
        center: activeFavoriteView.center,
        zoom: activeFavoriteView.zoom,
        pitch: targetPitch,
        duration: 700
      });
      setPendingFavoriteNavigationName(undefined);
      setStatus(`Valgte favoritt «${activeFavoriteView.name}», gjenopprettet lagene og flyttet kartet dit.`);
    });

    return () => {
      window.cancelAnimationFrame(frame);
    };
  }, [activeFavoriteView, adjustElevatedHeights, is3d, pendingFavoriteNavigationName]);

  function saveCurrentFavoriteView() {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    const suggestedName = activeFavoriteName ?? `Favoritt ${favoriteViews.length + 1}`;
    const rawName = window.prompt('Navn på favorittsted:', suggestedName);
    if (rawName === null) {
      return;
    }

    const favoriteName = rawName.trim();
    if (!favoriteName) {
      setStatus('Favorittstedet ble ikke lagret fordi det manglet navn.');
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
      `${existed ? 'Oppdaterte' : 'Lagret'} favoritt «${favoriteName}» på ${savedCenter[0].toFixed(5)}, ${savedCenter[1].toFixed(5)} (z=${savedZoom.toFixed(2)}) med gjeldende lag.`
    );
  }

  function clearStoredFavoriteView() {
    if (!activeFavoriteView) {
      return;
    }

    removeFavoriteView(activeFavoriteView.name);
    setStatus(`Slettet favoritt «${activeFavoriteView.name}».`);
  }

  function selectStoredFavoriteView(name: string) {
    const map = mapRef.current;
    const selectedFavoriteView = favoriteViews.find(favoriteView => favoriteView.name === name);

    selectFavoriteView(name);

    if (map && selectedFavoriteView) {
      setError(undefined);
      setPendingFavoriteNavigationName(name);
      setStatus(`Valgte favoritt «${name}», gjenoppretter lag og kameramodus før kartet flyttes.`);
      return;
    }

    setStatus(`Valgte favoritt «${name}».`);
  }

  function applyFeatureFilter(featureFilter: ActiveFeatureFilter) {
    const propertyKey = featureFilter.propertyKey.trim();
    const value = featureFilter.value.trim();
    if (!propertyKey || !value) {
      return;
    }

    setError(undefined);
    setActiveFeatureFilter({ propertyKey, value });
    setStatus(`Filtrerer synlige lag på ${propertyKey} «${value}».`);
  }

  function clearFeatureFilter() {
    if (!activeFeatureFilterRef.current) {
      return;
    }

    const clearedFeatureFilter = activeFeatureFilterRef.current;
    setError(undefined);
    setActiveFeatureFilter(undefined);
    setStatus(`Fjernet filteret ${clearedFeatureFilter.propertyKey} «${clearedFeatureFilter.value}».`);
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
  }

  useEffect(() => {
    if (!mapContainerRef.current) {
      return;
    }

    let cancelled = false;
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
      setError(event.error?.message ?? 'Ukjent MapLibre-feil');
      setStatus('MapLibre feilet under lasting av kartstil eller lag');
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.FullscreenControl(), 'top-right');
    map.addControl(new maplibregl.GlobeControl(), 'top-right');
    configureInitialMapInteraction(map);

    let visibleRequestId = 0;

    function loadingStatus(
      visibleFeatureCollections: VisibleFeatureCollections,
      layerId: VisibleFeatureCollectionKey,
      buildingZoomActive: boolean
    ) {
      return `Laster kartdata fortløpende… oppdaterte ${layerId}. Nå vises ${visibleFeatureCollections.parcels.features.length} parseller, ${visibleFeatureCollections.buildings.features.length} bygninger, ${visibleFeatureCollections.platformEdges.features.length} plattformkanter, ${visibleFeatureCollections.trackCentres.features.length} spormidt, ${visibleFeatureCollections.bygning.features.length} Bygning-linjefeaturer, ${visibleFeatureCollections.bygningOmrade.features.length} Bygning-områdefeaturer, ${visibleFeatureCollections.bygningSenterlinje.features.length} Bygning-senterlinjefeaturer og ${visibleFeatureCollections.bygningPosisjon.features.length} Bygning-posisjonsfeaturer.${buildingZoomActive ? '' : ` Bygningslag lastes fra zoom ${MIN_BUILDING_ZOOM}.`}`;
    }

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
        upsertObjtypeLabelLayer(map, emptyVisibleFeatureCollections, currentFilteredLayerVisibility());
        if (!cancelled && requestId === visibleRequestId) {
          setError(undefined);
          closeSelectedFeatureInspectorRef.current();
          setStatus(
            `Zoom inn over nivå ${MIN_VECTOR_ZOOM} for å laste vektordata (nåværende z=${map.getZoom().toFixed(1)}).`
          );
        }
        return;
      }

      try {
        await useLayerVisibilityStore.getState().resolveAvailableLayerIds();
        const currentVisibility = currentFilteredLayerVisibility();
        const buildingZoomActive = isBuildingZoom(map);
        const {
          parcels,
          buildings,
          platformEdges,
          trackCentres,
          bygning,
          bygningOmrade,
          bygningSenterlinje,
          bygningPosisjon
        } = await getVisibleFeatureCollections(map, currentVisibility, async (collections, layerId) => {
          if (cancelled || requestId !== visibleRequestId) {
            return;
          }

          latestVectorDataRef.current = collections;
          const renderedCollections = filterVisibleFeatureCollectionsByProperty(
            latestVectorDataRef.current,
            activeFeatureFilterRef.current
          );
          await setVisibleFeatureCollectionSource(map, layerId, renderedCollections[layerId]);
          setStatus(loadingStatus(collections, layerId, buildingZoomActive));
        });
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
          `Lastet ${parcels.features.length} parseller, ${buildings.features.length} bygninger, ${platformEdges.features.length} plattformkanter, ${trackCentres.features.length} spormidt, ${bygning.features.length} Bygning-linjefeaturer, ${bygningOmrade.features.length} Bygning-områdefeaturer, ${bygningSenterlinje.features.length} Bygning-senterlinjefeaturer og ${bygningPosisjon.features.length} Bygning-posisjonsfeaturer. ${activeFeatureFilterRef.current ? ` Viser bare ${activeFeatureFilterRef.current.propertyKey} «${activeFeatureFilterRef.current.value}».` : ''}${buildingZoomActive ? '' : ` Bygningslag lastes fra zoom ${MIN_BUILDING_ZOOM}.`}`
        );
      } catch (cause) {
        if (!cancelled && requestId === visibleRequestId) {
          setError(cause instanceof Error ? cause.message : 'Ukjent feil');
          setStatus('Kunne ikke laste synlige kartdata på nytt');
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
      visibleRequestId += 1;
      cancelPendingMapWork();
    }

    map.once('load', () => {
      applyBackgroundMap(map, backgroundMapRef.current);
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
        currentFilteredLayerVisibility(),
        adjustElevatedHeightsRef.current,
        false
      );
      upsertObjtypeLabelLayer(map, emptyVisibleFeatureCollections, currentFilteredLayerVisibility());
      applyObjtypeLabelVisibility(map, !is3dRef.current && map.getZoom() > OBJTYPE_LABEL_MIN_ZOOM);
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
      setStatus(`Zoom inn over nivå ${MIN_VECTOR_ZOOM} for å laste vektordata.`);
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
      resizeObserver.disconnect();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyBackgroundMap(map, backgroundMap);
  }, [backgroundMap, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyMapDimensionMode(map, is3d, currentFilteredLayerVisibility(), isTerrainEnabled(is3d, adjustElevatedHeights));
    applyObjtypeLabelVisibility(map, !is3d && map.getZoom() > OBJTYPE_LABEL_MIN_ZOOM);
  }, [adjustElevatedHeights, is3d, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady || !isVectorZoom(map)) {
      return;
    }

    void applyRenderedVisibleData(
      map,
      latestVectorDataRef.current,
      currentFilteredLayerVisibility(),
      activeFeatureFilter
    );
  }, [activeFeatureFilter, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyMapLayerVisibility(map, is3d, filteredLayerVisibility, isTerrainEnabled(is3d, adjustElevatedHeights));

    const visibilityChanged = layerVisibilityChanged(previousLayerVisibilityRef.current, filteredLayerVisibility);
    previousLayerVisibilityRef.current = filteredLayerVisibility;

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
        filteredLayerVisibility,
        adjustElevatedHeights && is3d,
        is3d
      );
    }, DEFERRED_ELEVATED_SOURCE_DELAY_MS);
  }, [adjustElevatedHeights, filteredLayerVisibility, isMapReady, is3d]);

  async function createRandomBuilding() {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    if (!isVectorZoom(map)) {
      setError(`Zoom inn over nivå ${MIN_VECTOR_ZOOM} før du oppretter parseller`);
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
      } = await getVisibleFeatureCollections(map, filteredLayerVisibility);
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
      await applyRenderedVisibleData(map, latestVectorDataRef.current, filteredLayerVisibility);
      const createdStatus = `Opprettet ${buildingsToCreate.length} bygning${buildingsToCreate.length === 1 ? '' : 'er'} med en parsell på ${area * 15} m2 etter ${placementAttempts} plasseringsforsøk. ${buildings.features.length} bygninger lastet.`;
      setStatus(createdStatus);
      map.once('idle', () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${createdStatus} Native kildefeaturer P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendret P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`
        );
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ukjent feil');
      setStatus('Kunne ikke opprette bygning');
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
      setError(`Zoom inn over nivå ${MIN_VECTOR_ZOOM} før du tømmer data`);
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
      } = await getVisibleFeatureCollections(map, filteredLayerVisibility);
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
      await applyRenderedVisibleData(map, latestVectorDataRef.current, filteredLayerVisibility);
      const clearedStatus = `Tømte ${buildings.features.length} bygninger og ${parcels.features.length} parseller.`;
      setStatus(clearedStatus);
      map.once('idle', () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${clearedStatus} Native kildefeaturer P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendret P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`
        );
      });
      setIsMapReady(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ukjent feil');
      setStatus('Kunne ikke tømme data');
    } finally {
      setIsClearing(false);
    }
  }

  return (
    <section
      ref={mapSectionRef}
      className="relative min-h-0 w-full overflow-hidden rounded-[min(var(--radius-4xl),24px)] border border-border bg-card shadow-sm"
      aria-label="Matrikkel-, FKB-Bane- og Bygning-kart">
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
          {isCreating ? 'Oppretter parsell...' : 'Opprett tilfeldig parsell'}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          className="border-destructive/30 bg-destructive text-white shadow-md hover:bg-destructive/90 hover:text-white"
          disabled={!isMapReady || !isVectorZoomActive || isCreating || isClearing}
          onClick={clearData}>
          <Eraser data-icon="inline-start" />
          {isClearing ? 'Tømmer data...' : 'Tøm parseller'}
        </Button>
      </div>
      <div
        ref={mapLayersPanelRef}
        className="absolute right-12 bottom-[88px] z-[3] max-sm:top-20 max-sm:right-auto max-sm:bottom-auto max-sm:left-4">
        <MapLayersCard
          backgroundMap={backgroundMap}
          availableLayerIds={availableLayerIds}
          is3d={is3d}
          isLoadingAvailableLayers={isLoadingAvailableLayers}
          terrainEnabled={is3d && !adjustElevatedHeights}
          visibility={filteredLayerVisibility}
          favoriteViews={favoriteViews}
          activeFavoriteName={activeFavoriteView?.name}
          onSelectBackgroundMap={setBackgroundMap}
          onToggle3d={toggleMapDimension}
          onToggleTerrain={() => setAdjustElevatedHeights(value => !value)}
          onSaveFavoriteView={saveCurrentFavoriteView}
          onClearFavoriteView={clearStoredFavoriteView}
          onSelectFavoriteView={selectStoredFavoriteView}
        />
      </div>
      {selectedFeature ? (
        <div
          ref={featureInspectorPanelRef}
          className={cn(
            'absolute top-4 z-[3] max-sm:right-4 max-sm:bottom-[88px] max-sm:left-4 max-sm:top-auto',
            placeInspectorLeftOfLayers ? 'right-[272px]' : 'right-4'
          )}>
          <FeaturePropertiesCard
            feature={selectedFeature}
            activeFeatureFilter={activeFeatureFilter}
            onApplyFeatureFilter={applyFeatureFilter}
            onClearFeatureFilter={clearFeatureFilter}
            onHoverPositionIndex={setHoveredPositionIndex}
            onClose={closeSelectedFeatureInspector}
          />
        </div>
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

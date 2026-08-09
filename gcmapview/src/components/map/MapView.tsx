import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
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
import { applyMapDimensionMode, applyMapLayerVisibility, configureInitialMapInteraction } from '../../map/mapDimension';
import { useMapDimension } from './MapDimensionContext';
import { FeaturePropertiesCard } from './FeaturePropertiesCard';
import { MapLayersCard } from './MapLayersCard';
import { useLayerVisibilityStore } from '../../store/layerVisibilityStore';
import { useMapViewStore } from '../../store/mapViewStore';
import { hasInspectableFeatureAtPoint, inspectFeaturesAtPoint } from '../../map/featureInspect';
import type { FeatureCollection } from '../../map/geojson';
import { buildingCentroidsFeatureCollection, featureCentroid, logLoadedCoordinates } from './mapViewGeometry';
import { randomNonOverlappingBuildingAndParcel } from './mapViewRandomFeatures';
import {
  addNativeFeatureSourcesAndLayers,
  clearVectorSources,
  createFeature,
  deleteFeature,
  emptyFeatureCollection,
  emptyVisibleFeatureCollections,
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
  upsertGeoJsonSource,
  visibleOgcBbox
} from './mapViewData';
import { useSelectedFeature } from './useSelectedFeature';

/** Default initial view when no local favorite view has been saved. */
const OTTA_CENTER: [number, number] = [9.54, 61.77];
const OTTA_ZOOM = 15;

const mapStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 17,
      attribution: '&copy; OpenStreetMap contributors'
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

export function MapView() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map>(null);
  const buildingMarkerRefs = useRef<maplibregl.Marker[]>([]);
  const pendingReloadTimeoutRef = useRef<number | undefined>(undefined);
  const reloadVisibleDataRef = useRef<(() => Promise<void>) | undefined>(undefined);
  const { is3d, adjustElevatedHeights, setIs3d, setAdjustElevatedHeights } = useMapDimension();
  const is3dRef = useRef(is3d);
  is3dRef.current = is3d;
  const adjustElevatedHeightsRef = useRef(adjustElevatedHeights);
  adjustElevatedHeightsRef.current = adjustElevatedHeights;
  const latestVectorDataRef = useRef<VisibleFeatureCollections>(emptyVisibleFeatureCollections);
  const layerVisibility = useLayerVisibilityStore(state => state.visibility);
  const setLayerVisibility = useLayerVisibilityStore(state => state.setVisibility);
  const previousLayerVisibilityRef = useRef(layerVisibility);
  const favoriteViews = useMapViewStore(state => state.favoriteViews);
  const activeFavoriteName = useMapViewStore(state => state.activeFavoriteName);
  const saveFavoriteView = useMapViewStore(state => state.saveFavoriteView);
  const selectFavoriteView = useMapViewStore(state => state.selectFavoriteView);
  const removeFavoriteView = useMapViewStore(state => state.removeFavoriteView);
  const activeFavoriteView = favoriteViews.find(favoriteView => favoriteView.name === activeFavoriteName) ?? favoriteViews[0];
  const [status, setStatus] = useState('Loading map...');
  const [error, setError] = useState<string>();
  const [isMapReady, setIsMapReady] = useState(false);
  const [isVectorZoomActive, setIsVectorZoomActive] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const { selectedFeature, setHoveredPositionIndex, setSelectedFeature } = useSelectedFeature({ mapRef, is3d });

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

  function applyBuildingMarkerVisibility(visible: boolean) {
    for (const marker of buildingMarkerRefs.current) {
      marker.getElement().style.display = visible ? '' : 'none';
    }
  }

  function updateBuildingDebugMarkers(map: maplibregl.Map, buildings: FeatureCollection) {
    for (const marker of buildingMarkerRefs.current) {
      marker.remove();
    }

    const showMarkers = !is3dRef.current && useLayerVisibilityStore.getState().visibility.buildings;

    buildingMarkerRefs.current = buildings.features.flatMap(building => {
      const centroid = featureCentroid(building);
      if (!centroid) {
        return [];
      }

      const markerElement = document.createElement('div');
      markerElement.className =
        'h-1.5 w-1.5 rounded-full border border-white bg-black shadow-[0_0_0_1px_rgb(0_0_0/0.45)]';
      markerElement.title = `Building ${building.id ?? ''}`.trim();
      markerElement.style.display = showMarkers ? '' : 'none';

      return [
        new maplibregl.Marker({
          element: markerElement,
          anchor: 'center'
        })
          .setLngLat([centroid[0], centroid[1]])
          .addTo(map)
      ];
    });
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

  useEffect(() => {
    if (!mapContainerRef.current) {
      return;
    }

    let cancelled = false;
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapStyle,
      center: activeFavoriteView?.center ?? OTTA_CENTER,
      zoom: activeFavoriteView?.zoom ?? OTTA_ZOOM
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
      const requestId = ++visibleRequestId;
      const vectorZoomActive = isVectorZoom(map);
      setIsVectorZoomActive(vectorZoomActive);

      if (!vectorZoomActive) {
        latestVectorDataRef.current = emptyVisibleFeatureCollections;
        await clearVectorSources(map);
        updateBuildingDebugMarkers(map, emptyFeatureCollection);
        if (!cancelled && requestId === visibleRequestId) {
          setError(undefined);
          setSelectedFeature(undefined);
          setStatus(
            `Zoom in above level ${MIN_VECTOR_ZOOM} to load vector data (current z=${map.getZoom().toFixed(1)}).`
          );
        }
        return;
      }

      try {
        const currentVisibility = useLayerVisibilityStore.getState().visibility;
        const { bbox, parcels, buildings, platformEdges, trackCentres, bygning, bygningOmrade, bygningSenterlinje, bygningPosisjon } = await getVisibleFeatureCollections(
          map,
          currentVisibility
        );
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
        await setNativeFeatureSources(
          map,
          parcels,
          buildings,
          platformEdges,
          trackCentres,
          bygning,
          bygningOmrade,
          bygningSenterlinje,
          bygningPosisjon,
          currentVisibility,
          adjustElevatedHeightsRef.current
        );
        await upsertGeoJsonSource(map, 'building-centroids', buildingCentroidsFeatureCollection(buildings));
        updateBuildingDebugMarkers(map, buildings);
        setError(undefined);
        setStatus(
          `Loaded ${parcels.features.length} parcels, ${buildings.features.length} buildings, ${platformEdges.features.length} platform edges, ${trackCentres.features.length} track centres, ${bygning.features.length} Bygning line features, ${bygningOmrade.features.length} Bygning area features, ${bygningSenterlinje.features.length} Bygning centerline features, and ${bygningPosisjon.features.length} Bygning position features for bbox ${bbox.map(value => value.toFixed(5)).join(',')}.${isBuildingZoom(map) ? '' : ` Building layers load from zoom ${MIN_BUILDING_ZOOM}.`}`
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
        void reloadVisibleData();
      }, 120);
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
        adjustElevatedHeightsRef.current
      );
      updateBuildingDebugMarkers(map, emptyFeatureCollection);
      map.on('moveend', scheduleVisibleDataReload);

      map.on('click', event => {
        setSelectedFeature(inspectFeaturesAtPoint(map, event.point));
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
      if (pendingReloadTimeoutRef.current !== undefined) {
        window.clearTimeout(pendingReloadTimeoutRef.current);
        pendingReloadTimeoutRef.current = undefined;
      }
      map.off('moveend', scheduleVisibleDataReload);
      mapRef.current = null;
      for (const marker of buildingMarkerRefs.current) {
        marker.remove();
      }
      buildingMarkerRefs.current = [];
      resizeObserver.disconnect();
      map.remove();
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyMapDimensionMode(map, is3d, useLayerVisibilityStore.getState().visibility);
    applyBuildingMarkerVisibility(useLayerVisibilityStore.getState().visibility.buildings && !is3d);
  }, [is3d, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    applyMapLayerVisibility(map, is3d, layerVisibility);
    applyBuildingMarkerVisibility(layerVisibility.buildings && !is3d);

    const visibilityChanged = layerVisibilityChanged(previousLayerVisibilityRef.current, layerVisibility);
    previousLayerVisibilityRef.current = layerVisibility;

    if (visibilityChanged && isVectorZoom(map)) {
      void reloadVisibleDataRef.current?.();
      return;
    }

    const latest = latestVectorDataRef.current;
    void setNativeFeatureSources(
      map,
      latest.parcels,
      latest.buildings,
      latest.platformEdges,
      latest.trackCentres,
      latest.bygning,
      latest.bygningOmrade,
      latest.bygningSenterlinje,
      latest.bygningPosisjon,
      layerVisibility,
      adjustElevatedHeights && is3d
    );
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
      await setNativeFeatureSources(
        map,
        parcels,
        buildings,
        platformEdges,
        trackCentres,
        bygning,
        bygningOmrade,
        bygningSenterlinje,
        bygningPosisjon,
        layerVisibility,
        adjustElevatedHeights && is3d
      );
      await upsertGeoJsonSource(map, 'building-centroids', buildingCentroidsFeatureCollection(buildings));
      updateBuildingDebugMarkers(map, buildings);
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
      await setNativeFeatureSources(
        map,
        reloadedParcels,
        reloadedBuildings,
        reloadedPlatformEdges,
        reloadedTrackCentres,
        reloadedBygning,
        reloadedBygningOmrade,
        reloadedBygningSenterlinje,
        reloadedBygningPosisjon,
        layerVisibility,
        adjustElevatedHeights && is3d
      );
      await upsertGeoJsonSource(map, 'building-centroids', buildingCentroidsFeatureCollection(reloadedBuildings));
      updateBuildingDebugMarkers(map, reloadedBuildings);
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
      aria-label="Cadastre, Bane, and Bygning map">
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
          onHoverPositionIndex={setHoveredPositionIndex}
          onClose={() => setSelectedFeature(undefined)}
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

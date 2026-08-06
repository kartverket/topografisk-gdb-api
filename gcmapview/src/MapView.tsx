import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { AlertCircle, Eraser, Plus } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import {
  buildingItemUrl,
  buildingsCreateUrl,
  buildingsItemsInBboxUrl,
  buildingsItemsUrl,
  type OgcBbox,
  parcelItemUrl,
  parcelsCreateUrl,
  parcelsItemsInBboxUrl,
  parcelsItemsUrl,
  platformEdgesItemsInBboxUrl,
  trackCentresItemsInBboxUrl,
} from "./geocomponentsApi";
import {
  addBaneSourcesAndLayers,
  normalizeBaneFeatureCollection,
  wgs84BboxToBaneBbox,
} from "./baneLayers";
import {
  addExtrusionLayers,
  applyMapDimensionMode,
  configureInitialMapInteraction,
  upsertElevatedLineSources,
} from "./mapDimension";
import {
  buildingExtrusionHeightExpression,
  heightColorExpression,
} from "./map3d";
import { useMapDimension } from "./MapDimensionContext";
import type {
  Coordinates,
  Feature,
  FeatureCollection,
  Position,
} from "./geojson";

const emptyFeatureCollection: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

/** Vector features are fetched only when the map zoom is strictly above this. */
const MIN_VECTOR_ZOOM = 10;

/** Fixed initial view — do not fit the camera to loaded feature extents. */
const OSLO_CENTER: [number, number] = [10.75, 59.91];
const OSLO_ZOOM = 11;

function isVectorZoom(map: maplibregl.Map) {
  return map.getZoom() > MIN_VECTOR_ZOOM;
}

type BuildingFeature = {
  type: "Feature";
  geometry: {
    type: "MultiPolygon";
    coordinates: number[][][][];
  };
  properties: {
    use: string;
    floors: number;
    parcel_id?: string;
  };
};

type ParcelFeature = {
  type: "Feature";
  geometry: {
    type: "MultiPolygon";
    coordinates: number[][][][];
  };
  properties: {
    label: string;
    source: string;
    area_m2: number;
  };
};

const mapStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      maxzoom: 17,
      attribution: "&copy; OpenStreetMap contributors",
    },
  },
  layers: [
    {
      id: "osm",
      type: "raster",
      source: "osm",
    },
  ],
};

function collectPositions(coordinates: Coordinates, positions: Position[]) {
  if (typeof coordinates[0] === "number") {
    positions.push(coordinates as Position);
    return;
  }

  for (const child of coordinates as Coordinates[]) {
    collectPositions(child, positions);
  }
}

function featureCentroid(feature: Feature): Position | undefined {
  const positions: Position[] = [];
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) {
    return undefined;
  }

  collectPositions(coordinates, positions);
  if (positions.length === 0) {
    return undefined;
  }

  const [lngSum, latSum] = positions.reduce(
    ([lng, lat], [positionLng, positionLat]) => [
      lng + positionLng,
      lat + positionLat,
    ],
    [0, 0],
  );

  return [lngSum / positions.length, latSum / positions.length];
}

function buildingCentroidsFeatureCollection(
  buildings: FeatureCollection,
): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: buildings.features.flatMap((building) => {
      const centroid = featureCentroid(building);
      if (!centroid) {
        return [];
      }

      return [
        {
          type: "Feature",
          geometry: {
            type: "Point",
            coordinates: centroid,
          },
          properties: building.properties,
        },
      ];
    }),
  };
}

function coordinateDebugSummary(featureCollection: FeatureCollection) {
  const positions: Position[] = [];
  const geometryTypes: Record<string, number> = {};

  for (const feature of featureCollection.features) {
    const geometry = feature.geometry;
    if (!geometry) {
      geometryTypes.null = (geometryTypes.null ?? 0) + 1;
      continue;
    }

    geometryTypes[geometry.type] = (geometryTypes[geometry.type] ?? 0) + 1;
    if (geometry.coordinates) {
      collectPositions(geometry.coordinates, positions);
    }
  }

  const lngs = positions.map(([lng]) => lng);
  const lats = positions.map(([, lat]) => lat);

  return {
    featureCount: featureCollection.features.length,
    geometryTypes,
    coordinateCount: positions.length,
    lngRange:
      lngs.length > 0 ? [Math.min(...lngs), Math.max(...lngs)] : undefined,
    latRange:
      lats.length > 0 ? [Math.min(...lats), Math.max(...lats)] : undefined,
    firstFeatureCoordinates:
      featureCollection.features[0]?.geometry?.coordinates ?? undefined,
  };
}

function logLoadedCoordinates(
  label: string,
  featureCollection: FeatureCollection,
) {
  console.info(
    `[gcmapview] loaded ${label} coordinates`,
    coordinateDebugSummary(featureCollection),
  );
}

function signedRingArea(ring: Position[]) {
  return ring.reduce((sum, [x1, y1], index) => {
    const [x2, y2] = ring[(index + 1) % ring.length];
    return sum + x1 * y2 - x2 * y1;
  }, 0);
}

function normalizeRings(rings: Position[][]) {
  return rings.map((ring, index) => {
    const shouldBeCounterClockwise = index === 0;
    const isCounterClockwise = signedRingArea(ring) > 0;
    return shouldBeCounterClockwise === isCounterClockwise
      ? ring
      : [...ring].reverse();
  });
}

function normalizePolygonFeatureCollection(
  featureCollection: FeatureCollection,
): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: featureCollection.features.map((feature) => {
      const geometry = feature.geometry;
      if (!geometry?.coordinates) {
        return feature;
      }

      if (geometry.type === "Polygon") {
        return {
          ...feature,
          geometry: {
            type: "Polygon",
            coordinates: normalizeRings(geometry.coordinates as Position[][]),
          },
        };
      }

      if (geometry.type === "MultiPolygon") {
        const polygons = geometry.coordinates as Position[][][];
        if (polygons.length === 1) {
          return {
            ...feature,
            geometry: {
              type: "Polygon",
              coordinates: normalizeRings(polygons[0]),
            },
          };
        }

        return {
          ...feature,
          geometry: {
            type: "MultiPolygon",
            coordinates: polygons.map(normalizeRings),
          },
        };
      }

      return feature;
    }),
  };
}

function addNativeFeatureSourcesAndLayers(
  map: maplibregl.Map,
  parcels: FeatureCollection,
  buildings: FeatureCollection,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
) {
  map.addSource("parcels", {
    type: "geojson",
    data: normalizePolygonFeatureCollection(parcels),
  });
  map.addSource("buildings", {
    type: "geojson",
    data: normalizePolygonFeatureCollection(buildings),
  });
  map.addSource("building-centroids", {
    type: "geojson",
    data: buildingCentroidsFeatureCollection(buildings),
  });

  map.addLayer({
    id: "building-centroids-circle",
    type: "circle",
    source: "building-centroids",
    paint: {
      "circle-color": heightColorExpression(
        buildingExtrusionHeightExpression(),
      ),
      "circle-opacity": 0.8,
      "circle-radius": 3,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1,
    },
  });
  map.addLayer({
    id: "parcels-fill",
    type: "fill",
    source: "parcels",
    filter: ["==", "$type", "Polygon"],
    paint: {
      "fill-color": "#ffc040",
      "fill-opacity": 0.32,
      "fill-outline-color": "#005cff",
    },
  });
  map.addLayer({
    id: "parcels-outline",
    type: "line",
    source: "parcels",
    filter: ["==", "$type", "Polygon"],
    paint: {
      "line-color": "#ffc040",
      "line-opacity": 1,
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 14, 4],
    },
  });
  const buildingHeightColor = heightColorExpression(
    buildingExtrusionHeightExpression(),
  );
  map.addLayer({
    id: "buildings-fill",
    type: "fill",
    source: "buildings",
    filter: ["==", "$type", "Polygon"],
    paint: {
      "fill-color": buildingHeightColor,
      "fill-opacity": 0.55,
      "fill-outline-color": buildingHeightColor,
    },
  });
  map.addLayer({
    id: "buildings-outline",
    type: "line",
    source: "buildings",
    filter: ["==", "$type", "Polygon"],
    paint: {
      "line-color": buildingHeightColor,
      "line-opacity": 1,
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 14, 4],
    },
  });
  // Bane lines are read-only and drawn above cadastre fills.
  addBaneSourcesAndLayers(map, platformEdges, trackCentres);
  addExtrusionLayers(map);
  upsertElevatedLineSources(
    map,
    normalizeBaneFeatureCollection(platformEdges),
    normalizeBaneFeatureCollection(trackCentres),
  );
}

async function getFeatureCollection(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Request failed with ${response.status}`);
  }

  return (await response.json()) as FeatureCollection;
}

function visibleOgcBbox(map: maplibregl.Map): OgcBbox {
  const container = map.getContainer();
  const width = container.clientWidth;
  const height = container.clientHeight;
  const screenPoints: Array<[number, number]> = [
    [0, 0],
    [width / 2, 0],
    [width, 0],
    [width, height / 2],
    [width, height],
    [width / 2, height],
    [0, height],
    [0, height / 2],
  ];
  const coordinates = screenPoints.map(([x, y]) => map.unproject([x, y]));
  const longitudes = coordinates.map(({ lng }) => lng);
  const latitudes = coordinates.map(({ lat }) => lat);

  return [
    Math.min(...longitudes),
    Math.max(-90, Math.min(...latitudes)),
    Math.max(...longitudes),
    Math.min(90, Math.max(...latitudes)),
  ];
}

async function getVisibleFeatureCollections(map: maplibregl.Map) {
  const bbox = visibleOgcBbox(map);
  const baneBbox = wgs84BboxToBaneBbox(bbox);
  const [parcels, buildings, platformEdges, trackCentres] = await Promise.all([
    getFeatureCollection(parcelsItemsInBboxUrl(bbox)),
    getFeatureCollection(buildingsItemsInBboxUrl(bbox)),
    getFeatureCollection(platformEdgesItemsInBboxUrl(baneBbox)),
    getFeatureCollection(trackCentresItemsInBboxUrl(baneBbox)),
  ]);
  return { bbox, parcels, buildings, platformEdges, trackCentres };
}

function idFromLocation(location: string | null) {
  if (!location) {
    return undefined;
  }

  return decodeURIComponent(location.split("/").filter(Boolean).at(-1) ?? "");
}

async function createFeature(
  url: string,
  feature: BuildingFeature | ParcelFeature,
) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "content-type": "application/geo+json",
    },
    body: JSON.stringify(feature),
  });

  if (!response.ok) {
    throw new Error(`Create failed with ${response.status}`);
  }

  const locationId = idFromLocation(response.headers.get("location"));
  if (locationId) {
    return locationId;
  }

  const body = (await response.text()).trim();
  if (!body) {
    return undefined;
  }

  try {
    const parsed = JSON.parse(body) as unknown;
    if (typeof parsed === "string") {
      return parsed;
    }
    if (parsed && typeof parsed === "object" && "id" in parsed) {
      return String((parsed as { id: unknown }).id);
    }
  } catch {
    return body.replace(/^"|"$/g, "");
  }

  return undefined;
}

async function deleteFeature(url: string) {
  const response = await fetch(url, { method: "DELETE" });
  if (!response.ok && response.status !== 404) {
    throw new Error(`Delete failed with ${response.status}`);
  }
}

function randomBetween(min: number, max: number) {
  return min + Math.random() * (max - min);
}

function randomInt(min: number, max: number) {
  return Math.floor(randomBetween(min, max + 1));
}

type Offset = [number, number];

function offsetPolygonArea(offsets: Offset[]) {
  const doubledArea = offsets.reduce((sum, [x1, y1], index) => {
    const [x2, y2] = offsets[(index + 1) % offsets.length];
    return sum + x1 * y2 - x2 * y1;
  }, 0);

  return Math.abs(doubledArea) / 2;
}

function scaleOffsetsToArea(offsets: Offset[], targetAreaM2: number) {
  const currentArea = offsetPolygonArea(offsets);
  const scale = currentArea > 0 ? Math.sqrt(targetAreaM2 / currentArea) : 1;
  return offsets.map(([x, y]): Offset => [x * scale, y * scale]);
}

function rotateOffsets(offsets: Offset[], angle: number) {
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  return offsets.map(
    ([x, y]): Offset => [x * cosine - y * sine, x * sine + y * cosine],
  );
}

function parcelOffsets(targetAreaM2: number) {
  const minPoints = 7;
  const maxPoints = 16;
  const pointCount = randomInt(minPoints, maxPoints);
  const baseRadius = Math.sqrt(targetAreaM2 / Math.PI);
  const aspectRatio = randomBetween(0.7, 1.5);
  const offsets = Array.from({ length: pointCount }, (_, index): Offset => {
    const angle =
      (index / pointCount) * Math.PI * 2 +
      randomBetween(-Math.PI / pointCount / 3, Math.PI / pointCount / 3);
    const radius = baseRadius * randomBetween(0.82, 1.18);
    return [Math.cos(angle) * radius * aspectRatio, Math.sin(angle) * radius];
  }).sort(([xA, yA], [xB, yB]) => Math.atan2(yA, xA) - Math.atan2(yB, xB));

  return rotateOffsets(
    scaleOffsetsToArea(offsets, targetAreaM2),
    randomBetween(0, Math.PI),
  );
}

function buildingOffsets(targetAreaM2: number) {
  const aspectRatio = randomBetween(1.2, 2.4);
  const width = Math.sqrt(targetAreaM2 * aspectRatio);
  const height = targetAreaM2 / width;
  let offsets: Offset[];

  if (Math.random() < 0.45) {
    offsets = [
      [-width / 2, -height / 2],
      [width / 2, -height / 2],
      [width / 2, -height * 0.05],
      [width * 0.15, -height * 0.05],
      [width * 0.15, height / 2],
      [-width / 2, height / 2],
    ];
  } else {
    const chamfer = Math.min(width, height) * randomBetween(0.12, 0.24);
    offsets = [
      [-width / 2 + chamfer, -height / 2],
      [width / 2 - chamfer, -height / 2],
      [width / 2, -height / 2 + chamfer],
      [width / 2, height / 2 - chamfer],
      [width / 2 - chamfer, height / 2],
      [-width / 2 + chamfer, height / 2],
      [-width / 2, height / 2 - chamfer],
      [-width / 2, -height / 2 + chamfer],
    ];
  }

  return rotateOffsets(
    scaleOffsetsToArea(offsets, targetAreaM2),
    randomBetween(0, Math.PI),
  );
}

function offsetsToRing(
  offsets: Offset[],
  lng: number,
  lat: number,
  metersPerDegreeLng: number,
  metersPerDegreeLat: number,
) {
  const ring = offsets.map(([x, y]) => [
    lng + x / metersPerDegreeLng,
    lat + y / metersPerDegreeLat,
  ]);

  return [...ring, ring[0]];
}

function randomBuildingAndParcelInView(map: maplibregl.Map): {
  area: number;
  building: BuildingFeature;
  secondaryBuilding?: {
    area: number;
    feature: BuildingFeature;
  };
  parcel: ParcelFeature;
} {
  const bounds = map.getBounds();
  const west = bounds.getWest();
  const east = bounds.getEast();
  const south = bounds.getSouth();
  const north = bounds.getNorth();
  const lng = randomBetween(west, east);
  const lat = randomBetween(south, north);
  const area = Math.round(randomBetween(20, 200));
  const parcelArea = area * 15;
  const metersPerDegreeLat = 111_320;
  const metersPerDegreeLng = Math.max(
    metersPerDegreeLat * Math.cos((lat * Math.PI) / 180),
    1,
  );
  const buildingRing = offsetsToRing(
    buildingOffsets(area),
    lng,
    lat,
    metersPerDegreeLng,
    metersPerDegreeLat,
  );
  const parcelRing = offsetsToRing(
    parcelOffsets(parcelArea),
    lng,
    lat,
    metersPerDegreeLng,
    metersPerDegreeLat,
  );
  const shouldAddSecondaryBuilding = Math.random() < 0.55;
  const secondaryArea = Math.max(
    10,
    Math.round(area * randomBetween(0.2, 0.5)),
  );
  const parcelRadius = Math.sqrt(parcelArea / Math.PI);
  const secondaryAngle = randomBetween(0, Math.PI * 2);
  const secondaryDistance = parcelRadius * randomBetween(0.3, 0.48);
  const secondaryLng =
    lng + (Math.cos(secondaryAngle) * secondaryDistance) / metersPerDegreeLng;
  const secondaryLat =
    lat + (Math.sin(secondaryAngle) * secondaryDistance) / metersPerDegreeLat;
  const secondaryRing = offsetsToRing(
    buildingOffsets(secondaryArea),
    secondaryLng,
    secondaryLat,
    metersPerDegreeLng,
    metersPerDegreeLat,
  );

  return {
    area,
    building: {
      type: "Feature",
      geometry: {
        type: "MultiPolygon",
        coordinates: [[buildingRing]],
      },
      properties: {
        use: "random",
        floors: Math.floor(randomBetween(1, 5)),
      },
    },
    secondaryBuilding: shouldAddSecondaryBuilding
      ? {
          area: secondaryArea,
          feature: {
            type: "Feature",
            geometry: {
              type: "MultiPolygon",
              coordinates: [[secondaryRing]],
            },
            properties: {
              use: "outbuilding",
              floors: 1,
            },
          },
        }
      : undefined,
    parcel: {
      type: "Feature",
      geometry: {
        type: "MultiPolygon",
        coordinates: [[parcelRing]],
      },
      properties: {
        label: `Parcel ${Date.now()}`,
        source: "gcmapview",
        area_m2: parcelArea,
      },
    },
  };
}

type FeatureRectangle = {
  west: number;
  south: number;
  east: number;
  north: number;
};

function featureRectangle(
  feature: Feature | ParcelFeature,
): FeatureRectangle | undefined {
  const coordinates = feature.geometry?.coordinates;
  if (!coordinates) {
    return undefined;
  }

  const positions: Position[] = [];
  collectPositions(coordinates as Coordinates, positions);
  if (positions.length === 0) {
    return undefined;
  }

  const longitudes = positions.map(([longitude]) => longitude);
  const latitudes = positions.map(([, latitude]) => latitude);
  return {
    west: Math.min(...longitudes),
    south: Math.min(...latitudes),
    east: Math.max(...longitudes),
    north: Math.max(...latitudes),
  };
}

function rectanglesOverlap(first: FeatureRectangle, second: FeatureRectangle) {
  return !(
    first.east <= second.west ||
    first.west >= second.east ||
    first.north <= second.south ||
    first.south >= second.north
  );
}

function randomNonOverlappingBuildingAndParcel(
  map: maplibregl.Map,
  existingParcels: FeatureCollection,
) {
  const existingRectangles = existingParcels.features
    .map(featureRectangle)
    .filter((rectangle): rectangle is FeatureRectangle => Boolean(rectangle));

  for (let attempt = 1; attempt <= 80; attempt += 1) {
    const candidate = randomBuildingAndParcelInView(map);
    const candidateRectangle = featureRectangle(candidate.parcel);
    if (
      candidateRectangle &&
      existingRectangles.every(
        (existingRectangle) =>
          !rectanglesOverlap(candidateRectangle, existingRectangle),
      )
    ) {
      return { ...candidate, placementAttempts: attempt };
    }
  }

  throw new Error(
    "No non-overlapping parcel placement found in the current map view",
  );
}

async function upsertGeoJsonSource(
  map: maplibregl.Map,
  sourceId: string,
  data: FeatureCollection,
) {
  const source = map.getSource(sourceId) as
    | maplibregl.GeoJSONSource
    | undefined;

  if (source) {
    source.setData(data);
    return;
  }

  map.addSource(sourceId, {
    type: "geojson",
    data,
  });
}

async function setNativeFeatureSources(
  map: maplibregl.Map,
  parcels: FeatureCollection,
  buildings: FeatureCollection,
  platformEdges: FeatureCollection,
  trackCentres: FeatureCollection,
) {
  const normalizedPlatformEdges = normalizeBaneFeatureCollection(platformEdges);
  const normalizedTrackCentres = normalizeBaneFeatureCollection(trackCentres);
  await Promise.all([
    upsertGeoJsonSource(
      map,
      "parcels",
      normalizePolygonFeatureCollection(parcels),
    ),
    upsertGeoJsonSource(
      map,
      "buildings",
      normalizePolygonFeatureCollection(buildings),
    ),
    upsertGeoJsonSource(map, "bane-platform-edges", normalizedPlatformEdges),
    upsertGeoJsonSource(map, "bane-track-centres", normalizedTrackCentres),
  ]);
  upsertElevatedLineSources(
    map,
    normalizedPlatformEdges,
    normalizedTrackCentres,
  );
}

async function clearVectorSources(map: maplibregl.Map) {
  await setNativeFeatureSources(
    map,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
    emptyFeatureCollection,
  );
  await upsertGeoJsonSource(map, "building-centroids", emptyFeatureCollection);
}

function logNativeRenderingState(map: maplibregl.Map) {
  const state = {
    parcelsSourceLoaded: map.isSourceLoaded("parcels"),
    buildingsSourceLoaded: map.isSourceLoaded("buildings"),
    parcelSourceFeatures: map.querySourceFeatures("parcels").length,
    buildingSourceFeatures: map.querySourceFeatures("buildings").length,
    parcelRenderedFeatures: map.queryRenderedFeatures({
      layers: ["parcels-fill", "parcels-outline"],
    }).length,
    buildingRenderedFeatures: map.queryRenderedFeatures({
      layers: ["buildings-fill", "buildings-outline"],
    }).length,
  };

  console.info(
    "[gcmapview] native MapLibre rendering state",
    JSON.stringify(state),
  );
  return state;
}

export function MapView() {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map>(null);
  const buildingMarkerRefs = useRef<maplibregl.Marker[]>([]);
  const { is3d } = useMapDimension();
  const [status, setStatus] = useState("Loading map...");
  const [error, setError] = useState<string>();
  const [isMapReady, setIsMapReady] = useState(false);
  const [isVectorZoomActive, setIsVectorZoomActive] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [isClearing, setIsClearing] = useState(false);

  function updateBuildingDebugMarkers(
    map: maplibregl.Map,
    buildings: FeatureCollection,
  ) {
    for (const marker of buildingMarkerRefs.current) {
      marker.remove();
    }

    buildingMarkerRefs.current = buildings.features.flatMap((building) => {
      const centroid = featureCentroid(building);
      if (!centroid) {
        return [];
      }

      const markerElement = document.createElement("div");
      markerElement.className =
        "h-1.5 w-1.5 rounded-full border border-white bg-[#006eff] shadow-[0_0_0_1px_rgb(0_110_255/0.45)]";
      markerElement.title = `Building ${building.id ?? ""}`.trim();

      return [
        new maplibregl.Marker({
          element: markerElement,
          anchor: "center",
        })
          .setLngLat([centroid[0], centroid[1]])
          .addTo(map),
      ];
    });
  }

  useEffect(() => {
    if (!mapContainerRef.current) {
      return;
    }

    let cancelled = false;
    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: mapStyle,
      center: OSLO_CENTER,
      zoom: OSLO_ZOOM,
    });
    mapRef.current = map;
    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(mapContainerRef.current);

    map.on("error", (event) => {
      console.error("[gcmapview] MapLibre error", event.error);
      setError(event.error?.message ?? "Unknown MapLibre error");
      setStatus("MapLibre failed while loading the map style or layers");
    });

    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.addControl(new maplibregl.FullscreenControl(), "top-right");
    map.addControl(new maplibregl.GlobeControl(), "top-right");
    configureInitialMapInteraction(map);

    let visibleRequestId = 0;
    async function reloadVisibleData() {
      const requestId = ++visibleRequestId;
      const vectorZoomActive = isVectorZoom(map);
      setIsVectorZoomActive(vectorZoomActive);

      if (!vectorZoomActive) {
        await clearVectorSources(map);
        updateBuildingDebugMarkers(map, emptyFeatureCollection);
        if (!cancelled && requestId === visibleRequestId) {
          setError(undefined);
          setStatus(
            `Zoom in above level ${MIN_VECTOR_ZOOM} to load vector data (current z=${map.getZoom().toFixed(1)}).`,
          );
        }
        return;
      }

      try {
        const { bbox, parcels, buildings, platformEdges, trackCentres } =
          await getVisibleFeatureCollections(map);
        if (cancelled || requestId !== visibleRequestId) {
          return;
        }

        await setNativeFeatureSources(
          map,
          parcels,
          buildings,
          platformEdges,
          trackCentres,
        );
        await upsertGeoJsonSource(
          map,
          "building-centroids",
          buildingCentroidsFeatureCollection(buildings),
        );
        updateBuildingDebugMarkers(map, buildings);
        setError(undefined);
        setStatus(
          `Loaded ${parcels.features.length} parcels, ${buildings.features.length} buildings, ${platformEdges.features.length} platform edges, and ${trackCentres.features.length} track centres for bbox ${bbox.map((value) => value.toFixed(5)).join(",")}.`,
        );
      } catch (cause) {
        if (!cancelled && requestId === visibleRequestId) {
          setError(cause instanceof Error ? cause.message : "Unknown error");
          setStatus("Could not reload visible map data");
        }
      }
    }

    map.once("load", () => {
      addNativeFeatureSourcesAndLayers(
        map,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
        emptyFeatureCollection,
      );
      updateBuildingDebugMarkers(map, emptyFeatureCollection);
      map.on("moveend", reloadVisibleData);
      setIsMapReady(true);
      setIsVectorZoomActive(isVectorZoom(map));
      setStatus(`Zoom in above level ${MIN_VECTOR_ZOOM} to load vector data.`);
      void reloadVisibleData();
    });

    return () => {
      cancelled = true;
      visibleRequestId += 1;
      map.off("moveend", reloadVisibleData);
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

    applyMapDimensionMode(map, is3d);
    if (is3d) {
      for (const marker of buildingMarkerRefs.current) {
        marker.remove();
      }
      buildingMarkerRefs.current = [];
    }
  }, [is3d, isMapReady]);

  async function createRandomBuilding() {
    const map = mapRef.current;
    if (!map) {
      return;
    }
    if (!isVectorZoom(map)) {
      setError(
        `Zoom in above level ${MIN_VECTOR_ZOOM} before creating parcels`,
      );
      return;
    }

    setIsCreating(true);
    setError(undefined);

    try {
      const existingParcels = await getFeatureCollection(
        parcelsItemsInBboxUrl(visibleOgcBbox(map)),
      );
      const { area, building, secondaryBuilding, parcel, placementAttempts } =
        randomNonOverlappingBuildingAndParcel(map, existingParcels);
      console.info(
        "[gcmapview] storing generated parcel/building coordinates",
        {
          placementAttempts,
          existingParcelCount: existingParcels.features.length,
          buildingAreaM2: area,
          secondaryBuildingAreaM2: secondaryBuilding?.area,
          parcelAreaM2: area * 15,
          buildingCoordinates: building.geometry.coordinates,
          secondaryBuildingCoordinates:
            secondaryBuilding?.feature.geometry.coordinates,
          parcelCoordinates: parcel.geometry.coordinates,
        },
      );
      const parcelId = await createFeature(parcelsCreateUrl, parcel);
      const buildingsToCreate = [building];
      if (secondaryBuilding) {
        buildingsToCreate.push(secondaryBuilding.feature);
      }
      await Promise.all(
        buildingsToCreate.map((feature) =>
          createFeature(buildingsCreateUrl, {
            ...feature,
            properties: {
              ...feature.properties,
              ...(parcelId ? { parcel_id: parcelId } : {}),
            },
          }),
        ),
      );

      const { parcels, buildings, platformEdges, trackCentres } =
        await getVisibleFeatureCollections(map);
      logLoadedCoordinates("parcels after create", parcels);
      logLoadedCoordinates("buildings after create", buildings);
      await setNativeFeatureSources(
        map,
        parcels,
        buildings,
        platformEdges,
        trackCentres,
      );
      await upsertGeoJsonSource(
        map,
        "building-centroids",
        buildingCentroidsFeatureCollection(buildings),
      );
      updateBuildingDebugMarkers(map, buildings);
      const createdStatus = `Created ${buildingsToCreate.length} building${buildingsToCreate.length === 1 ? "" : "s"} with a ${area * 15} m2 parcel after ${placementAttempts} placement attempt${placementAttempts === 1 ? "" : "s"}. ${buildings.features.length} buildings loaded.`;
      setStatus(createdStatus);
      map.once("idle", () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${createdStatus} Native source features P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendered P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`,
        );
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unknown error");
      setStatus("Could not create building");
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
        getFeatureCollection(parcelsItemsUrl),
      ]);
      logLoadedCoordinates("buildings before clear", buildings);
      logLoadedCoordinates("parcels before clear", parcels);

      await Promise.all(
        buildings.features.map((building) =>
          building.id === undefined
            ? Promise.resolve()
            : deleteFeature(buildingItemUrl(building.id)),
        ),
      );
      await Promise.all(
        parcels.features.map((parcel) =>
          parcel.id === undefined
            ? Promise.resolve()
            : deleteFeature(parcelItemUrl(parcel.id)),
        ),
      );

      const {
        parcels: reloadedParcels,
        buildings: reloadedBuildings,
        platformEdges: reloadedPlatformEdges,
        trackCentres: reloadedTrackCentres,
      } = await getVisibleFeatureCollections(map);
      logLoadedCoordinates("parcels after clear", reloadedParcels);
      logLoadedCoordinates("buildings after clear", reloadedBuildings);
      await setNativeFeatureSources(
        map,
        reloadedParcels,
        reloadedBuildings,
        reloadedPlatformEdges,
        reloadedTrackCentres,
      );
      await upsertGeoJsonSource(
        map,
        "building-centroids",
        buildingCentroidsFeatureCollection(reloadedBuildings),
      );
      updateBuildingDebugMarkers(map, reloadedBuildings);
      const clearedStatus = `Cleared ${buildings.features.length} buildings and ${parcels.features.length} parcels.`;
      setStatus(clearedStatus);
      map.once("idle", () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${clearedStatus} Native source features P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendered P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`,
        );
      });
      setIsMapReady(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unknown error");
      setStatus("Could not clear data");
    } finally {
      setIsClearing(false);
    }
  }

  return (
    <section
      className="relative min-h-0 w-full overflow-hidden rounded-[min(var(--radius-4xl),24px)] border border-border bg-card shadow-sm"
      aria-label="Cadastre and Bane map"
    >
      <div ref={mapContainerRef} className="absolute inset-0 h-full w-full" />
      <div className="absolute top-4 left-4 z-[3] flex flex-col items-start gap-2 sm:flex-row">
        <Button
          size="sm"
          disabled={
            !isMapReady || !isVectorZoomActive || isCreating || isClearing
          }
          onClick={createRandomBuilding}
        >
          <Plus data-icon="inline-start" />
          {isCreating ? "Creating parcel..." : "Create random parcel"}
        </Button>
        <Button
          size="sm"
          variant="destructive"
          disabled={
            !isMapReady || !isVectorZoomActive || isCreating || isClearing
          }
          onClick={clearData}
        >
          <Eraser data-icon="inline-start" />
          {isClearing ? "Clearing data..." : "Clear data"}
        </Button>
      </div>
      <Card
        size="sm"
        className="absolute right-4 bottom-[88px] z-[3] w-[220px] bg-card/95 shadow-md max-sm:top-20 max-sm:right-auto max-sm:bottom-auto max-sm:left-4"
        aria-label="Map layers"
      >
        <CardHeader className="pb-0">
          <CardTitle>Layers</CardTitle>
          <CardDescription>
            Height colour: blue 0 m → red 300 m+
            {!is3d ? " · Bane read-only" : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Separator />
          <div className="space-y-1">
            <div
              className="h-2.5 w-full rounded-full"
              style={{
                background:
                  "linear-gradient(to right, hsl(240 85% 45%), hsl(120 85% 45%), hsl(0 85% 45%))",
              }}
              aria-hidden
            />
            <div className="flex justify-between text-[11px] text-muted-foreground">
              <span>0 m</span>
              <span>300 m+</span>
            </div>
          </div>
          <ul className="m-0 space-y-2 p-0 text-sm text-muted-foreground">
            <li className="flex items-center gap-2">
              <span className="inline-block h-2.5 w-4 shrink-0 rounded-full bg-[#ffc040] opacity-80" />
              Cadastre parcels
            </li>
            <li className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-4 shrink-0 rounded-full opacity-80"
                style={{
                  background:
                    "linear-gradient(to right, hsl(240 85% 45%), hsl(0 85% 45%))",
                }}
              />
              Cadastre buildings
            </li>
            <li className="flex items-center gap-2">
              <span
                className="inline-block h-1 w-4 shrink-0 rounded-full"
                style={{
                  background:
                    "linear-gradient(to right, hsl(240 85% 45%), hsl(0 85% 45%))",
                }}
              />
              Bane platform edges
              <Badge variant="outline" className="ml-auto">
                RO
              </Badge>
            </li>
            <li className="flex items-center gap-2">
              <span
                className="inline-block h-1 w-4 shrink-0 rounded-full"
                style={{
                  background:
                    "linear-gradient(to right, hsl(240 85% 45%), hsl(0 85% 45%))",
                }}
              />
              Bane track centres
              <Badge variant="outline" className="ml-auto">
                RO
              </Badge>
            </li>
          </ul>
        </CardContent>
      </Card>
      <div className="absolute bottom-4 left-4 z-[3] max-w-[min(720px,calc(100%-2rem))]">
        {error ? (
          <Alert variant="destructive" className="bg-card/95 shadow-md">
            <AlertCircle />
            <AlertTitle>{status}</AlertTitle>
            <AlertDescription>
              <code className="text-xs">{error}</code>
            </AlertDescription>
          </Alert>
        ) : (
          <div
            className={cn(
              "rounded-2xl border border-border bg-card/95 px-3 py-2 text-sm text-foreground shadow-md",
            )}
          >
            {status}
          </div>
        )}
      </div>
    </section>
  );
}

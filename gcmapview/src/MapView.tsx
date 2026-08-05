import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
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
} from "./geocomponentsApi";

type Position = [number, number, ...number[]];
type Coordinates = Position | Coordinates[];

type Feature = {
  id?: string | number;
  type: "Feature";
  geometry: {
    type: string;
    coordinates?: Coordinates;
  } | null;
  properties?: Record<string, unknown> | null;
};

type FeatureCollection = {
  type: "FeatureCollection";
  features: Feature[];
};

const emptyFeatureCollection: FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};

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

function extendBounds(
  bounds: maplibregl.LngLatBounds,
  coordinates: Coordinates,
) {
  if (typeof coordinates[0] === "number") {
    const [lng, lat] = coordinates as Position;
    bounds.extend([lng, lat]);
    return;
  }

  for (const child of coordinates as Coordinates[]) {
    extendBounds(bounds, child);
  }
}

function featureBounds(featureCollection: FeatureCollection) {
  const bounds = new maplibregl.LngLatBounds();

  for (const feature of featureCollection.features) {
    const coordinates = feature.geometry?.coordinates;
    if (coordinates) {
      extendBounds(bounds, coordinates);
    }
  }

  return bounds.isEmpty() ? undefined : bounds;
}

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

function logLayerState(map: maplibregl.Map) {
  console.info("[gcmapview] map layer/source state", {
    parcelsSource: Boolean(map.getSource("parcels")),
    buildingsSource: Boolean(map.getSource("buildings")),
    buildingCentroidsSource: Boolean(map.getSource("building-centroids")),
    parcelsFillLayer: Boolean(map.getLayer("parcels-fill")),
    parcelsOutlineLayer: Boolean(map.getLayer("parcels-outline")),
    buildingsFillLayer: Boolean(map.getLayer("buildings-fill")),
    buildingsOutlineLayer: Boolean(map.getLayer("buildings-outline")),
    buildingCentroidsLayer: Boolean(map.getLayer("building-centroids-circle")),
  });
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
      "circle-color": "#006eff",
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
  map.addLayer({
    id: "buildings-fill",
    type: "fill",
    source: "buildings",
    filter: ["==", "$type", "Polygon"],
    paint: {
      "fill-color": "#2563eb",
      "fill-opacity": 0.55,
      "fill-outline-color": "#003cff",
    },
  });
  map.addLayer({
    id: "buildings-outline",
    type: "line",
    source: "buildings",
    filter: ["==", "$type", "Polygon"],
    paint: {
      "line-color": "#003cff",
      "line-opacity": 1,
      "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 14, 4],
    },
  });
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
  const [parcels, buildings] = await Promise.all([
    getFeatureCollection(parcelsItemsInBboxUrl(bbox)),
    getFeatureCollection(buildingsItemsInBboxUrl(bbox)),
  ]);
  return { bbox, parcels, buildings };
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

function rectanglesOverlap(
  first: FeatureRectangle,
  second: FeatureRectangle,
) {
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

async function setNativePolygonSources(
  map: maplibregl.Map,
  parcels: FeatureCollection,
  buildings: FeatureCollection,
) {
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
  ]);
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
  const [status, setStatus] = useState("Loading data from geocomponents...");
  const [error, setError] = useState<string>();
  const [isMapReady, setIsMapReady] = useState(false);
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
      markerElement.className = "building-debug-marker";
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
      center: [10.75, 59.91],
      zoom: 5,
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
    map.addControl(new maplibregl.GlobeControl(), "top-right");

    let visibleRequestId = 0;
    async function reloadVisibleData() {
      const requestId = ++visibleRequestId;
      try {
        const { bbox, parcels, buildings } =
          await getVisibleFeatureCollections(map);
        if (cancelled || requestId !== visibleRequestId) {
          return;
        }

        await setNativePolygonSources(map, parcels, buildings);
        await upsertGeoJsonSource(
          map,
          "building-centroids",
          buildingCentroidsFeatureCollection(buildings),
        );
        updateBuildingDebugMarkers(map, buildings);
        setError(undefined);
        setStatus(
          `Loaded ${parcels.features.length} visible parcels and ${buildings.features.length} visible buildings for bbox ${bbox.map((value) => value.toFixed(5)).join(",")}.`,
        );
      } catch (cause) {
        if (!cancelled && requestId === visibleRequestId) {
          setError(cause instanceof Error ? cause.message : "Unknown error");
          setStatus("Could not reload visible map data");
        }
      }
    }

    map.once("load", async () => {
      const initialBbox = visibleOgcBbox(map);
      const [parcelsResult, buildingsResult] = await Promise.allSettled([
        getFeatureCollection(parcelsItemsInBboxUrl(initialBbox)),
        getFeatureCollection(buildingsItemsInBboxUrl(initialBbox)),
      ]);
      if (cancelled) {
        return;
      }

      let parcelsCount = 0;
      let buildingsCount = 0;
      let parcels = emptyFeatureCollection;
      let buildings = emptyFeatureCollection;
      let initialDataBounds: maplibregl.LngLatBounds | undefined;
      const errors: string[] = [];

      if (parcelsResult.status === "fulfilled") {
        parcels = parcelsResult.value;
        logLoadedCoordinates("parcels", parcels);
        parcelsCount = parcels.features.length;
        initialDataBounds = featureBounds(parcels);
      } else {
        errors.push(`parcels: ${parcelsResult.reason}`);
      }

      if (buildingsResult.status === "fulfilled") {
        buildings = buildingsResult.value;
        logLoadedCoordinates("buildings", buildings);
        buildingsCount = buildings.features.length;
        initialDataBounds ??= featureBounds(buildings);
      } else {
        errors.push(`buildings: ${buildingsResult.reason}`);
      }

      addNativeFeatureSourcesAndLayers(map, parcels, buildings);
      updateBuildingDebugMarkers(map, buildings);
      map.on("moveend", reloadVisibleData);

      if (initialDataBounds) {
        map.fitBounds(initialDataBounds, { padding: 64, maxZoom: 19 });
      }

      logLayerState(map);
      setIsMapReady(errors.length === 0);
      setError(errors.length > 0 ? errors.join("; ") : undefined);
      const loadedStatus =
        parcelsCount + buildingsCount === 0
          ? "Dataset loaded, but no parcels or buildings were returned. Use Create random building to add data."
          : `Loaded ${parcelsCount} parcels and ${buildingsCount} buildings from the API.`;
      setStatus(loadedStatus);
      map.once("idle", () => {
        const nativeState = logNativeRenderingState(map);
        setStatus(
          `${loadedStatus} Native source features P:${nativeState.parcelSourceFeatures} B:${nativeState.buildingSourceFeatures}; rendered P:${nativeState.parcelRenderedFeatures} B:${nativeState.buildingRenderedFeatures}.`,
        );
      });
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

  async function createRandomBuilding() {
    const map = mapRef.current;
    if (!map) {
      return;
    }

    setIsCreating(true);
    setError(undefined);

    try {
      const existingParcels = await getFeatureCollection(
        parcelsItemsInBboxUrl(visibleOgcBbox(map)),
      );
      const {
        area,
        building,
        secondaryBuilding,
        parcel,
        placementAttempts,
      } = randomNonOverlappingBuildingAndParcel(map, existingParcels);
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

      const currentBounds = map.getBounds();
      const { parcels, buildings } = await getVisibleFeatureCollections(map);
      logLoadedCoordinates("parcels after create", parcels);
      logLoadedCoordinates("buildings after create", buildings);
      await setNativePolygonSources(map, parcels, buildings);
      await upsertGeoJsonSource(
        map,
        "building-centroids",
        buildingCentroidsFeatureCollection(buildings),
      );
      updateBuildingDebugMarkers(map, buildings);
      map.fitBounds(currentBounds, { animate: false });
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

    setIsClearing(true);
    setError(undefined);

    try {
      const currentBounds = map.getBounds();
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
      } = await getVisibleFeatureCollections(map);
      logLoadedCoordinates("parcels after clear", reloadedParcels);
      logLoadedCoordinates("buildings after clear", reloadedBuildings);
      await setNativePolygonSources(map, reloadedParcels, reloadedBuildings);
      await upsertGeoJsonSource(
        map,
        "building-centroids",
        buildingCentroidsFeatureCollection(reloadedBuildings),
      );
      updateBuildingDebugMarkers(map, reloadedBuildings);
      map.fitBounds(currentBounds, { animate: false });
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
    <section className="map-card" aria-label="Cadastre parcels map">
      <div ref={mapContainerRef} className="map" />
      <div className="map-actions">
        <button
          type="button"
          className="map-action-button"
          disabled={!isMapReady || isCreating || isClearing}
          onClick={createRandomBuilding}
        >
          {isCreating ? "Creating parcel..." : "Create random parcel"}
        </button>
        <button
          type="button"
          className="map-action-button map-action-button--danger"
          disabled={!isMapReady || isCreating || isClearing}
          onClick={clearData}
        >
          {isClearing ? "Clearing data..." : "Clear data"}
        </button>
      </div>
      <div className={error ? "map-status map-status--error" : "map-status"}>
        <span>{status}</span>
        {error ? <code>{error}</code> : null}
      </div>
    </section>
  );
}

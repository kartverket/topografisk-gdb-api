import {
  BYGNING_LINEWORK_ELEVATED_LINE_WIDTH_M,
  BYGNING_ELEVATED_LINE_THICKNESS_M,
  BYGNING_ELEVATED_LINE_WIDTH_M,
  elevatedLineSegments,
  lowestPositiveLineHeight
} from '../map/map3d';
import { bygningOmradeExtrusionFeatureCollection, lowestPositiveBygningOmradeHeight } from '../map/bygningOmradeLayers';
import {
  terrainSampleKey,
  type ElevatedSourcesWorkerRequest,
  type ElevatedSourcesWorkerResponse
} from '../map/elevatedSourcesShared';
import type { FeatureCollection } from '../map/geojson';

const emptyFeatureCollection: FeatureCollection = { type: 'FeatureCollection', features: [] };

function terrainLookupFromSamples(terrainSamples: Record<string, number>) {
  return (longitude: number, latitude: number) => terrainSamples[terrainSampleKey(longitude, latitude)];
}

self.onmessage = (event: MessageEvent<ElevatedSourcesWorkerRequest>) => {
  const {
    requestId,
    platformEdges,
    trackCentres,
    bygning,
    bygningSenterlinje,
    bygningOmrade,
    visibility,
    adjustHeights,
    terrainEnabled,
    baneTerrainClearanceMeters,
    terrainSamples
  } = event.data;

  const heightSamples = [
    ...(visibility.platformEdges ? [lowestPositiveLineHeight([platformEdges])] : []),
    ...(visibility.trackCentres ? [lowestPositiveLineHeight([trackCentres])] : []),
    ...(visibility.bygning ? [lowestPositiveLineHeight([bygning])] : []),
    ...(visibility.bygningSenterlinje ? [lowestPositiveLineHeight([bygningSenterlinje])] : []),
    ...(visibility.bygningOmrade ? [lowestPositiveBygningOmradeHeight(bygningOmrade)] : [])
  ].filter(height => height > 0);

  const heightOffset = adjustHeights && heightSamples.length > 0 ? Math.min(...heightSamples) : 0;
  const terrainLookup = terrainEnabled ? terrainLookupFromSamples(terrainSamples) : undefined;
  const baneTerrainLookup = terrainLookup
    ? (longitude: number, latitude: number) => {
        const terrainElevation = terrainLookup(longitude, latitude);
        return typeof terrainElevation === 'number' ? terrainElevation - baneTerrainClearanceMeters : undefined;
      }
    : undefined;

  const response: ElevatedSourcesWorkerResponse = {
    requestId,
    platformData: visibility.platformEdges
      ? elevatedLineSegments(platformEdges, undefined, undefined, heightOffset, baneTerrainLookup, terrainEnabled)
      : emptyFeatureCollection,
    trackData: visibility.trackCentres
      ? elevatedLineSegments(trackCentres, undefined, undefined, heightOffset, baneTerrainLookup, terrainEnabled)
      : emptyFeatureCollection,
    bygningData: visibility.bygning
      ? elevatedLineSegments(
          bygning,
          BYGNING_LINEWORK_ELEVATED_LINE_WIDTH_M,
          BYGNING_ELEVATED_LINE_THICKNESS_M,
          heightOffset,
          terrainLookup
        )
      : emptyFeatureCollection,
    bygningSenterlinjeData: visibility.bygningSenterlinje
      ? elevatedLineSegments(
          bygningSenterlinje,
          BYGNING_ELEVATED_LINE_WIDTH_M,
          BYGNING_ELEVATED_LINE_THICKNESS_M,
          heightOffset,
          terrainLookup
        )
      : emptyFeatureCollection,
    bygningOmradeData: visibility.bygningOmrade
      ? bygningOmradeExtrusionFeatureCollection(bygningOmrade, heightOffset, terrainLookup)
      : emptyFeatureCollection
  };

  self.postMessage(response);
};

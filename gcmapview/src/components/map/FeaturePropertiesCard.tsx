import { useEffect, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from 'react';
import { Check, Filter, FilterX, Loader2, Pencil, Trash2, Undo2, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { Position } from '../../map/geojson';
import {
  FILTERABLE_FEATURE_PROPERTY_KEYS,
  filterableFeaturePropertyValue,
  formatPropertyValue,
  type ActiveFeatureFilter,
  type InspectedFeature
} from '../../map/featureInspect';

type FeaturePropertiesCardProps = {
  feature: InspectedFeature;
  activeFeatureFilter?: ActiveFeatureFilter;
  onClose: () => void;
  onApplyFeatureFilter?: (featureFilter: ActiveFeatureFilter) => void;
  onClearFeatureFilter?: () => void;
  onHoverPositionIndex?: (index: number | undefined) => void;
  onDeleteFeature?: () => void;
  isDeletingFeature?: boolean;
  canEditFeature?: boolean;
  canVisualEditFeature?: boolean;
  editingDisabledReason?: string;
  isEditingFeature?: boolean;
  onStartFeatureEditing?: () => void;
  onCancelFeatureEditing?: () => void;
  onPreviewFeaturePositionChanges?: (positions: Position[]) => void;
  onCommitFeaturePositionChanges?: (positions: Position[]) => Promise<void>;
  isSavingFeatureChanges?: boolean;
  onHeaderPointerDown?: (event: ReactPointerEvent<HTMLDivElement>) => void;
};

type EditablePositionDraft = {
  x: string;
  y: string;
  z: string;
};

type ExpandableSectionHeaderProps = {
  label: string;
  badges?: ReactNode;
};

function ExpandableSectionHeader({ label, badges }: ExpandableSectionHeaderProps) {
  return (
    <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-foreground [&::-webkit-details-marker]:hidden">
      <span className="flex size-4 shrink-0 items-center justify-center border border-border text-[11px] leading-none group-open:hidden">
        +
      </span>
      <span className="hidden size-4 shrink-0 items-center justify-center border border-border text-[11px] leading-none group-open:flex">
        -
      </span>
      <span className="inline-flex min-w-0 items-center gap-2">
        <span>{label}</span>
        {badges}
      </span>
    </summary>
  );
}

function isJsonPropertyValue(value: unknown): value is Record<string, unknown> | unknown[] {
  return typeof value === 'object' && value !== null;
}

function formatPositionCoordinate(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return formatPropertyValue(value);
  }

  return Number(value.toFixed(4)).toString();
}

function propertyEntries(value: Record<string, unknown> | unknown[]) {
  if (Array.isArray(value)) {
    return value.map((item, index) => [`[${index}]`, item] as const);
  }

  return Object.entries(value).sort(([a], [b]) => a.localeCompare(b));
}

function positionDraftsFromPositions(positions: Position[]): EditablePositionDraft[] {
  return positions.map(([x, y, z]) => ({ x: String(x), y: String(y), z: z === undefined ? '' : String(z) }));
}

function positionsFromDrafts(drafts: EditablePositionDraft[], fallbackPositions: Position[]): Position[] {
  return fallbackPositions.map((position, index) => {
    const draft = drafts[index];
    const x = Number(draft?.x);
    const y = Number(draft?.y);
    const zValue = draft?.z.trim() ?? '';
    const z = zValue ? Number(zValue) : undefined;

    if (!Number.isFinite(x) || !Number.isFinite(y) || (zValue && !Number.isFinite(z))) {
      throw new Error(`Ugyldig koordinatverdi på rad ${index + 1}.`);
    }

    const trailing = position.slice(3);
    return z === undefined ? ([x, y, ...trailing] as Position) : ([x, y, z, ...trailing] as Position);
  });
}

type RenderPropertyEntryOptions = {
  featureProperties: Record<string, unknown>;
  activeFeatureFilter?: ActiveFeatureFilter;
  onApplyFeatureFilter?: (featureFilter: ActiveFeatureFilter) => void;
  onClearFeatureFilter?: () => void;
  nested?: boolean;
  path?: string;
};

function renderPropertyEntry(
  key: string,
  value: unknown,
  {
    featureProperties,
    activeFeatureFilter,
    onApplyFeatureFilter,
    onClearFeatureFilter,
    nested = false,
    path = key
  }: RenderPropertyEntryOptions
) {
  if (isJsonPropertyValue(value)) {
    const entries = propertyEntries(value);

    return (
      <details
        key={path}
        open
        className="group">
        <ExpandableSectionHeader
          label={key}
          badges={
            <Badge
              variant="outline"
              className="font-mono text-[11px]">
              {entries.length}
            </Badge>
          }
        />
        {entries.length === 0 ? (
          <p className="mt-2 text-xs text-muted-foreground">Empty {Array.isArray(value) ? 'array' : 'object'}</p>
        ) : (
          <div className="mt-2 grid gap-2 pl-6">
            {entries.map(([childKey, childValue]) =>
              renderPropertyEntry(childKey, childValue, {
                featureProperties,
                activeFeatureFilter,
                onApplyFeatureFilter,
                onClearFeatureFilter,
                nested: true,
                path: `${path}.${childKey}`
              })
            )}
          </div>
        )}
      </details>
    );
  }

  const isFilterableKey =
    !nested && FILTERABLE_FEATURE_PROPERTY_KEYS.includes(key as (typeof FILTERABLE_FEATURE_PROPERTY_KEYS)[number]);
  const filterValue = isFilterableKey ? filterableFeaturePropertyValue(featureProperties, key) : undefined;
  const isActiveFilter = Boolean(
    filterValue && activeFeatureFilter?.propertyKey === key && activeFeatureFilter.value === filterValue
  );

  return (
    <div
      key={path}
      className="min-w-0">
      <dt className="font-medium text-muted-foreground">{key}</dt>
      {filterValue ? (
        <dd className="m-0 flex items-start justify-between gap-2">
          <span className="min-w-0 break-words font-mono text-[12px] text-foreground">
            {formatPropertyValue(value)}
          </span>
          <Button
            type="button"
            size="icon-sm"
            variant={isActiveFilter ? 'secondary' : 'ghost'}
            className="size-6 shrink-0"
            aria-label={isActiveFilter ? `Clear ${key} filter ${filterValue}` : `Filter by ${key} ${filterValue}`}
            title={isActiveFilter ? `Clear ${key} filter ${filterValue}` : `Filter by ${key} ${filterValue}`}
            onClick={() =>
              isActiveFilter
                ? onClearFeatureFilter?.()
                : onApplyFeatureFilter?.({ propertyKey: key, value: filterValue })
            }>
            {isActiveFilter ? <FilterX /> : <Filter />}
          </Button>
        </dd>
      ) : (
        <dd className="m-0 break-words font-mono text-[12px] text-foreground">{formatPropertyValue(value)}</dd>
      )}
    </div>
  );
}

export function FeaturePropertiesCard({
  feature,
  activeFeatureFilter,
  onClose,
  onApplyFeatureFilter,
  onClearFeatureFilter,
  onHoverPositionIndex,
  onDeleteFeature,
  isDeletingFeature = false,
  canEditFeature = false,
  canVisualEditFeature = false,
  editingDisabledReason,
  isEditingFeature = false,
  onStartFeatureEditing,
  onCancelFeatureEditing,
  onPreviewFeaturePositionChanges,
  onCommitFeaturePositionChanges,
  isSavingFeatureChanges = false,
  onHeaderPointerDown
}: FeaturePropertiesCardProps) {
  const isSourceLoading = Boolean(feature.positionsLoading);
  const entries = Object.entries(feature.properties).sort(([a], [b]) => a.localeCompare(b));
  const [positionDrafts, setPositionDrafts] = useState<EditablePositionDraft[]>(() =>
    positionDraftsFromPositions(feature.positions)
  );
  const [editError, setEditError] = useState<string>();
  const editingDisabled = Boolean(editingDisabledReason);
  const hasPositionEditor = canEditFeature && feature.positions.length > 0 && Boolean(onCommitFeaturePositionChanges);
  const canCommitEditing = hasPositionEditor && isEditingFeature;

  useEffect(() => {
    setEditError(undefined);
  }, [feature.collectionId, feature.featureId, feature.layerId]);

  useEffect(() => {
    setPositionDrafts(positionDraftsFromPositions(feature.positions));
  }, [feature.positions]);

  useEffect(() => {
    if (!isEditingFeature) {
      setPositionDrafts(positionDraftsFromPositions(feature.positions));
    }
    setEditError(undefined);
  }, [feature.positions, isEditingFeature]);

  function updatePositionDraft(index: number, axis: 'x' | 'y' | 'z', value: string) {
    setPositionDrafts(current => {
      const nextDrafts = current.map((draft, draftIndex) =>
        draftIndex === index ? { ...draft, [axis]: value } : draft
      );

      try {
        const previewPositions = positionsFromDrafts(nextDrafts, feature.positions);
        onPreviewFeaturePositionChanges?.(previewPositions);
        setEditError(undefined);
      } catch {
        // Allow incomplete typing without tearing down the current preview.
      }

      return nextDrafts;
    });
  }

  async function commitEditedPositions() {
    if (!onCommitFeaturePositionChanges) {
      return;
    }

    try {
      const nextPositions = positionsFromDrafts(positionDrafts, feature.positions);

      setEditError(undefined);
      await onCommitFeaturePositionChanges(nextPositions);
    } catch (cause) {
      setEditError(cause instanceof Error ? cause.message : 'Kunne ikke lagre koordinatene.');
    }
  }

  return (
    <Card
      size="sm"
      className="max-h-[min(70vh,28rem)] w-full overflow-hidden bg-card/95 shadow-md"
      aria-label="Selected feature properties">
      <CardHeader
        className="relative cursor-grab pb-0 pr-44 active:cursor-grabbing"
        onPointerDown={onHeaderPointerDown}>
        <CardTitle className="truncate text-base">{feature.layerLabel}</CardTitle>
        <div className="absolute top-0 right-0 flex flex-row-reverse items-center gap-1 px-(--card-spacing)">
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="size-8"
            aria-label="Close properties"
            title="Lukk"
            onClick={onClose}>
            <X />
          </Button>
          {onDeleteFeature ? (
            <Button
              type="button"
              size="icon-sm"
              variant="destructive"
              className="size-8"
              aria-label="Slett objekt"
              title={isDeletingFeature ? 'Sletter objekt...' : 'Slett objekt'}
              disabled={isDeletingFeature || isSavingFeatureChanges || isEditingFeature}
              onClick={onDeleteFeature}>
              {isDeletingFeature ? <Loader2 className="animate-spin" /> : <Trash2 />}
            </Button>
          ) : null}
          {canCommitEditing ? (
            <>
              <Button
                type="button"
                size="icon-sm"
                variant="outline"
                className="size-8"
                aria-label="Avbryt redigering"
                title="Avbryt redigering"
                disabled={isDeletingFeature || isSavingFeatureChanges}
                onClick={() => {
                  setPositionDrafts(positionDraftsFromPositions(feature.positions));
                  setEditError(undefined);
                  onCancelFeatureEditing?.();
                }}>
                <Undo2 />
              </Button>
              <Button
                type="button"
                size="icon-sm"
                className="size-8"
                aria-label="Lagre endringer"
                title="Lagre endringer"
                disabled={isDeletingFeature || isSavingFeatureChanges}
                onClick={() => void commitEditedPositions()}>
                {isSavingFeatureChanges ? <Loader2 className="animate-spin" /> : <Check />}
              </Button>
            </>
          ) : null}
          {hasPositionEditor && !isEditingFeature ? (
            <Button
              type="button"
              size="icon-sm"
              variant="secondary"
              className="size-8"
              aria-label="Rediger objekt"
              title={editingDisabledReason ?? 'Rediger objekt'}
              disabled={editingDisabled || isSourceLoading || isDeletingFeature || isSavingFeatureChanges}
              onClick={() => {
                setPositionDrafts(positionDraftsFromPositions(feature.positions));
                setEditError(undefined);
                onStartFeatureEditing?.();
              }}>
              <Pencil />
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-2 overflow-y-auto pt-2">
        <Separator />
        {feature.positions.length > 0 || isSourceLoading ? (
          <details
            className="group"
            open={isEditingFeature || undefined}>
            <ExpandableSectionHeader
              label="Positions"
              badges={
                <>
                  {isSourceLoading ? (
                    <Badge
                      variant="outline"
                      className="font-mono text-[11px]">
                      loading
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="font-mono text-[11px]">
                      {feature.positions.length}
                    </Badge>
                  )}
                  {feature.positionsCoordinateSystem ? (
                    <Badge
                      variant="secondary"
                      className="font-mono text-[11px]">
                      {feature.positionsCoordinateSystem}
                    </Badge>
                  ) : null}
                </>
              }
            />
            {isSourceLoading ? (
              <p className="mt-2 pl-6 text-xs text-muted-foreground">Loading source coordinates…</p>
            ) : (
              <div className="mt-2 space-y-1 pl-6 text-[12px] font-mono">
                {isEditingFeature ? (
                  <p className="text-xs text-muted-foreground">
                    {canVisualEditFeature
                      ? 'Rediger x, y og z. Dra punktene i kartet for å oppdatere x/y visuelt før commit.'
                      : 'Rediger x, y og z. I 3D kan du holde Ctrl og dra opp eller ned for å justere z visuelt med 1 cm per piksel før commit.'}
                  </p>
                ) : null}
                <div className="grid grid-cols-3 gap-x-3 text-muted-foreground">
                  <span className="font-medium">x</span>
                  <span className="font-medium">y</span>
                  <span className="font-medium">z</span>
                </div>
                {feature.positions.map(([x, y, z], index) => {
                  const draft = positionDrafts[index];

                  return isEditingFeature ? (
                    <div
                      key={`${x}-${y}-${z ?? 'na'}-${index}`}
                      className="grid grid-cols-3 gap-x-3 rounded-sm text-foreground"
                      onMouseEnter={() => onHoverPositionIndex?.(index)}
                      onMouseLeave={() => onHoverPositionIndex?.(undefined)}>
                      <input
                        type="text"
                        inputMode="decimal"
                        className="min-w-0 rounded-md border border-input bg-background px-2 py-1 text-[12px] shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                        aria-label={`Position ${index + 1} x`}
                        value={draft?.x ?? ''}
                        onFocus={() => onHoverPositionIndex?.(index)}
                        onBlur={() => onHoverPositionIndex?.(undefined)}
                        onChange={event => updatePositionDraft(index, 'x', event.target.value)}
                      />
                      <input
                        type="text"
                        inputMode="decimal"
                        className="min-w-0 rounded-md border border-input bg-background px-2 py-1 text-[12px] shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                        aria-label={`Position ${index + 1} y`}
                        value={draft?.y ?? ''}
                        onFocus={() => onHoverPositionIndex?.(index)}
                        onBlur={() => onHoverPositionIndex?.(undefined)}
                        onChange={event => updatePositionDraft(index, 'y', event.target.value)}
                      />
                      <input
                        type="text"
                        inputMode="decimal"
                        className="min-w-0 rounded-md border border-input bg-background px-2 py-1 text-[12px] shadow-xs outline-none transition-colors focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/40"
                        aria-label={`Position ${index + 1} z`}
                        value={draft?.z ?? ''}
                        onFocus={() => onHoverPositionIndex?.(index)}
                        onBlur={() => onHoverPositionIndex?.(undefined)}
                        onChange={event => updatePositionDraft(index, 'z', event.target.value)}
                      />
                    </div>
                  ) : (
                    <div
                      key={`${x}-${y}-${z ?? 'na'}-${index}`}
                      className="grid grid-cols-3 gap-x-3 rounded-sm text-foreground transition-colors hover:bg-accent/40"
                      onMouseEnter={() => onHoverPositionIndex?.(index)}
                      onMouseLeave={() => onHoverPositionIndex?.(undefined)}>
                      <span>{formatPositionCoordinate(x)}</span>
                      <span>{formatPositionCoordinate(y)}</span>
                      <span>{z === undefined ? '—' : formatPositionCoordinate(z)}</span>
                    </div>
                  );
                })}
                {isEditingFeature && editError ? <p className="text-xs text-destructive">{editError}</p> : null}
              </div>
            )}
          </details>
        ) : null}
        <dl className="m-0 grid gap-2 text-sm">
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">id</dt>
            <dd className="m-0 break-words font-mono text-[12px] text-foreground">
              {feature.featureId !== undefined ? (
                <Badge
                  variant="outline"
                  className="font-mono text-[11px]">
                  {String(feature.featureId)}
                </Badge>
              ) : (
                'No feature id'
              )}
            </dd>
          </div>
          {!isSourceLoading
            ? entries.map(([key, value]) =>
                renderPropertyEntry(key, value, {
                  featureProperties: feature.properties,
                  activeFeatureFilter,
                  onApplyFeatureFilter,
                  onClearFeatureFilter
                })
              )
            : null}
        </dl>
        {isSourceLoading ? (
          <p className="text-sm text-muted-foreground">Loading source properties…</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No additional properties</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

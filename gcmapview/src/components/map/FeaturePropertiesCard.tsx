import type { ReactNode } from 'react';
import { Filter, FilterX, X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
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
  onHoverPositionIndex
}: FeaturePropertiesCardProps) {
  const isSourceLoading = Boolean(feature.positionsLoading);
  const entries = Object.entries(feature.properties).sort(([a], [b]) => a.localeCompare(b));

  return (
    <Card
      size="sm"
      className="max-h-[min(70vh,28rem)] w-[min(400px,calc(100%-2rem))] overflow-hidden bg-card/95 shadow-md max-sm:w-auto"
      aria-label="Selected feature properties">
      <CardHeader className="pb-0">
        <CardTitle className="truncate pr-8 text-base">{feature.layerLabel}</CardTitle>
        <CardDescription className="flex flex-wrap items-center gap-1.5">
          {feature.featureId !== undefined ? (
            <Badge
              variant="outline"
              className="font-mono text-[11px]">
              id {String(feature.featureId)}
            </Badge>
          ) : (
            <span>No feature id</span>
          )}
        </CardDescription>
        <CardAction>
          <Button
            type="button"
            size="icon-sm"
            variant="ghost"
            className="-mt-1 -mr-1"
            aria-label="Close properties"
            onClick={onClose}>
            <X />
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-2 overflow-y-auto pt-2">
        <Separator />
        {feature.positions.length > 0 || isSourceLoading ? (
          <details className="group">
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
                <div className="grid grid-cols-3 gap-x-3 text-muted-foreground">
                  <span className="font-medium">x</span>
                  <span className="font-medium">y</span>
                  <span className="font-medium">z</span>
                </div>
                {feature.positions.map(([x, y, z], index) => (
                  <div
                    key={`${x}-${y}-${z ?? 'na'}-${index}`}
                    className="grid grid-cols-3 gap-x-3 rounded-sm text-foreground transition-colors hover:bg-accent/40"
                    onMouseEnter={() => onHoverPositionIndex?.(index)}
                    onMouseLeave={() => onHoverPositionIndex?.(undefined)}>
                    <span>{formatPositionCoordinate(x)}</span>
                    <span>{formatPositionCoordinate(y)}</span>
                    <span>{z === undefined ? '—' : formatPositionCoordinate(z)}</span>
                  </div>
                ))}
              </div>
            )}
          </details>
        ) : null}
        {isSourceLoading ? (
          <p className="text-sm text-muted-foreground">Loading source properties…</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No properties</p>
        ) : (
          <dl className="m-0 grid gap-2 text-sm">
            {entries.map(([key, value]) =>
              renderPropertyEntry(key, value, {
                featureProperties: feature.properties,
                activeFeatureFilter,
                onApplyFeatureFilter,
                onClearFeatureFilter
              })
            )}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

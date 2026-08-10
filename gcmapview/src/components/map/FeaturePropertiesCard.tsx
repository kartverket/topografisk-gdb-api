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
      className="absolute top-4 right-4 z-[3] max-h-[min(70vh,28rem)] w-[min(400px,calc(100%-2rem))] overflow-hidden bg-card/95 shadow-md max-sm:top-auto max-sm:right-4 max-sm:bottom-[88px] max-sm:left-4 max-sm:w-auto"
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
          <details className="rounded-md border border-border/60 bg-muted/20 px-3 py-2">
            <summary className="cursor-pointer text-sm font-medium text-foreground">
              <span className="inline-flex items-center gap-2">
                Positions
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
              </span>
            </summary>
            {isSourceLoading ? (
              <p className="mt-2 text-xs text-muted-foreground">Loading source coordinates…</p>
            ) : (
              <div className="mt-2 overflow-x-auto">
                <table className="min-w-full border-separate border-spacing-y-1 text-left text-[12px] font-mono">
                  <thead>
                    <tr className="text-muted-foreground">
                      <th className="pr-3 font-medium">x</th>
                      <th className="pr-3 font-medium">y</th>
                      <th className="font-medium">z</th>
                    </tr>
                  </thead>
                  <tbody>
                    {feature.positions.map(([x, y, z], index) => (
                      <tr
                        key={`${x}-${y}-${z ?? 'na'}-${index}`}
                        className="transition-colors hover:bg-accent/40"
                        onMouseEnter={() => onHoverPositionIndex?.(index)}
                        onMouseLeave={() => onHoverPositionIndex?.(undefined)}>
                        <td className="pr-3 text-foreground">{formatPropertyValue(x)}</td>
                        <td className="pr-3 text-foreground">{formatPropertyValue(y)}</td>
                        <td className="text-foreground">{z === undefined ? '—' : formatPropertyValue(z)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
            {entries.map(([key, value]) => {
              const isFilterableKey = FILTERABLE_FEATURE_PROPERTY_KEYS.includes(
                key as (typeof FILTERABLE_FEATURE_PROPERTY_KEYS)[number]
              );
              const filterValue = isFilterableKey ? filterableFeaturePropertyValue(feature.properties, key) : undefined;
              const isActiveFilter = Boolean(
                filterValue && activeFeatureFilter?.propertyKey === key && activeFeatureFilter.value === filterValue
              );

              return (
                <div
                  key={key}
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
                        aria-label={
                          isActiveFilter ? `Clear ${key} filter ${filterValue}` : `Filter by ${key} ${filterValue}`
                        }
                        title={
                          isActiveFilter ? `Clear ${key} filter ${filterValue}` : `Filter by ${key} ${filterValue}`
                        }
                        onClick={() =>
                          isActiveFilter
                            ? onClearFeatureFilter?.()
                            : onApplyFeatureFilter?.({ propertyKey: key, value: filterValue })
                        }>
                        {isActiveFilter ? <FilterX /> : <Filter />}
                      </Button>
                    </dd>
                  ) : (
                    <dd className="m-0 break-words font-mono text-[12px] text-foreground">
                      {formatPropertyValue(value)}
                    </dd>
                  )}
                </div>
              );
            })}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

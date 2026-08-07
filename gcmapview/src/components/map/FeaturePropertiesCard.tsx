import { X } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { formatPropertyValue, type InspectedFeature } from '../../map/featureInspect';

type FeaturePropertiesCardProps = {
  feature: InspectedFeature;
  onClose: () => void;
};

export function FeaturePropertiesCard({ feature, onClose }: FeaturePropertiesCardProps) {
  const entries = Object.entries(feature.properties).sort(([a], [b]) => a.localeCompare(b));

  return (
    <Card
      size="sm"
      className="absolute top-4 right-4 z-[3] max-h-[min(70vh,28rem)] w-[min(320px,calc(100%-2rem))] overflow-hidden bg-card/95 shadow-md max-sm:top-auto max-sm:right-4 max-sm:bottom-[88px] max-sm:left-4 max-sm:w-auto"
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
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">No properties</p>
        ) : (
          <dl className="m-0 grid gap-2 text-sm">
            {entries.map(([key, value]) => (
              <div
                key={key}
                className="min-w-0">
                <dt className="font-medium text-muted-foreground">{key}</dt>
                <dd className="m-0 break-words font-mono text-[12px] text-foreground">{formatPropertyValue(value)}</dd>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

import { Eye, EyeOff } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import {
  MAP_LAYER_IDS,
  MAP_LAYER_LABELS,
  type LayerVisibility,
  type MapLayerId,
  useLayerVisibilityStore
} from '../../store/layerVisibilityStore';

const layerSwatchClassName = 'inline-block shrink-0 rounded-full opacity-80';

function LayerToggleRow({
  layerId,
  visible,
  readOnly,
  onToggle
}: {
  layerId: MapLayerId;
  visible: boolean;
  readOnly?: boolean;
  onToggle: () => void;
}) {
  const isLine = layerId === 'platformEdges' || layerId === 'trackCentres';

  return (
    <li>
      <button
        type="button"
        className={cn(
          'flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left transition-opacity hover:bg-muted/60',
          visible ? 'text-foreground' : 'text-muted-foreground opacity-55'
        )}
        aria-pressed={visible}
        title={visible ? `Hide ${MAP_LAYER_LABELS[layerId]}` : `Show ${MAP_LAYER_LABELS[layerId]}`}
        onClick={onToggle}>
        {layerId === 'parcels' ? (
          <span className={cn(layerSwatchClassName, 'h-2.5 w-4 bg-[#ffc040]')} />
        ) : layerId === 'platformEdges' ? (
          <span className={cn(layerSwatchClassName, 'h-1 w-4 bg-black')} />
        ) : (
          <span
            className={cn(layerSwatchClassName, isLine ? 'h-1 w-4' : 'h-2.5 w-4')}
            style={{
              background: 'linear-gradient(to right, hsl(240 85% 45%), hsl(0 85% 45%))'
            }}
          />
        )}
        <span className="min-w-0 flex-1 text-sm leading-snug">{MAP_LAYER_LABELS[layerId]}</span>
        {readOnly ? (
          <Badge
            variant="outline"
            className="shrink-0">
            RO
          </Badge>
        ) : null}
        {visible ? (
          <Eye
            className="size-3.5 shrink-0 text-muted-foreground"
            aria-hidden
          />
        ) : (
          <EyeOff
            className="size-3.5 shrink-0 text-muted-foreground"
            aria-hidden
          />
        )}
      </button>
    </li>
  );
}

type MapLayersCardProps = {
  is3d: boolean;
  visibility: LayerVisibility;
};

export function MapLayersCard({ is3d, visibility }: MapLayersCardProps) {
  const toggleLayer = useLayerVisibilityStore(state => state.toggleLayer);

  return (
    <Card
      size="sm"
      className="absolute right-4 bottom-[88px] z-[3] w-[240px] bg-card/95 shadow-md max-sm:top-20 max-sm:right-auto max-sm:bottom-auto max-sm:left-4"
      aria-label="Map layers">
      <CardHeader className="pb-0">
        <CardTitle>Layers</CardTitle>
        <CardDescription>
          Height colour: blue 0 m → red 300 m+
          {!is3d ? ' · Bane read-only' : ''}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        <Separator />
        <div className="space-y-1">
          <div
            className="h-2.5 w-full rounded-full"
            style={{
              background: 'linear-gradient(to right, hsl(240 85% 45%), hsl(120 85% 45%), hsl(0 85% 45%))'
            }}
            aria-hidden
          />
          <div className="flex justify-between text-[11px] text-muted-foreground">
            <span>0 m</span>
            <span>300 m+</span>
          </div>
        </div>
        <ul className="m-0 space-y-1 p-0 text-sm">
          {MAP_LAYER_IDS.map(layerId => (
            <LayerToggleRow
              key={layerId}
              layerId={layerId}
              visible={visibility[layerId]}
              readOnly={layerId === 'platformEdges' || layerId === 'trackCentres'}
              onToggle={() => toggleLayer(layerId)}
            />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

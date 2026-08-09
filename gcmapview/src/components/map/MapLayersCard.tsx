import { Eye, EyeOff } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import type { FavoriteMapView } from '../../store/mapViewStore';

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
  const isLine =
    layerId === 'platformEdges' ||
    layerId === 'trackCentres' ||
    layerId === 'bygning' ||
    layerId === 'bygningSenterlinje';
  const isReadOnly =
    layerId === 'platformEdges' ||
    layerId === 'trackCentres' ||
    layerId === 'bygning' ||
    layerId === 'bygningOmrade' ||
    layerId === 'bygningSenterlinje' ||
    layerId === 'bygningPosisjon';

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
        ) : layerId === 'bygning' ? (
          <span className={cn(layerSwatchClassName, 'h-1 w-4 bg-black')} />
        ) : layerId === 'bygningOmrade' ? (
          <span className={cn(layerSwatchClassName, 'h-2.5 w-4 bg-black')} />
        ) : layerId === 'bygningSenterlinje' ? (
          <span className={cn(layerSwatchClassName, 'h-1 w-4 bg-[#8a5a2b]')} />
        ) : layerId === 'bygningPosisjon' ? (
          <span className={cn(layerSwatchClassName, 'h-2.5 w-2.5 border border-white bg-black')} />
        ) : (
          <span
            className={cn(layerSwatchClassName, isLine ? 'h-1 w-4' : 'h-2.5 w-4')}
            style={{
              background: 'linear-gradient(to right, hsl(240 85% 45%), hsl(0 85% 45%))'
            }}
          />
        )}
        <span className="min-w-0 flex-1 text-sm leading-snug">{MAP_LAYER_LABELS[layerId]}</span>
        {readOnly ?? isReadOnly ? (
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
  favoriteViews: FavoriteMapView[];
  activeFavoriteName?: string;
  onSaveFavoriteView: () => void;
  onClearFavoriteView: () => void;
  onSelectFavoriteView: (name: string) => void;
};

export function MapLayersCard({
  is3d,
  visibility,
  favoriteViews,
  activeFavoriteName,
  onSaveFavoriteView,
  onClearFavoriteView,
  onSelectFavoriteView
}: MapLayersCardProps) {
  const toggleLayer = useLayerVisibilityStore(state => state.toggleLayer);
  const activeFavoriteView = favoriteViews.find(favoriteView => favoriteView.name === activeFavoriteName) ?? favoriteViews[0];

  return (
    <Card
      size="sm"
      className="absolute right-4 bottom-[88px] z-[3] w-[240px] bg-card/95 shadow-md max-sm:top-20 max-sm:right-auto max-sm:bottom-auto max-sm:left-4"
      aria-label="Map layers">
      <CardHeader className="pb-0">
        <CardTitle>Layers</CardTitle>
        <CardDescription>
          Height colour: blue 0 m → red 300 m+
          {!is3d ? ' · Imported Bygning/Bane layers are read-only' : ''}
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
              readOnly={
                layerId === 'platformEdges' ||
                layerId === 'trackCentres' ||
                layerId === 'bygning' ||
                layerId === 'bygningOmrade' ||
                layerId === 'bygningSenterlinje' ||
                layerId === 'bygningPosisjon'
              }
              onToggle={() => toggleLayer(layerId)}
            />
          ))}
        </ul>
        <Separator />
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-medium">Favorite locations</span>
            {activeFavoriteView ? (
              <Badge
                variant="secondary"
                className="font-mono text-[11px]">
                z {activeFavoriteView.zoom.toFixed(2)}
              </Badge>
            ) : (
              <Badge variant="outline">Not set</Badge>
            )}
          </div>
          {favoriteViews.length > 0 ? (
            <>
              <select
                className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
                aria-label="Select favorite location"
                value={activeFavoriteView?.name ?? ''}
                onChange={event => onSelectFavoriteView(event.target.value)}>
                {favoriteViews.map(favoriteView => (
                  <option
                    key={favoriteView.name}
                    value={favoriteView.name}>
                    {favoriteView.name}
                  </option>
                ))}
              </select>
              <p className="text-[11px] font-mono text-muted-foreground">
                {activeFavoriteView?.center[0].toFixed(5)}, {activeFavoriteView?.center[1].toFixed(5)}
              </p>
            </>
          ) : (
            <p className="text-[11px] text-muted-foreground">Save named map centers and zoom levels locally.</p>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="xs"
              onClick={onSaveFavoriteView}>
              Save current
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              disabled={!activeFavoriteView}
              onClick={onClearFavoriteView}>
              Delete selected
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

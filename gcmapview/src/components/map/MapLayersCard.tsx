import { Compass, Cuboid, Eye, EyeOff, Map, Mountain, ScanLine } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import {
  MAP_LAYER_IDS,
  MAP_LAYER_LABELS,
  type LayerVisibility,
  type MapLayerId,
  useLayerVisibilityStore
} from '../../store/layerVisibilityStore';
import type { FavoriteMapView } from '../../store/mapViewStore';
import type { BackgroundMapId } from './MapView';

const layerSwatchClassName = 'inline-block shrink-0 rounded-full opacity-80';

const backgroundMapOptions: Array<{
  id: BackgroundMapId;
  label: string;
  title: string;
  icon: typeof Map;
}> = [
  {
    id: 'topo',
    label: 'Topo',
    title: 'Vis Kartverkets topografiske bakgrunnskart',
    icon: Map
  },
  {
    id: 'toporaster',
    label: 'Topo raster',
    title: 'Vis Kartverkets topografiske rasterlag',
    icon: Compass
  },
  {
    id: 'topograatone',
    label: 'Topo gråtone',
    title: 'Vis Kartverkets topografiske gråtonelag',
    icon: ScanLine
  },
  {
    id: 'none',
    label: 'Av',
    title: 'Skjul bakgrunnskart',
    icon: EyeOff
  }
];

function LayerToggleRow({
  layerId,
  visible,
  onToggle
}: {
  layerId: MapLayerId;
  visible: boolean;
  onToggle: () => void;
}) {
  const isLine =
    layerId === 'platformEdges' ||
    layerId === 'trackCentres' ||
    layerId === 'bygning' ||
    layerId === 'bygningSenterlinje';

  return (
    <li>
      <Tooltip>
        <TooltipTrigger
          render={
            <button
              type="button"
              className={cn(
                'flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left transition-opacity hover:bg-muted/60',
                visible ? 'text-foreground' : 'text-muted-foreground opacity-55'
              )}
              aria-pressed={visible}
              onClick={onToggle}
            />
          }>
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
        </TooltipTrigger>
        <TooltipContent>
          {visible ? `Skjul ${MAP_LAYER_LABELS[layerId]}` : `Vis ${MAP_LAYER_LABELS[layerId]}`}
        </TooltipContent>
      </Tooltip>
    </li>
  );
}

type MapLayersCardProps = {
  backgroundMap: BackgroundMapId;
  availableLayerIds?: readonly MapLayerId[];
  is3d: boolean;
  isLoadingAvailableLayers?: boolean;
  terrainEnabled: boolean;
  visibility: LayerVisibility;
  favoriteViews: FavoriteMapView[];
  activeFavoriteName?: string;
  onSelectBackgroundMap: (backgroundMap: BackgroundMapId) => void;
  onToggle3d: () => void;
  onToggleTerrain: () => void;
  onSaveFavoriteView: () => void;
  onClearFavoriteView: () => void;
  onSelectFavoriteView: (name: string) => void;
};

export function MapLayersCard({
  backgroundMap,
  availableLayerIds = MAP_LAYER_IDS,
  is3d,
  isLoadingAvailableLayers = false,
  terrainEnabled,
  visibility,
  favoriteViews,
  activeFavoriteName,
  onSelectBackgroundMap,
  onToggle3d,
  onToggleTerrain,
  onSaveFavoriteView,
  onClearFavoriteView,
  onSelectFavoriteView
}: MapLayersCardProps) {
  const toggleLayer = useLayerVisibilityStore(state => state.toggleLayer);
  const activeFavoriteView =
    favoriteViews.find(favoriteView => favoriteView.name === activeFavoriteName) ?? favoriteViews[0];

  return (
    <TooltipProvider>
      <Card
        size="sm"
        className="w-[240px] bg-card/95 shadow-md"
        aria-label="Kartlag">
        <CardHeader className="pb-0">
          <CardTitle>Kartlag</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between gap-3">
            <div
              className="flex items-center gap-1 rounded-full border border-border/70 bg-background/80 p-1"
              role="group"
              aria-label="Kart- og visningsvalg">
              {backgroundMapOptions.map(option => {
                const Icon = option.icon;
                return (
                  <Tooltip key={option.id}>
                    <TooltipTrigger
                      render={
                        <Button
                          type="button"
                          size="icon-xs"
                          variant={backgroundMap === option.id ? 'default' : 'ghost'}
                          className={cn('rounded-full')}
                          aria-pressed={backgroundMap === option.id}
                          aria-label={option.label}
                          onClick={() => onSelectBackgroundMap(option.id)}
                        />
                      }>
                      <Icon aria-hidden />
                    </TooltipTrigger>
                    <TooltipContent>{option.title}</TooltipContent>
                  </Tooltip>
                );
              })}
              <span
                className="mx-0.5 h-4 w-px bg-border/70"
                aria-hidden
              />
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      size="xs"
                      variant={is3d ? 'default' : 'ghost'}
                      className="rounded-full px-2"
                      aria-pressed={is3d}
                      aria-label="3D-visning"
                      onClick={onToggle3d}
                    />
                  }>
                  <Cuboid
                    className="size-3"
                    aria-hidden
                  />
                  <span className="text-[10px] font-semibold uppercase">3D</span>
                </TooltipTrigger>
                <TooltipContent>{is3d ? 'Bytt til 2D-kart' : 'Bytt til 3D-kart med høyde'}</TooltipContent>
              </Tooltip>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Button
                      type="button"
                      size="icon-xs"
                      variant={terrainEnabled ? 'default' : 'ghost'}
                      className={cn('rounded-full', !is3d ? 'cursor-default opacity-45' : '')}
                      aria-pressed={terrainEnabled}
                      aria-label="Terreng"
                      aria-disabled={!is3d}
                      onClick={() => {
                        if (is3d) {
                          onToggleTerrain();
                        }
                      }}
                    />
                  }>
                  <Mountain aria-hidden />
                </TooltipTrigger>
                <TooltipContent>
                  {!is3d
                    ? 'Terreng blir tilgjengelig i 3D-visning'
                    : terrainEnabled
                      ? 'Slå av terrengvisning'
                      : 'Slå på terrengvisning'}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
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
            {availableLayerIds.map(layerId => (
              <LayerToggleRow
                key={layerId}
                layerId={layerId}
                visible={visibility[layerId]}
                onToggle={() => toggleLayer(layerId)}
              />
            ))}
          </ul>
          {isLoadingAvailableLayers ? (
            <p className="text-[11px] text-muted-foreground">Laster tilgjengelige lag...</p>
          ) : null}
          {!isLoadingAvailableLayers && availableLayerIds.length === 0 ? (
            <p className="text-[11px] text-muted-foreground">Ingen datasett eksponerer kartlag akkurat nå.</p>
          ) : null}
          <Separator />
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">Favorittsteder</span>
              {activeFavoriteView ? (
                <Badge
                  variant="secondary"
                  className="font-mono text-[11px]">
                  z {activeFavoriteView.zoom.toFixed(2)}
                </Badge>
              ) : (
                <Badge variant="outline">Ikke satt</Badge>
              )}
            </div>
            {favoriteViews.length > 0 ? (
              <>
                <select
                  className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm"
                  aria-label="Velg favorittsted"
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
              <p className="text-[11px] text-muted-foreground">Lagre navngitte kartsentre og zoomnivåer lokalt.</p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                size="xs"
                onClick={onSaveFavoriteView}>
                Lagre gjeldende
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="xs"
                disabled={!activeFavoriteView}
                onClick={onClearFavoriteView}>
                Slett valgt
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}

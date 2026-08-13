import { NavLink, useLocation } from 'react-router';
import { Cuboid, Map, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useMapDimension } from '../map/useMapDimension';

export function AppNav() {
  const location = useLocation();
  const { is3d, adjustElevatedHeights, setIs3d, setAdjustElevatedHeights } = useMapDimension();

  return (
    <div className="flex flex-wrap items-center gap-2">
      <nav
        className="flex gap-2"
        aria-label="Main navigation">
        <Button
          variant={location.pathname === '/' ? 'default' : 'outline'}
          size="sm"
          nativeButton={false}
          render={
            <NavLink
              to="/"
              end
            />
          }>
          <Map data-icon="inline-start" />
          Map
        </Button>
        <Button
          variant={location.pathname === '/import' ? 'default' : 'outline'}
          size="sm"
          nativeButton={false}
          render={<NavLink to="/import" />}>
          <Upload data-icon="inline-start" />
          Import
        </Button>
      </nav>
      <Button
        size="sm"
        variant={is3d ? 'default' : 'outline'}
        aria-pressed={is3d}
        title={is3d ? 'Switch to 2D map' : 'Switch to 3D map with height'}
        onClick={() => setIs3d(value => !value)}>
        <Cuboid data-icon="inline-start" />
        {is3d ? '3D on' : '3D off'}
      </Button>
      {is3d ? (
        <label className="flex items-center gap-2 rounded-md border border-border bg-card/80 px-3 py-1.5 text-sm shadow-sm">
          <input
            type="checkbox"
            className="size-4 accent-foreground"
            checked={!adjustElevatedHeights}
            onChange={event => setAdjustElevatedHeights(!event.target.checked)}
          />
          <span>Terrain</span>
        </label>
      ) : null}
    </div>
  );
}

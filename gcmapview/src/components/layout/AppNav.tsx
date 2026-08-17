import { NavLink, useLocation } from 'react-router';
import { Map, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function AppNav() {
  const location = useLocation();

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
    </div>
  );
}

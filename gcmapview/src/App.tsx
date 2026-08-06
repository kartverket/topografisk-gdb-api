import { NavLink, Navigate, Route, Routes, useLocation } from 'react-router'
import { Cuboid, Map, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ImportView } from './ImportView'
import {
  MapDimensionProvider,
  useMapDimension,
} from './MapDimensionContext'
import { MapView } from './MapView'

function AppNav() {
  const location = useLocation()
  const { is3d, setIs3d } = useMapDimension()

  return (
    <div className="flex flex-wrap items-center gap-2">
      <nav className="flex gap-2" aria-label="Main navigation">
        <Button
          variant={location.pathname === '/' ? 'default' : 'outline'}
          size="sm"
          render={<NavLink to="/" end />}
        >
          <Map data-icon="inline-start" />
          Map
        </Button>
        <Button
          variant={location.pathname === '/import' ? 'default' : 'outline'}
          size="sm"
          render={<NavLink to="/import" />}
        >
          <Upload data-icon="inline-start" />
          Import
        </Button>
      </nav>
      <Button
        size="sm"
        variant={is3d ? 'default' : 'outline'}
        aria-pressed={is3d}
        title={is3d ? 'Switch to 2D map' : 'Switch to 3D map with height'}
        onClick={() => setIs3d((value) => !value)}
      >
        <Cuboid data-icon="inline-start" />
        {is3d ? '3D on' : '3D off'}
      </Button>
    </div>
  )
}

function App() {
  return (
    <MapDimensionProvider>
      <main className="box-border grid h-svh grid-rows-[auto_minmax(0,1fr)] gap-4 p-6 text-left md:gap-5">
        <header className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
          <div className="space-y-1">
            <p className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">
              geocomponents OGC API
            </p>
            <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              Geocomponents map
            </h1>
          </div>
          <AppNav />
        </header>
        <Routes>
          <Route path="/" element={<MapView />} />
          <Route path="/import" element={<ImportView />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </MapDimensionProvider>
  )
}

export default App

import { Navigate, Route, Routes } from 'react-router'
import { ImportView } from './components/import/ImportView'
import { AppNav } from './components/layout/AppNav'
import { MapDimensionProvider } from './components/map/MapDimensionContext'
import { MapView } from './components/map/MapView'

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

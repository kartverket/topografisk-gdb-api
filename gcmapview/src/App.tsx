import { Link, Navigate, Route, Routes } from 'react-router';
import { DebugView } from './components/debug/DebugView';
import { ImportView } from './components/import/ImportView';
import { AppNav } from './components/layout/AppNav';
import { MapDimensionProvider } from './components/map/MapDimensionContext';
import { MapView } from './components/map/MapView';

function App() {
  return (
    <MapDimensionProvider>
      <main className="box-border grid h-svh grid-rows-[auto_minmax(0,1fr)] gap-4 p-6 text-left md:gap-5">
        <header className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-end">
          <div className="space-y-1">
            <h1 className="text-3xl font-bold tracking-tight text-foreground md:text-4xl">
              <Link
                to="/"
                className="rounded-sm outline-none transition-opacity hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring/50">
                Geocomponents map
              </Link>
            </h1>
          </div>
          <AppNav />
        </header>
        <Routes>
          <Route
            path="/"
            element={<MapView />}
          />
          <Route
            path="/import"
            element={<ImportView />}
          />
          <Route
            path="/debug"
            element={<DebugView />}
          />
          <Route
            path="*"
            element={
              <Navigate
                to="/"
                replace
              />
            }
          />
        </Routes>
      </main>
    </MapDimensionProvider>
  );
}

export default App;

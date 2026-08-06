import { NavLink, Navigate, Route, Routes } from 'react-router';
import { ImportView } from './ImportView';
import { MapView } from './MapView';

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  [
    'shrink-0 rounded-full border px-3.5 py-2 text-sm no-underline',
    isActive ? 'border-ink-strong bg-ink-strong text-white' : 'border-nav-border bg-nav text-link'
  ].join(' ');

function App() {
  return (
    <main className="box-border grid h-svh grid-rows-[auto_minmax(0,1fr)] gap-[18px] p-6 text-left max-[720px]:gap-3 max-[720px]:p-3.5">
      <header className="flex items-end justify-between gap-6 max-[720px]:flex-col max-[720px]:items-start max-[720px]:gap-3">
        <div>
          <p className="text-[13px] font-bold tracking-[0.12em] text-muted uppercase">geocomponents OGC API</p>
          <h1 className="mt-0.5">Geocomponents map</h1>
        </div>
        <nav
          className="flex gap-2"
          aria-label="Main navigation">
          <NavLink
            to="/"
            end
            className={navLinkClass}>
            Map
          </NavLink>
          <NavLink
            to="/import"
            className={navLinkClass}>
            Import
          </NavLink>
        </nav>
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
  );
}

export default App;

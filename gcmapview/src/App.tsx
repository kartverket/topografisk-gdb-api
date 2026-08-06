import './App.css'
import { NavLink, Navigate, Route, Routes } from 'react-router'
import { ImportView } from './ImportView'
import { MapView } from './MapView'

function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">geocomponents OGC API</p>
          <h1>Geocomponents map</h1>
        </div>
        <nav className="app-nav" aria-label="Main navigation">
          <NavLink to="/" end>
            Map
          </NavLink>
          <NavLink to="/import">Import</NavLink>
        </nav>
      </header>
      <Routes>
        <Route path="/" element={<MapView />} />
        <Route path="/import" element={<ImportView />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </main>
  )
}

export default App

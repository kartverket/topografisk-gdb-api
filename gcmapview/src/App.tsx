import './App.css'
import { parcelsItemsUrl } from './geocomponentsApi'
import { MapView } from './MapView'

function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <p className="eyebrow">geocomponents OGC API</p>
          <h1>Cadastre parcels</h1>
        </div>
        <a
          href={parcelsItemsUrl}
          target="_blank"
          rel="noreferrer"
        >
          GeoJSON endpoint
        </a>
      </header>
      <MapView />
    </main>
  )
}

export default App

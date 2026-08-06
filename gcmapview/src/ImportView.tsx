import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { type ImportResult, uploadJsonFg } from './gcimportApi'

export function ImportView() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState('')
  const [isUploading, setIsUploading] = useState(false)

  async function submit() {
    if (!file) return
    setIsUploading(true)
    setError('')
    setResult(null)
    try {
      setResult(await uploadJsonFg(file))
    } catch (uploadError) {
      setError(
        uploadError instanceof Error ? uploadError.message : 'Import failed',
      )
    } finally {
      setIsUploading(false)
    }
  }

  function chooseFile(selected: File | undefined) {
    setFile(selected ?? null)
    setError('')
    setResult(null)
  }

  return (
    <section className="import-card">
      <div className="import-card__intro">
        <p className="eyebrow">JSON-FG upload</p>
        <h2>Import Bane features</h2>
        <p>
          Upload one JSON-FG FeatureCollection. Features are validated,
          transformed to EPSG:5973, and upserted by their Bane identity.
        </p>
      </div>

      <div
        className={`import-dropzone${file ? ' import-dropzone--selected' : ''}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          chooseFile(event.dataTransfer.files[0])
        }}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            inputRef.current?.click()
          }
        }}
        role="button"
        tabIndex={0}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".json,.jsonfg,application/json,application/geo+json"
          onChange={(event) => chooseFile(event.target.files?.[0])}
          hidden
        />
        <strong>{file ? file.name : 'Choose or drop a JSON-FG file'}</strong>
        <span>
          {file
            ? `${(file.size / 1024).toFixed(1)} KB`
            : 'A FeatureCollection containing Bane featureType values'}
        </span>
      </div>

      <button
        className="primary-button"
        disabled={!file || isUploading}
        onClick={submit}
        type="button"
      >
        {isUploading ? 'Importing…' : 'Import dataset'}
      </button>

      {error && (
        <div className="import-message import-message--error" role="alert">
          <strong>Import failed</strong>
          <span>{error}</span>
        </div>
      )}

      {result && (
        <div className="import-message import-message--success" role="status">
          <strong>
            Imported {result.total} feature{result.total === 1 ? '' : 's'}
          </strong>
          <span>
            {result.features
              .map((feature) => feature.collection)
              .filter((collection, index, all) => all.indexOf(collection) === index)
              .join(', ') || 'No features in the file'}
          </span>
          {result.features.length > 0 && (
            <code>
              {result.features
                .slice(0, 3)
                .map((feature) => feature.id)
                .join(', ')}
              {result.features.length > 3
                ? ` (+${result.features.length - 3} more)`
                : ''}
            </code>
          )}
          <Link to="/">View Bane layers on the map</Link>
        </div>
      )}
    </section>
  )
}

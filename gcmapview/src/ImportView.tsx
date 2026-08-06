import { useRef, useState } from 'react';
import { Link } from 'react-router';
import { type ImportResult, uploadJsonFg } from './gcimportApi';

export function ImportView() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  async function submit() {
    if (!file) return;
    setIsUploading(true);
    setError('');
    setResult(null);
    try {
      setResult(await uploadJsonFg(file));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Import failed');
    } finally {
      setIsUploading(false);
    }
  }

  function chooseFile(selected: File | undefined) {
    setFile(selected ?? null);
    setError('');
    setResult(null);
  }

  return (
    <section className="mx-auto grid w-[min(100%,720px)] max-w-[720px] gap-[18px] rounded-[18px] border border-panel-border bg-white p-7 shadow-[0_20px_45px_rgb(15_23_42/0.1)] max-[720px]:p-5">
      <div className="grid gap-2">
        <p className="text-[13px] font-bold tracking-[0.12em] text-muted uppercase">JSON-FG upload</p>
        <h2>Import Bane features</h2>
        <p className="max-w-[52ch] text-slate-600">
          Upload one JSON-FG FeatureCollection. Features are validated, transformed to EPSG:5973, and upserted by their
          Bane identity.
        </p>
      </div>

      <div
        className={[
          'grid cursor-pointer gap-1.5 rounded-[14px] border-[1.5px] border-dashed border-slate-400 bg-slate-50 px-5 py-7 text-left hover:border-link focus-visible:border-link focus-visible:outline-none',
          file ? 'border-solid border-link bg-nav' : ''
        ].join(' ')}
        onClick={() => inputRef.current?.click()}
        onDragOver={event => event.preventDefault()}
        onDrop={event => {
          event.preventDefault();
          chooseFile(event.dataTransfer.files[0]);
        }}
        onKeyDown={event => {
          if (event.key === 'Enter' || event.key === ' ') {
            inputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}>
        <input
          ref={inputRef}
          type="file"
          accept=".json,.jsonfg,application/json,application/geo+json"
          onChange={event => chooseFile(event.target.files?.[0])}
          hidden
        />
        <strong className="text-base text-ink-strong">{file ? file.name : 'Choose or drop a JSON-FG file'}</strong>
        <span className="text-sm text-slate-500">
          {file ? `${(file.size / 1024).toFixed(1)} KB` : 'A FeatureCollection containing Bane featureType values'}
        </span>
      </div>

      <button
        className="justify-self-start rounded-full border border-ink-strong bg-ink-strong px-[18px] py-3 text-sm font-bold font-sans text-white disabled:cursor-not-allowed disabled:opacity-55"
        disabled={!file || isUploading}
        onClick={submit}
        type="button">
        {isUploading ? 'Importing…' : 'Import dataset'}
      </button>

      {error && (
        <div
          className="grid gap-1.5 rounded-xl border border-red-200 bg-red-50 px-4 py-3.5 text-red-800"
          role="alert">
          <strong>Import failed</strong>
          <span className="text-sm">{error}</span>
        </div>
      )}

      {result && (
        <div
          className="grid gap-1.5 rounded-xl border border-green-200 bg-green-50 px-4 py-3.5 text-green-800"
          role="status">
          <strong>
            Imported {result.total} feature{result.total === 1 ? '' : 's'}
          </strong>
          <span className="text-sm">
            {result.features
              .map(feature => feature.collection)
              .filter((collection, index, all) => all.indexOf(collection) === index)
              .join(', ') || 'No features in the file'}
          </span>
          {result.features.length > 0 && (
            <code>
              {result.features
                .slice(0, 3)
                .map(feature => feature.id)
                .join(', ')}
              {result.features.length > 3 ? ` (+${result.features.length - 3} more)` : ''}
            </code>
          )}
          <Link
            className="w-fit text-sm text-link"
            to="/">
            View Bane layers on the map
          </Link>
        </div>
      )}
    </section>
  );
}

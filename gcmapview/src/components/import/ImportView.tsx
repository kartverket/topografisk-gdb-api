import { useRef, useState } from 'react';
import { Link } from 'react-router';
import { AlertCircle, CheckCircle2, FileJson, Loader2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { inferImportProfile, type ImportProfile, type ImportResult, uploadJsonFg } from '../../api/gcimportApi';

const PROFILE_META: Record<ImportProfile, { title: string; crs: string; detail: string; footer: string }> = {
  bane: {
    title: 'Bane',
    crs: 'EPSG:5973',
    detail: 'Jernbaneplattformkant and Spormidt are preserved as MultiLineString geometry and upserted by lokalid + identifikasjon_navnerom.',
    footer: 'Upserts are idempotent by Bane business key.'
  },
  bygning: {
    title: 'Bygning',
    crs: 'EPSG:5972',
    detail:
      'Bygning linework and area footprints are routed through one importer and preserved as MultiLineString or MultiPolygon geometry by collection.',
    footer: 'Upserts are idempotent by Bygning business key.'
  }
};

export function ImportView() {
  const inputRef = useRef<HTMLInputElement>(null);
  const selectionVersionRef = useRef(0);
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<ImportProfile>('bane');
  const [detectedProfile, setDetectedProfile] = useState<ImportProfile | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const profileMeta = PROFILE_META[profile];

  async function submit() {
    if (!file) return;
    setIsUploading(true);
    setError('');
    setResult(null);
    try {
      setResult(await uploadJsonFg(file, profile));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Import failed');
    } finally {
      setIsUploading(false);
    }
  }

  async function chooseFile(selected: File | undefined) {
    const nextFile = selected ?? null;
    const selectionVersion = selectionVersionRef.current + 1;
    selectionVersionRef.current = selectionVersion;
    setFile(nextFile);
    setError('');
    setResult(null);
    setDetectedProfile(null);
    if (!nextFile) return;

    const inferredProfile = await inferImportProfile(nextFile);
    if (selectionVersionRef.current !== selectionVersion || inferredProfile === null) {
      return;
    }
    setProfile(inferredProfile);
    setDetectedProfile(inferredProfile);
  }

  function chooseProfile(nextProfile: ImportProfile) {
    setProfile(nextProfile);
    setDetectedProfile(null);
    setError('');
    setResult(null);
  }

  const collections = result ? [...new Set(result.features.map(feature => feature.collection))] : [];

  return (
    <Card className="mx-auto w-full max-w-xl">
      <CardHeader>
        <p className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">Feature import</p>
        <CardTitle className="text-2xl">Import {profileMeta.title} features</CardTitle>
        <CardDescription className="max-w-[52ch]">
          Upload JSON-FG, or classic GeoJSON (.geojson with CRS and objtype). Features are validated, transformed to{' '}
          {profileMeta.crs}, and imported with the selected dataset profile.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {(['bane', 'bygning'] as const).map(option => (
              <Button
                key={option}
                type="button"
                variant={profile === option ? 'default' : 'outline'}
                onClick={() => chooseProfile(option)}>
                {PROFILE_META[option].title}
              </Button>
            ))}
          </div>
          <p className="text-sm text-muted-foreground">{profileMeta.detail}</p>
          {detectedProfile && file && (
            <p className="text-sm text-muted-foreground">Detected {PROFILE_META[detectedProfile].title} from file contents.</p>
          )}
        </div>

        <button
          type="button"
          className={cn(
            'grid w-full cursor-pointer gap-1.5 rounded-2xl border border-dashed border-border bg-muted/40 px-5 py-7 text-left transition-colors hover:border-ring hover:bg-muted/60 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none',
            file && 'border-solid border-primary bg-accent'
          )}
          onClick={() => inputRef.current?.click()}
          onDragOver={event => event.preventDefault()}
          onDrop={event => {
            event.preventDefault();
            chooseFile(event.dataTransfer.files[0]);
          }}>
          <input
            ref={inputRef}
            type="file"
            accept=".json,.jsonfg,.geojson,application/json,application/geo+json"
            onChange={event => chooseFile(event.target.files?.[0])}
            hidden
          />
          <span className="inline-flex items-center gap-2 text-base font-medium text-foreground">
            <FileJson className="size-4" />
            {file ? file.name : 'Choose or drop a JSON-FG or .geojson file'}
          </span>
          <span className="text-sm text-muted-foreground">
            {file
              ? `${(file.size / 1024).toFixed(1)} KB`
              : '.jsonfg/.json for JSON-FG, .geojson for classic CRS exports'}
          </span>
        </button>

        <Button
          size="lg"
          disabled={!file || isUploading}
          onClick={submit}>
          {isUploading ? (
            <>
              <Loader2
                data-icon="inline-start"
                className="animate-spin"
              />
              Importing…
            </>
          ) : (
            'Import dataset'
          )}
        </Button>

        {error && (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Import failed</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {result && (
          <Alert className="border-chart-1/40 bg-chart-1/10">
            <CheckCircle2 className="text-foreground" />
            <AlertTitle>
              Imported {result.total} feature
              {result.total === 1 ? '' : 's'}
            </AlertTitle>
            <AlertDescription className="space-y-3">
              <div className="flex flex-wrap gap-1.5">
                {collections.length > 0 ? (
                  collections.map(collection => (
                    <Badge
                      key={collection}
                      variant="secondary">
                      {collection}
                    </Badge>
                  ))
                ) : (
                  <span>No features in the file</span>
                )}
              </div>
              {result.features.length > 0 && (
                <>
                  <Separator />
                  <code className="block rounded-md bg-background/80 px-2 py-1 font-mono text-xs text-foreground">
                    {result.features
                      .slice(0, 3)
                      .map(feature => feature.id)
                      .join(', ')}
                    {result.features.length > 3 ? ` (+${result.features.length - 3} more)` : ''}
                  </code>
                </>
              )}
              <Button
                variant="link"
                size="sm"
                className="h-auto px-0"
                render={<Link to="/" />}>
                Return to map
              </Button>
            </AlertDescription>
          </Alert>
        )}
      </CardContent>

      <CardFooter className="text-xs text-muted-foreground">{profileMeta.footer}</CardFooter>
    </Card>
  );
}

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { AlertCircle, CheckCircle2, FileJson, Loader2 } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import {
  getImportRun,
  inferImportProfile,
  type ImportProfile,
  type ImportResult,
  type ImportRun,
  startImport
} from '../../api/importApi';

const PROFILE_META: Record<ImportProfile, { title: string; crs: string; detail: string; footer: string }> = {
  fkb_bane: {
    title: 'FKB-Bane',
    crs: 'EPSG:5973',
    detail:
      'Jernbaneplattformkant og Spormidt bevares som MultiLineString-geometri og oppdateres ved lokalid + identifikasjon_navnerom.',
    footer: 'Oppdateringer er idempotente for FKB-Bane sin forretningsnøkkel.'
  },
  bygning: {
    title: 'Bygning',
    crs: 'EPSG:5972',
    detail:
      'Bygningslinjer, senterlinjer, posisjoner og omriss rutes gjennom samme importløp og bevares etter samlingsgeometri.',
    footer: 'Oppdateringer er idempotente for Bygning sin forretningsnøkkel.'
  }
};

export function ImportView() {
  const inputRef = useRef<HTMLInputElement>(null);
  const selectionVersionRef = useRef(0);
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<ImportProfile>('fkb_bane');
  const [detectedProfile, setDetectedProfile] = useState<ImportProfile | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [importRun, setImportRun] = useState<ImportRun | null>(null);
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const profileMeta = PROFILE_META[profile];
  const importId = result?.import_id;
  const importLocation = result?.location;
  const importProfile = result?.profile;

  useEffect(() => {
    if (!importId || !importLocation || !importProfile) {
      return;
    }
    const currentImportId = importId;
    const currentImportLocation = importLocation;
    const currentImportProfile = importProfile;
    let cancelled = false;
    let timer: number | undefined;

    async function poll() {
      try {
        const run = await getImportRun(currentImportId, currentImportLocation, currentImportProfile);
        if (cancelled) return;
        setImportRun(run);
        if (run.status === 'accepted' || run.status === 'running') {
          timer = window.setTimeout(poll, 1000);
        }
      } catch (pollError) {
        if (cancelled) return;
        setError(pollError instanceof Error ? pollError.message : 'Kunne ikke hente importstatus');
      }
    }

    void poll();
    return () => {
      cancelled = true;
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
    };
  }, [importId, importLocation, importProfile]);

  async function submit() {
    if (!file) return;
    setIsUploading(true);
    setError('');
    setResult(null);
    setImportRun(null);
    try {
      setResult(await startImport(file, profile));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Importen mislyktes');
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
    setImportRun(null);
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
    setImportRun(null);
  }

  const progressPercent = progressValue(importRun);
  const isActive = isUploading || importRun?.status === 'accepted' || importRun?.status === 'running';
  const currentPhase = importRun?.phase ?? 'accepted';
  const currentStatus = importRun?.status ?? 'accepted';

  return (
    <Card className="mx-auto w-full max-w-xl">
      <CardHeader>
        <p className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">Import</p>
        <CardTitle className="text-2xl">Importer {profileMeta.title}-data</CardTitle>
        <CardDescription className="max-w-[52ch]">
          Last opp JSON-FG eller klassisk GeoJSON (.geojson med CRS og objtype). Objektene blir validert, transformert
          til {profileMeta.crs} og importert med valgt datasettprofil.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            {(['fkb_bane', 'bygning'] as const).map(option => (
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
            <p className="text-sm text-muted-foreground">
              Oppdaget {PROFILE_META[detectedProfile].title} fra filinnholdet.
            </p>
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
            {file ? file.name : 'Velg eller slipp en JSON-FG- eller .geojson-fil'}
          </span>
          <span className="text-sm text-muted-foreground">
            {file
              ? `${(file.size / 1024).toFixed(1)} KB`
              : '.jsonfg/.json for JSON-FG, .geojson for klassiske CRS-eksporter'}
          </span>
        </button>

        <Button
          size="lg"
          disabled={!file || isActive}
          onClick={submit}>
          {isActive ? (
            <>
              <Loader2
                data-icon="inline-start"
                className="animate-spin"
              />
              Importerer…
            </>
          ) : (
            'Importer datasett'
          )}
        </Button>

        {error && (
          <Alert variant="destructive">
            <AlertCircle />
            <AlertTitle>Importen mislyktes</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {result && (
          <Alert className="border-chart-1/40 bg-chart-1/10">
            <CheckCircle2 className="text-foreground" />
            <AlertTitle>{statusTitle(importRun, result)}</AlertTitle>
            <AlertDescription className="space-y-3">
              <div className="space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  <Badge variant="secondary">Import-ID: {result.import_id}</Badge>
                  <Badge variant="secondary">Fase: {phaseLabel(currentPhase)}</Badge>
                  <Badge variant="secondary">Batcher: {importRun?.processed_batches ?? 0}</Badge>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {phaseSteps(currentPhase, currentStatus).map(step => (
                    <Badge
                      key={step.label}
                      variant={step.variant}>
                      {step.label}
                    </Badge>
                  ))}
                </div>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{progressLabel(importRun, result)}</span>
                    <span>{progressPercent === null ? indeterminateLabel(currentPhase) : `${progressPercent}%`}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-muted">
                    <div
                      className={cn(
                        'h-full rounded-full bg-primary transition-all',
                        progressPercent === null && 'w-1/3 animate-pulse'
                      )}
                      style={progressPercent === null ? undefined : { width: `${progressPercent}%` }}
                    />
                  </div>
                  {progressPercent === null && (
                    <p className="text-xs text-muted-foreground">{indeterminateDescription(currentPhase)}</p>
                  )}
                </div>
              </div>
              {importRun && (importRun.succeeded_features > 0 || importRun.failed_features > 0) && (
                <>
                  <Separator />
                  <div className="grid gap-1 text-xs text-foreground">
                    <div>Vellykkede objekter: {importRun.succeeded_features}</div>
                    <div>Feilede objekter: {importRun.failed_features}</div>
                    <div>Vellykkede batcher: {importRun.succeeded_batches}</div>
                    <div>Feilede batcher: {importRun.failed_batches}</div>
                  </div>
                </>
              )}
              {importRun && terminalStats(importRun) && (
                <>
                  <Separator />
                  <div className="grid gap-1 text-xs text-foreground">
                    <div>Kjøretid: {terminalStats(importRun)?.durationLabel}</div>
                    <div>Hastighet: {terminalStats(importRun)?.throughputLabel}</div>
                    <div>Fullført: {terminalStats(importRun)?.completedLabel}</div>
                  </div>
                </>
              )}
              {importRun?.last_error?.reason && (
                <>
                  <Separator />
                  <div className="text-xs text-destructive">{importRun.last_error.reason}</div>
                </>
              )}
              <Button
                variant="link"
                size="sm"
                className="h-auto px-0"
                render={<Link to="/" />}>
                Tilbake til kartet
              </Button>
            </AlertDescription>
          </Alert>
        )}
      </CardContent>

      <CardFooter className="text-xs text-muted-foreground">{profileMeta.footer}</CardFooter>
    </Card>
  );
}

function progressValue(importRun: ImportRun | null): number | null {
  if (!importRun) {
    return null;
  }
  if (importRun.progress !== null) {
    return importRun.progress;
  }
  if (importRun.total_features === null || importRun.total_features <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round((importRun.processed_features / importRun.total_features) * 100)));
}

function progressLabel(importRun: ImportRun | null, result: ImportResult): string {
  if (!importRun) {
    return `Import ${result.import_id} er mottatt av jobbtjenesten`;
  }
  if (importRun.phase === 'accepted') {
    return 'Lagt i jobbkø og venter på at importen skal starte';
  }
  if (importRun.phase === 'parsing') {
    return 'Tolker filen og finner totalt antall objekter';
  }
  if (importRun.total_features === null) {
    return 'Forbereder opptelling av objekter';
  }
  return `${importRun.processed_features} / ${importRun.total_features} objekter, ${importRun.processed_batches} batcher behandlet`;
}

function statusTitle(importRun: ImportRun | null, result: ImportResult): string {
  if (!importRun) {
    return `Import ${result.import_id} er mottatt`;
  }
  if (importRun.status === 'successful') {
    return `Importerte ${importRun.succeeded_features} objekt${importRun.succeeded_features === 1 ? '' : 'er'}`;
  }
  if (importRun.status === 'failed') {
    return 'Importen mislyktes';
  }
  if (importRun.phase === 'accepted') {
    return 'Venter på import';
  }
  if (importRun.phase === 'parsing') {
    return 'Tolker import';
  }
  return 'Import pågår';
}

function terminalStats(importRun: ImportRun): {
  durationLabel: string;
  throughputLabel: string;
  completedLabel: string;
} | null {
  if (!importRun.completed_at) {
    return null;
  }

  const startedAt = Date.parse(importRun.started_at);
  const completedAt = Date.parse(importRun.completed_at);
  if (Number.isNaN(startedAt) || Number.isNaN(completedAt) || completedAt < startedAt) {
    return null;
  }

  const durationSeconds = Math.max(0.001, (completedAt - startedAt) / 1000);
  const processedFeatures = importRun.succeeded_features + importRun.failed_features;
  const featuresPerSecond = processedFeatures / durationSeconds;

  return {
    durationLabel: formatDuration(durationSeconds),
    throughputLabel: `${featuresPerSecond.toFixed(featuresPerSecond >= 10 ? 0 : 1)} objekter/s`,
    completedLabel: new Date(completedAt).toLocaleTimeString()
  };
}

function formatDuration(durationSeconds: number): string {
  if (durationSeconds < 60) {
    return `${durationSeconds.toFixed(durationSeconds >= 10 ? 0 : 1)} s`;
  }
  const minutes = Math.floor(durationSeconds / 60);
  const seconds = Math.round(durationSeconds % 60);
  return `${minutes}m ${seconds}s`;
}

function indeterminateLabel(phase: string | null): string {
  if (phase === 'accepted') {
    return 'Mottatt';
  }
  if (phase === 'parsing') {
    return 'Tolker…';
  }
  return 'Arbeider…';
}

function indeterminateDescription(phase: string | null): string {
  if (phase === 'accepted') {
    return 'gcjobs har mottatt opplastingen og sender den videre til gcimport.';
  }
  if (phase === 'parsing') {
    return 'Filen tolkes før batchframdrift kan måles.';
  }
  return 'Venter på den første målbare framdriftsoppdateringen.';
}

function phaseLabel(phase: string | null): string {
  if (phase === 'accepted') {
    return 'Mottatt';
  }
  if (phase === 'parsing') {
    return 'Tolking';
  }
  if (phase === 'importing') {
    return 'Import';
  }
  if (phase === 'completed') {
    return 'Fullført';
  }
  if (phase === 'forwarding') {
    return 'Videresending';
  }
  return phase ?? 'Ukjent';
}

function phaseSteps(
  phase: string | null,
  status: ImportRun['status'] | 'accepted'
): Array<{ label: string; variant: 'default' | 'secondary' | 'outline' | 'destructive' }> {
  const current = phase ?? 'accepted';
  const currentIndex = ['accepted', 'parsing', 'importing', 'completed'].indexOf(current);
  return [
    { label: 'Mottatt', phase: 'accepted' },
    { label: 'Tolking', phase: 'parsing' },
    { label: 'Import', phase: 'importing' },
    { label: status === 'failed' ? 'Feilet' : 'Fullført', phase: status === 'failed' ? 'failed' : 'completed' }
  ].map(step => {
    if (status === 'failed' && step.phase === 'failed') {
      return { label: step.label, variant: 'destructive' as const };
    }
    if (step.phase === current) {
      return { label: step.label, variant: 'default' as const };
    }
    if (step.phase === 'completed' && status === 'successful') {
      return { label: step.label, variant: 'default' as const };
    }
    const stepIndex = ['accepted', 'parsing', 'importing', 'completed'].indexOf(step.phase);
    if (stepIndex !== -1 && currentIndex !== -1 && stepIndex < currentIndex) {
      return { label: step.label, variant: 'secondary' as const };
    }
    return { label: step.label, variant: 'outline' as const };
  });
}

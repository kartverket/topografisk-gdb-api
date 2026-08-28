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
  const [files, setFiles] = useState<File[]>([]);
  const [profile, setProfile] = useState<ImportProfile>('fkb_bane');
  const [detectedProfile, setDetectedProfile] = useState<ImportProfile | null>(null);
  const [hasMixedDetectedProfiles, setHasMixedDetectedProfiles] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [importRun, setImportRun] = useState<ImportRun | null>(null);
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const profileMeta = PROFILE_META[profile];
  const totalSelectedBytes = files.reduce((total, currentFile) => total + currentFile.size, 0);
  const sosiFileCount = files.filter(file => isSosiFilename(file.name)).length;
  const hasOnlySosiFiles = files.length > 0 && sosiFileCount === files.length;
  const hasMixedSosiSelection = sosiFileCount > 0 && sosiFileCount < files.length;
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
    if (files.length === 0 || hasMixedDetectedProfiles || hasMixedSosiSelection) return;
    setIsUploading(true);
    setError('');
    setResult(null);
    setImportRun(null);
    try {
      setResult(await startImport(files, profile));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : 'Importen mislyktes');
    } finally {
      setIsUploading(false);
    }
  }

  async function chooseFiles(selected: FileList | File[] | null | undefined) {
    const nextFiles = deduplicateFiles(Array.from(selected ?? []));
    const selectionVersion = selectionVersionRef.current + 1;
    selectionVersionRef.current = selectionVersion;
    setFiles(nextFiles);
    setError('');
    setResult(null);
    setImportRun(null);
    setDetectedProfile(null);
    setHasMixedDetectedProfiles(false);
    if (nextFiles.length === 0) return;

    const inferredProfiles = await Promise.all(nextFiles.map(file => inferImportProfile(file)));
    if (selectionVersionRef.current !== selectionVersion) {
      return;
    }

    const uniqueProfiles = Array.from(
      new Set(inferredProfiles.filter((value): value is ImportProfile => value !== null))
    );
    setHasMixedDetectedProfiles(uniqueProfiles.length > 1);
    if (uniqueProfiles.length === 1) {
      setProfile(uniqueProfiles[0]);
      setDetectedProfile(uniqueProfiles[0]);
    }
  }

  function chooseProfile(nextProfile: ImportProfile) {
    setProfile(nextProfile);
    setDetectedProfile(null);
    setError('');
    setResult(null);
    setImportRun(null);
  }

  const importedFileNames = importRun?.filenames.length ? importRun.filenames : files.map(file => file.name);
  const isSosiRun = importedFileNames.length > 0 && importedFileNames.every(isSosiFilename);
  const isStatsOnlyMode = hasOnlySosiFiles || isSosiRun;
  const progressPercent = progressValue(importRun, isStatsOnlyMode);
  const isActive = isUploading || importRun?.status === 'accepted' || importRun?.status === 'running';
  const currentPhase = importRun?.phase ?? 'accepted';
  const currentStatus = importRun?.status ?? 'accepted';

  return (
    <section className="min-h-0 overflow-y-auto pr-1">
      <Card className="mx-auto w-full max-w-xl">
        <CardHeader>
          <p className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">Import</p>
          <CardTitle className="text-2xl">
            {hasOnlySosiFiles ? 'Analyser SOSI-filer' : `Importer ${profileMeta.title}-data`}
          </CardTitle>
          <CardDescription className="max-w-[52ch]">
            {hasOnlySosiFiles
              ? 'Last opp en eller flere SOSI-filer. gcimport tolker dem kun for statistikk, og ingen objekter sendes videre eller lagres i datasettet.'
              : `Last opp en eller flere JSON-FG-, GeoJSON- eller SOSI-filer. JSON-FG og GeoJSON valideres, transformeres til ${profileMeta.crs} og importeres med valgt datasettprofil, mens SOSI bare analyseres for statistikk.`}
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
            {detectedProfile && files.length > 0 && (
              <p className="text-sm text-muted-foreground">
                Oppdaget {PROFILE_META[detectedProfile].title} fra filinnholdet i utvalget.
              </p>
            )}
            {hasOnlySosiFiles && (
              <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-foreground">
                SOSI-opplasting kjører i statistikkmodus. Ingen objekter blir importert, selv om du velger en
                datasettprofil.
              </div>
            )}
          </div>

          <button
            type="button"
            disabled={isActive}
            className={cn(
              'grid w-full gap-1.5 rounded-2xl border border-dashed border-border bg-muted/40 px-5 py-7 text-left transition-colors focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 focus-visible:outline-none',
              !isActive && 'cursor-pointer hover:border-ring hover:bg-muted/60',
              isActive && 'cursor-not-allowed opacity-70',
              files.length > 0 && 'border-solid border-primary bg-accent'
            )}
            onClick={() => inputRef.current?.click()}
            onDragOver={event => event.preventDefault()}
            onDrop={event => {
              event.preventDefault();
              if (isActive) {
                return;
              }
              void chooseFiles(event.dataTransfer.files);
            }}>
            <input
              ref={inputRef}
              type="file"
              multiple
              accept=".json,.jsonfg,.geojson,.sos,application/json,application/geo+json,text/plain"
              onChange={event => {
                void chooseFiles(event.target.files);
                event.target.value = '';
              }}
              hidden
            />
            <span className="inline-flex items-center gap-2 text-base font-medium text-foreground">
              <FileJson className="size-4" />
              {files.length === 0
                ? 'Velg eller slipp JSON-FG-, .geojson- eller .sos-filer'
                : files.length === 1
                  ? files[0].name
                  : `${files.length} filer valgt`}
            </span>
            <span className="text-sm text-muted-foreground">
              {files.length > 0
                ? `${formatFileSize(totalSelectedBytes)} totalt`
                : '.jsonfg/.json for JSON-FG, .geojson for klassiske CRS-eksporter, .sos for statistikkmodus'}
            </span>
          </button>

          {files.length > 0 && (
            <div className="space-y-2 rounded-2xl border bg-background/70 p-3">
              <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span>{files.length} filer klare for samlet import</span>
                <span>{formatFileSize(totalSelectedBytes)}</span>
              </div>
              <div className="space-y-1.5">
                {files.map(currentFile => (
                  <div
                    key={`${currentFile.name}:${currentFile.size}:${currentFile.lastModified}`}
                    className="flex items-center justify-between gap-3 text-sm text-foreground">
                    <span className="truncate">{currentFile.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{formatFileSize(currentFile.size)}</span>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                {hasOnlySosiFiles
                  ? 'Alle valgte SOSI-filer lastes opp samlet og analyseres for strukturell statistikk. Ingen objekter skrives til datasettet.'
                  : 'Alle valgte filer lastes opp til jobb- og importtjenesten før validering og import starter.'}
              </p>
            </div>
          )}

          <Button
            size="lg"
            disabled={files.length === 0 || isActive || hasMixedDetectedProfiles || hasMixedSosiSelection}
            onClick={submit}>
            {isActive ? (
              <>
                <Loader2
                  data-icon="inline-start"
                  className="animate-spin"
                />
                {isStatsOnlyMode ? 'Analyserer…' : 'Importerer…'}
              </>
            ) : hasOnlySosiFiles ? (
              files.length > 1 ? (
                `Analyser ${files.length} SOSI-filer`
              ) : (
                'Analyser SOSI-fil'
              )
            ) : files.length > 1 ? (
              `Importer ${files.length} filer`
            ) : (
              'Importer datasett'
            )}
          </Button>

          {hasMixedDetectedProfiles && (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertTitle>Blandet datasettutvalg</AlertTitle>
              <AlertDescription>Velg filer som tilhører samme datasettprofil før importen startes.</AlertDescription>
            </Alert>
          )}

          {hasMixedSosiSelection && (
            <Alert variant="destructive">
              <AlertCircle />
              <AlertTitle>Blandet filformatutvalg</AlertTitle>
              <AlertDescription>
                SOSI-filer kan ikke blandes med JSON-FG eller GeoJSON i samme opplasting.
              </AlertDescription>
            </Alert>
          )}

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
              <AlertTitle>{statusTitle(importRun, result, isStatsOnlyMode)}</AlertTitle>
              <AlertDescription className="space-y-3">
                {isStatsOnlyMode && (
                  <div className="rounded-2xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-xs text-foreground">
                    Denne kjøringen analyserer bare SOSI-struktur og teller innhold. Ingen objekter blir importert eller
                    skrevet til kartdatasettet.
                  </div>
                )}
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="secondary">Import-ID: {result.import_id}</Badge>
                    <Badge variant="secondary">Filer: {importedFileNames.length}</Badge>
                    <Badge variant="secondary">Fase: {phaseLabel(currentPhase)}</Badge>
                    <Badge variant="secondary">Batcher: {importRun?.processed_batches ?? 0}</Badge>
                    {isStatsOnlyMode && <Badge variant="secondary">Kun statistikk</Badge>}
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
                      <span>{progressLabel(importRun, result, isStatsOnlyMode)}</span>
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
                      <p className="text-xs text-muted-foreground">
                        {indeterminateDescription(currentPhase, isStatsOnlyMode)}
                      </p>
                    )}
                  </div>
                </div>
                {importedFileNames.length > 0 && (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      <div className="text-xs font-medium tracking-[0.12em] text-muted-foreground uppercase">
                        Kildefiler
                      </div>
                      <div className="grid gap-1 text-xs text-foreground">
                        {importedFileNames.map(fileName => (
                          <div key={fileName}>{fileName}</div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
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
                {isStatsOnlyMode && importRun?.status === 'successful' && (
                  <>
                    <Separator />
                    <div className="grid gap-1 text-xs text-foreground">
                      <div>Tolkede objekter: {importRun.total_features ?? 0}</div>
                      <div>Importerte objekter: 0</div>
                      <div>Analyserte filer: {importedFileNames.length}</div>
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

        <CardFooter className="text-xs text-muted-foreground">
          {hasOnlySosiFiles ? 'SOSI kjøres som analyse uten varige dataendringer.' : profileMeta.footer}
        </CardFooter>
      </Card>
    </section>
  );
}

function progressValue(importRun: ImportRun | null, isStatsOnly: boolean): number | null {
  if (!importRun) {
    return null;
  }
  if (isStatsOnly && importRun.status === 'successful') {
    return 100;
  }
  if (importRun.progress !== null) {
    return importRun.progress;
  }
  if (importRun.total_features === null || importRun.total_features <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, Math.round((importRun.processed_features / importRun.total_features) * 100)));
}

function progressLabel(importRun: ImportRun | null, result: ImportResult, isStatsOnly: boolean): string {
  if (!importRun) {
    return isStatsOnly
      ? `SOSI-analyse ${result.import_id} er mottatt av jobbtjenesten`
      : `Import ${result.import_id} er mottatt av jobbtjenesten`;
  }
  if (importRun.phase === 'accepted') {
    return 'Lagt i jobbkø og venter på at importen skal starte';
  }
  if (importRun.phase === 'parsing') {
    return isStatsOnly ? 'Tolker SOSI-filen og beregner statistikk' : 'Tolker filen og finner totalt antall objekter';
  }
  if (isStatsOnly && importRun.status === 'successful') {
    return 'SOSI-analysen er fullført. Ingen objekter ble importert.';
  }
  if (importRun.total_features === null) {
    return isStatsOnly ? 'Forbereder statistikkoppsummering' : 'Forbereder opptelling av objekter';
  }
  return `${importRun.processed_features} / ${importRun.total_features} objekter, ${importRun.processed_batches} batcher behandlet`;
}

function statusTitle(importRun: ImportRun | null, result: ImportResult, isStatsOnly: boolean): string {
  if (!importRun) {
    return isStatsOnly ? `SOSI-analyse ${result.import_id} er mottatt` : `Import ${result.import_id} er mottatt`;
  }
  if (isStatsOnly && importRun.status === 'successful') {
    return 'SOSI analysert, ingen objekter importert';
  }
  if (importRun.status === 'successful') {
    return `Importerte ${importRun.succeeded_features} objekt${importRun.succeeded_features === 1 ? '' : 'er'}`;
  }
  if (importRun.status === 'failed') {
    return isStatsOnly ? 'SOSI-analysen mislyktes' : 'Importen mislyktes';
  }
  if (importRun.phase === 'accepted') {
    return isStatsOnly ? 'Venter på SOSI-analyse' : 'Venter på import';
  }
  if (importRun.phase === 'parsing') {
    return isStatsOnly ? 'Tolker SOSI' : 'Tolker import';
  }
  return isStatsOnly ? 'SOSI-analyse pågår' : 'Import pågår';
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

function indeterminateDescription(phase: string | null, isStatsOnly: boolean): string {
  if (phase === 'accepted') {
    return 'gcjobs har mottatt opplastingen og sender den videre til gcimport.';
  }
  if (phase === 'parsing') {
    return isStatsOnly
      ? 'SOSI-filen tolkes før statistikkoppsummeringen kan vises.'
      : 'Filen tolkes før batchframdrift kan måles.';
  }
  return 'Venter på den første målbare framdriftsoppdateringen.';
}

function isSosiFilename(filename: string): boolean {
  return filename.trim().toLowerCase().endsWith('.sos');
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

function deduplicateFiles(files: File[]): File[] {
  return Array.from(new Map(files.map(file => [`${file.name}:${file.size}:${file.lastModified}`, file])).values());
}

function formatFileSize(sizeBytes: number): string {
  if (sizeBytes >= 1024 * 1024) {
    return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(sizeBytes / 1024).toFixed(1)} KB`;
}

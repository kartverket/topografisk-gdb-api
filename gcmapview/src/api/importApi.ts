import { gcapiRuntimeApiUrl, resolveApiBaseUrl } from './runtimeConfig';

export const gcapiApiBaseUrl = resolveApiBaseUrl(
  gcapiRuntimeApiUrl(),
  import.meta.env.GCAPI_API_URL,
  'GCAPI_API_URL',
  'http://localhost:8004'
);

export type ImportProfile = 'fkb_bane' | 'bygning';

const profileTokens: Record<ImportProfile, ReadonlySet<string>> = {
  fkb_bane: new Set(['jernbaneplattformkant', 'spormidt']),
  bygning: new Set([
    'annenbygning',
    'bygning',
    'bygningbru',
    'bygning_omrade',
    'bygning_senterlinje',
    'bygningsavgrensningtiltak',
    'bygningsdelelinje',
    'bygningslinje',
    'fiktivbygningsavgrensning',
    'grunnmur',
    'hjelpelinje3d',
    'låvebru',
    'mønelinje',
    'takkant',
    'takoverbyggkant',
    'takplatå',
    'takoverbygg',
    'taksprang',
    'taksprangbunn',
    'trappbygg',
    'veggfrittstående',
    'veranda'
  ])
};

export type ImportResult = {
  import_id: string;
  status: 'accepted' | 'running';
  location: string | null;
  profile: ImportProfile;
};

export type ImportJobStatus = 'accepted' | 'running' | 'successful' | 'failed';

export type ImportRun = {
  id: string;
  process_id: string | null;
  status: ImportJobStatus;
  phase: string | null;
  started_at: string;
  completed_at: string | null;
  last_event_at: string;
  total_features: number | null;
  processed_features: number;
  succeeded_features: number;
  failed_features: number;
  processed_batches: number;
  succeeded_batches: number;
  failed_batches: number;
  last_error: {
    reason?: string;
    errors?: string[];
    collection?: string;
    feature_id?: string;
  } | null;
  progress: number | null;
};

type JobStatusResponse = {
  jobID?: unknown;
  processID?: unknown;
  status?: unknown;
  phase?: unknown;
  created?: unknown;
  started?: unknown;
  finished?: unknown;
  updated?: unknown;
  progress?: unknown;
  totalFeatures?: unknown;
  processedFeatures?: unknown;
  succeededFeatures?: unknown;
  failedFeatures?: unknown;
  processedBatches?: unknown;
  succeededBatches?: unknown;
  failedBatches?: unknown;
  lastError?: unknown;
};

function inferProfileFromToken(value: unknown): ImportProfile | null {
  if (typeof value !== 'string') return null;
  const token = value.trim().toLowerCase();
  if (!token) return null;
  if (profileTokens.fkb_bane.has(token)) return 'fkb_bane';
  if (profileTokens.bygning.has(token)) return 'bygning';
  return null;
}

function inferProfileFromFeature(feature: unknown): ImportProfile | null {
  if (typeof feature !== 'object' || feature === null) return null;
  if ('featureType' in feature) {
    const inferred = inferProfileFromToken(feature.featureType);
    if (inferred) return inferred;
  }
  if ('properties' in feature && typeof feature.properties === 'object' && feature.properties !== null) {
    if ('objtype' in feature.properties) {
      return inferProfileFromToken(feature.properties.objtype);
    }
  }
  return null;
}

export async function inferImportProfile(file: File): Promise<ImportProfile | null> {
  try {
    const document: unknown = JSON.parse(await file.text());
    if (typeof document !== 'object' || document === null || !('features' in document)) {
      return null;
    }
    const { features } = document;
    if (!Array.isArray(features)) return null;

    let inferredProfile: ImportProfile | null = null;
    for (const feature of features) {
      const candidate = inferProfileFromFeature(feature);
      if (!candidate) continue;
      if (inferredProfile === null) {
        inferredProfile = candidate;
        continue;
      }
      if (candidate !== inferredProfile) return null;
    }
    return inferredProfile;
  } catch {
    return null;
  }
}

function errorMessage(body: unknown, status: number) {
  if (typeof body === 'object' && body !== null && 'detail' in body) {
    const detail = body.detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null) {
      if ('message' in detail && typeof detail.message === 'string') {
        if ('errors' in detail && Array.isArray(detail.errors)) {
          return `${detail.message}: ${detail.errors.join('; ')}`;
        }
        if ('reason' in detail && typeof detail.reason === 'string') {
          return `${detail.message}: ${detail.reason}`;
        }
        return detail.message;
      }
    }
  }
  return `Import failed with HTTP ${status}`;
}

export async function startImport(file: File, profile: ImportProfile): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  const processId = profile === 'fkb_bane' ? 'import-fkb-bane' : 'import-bygning';
  const response = await fetch(`${gcapiApiBaseUrl}/datasets/${profile}/ogc_api/processes/${processId}/execution`, {
    method: 'POST',
    body: form
  });

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  const payload = body as JobStatusResponse;
  return {
    import_id: typeof payload.jobID === 'string' ? payload.jobID : '',
    status: payload.status === 'running' ? 'running' : 'accepted',
    location: response.headers.get('Location'),
    profile
  };
}

function integerOrZero(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function integerOrNull(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function stringOrNull(value: unknown) {
  return typeof value === 'string' && value ? value : null;
}

function mapJobStatus(body: JobStatusResponse): ImportRun {
  const startedAt = stringOrNull(body.started) ?? stringOrNull(body.created) ?? new Date(0).toISOString();
  const updatedAt = stringOrNull(body.updated) ?? startedAt;
  const completedAt = stringOrNull(body.finished);
  const lastError =
    typeof body.lastError === 'object' && body.lastError !== null
      ? (body.lastError as ImportRun['last_error'])
      : null;

  return {
    id: typeof body.jobID === 'string' ? body.jobID : '',
    process_id: stringOrNull(body.processID),
    status: body.status === 'accepted' || body.status === 'running' || body.status === 'successful' || body.status === 'failed'
      ? body.status
      : 'running',
    phase: stringOrNull(body.phase),
    started_at: startedAt,
    completed_at: completedAt,
    last_event_at: updatedAt,
    total_features: integerOrNull(body.totalFeatures),
    processed_features: integerOrZero(body.processedFeatures),
    succeeded_features: integerOrZero(body.succeededFeatures),
    failed_features: integerOrZero(body.failedFeatures),
    processed_batches: integerOrZero(body.processedBatches),
    succeeded_batches: integerOrZero(body.succeededBatches),
    failed_batches: integerOrZero(body.failedBatches),
    last_error: lastError,
    progress: integerOrNull(body.progress)
  };
}

export async function getImportRun(importId: string, resultLocation: string | null, profile: ImportProfile): Promise<ImportRun> {
  const fallbackUrl = `${gcapiApiBaseUrl}/datasets/${profile}/ogc_api/jobs/${encodeURIComponent(importId)}`;
  const response = await fetch(resultLocation ?? fallbackUrl);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  return mapJobStatus(body as JobStatusResponse);
}

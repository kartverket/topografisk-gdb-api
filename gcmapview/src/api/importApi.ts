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

function gcapiDatasetJobUrl(profile: ImportProfile, suffix: string) {
  const baseUrl = new URL(`${gcapiApiBaseUrl.replace(/\/$/, '')}/`);
  const normalizedSuffix = suffix.replace(/^\//, '');
  return new URL(`/datasets/${profile}/ogc_api/jobs/${normalizedSuffix}`, baseUrl).toString();
}

function normalizeImportJobLocation(
  location: string | null,
  profile: ImportProfile,
  importId: string
) {
  const fallbackUrl = gcapiDatasetJobUrl(profile, encodeURIComponent(importId));
  if (!location) {
    return fallbackUrl;
  }

  try {
    const resolved = new URL(location, `${gcapiApiBaseUrl.replace(/\/$/, '')}/`);
    const prefix = `/datasets/${profile}/ogc_api/jobs/`;
    if (!resolved.pathname.startsWith(prefix)) {
      return fallbackUrl;
    }
    return new URL(`${resolved.pathname}${resolved.search}`, `${gcapiApiBaseUrl.replace(/\/$/, '')}/`).toString();
  } catch {
    return fallbackUrl;
  }
}

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

const IMPORT_PROCESS_ID = 'import';

export async function startImport(file: File, profile: ImportProfile): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(
    `${gcapiApiBaseUrl}/datasets/${profile}/ogc_api/processes/${IMPORT_PROCESS_ID}/execution`,
    {
      method: 'POST',
      body: form
    }
  );

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  const payload = body as JobStatusResponse;
  const importId = typeof payload.jobID === 'string' ? payload.jobID : '';
  return {
    import_id: importId,
    status: executionStatus(payload.status),
    location: normalizeImportJobLocation(response.headers.get('Location'), profile, importId),
    profile
  };
}

function executionStatus(value: unknown): ImportResult['status'] {
  if (value === 'accepted' || value === 'running') {
    return value;
  }

  throw new Error(`Unexpected import execution status: ${String(value)}`);
}

function stringOrNull(value: unknown) {
  return typeof value === 'string' && value ? value : null;
}

function stringOrThrow(value: unknown, fieldName: string) {
  if (typeof value === 'string' && value) {
    return value;
  }

  throw new Error(`Unexpected import job response: missing ${fieldName}`);
}

function integerOrThrow(value: unknown, fieldName: string) {
  if (typeof value === 'number' && Number.isInteger(value) && value >= 0) {
    return value;
  }

  throw new Error(`Unexpected import job response: invalid ${fieldName}`);
}

function integerOrNull(value: unknown, fieldName: string) {
  if (value === null || value === undefined) {
    return null;
  }

  return integerOrThrow(value, fieldName);
}

function jobStatus(value: unknown): ImportJobStatus {
  if (value === 'accepted' || value === 'running' || value === 'successful' || value === 'failed') {
    return value;
  }

  throw new Error(`Unexpected import job status: ${String(value)}`);
}

function objectOrNull<T extends object>(value: unknown, fieldName: string): T | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === 'object') {
    return value as T;
  }

  throw new Error(`Unexpected import job response: invalid ${fieldName}`);
}

function mapJobStatus(body: JobStatusResponse): ImportRun {
  const status = jobStatus(body.status);
  const id = stringOrThrow(body.jobID, 'jobID');
  const processId = stringOrThrow(body.processID, 'processID');
  const createdAt = stringOrThrow(body.created, 'created');
  const updatedAt = stringOrThrow(body.updated, 'updated');
  const startedAt = stringOrNull(body.started) ?? createdAt;
  const completedAt = stringOrNull(body.finished);
  const lastError = objectOrNull<NonNullable<ImportRun['last_error']>>(body.lastError, 'lastError');

  return {
    id,
    process_id: processId,
    status,
    phase: stringOrNull(body.phase),
    started_at: startedAt,
    completed_at: completedAt,
    last_event_at: updatedAt,
    total_features: integerOrNull(body.totalFeatures, 'totalFeatures'),
    processed_features: integerOrThrow(body.processedFeatures, 'processedFeatures'),
    succeeded_features: integerOrThrow(body.succeededFeatures, 'succeededFeatures'),
    failed_features: integerOrThrow(body.failedFeatures, 'failedFeatures'),
    processed_batches: integerOrThrow(body.processedBatches, 'processedBatches'),
    succeeded_batches: integerOrThrow(body.succeededBatches, 'succeededBatches'),
    failed_batches: integerOrThrow(body.failedBatches, 'failedBatches'),
    last_error: lastError,
    progress: integerOrNull(body.progress, 'progress')
  };
}

export async function getImportRun(
  importId: string,
  resultLocation: string | null,
  profile: ImportProfile
): Promise<ImportRun> {
  const response = await fetch(normalizeImportJobLocation(resultLocation, profile, importId));
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  return mapJobStatus(body as JobStatusResponse);
}

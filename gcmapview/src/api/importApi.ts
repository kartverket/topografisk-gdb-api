import { gcjobsRuntimeApiUrl, resolveApiBaseUrl } from './runtimeConfig';

export const importApiBaseUrl = resolveApiBaseUrl(
  gcjobsRuntimeApiUrl(),
  import.meta.env.GCJOBS_API_URL,
  'GCJOBS_API_URL',
  'http://localhost:8003'
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
  status: 'accepted';
};

export type ImportRun = {
  id: string;
  status: 'running' | 'completed' | 'failed';
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
  const response = await fetch(`${importApiBaseUrl}/imports?profile=${encodeURIComponent(profile)}`, {
    method: 'POST',
    body: form
  });

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  return body as ImportResult;
}

export async function getImportRun(importId: string): Promise<ImportRun> {
  const response = await fetch(`${importApiBaseUrl}/imports/${encodeURIComponent(importId)}`);
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  return body as ImportRun;
}

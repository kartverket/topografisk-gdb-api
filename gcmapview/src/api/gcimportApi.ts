const defaultApiBaseUrl = '/gcimport-api';

export const gcimportApiBaseUrl = (import.meta.env.VITE_GCIMPORT_API_URL ?? defaultApiBaseUrl).replace(/\/$/, '');

export type ImportProfile = 'bane' | 'bygning';

const profileTokens: Record<ImportProfile, ReadonlySet<string>> = {
  bane: new Set(['jernbaneplattformkant', 'spormidt']),
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
  total: number;
  features: Array<{
    collection: string;
    id: string;
  }>;
};

function inferProfileFromToken(value: unknown): ImportProfile | null {
  if (typeof value !== 'string') return null;
  const token = value.trim().toLowerCase();
  if (!token) return null;
  if (profileTokens.bane.has(token)) return 'bane';
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

export async function uploadJsonFg(file: File, profile: ImportProfile): Promise<ImportResult> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch(`${gcimportApiBaseUrl}/imports?profile=${encodeURIComponent(profile)}`, {
    method: 'POST',
    body: form
  });

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(errorMessage(body, response.status));
  }
  return body as ImportResult;
}

type RuntimeConfig = {
  geocomponentsApiUrl?: unknown;
  gcimportApiUrl?: unknown;
};

declare global {
  interface Window {
    __GCMAPVIEW_CONFIG__?: RuntimeConfig;
  }
}

function normalizeApiBaseUrl(value: unknown) {
  if (typeof value !== 'string') return null;
  const trimmedValue = value.trim();
  if (!trimmedValue) return null;
  return trimmedValue.replace(/\/$/, '');
}

function getRuntimeConfig() {
  if (typeof window === 'undefined') return undefined;
  return window.__GCMAPVIEW_CONFIG__;
}

export function resolveApiBaseUrl(runtimeValue: unknown, buildValue: string | undefined, variableName: string) {
  const resolvedValue = normalizeApiBaseUrl(runtimeValue) ?? normalizeApiBaseUrl(buildValue);
  if (resolvedValue) return resolvedValue;
  throw new Error(`${variableName} must be configured`);
}

export function geocomponentsRuntimeApiUrl() {
  return getRuntimeConfig()?.geocomponentsApiUrl;
}

export function gcimportRuntimeApiUrl() {
  return getRuntimeConfig()?.gcimportApiUrl;
}

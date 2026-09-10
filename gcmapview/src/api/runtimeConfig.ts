type RuntimeConfig = {
  gcapiApiUrl?: unknown;
  featureEventsUrl?: unknown;
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

function devFallbackApiBaseUrl(value: string | undefined) {
  if (!import.meta.env.DEV) return null;
  return normalizeApiBaseUrl(value);
}

export function resolveApiBaseUrl(
  runtimeValue: unknown,
  buildValue: string | undefined,
  variableName: string,
  devFallbackValue?: string
) {
  const resolvedValue =
    normalizeApiBaseUrl(runtimeValue) ?? normalizeApiBaseUrl(buildValue) ?? devFallbackApiBaseUrl(devFallbackValue);
  if (resolvedValue) return resolvedValue;
  throw new Error(`${variableName} must be configured`);
}

export function gcapiRuntimeApiUrl() {
  return getRuntimeConfig()?.gcapiApiUrl;
}

export function featureEventsRuntimeUrl() {
  return getRuntimeConfig()?.featureEventsUrl;
}

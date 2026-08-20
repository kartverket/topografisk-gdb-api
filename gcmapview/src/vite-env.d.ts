/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly GEOCOMPONENTS_API_URL?: string;
  readonly GCJOBS_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

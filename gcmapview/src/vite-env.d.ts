/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly GEOCOMPONENTS_API_URL?: string;
  readonly GCIMPORT_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

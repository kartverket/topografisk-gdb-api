/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly GCAPI_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

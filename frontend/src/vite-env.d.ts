/// <reference types="vite/client" />

declare module "cytoscape-fcose";

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

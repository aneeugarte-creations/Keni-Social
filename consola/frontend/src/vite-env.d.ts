/// <reference types="vite/client" />

// Id de build horneado por Vite (`define` en vite.config.ts). Identifica la versión del
// bundle en ejecución; el detector de actualizaciones lo compara con `/version.json`.
declare const __BUILD_ID__: string;

// Asset importado con `?inline`: Vite lo incrusta como data-URI (string) en el propio chunk.
declare module "*.png?inline" {
  const dataUri: string;
  export default dataUri;
}

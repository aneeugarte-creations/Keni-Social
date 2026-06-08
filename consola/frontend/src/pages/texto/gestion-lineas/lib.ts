import type { ClaseLinea } from "./tipos";

export const CLASE_LABEL: Record<ClaseLinea, string> = {
  vertical: "Línea de contenido",
  origen: "Origen",
};

export const CLASE_AYUDA: Record<ClaseLinea, string> = {
  vertical:
    "Las líneas (verticales) agrupan el contenido por tema/sección. Las keywords ayudan a " +
    "auto-clasificar cada pieza en su línea.",
  origen:
    "El origen distingue contenido interno de externo. Las keywords ayudan a " +
    "clasificarlo automáticamente.",
};

/** Centinela del selector de marca: etiqueta global (sin marca). */
export const GLOBAL = "__global__";

export const CLAVE_ETIQUETAS = ["etiquetas"] as const;

/** Etiqueta humana del eje de una etiqueta editorial transversal (campaña / tipo). */
export const CLASE_ETIQUETA_LABEL: Record<string, string> = {
  campania: "Campaña",
  tipo: "Tipo",
};

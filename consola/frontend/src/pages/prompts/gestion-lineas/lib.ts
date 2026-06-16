import type { ClaseLinea } from "./tipos";

export const CLASE_LABEL: Record<ClaseLinea, string> = {
  vertical: "Línea de contenido",
  origen: "Origen",
};

export const CLASE_AYUDA: Record<ClaseLinea, string> = {
  vertical:
    "Agrupan contenido por tema/sección. Auto-clasifican con keywords.",
  origen:
    "Distinguen contenido interno de externo.",
};

/** Centinela del selector de marca: etiqueta global (sin marca). */
export const GLOBAL = "__global__";

export const CLAVE_ETIQUETAS = ["etiquetas"] as const;

/** Etiqueta humana del eje de una etiqueta editorial transversal (campaña / tipo). */
export const CLASE_ETIQUETA_LABEL: Record<string, string> = {
  campania: "Campaña",
  tipo: "Tipo",
};

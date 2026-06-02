/**
 * ETAPA de la cadena IA de una pieza, para el Feed de ideación (Flujo D, Fase 4).
 *
 * La visión de la "red social interna" pide ver el estado de la IA EN VIVO por pieza:
 * "generando copy → generando arte → lista para revisar → aprobada". Hoy NO existe un
 * endpoint dedicado de estado-por-etapa: lo PROVEERÁ el Flujo C (Orquestación, Fase 2),
 * que encadena los daemons con "estado visible por pieza" (ver plan §Fase 2).
 *
 * Mientras tanto, DERIVAMOS la etapa de lo que ya trae cada `Publicacion`:
 *  - `estado` (pendiente/en_curso/en_revision/aprobado/programado/publicado), y
 *  - la checklist `falta_copy` / `falta_imagen` / `falta_revision`.
 *
 * CABLEADO CON C (follow-up #3, ya en producción):
 *  El backend (Flujo C) YA expone la etapa real por pieza en `Publicacion.etapa_ia`,
 *  derivada por `pipeline_estado.etapa_de_pieza` (misma lógica que la derivación de abajo,
 *  pero como FUENTE ÚNICA en servidor). `etapaDePublicacion` la PREFIERE cuando viene; la
 *  derivación en cliente queda solo como DEGRADACIÓN para piezas legadas/parciales que aún
 *  no la traigan. La forma de salida (`EtapaIa`) es el contrato del feed.
 */
import type { Publicacion } from "@/types";

/** Las etapas observables de la tubería IA, en orden. */
export type EtapaIa =
  | "generando_copy"
  | "generando_arte"
  | "lista_para_revisar"
  | "aprobada"
  | "programada"
  | "publicada";

export interface MetaEtapa {
  /** Etiqueta humana corta (badge). */
  etiqueta: string;
  /** `true` mientras la IA aún trabaja la pieza (badge con spinner/pulso). */
  enCurso: boolean;
}

export const META_ETAPA: Record<EtapaIa, MetaEtapa> = {
  generando_copy: { etiqueta: "Generando copy", enCurso: true },
  generando_arte: { etiqueta: "Generando arte", enCurso: true },
  lista_para_revisar: { etiqueta: "Lista para revisar", enCurso: false },
  aprobada: { etiqueta: "Aprobada", enCurso: false },
  programada: { etiqueta: "Programada", enCurso: false },
  publicada: { etiqueta: "Publicada", enCurso: false },
};

/**
 * Deriva la etapa IA de una pieza a partir de su estado + checklist.
 *
 * Reglas (de "más avanzado" a "menos"):
 *  - `publicado`               → publicada
 *  - `programado`              → programada
 *  - `aprobado`                → aprobada
 *  - `en_revision`             → lista_para_revisar (gate humano: espera tu firma)
 *  - aún falta imagen y ya hay copy → generando_arte
 *  - en cualquier otro caso (falta copy / pendiente / en_curso) → generando_copy
 *
 * El backend (Flujo C) trae la etapa real en `p.etapa_ia`; `etapaDePublicacion` la PREFIERE
 * cuando llega y es una etapa conocida. Esta derivación queda como degradación (piezas
 * legadas/parciales que no la traigan).
 */
export function etapaDePublicacion(p: Publicacion): EtapaIa {
  // Etapa REAL de la tubería (Flujo C, `pipeline_estado.etapa_de_pieza`): si llega y es una
  // etapa conocida, manda sobre la derivación local. El backend la sirve hoy en
  // `Publicacion.etapa_ia`; el guard cubre respuestas legadas/parciales que la omitan.
  const explicita = (p as { etapa_ia?: string }).etapa_ia;
  if (explicita && explicita in META_ETAPA) return explicita as EtapaIa;

  if (p.estado === "publicado") return "publicada";
  if (p.estado === "programado") return "programada";
  if (p.estado === "aprobado") return "aprobada";
  if (p.estado === "en_revision") return "lista_para_revisar";
  if (!p.falta_copy && p.falta_imagen) return "generando_arte";
  return "generando_copy";
}

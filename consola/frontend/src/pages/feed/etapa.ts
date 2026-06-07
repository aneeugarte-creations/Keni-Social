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
  // "Generando arte" = en realidad la pieza LLEVA imagen pero le falta la FOTO real (la IA solo
  // hace la plantilla; la foto la sube una persona en "Editar"). El label lo dice claro.
  // Ola F: para piezas video este estado significa "Falta video"; la etiqueta dinámica
  // la calcula `etiquetaEtapa` a partir del formato; aquí "Falta imagen" es el fallback foto.
  generando_arte: { etiqueta: "Falta imagen", enCurso: true },
  lista_para_revisar: { etiqueta: "Lista para revisar", enCurso: false },
  aprobada: { etiqueta: "Aprobada", enCurso: false },
  programada: { etiqueta: "Programada", enCurso: false },
  publicada: { etiqueta: "Publicada", enCurso: false },
};

/**
 * Etiqueta dinámica de la etapa, teniendo en cuenta el formato de la pieza (Ola F).
 * Para piezas video, "generando_arte" significa "Falta video" en vez de "Falta imagen".
 */
export function etiquetaEtapa(etapa: EtapaIa, formato?: string): string {
  if (etapa === "generando_arte" && (formato ?? "").trim().toLowerCase() === "video") {
    return "Falta video";
  }
  return META_ETAPA[etapa].etiqueta;
}

/**
 * Deriva la etapa IA de una pieza a partir de su estado + checklist.
 *
 * Reglas (de "más avanzado" a "menos"):
 *  - `publicado`               → publicada
 *  - `programado`              → programada
 *  - `aprobado`                → aprobada
 *  - `en_revision`             → lista_para_revisar (gate humano: espera tu firma)
 *  - falta copy                → generando_copy
 *  - lleva imagen (copy-in / exenta) pero falta la FOTO real → generando_arte ("Falta imagen")
 *  - de solo texto, o con copy + foto real → lista_para_revisar
 *
 * IMAGEN vs PLANTILLA: la placa (`imagen`) es solo la PLANTILLA (parte del copy-in), no cuenta
 * como imagen real. "Lleva imagen" = hay copy-in o exención; necesita FOTO (`foto`/`imagen_fuente`).
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
  // ESPEJO del backend. Solo "generando_copy" si DE VERDAD falta el copy.
  if (!p.contenido?.trim()) return "generando_copy";
  // Ola F: las piezas VIDEO necesitan el asset de video (no una foto).
  // Las piezas FOTO necesitan una foto real (foto cruda, imagen de fuente o imagen subida bespoke).
  const esVideo = (p.formato ?? "").trim().toLowerCase() === "video";
  if (esVideo) {
    // falta_video es la checklist de video: si falta, la pieza no está lista.
    const hayVideo = !p.falta_video || !!(p as { video?: string }).video;
    if (!hayVideo) return "generando_arte";
  } else {
    // Foto: la foto cruda (`foto`), imagen de fuente (`imagen_fuente`) o imagen bespoke (`imagen` sin marca).
    const hayImagenReal = !!p.foto || !!p.imagen_fuente || (!p.marca && !!p.imagen);
    if (!hayImagenReal) return "generando_arte";
  }
  return "lista_para_revisar";
}

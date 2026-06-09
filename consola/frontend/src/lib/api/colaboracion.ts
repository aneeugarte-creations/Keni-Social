// Fragmento del cliente API: dominio «colaboracion». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CadenaAprobacion,
  RespuestaCadenasLote,
  RespuestaComentario,
  RespuestaComentarios,
  RespuestaCopyGuardado,
  RespuestaCopyVersiones,
  RespuestaDecisionAprobacion,
  RespuestaMensaje,
} from "@/types";

export const apiColaboracion = {
  // --- Ola COLABORACIÓN: comentarios + versiones de copy + aprobación multinivel ---
  comentarios: (contenidoId: string, plataformaId?: string, signal?: AbortSignal) => {
    const qs = plataformaId !== undefined ? `?plataforma_id=${encodeURIComponent(plataformaId)}` : "";
    return peticion<RespuestaComentarios>(
      `/contenido/${encodeURIComponent(contenidoId)}/comentarios${qs}`,
      { signal },
    );
  },
  crearComentario: (
    contenidoId: string,
    texto: string,
    plataformaId?: string,
    menciones?: string[],
  ) =>
    peticion<RespuestaComentario>(`/contenido/${encodeURIComponent(contenidoId)}/comentarios`, {
      metodo: "POST",
      json: { texto, plataforma_id: plataformaId ?? "", menciones: menciones ?? [] },
    }),
  actualizarComentario: (id: string, cuerpo: { texto?: string; resuelto?: boolean }) =>
    peticion<RespuestaComentario>(`/comentarios/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarComentario: (id: string) =>
    peticion<RespuestaMensaje>(`/comentarios/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  copyVersiones: (plataformaId: string, signal?: AbortSignal) =>
    peticion<RespuestaCopyVersiones>(
      `/plataformas/${encodeURIComponent(plataformaId)}/copy/versiones`,
      { signal },
    ),
  guardarCopy: (plataformaId: string, copy: string, nota?: string) =>
    peticion<RespuestaCopyGuardado>(`/plataformas/${encodeURIComponent(plataformaId)}/copy`, {
      metodo: "POST",
      json: { copy, nota: nota ?? "" },
    }),
  revertirCopy: (plataformaId: string, versionId: string) =>
    peticion<RespuestaCopyGuardado>(
      `/plataformas/${encodeURIComponent(plataformaId)}/copy/revertir`,
      { metodo: "POST", json: { version_id: versionId } },
    ),

  cadenaAprobacion: (plataformaId: string, signal?: AbortSignal) =>
    peticion<CadenaAprobacion>(`/plataformas/${encodeURIComponent(plataformaId)}/aprobacion`, {
      signal,
    }),
  /**
   * BATCH del feed: las cadenas de VARIAS piezas en una sola llamada (elimina el N+1 de un
   * GET /aprobacion por pieza visible). Siempre devuelve una entrada por id pedida.
   */
  cadenasAprobacion: (plataformaIds: string[], signal?: AbortSignal) =>
    peticion<RespuestaCadenasLote>(
      `/publicaciones/cadenas?ids=${encodeURIComponent(plataformaIds.join(","))}`,
      { signal },
    ),
  crearCadenaAprobacion: (plataformaId: string, etiquetas?: string[]) =>
    peticion<CadenaAprobacion>(`/plataformas/${encodeURIComponent(plataformaId)}/aprobacion`, {
      metodo: "POST",
      json: etiquetas !== undefined ? { etiquetas } : {},
    }),
  decidirNivelAprobacion: (
    nivelId: string,
    decision: "aprobado" | "rechazado",
    comentario?: string,
  ) =>
    peticion<RespuestaDecisionAprobacion>(
      `/aprobacion-nivel/${encodeURIComponent(nivelId)}/decidir`,
      { metodo: "POST", json: { decision, comentario: comentario ?? "" } },
    ),

};

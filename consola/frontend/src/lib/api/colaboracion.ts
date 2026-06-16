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
  comentarios: (publicacionId: string, piezaId?: string, signal?: AbortSignal) => {
    const qs = piezaId !== undefined ? `?pieza_id=${encodeURIComponent(piezaId)}` : "";
    return peticion<RespuestaComentarios>(
      `/publicaciones/${encodeURIComponent(publicacionId)}/comentarios${qs}`,
      { signal },
    );
  },
  crearComentario: (
    publicacionId: string,
    texto: string,
    piezaId?: string,
    menciones?: string[],
  ) =>
    peticion<RespuestaComentario>(`/publicaciones/${encodeURIComponent(publicacionId)}/comentarios`, {
      metodo: "POST",
      json: { texto, pieza_id: piezaId ?? "", menciones: menciones ?? [] },
    }),
  actualizarComentario: (id: string, cuerpo: { texto?: string; resuelto?: boolean }) =>
    peticion<RespuestaComentario>(`/comentarios/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarComentario: (id: string) =>
    peticion<RespuestaMensaje>(`/comentarios/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  copyVersiones: (piezaId: string, signal?: AbortSignal) =>
    peticion<RespuestaCopyVersiones>(
      `/plataformas/${encodeURIComponent(piezaId)}/copy/versiones`,
      { signal },
    ),
  guardarCopy: (piezaId: string, copy: string, nota?: string) =>
    peticion<RespuestaCopyGuardado>(`/plataformas/${encodeURIComponent(piezaId)}/copy`, {
      metodo: "POST",
      json: { copy, nota: nota ?? "" },
    }),
  revertirCopy: (piezaId: string, versionId: string) =>
    peticion<RespuestaCopyGuardado>(
      `/plataformas/${encodeURIComponent(piezaId)}/copy/revertir`,
      { metodo: "POST", json: { version_id: versionId } },
    ),

  cadenaAprobacion: (piezaId: string, signal?: AbortSignal) =>
    peticion<CadenaAprobacion>(`/plataformas/${encodeURIComponent(piezaId)}/aprobacion`, {
      signal,
    }),
  /**
   * BATCH del feed: las cadenas de VARIAS piezas en una sola llamada (elimina el N+1 de un
   * GET /aprobacion por pieza visible). Siempre devuelve una entrada por id pedida.
   */
  cadenasAprobacion: (plataformaIds: string[], signal?: AbortSignal) =>
    peticion<RespuestaCadenasLote>(
      `/piezas/cadenas?ids=${encodeURIComponent(plataformaIds.join(","))}`,
      { signal },
    ),
  crearCadenaAprobacion: (piezaId: string, etiquetas?: string[]) =>
    peticion<CadenaAprobacion>(`/plataformas/${encodeURIComponent(piezaId)}/aprobacion`, {
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

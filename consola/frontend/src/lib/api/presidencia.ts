// Fragmento del cliente API: dominio «presidencia» (cajón de Fuentes → Internas).
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoCrearNotaPresidencia,
  RespuestaCrearNotaPresidencia,
  RespuestaNotasPresidencia,
} from "@/types";

export const apiPresidencia = {
  // --- Cajón Presidencia: nota de WhatsApp (texto + media) -> pieza carrusel automática ---
  notasPresidencia: (params: { marca?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaNotasPresidencia>(`/presidencia/notas${query(params)}`, { signal }),
  crearNotaPresidencia: (cuerpo: CuerpoCrearNotaPresidencia) =>
    peticion<RespuestaCrearNotaPresidencia>("/presidencia/notas", {
      metodo: "POST",
      json: cuerpo,
    }),
};

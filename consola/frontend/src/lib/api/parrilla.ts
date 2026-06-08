// Fragmento del cliente API: dominio «parrilla». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  EstadoPropuestaParrilla,
  PropuestaParrilla,
  RespuestaImportarParrilla,
  RespuestaMensaje,
  RespuestaPropuestasParrilla,
} from "@/types";

export const apiParrilla = {
  // --- Importar documento a la parrilla (turnos + eventos) ---
  // Sube un documento (PDF/imagen/docx/xlsx/txt); un `claude -p` lo analiza en 2º plano
  // y produce una PROPUESTA (diff de operaciones que puede abarcar muchas semanas) que se
  // SONDEA por su propio estado (`/parrilla/propuestas/{id}`) hasta `estado != "generando"`.
  // Ya NO se elige semana destino: el documento puede cubrir hasta un año y cada operación
  // lleva su propia `fecha`. Aceptar mergea sobre el calendario real; descartar la archiva.
  importarParrilla: (archivo: File) => {
    const form = new FormData();
    form.set("archivo", archivo);
    return peticion<RespuestaImportarParrilla>("/parrilla/importar", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },
  propuestasParrilla: (
    params: { estado?: EstadoPropuestaParrilla } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaPropuestasParrilla>(
      `/parrilla/propuestas${query({ estado: params.estado })}`,
      { signal },
    ),
  propuestaParrilla: (id: string, signal?: AbortSignal) =>
    peticion<PropuestaParrilla>(`/parrilla/propuestas/${encodeURIComponent(id)}`, {
      signal,
    }),
  aplicarPropuestaParrilla: (id: string) =>
    peticion<RespuestaMensaje>(`/parrilla/propuestas/${encodeURIComponent(id)}/aplicar`, {
      metodo: "POST",
    }),
  descartarPropuestaParrilla: (id: string) =>
    peticion<RespuestaMensaje>(`/parrilla/propuestas/${encodeURIComponent(id)}/descartar`, {
      metodo: "POST",
    }),

};

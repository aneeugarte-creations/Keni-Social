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
  // --- Importar documento a la parrilla (turnos) ---
  // Sube un documento (PDF/imagen/docx/xlsx/txt); un `claude -p` lo analiza en 2º plano
  // y produce una PROPUESTA (diff de operaciones que puede abarcar muchas semanas) que se
  // SONDEA por su propio estado (`/parrilla/propuestas/{id}`) hasta `estado != "generando"`.
  // El documento puede cubrir hasta un año y cada operación lleva su propia `fecha`. Aceptar
  // mergea sobre el calendario real; descartar la archiva.
  // `modo="turnos"` (lo usa «Asignar turnos») mete a cada persona en la franja del equipo que
  // le corresponde por horario, en vez de crear una franja por persona/columna; la `marca` dice
  // de qué equipo son las franjas. Sin opts, comportamiento legado (modo eventos, sin marca).
  importarParrilla: (
    archivo: File,
    opts: { marca?: string; modo?: "eventos" | "turnos" } = {},
  ) => {
    const form = new FormData();
    form.set("archivo", archivo);
    if (opts.marca) form.set("marca", opts.marca);
    if (opts.modo) form.set("modo", opts.modo);
    return peticion<RespuestaImportarParrilla>("/parrilla/importar", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },
  // Import a la lista de TAREAS: además del fichero, acepta un ENLACE o TEXTO pegado, y la
  // MARCA del workspace (se estampa en los eventos creados para que la lista los muestre).
  // Mismo endpoint y misma propuesta que `importarParrilla`; se sondea y aplica igual.
  importarEventos: (entrada: {
    archivo?: File;
    url?: string;
    texto?: string;
    marca?: string;
    // "eventos" (defecto) extrae eventos a cubrir; "tareas" extrae encargos sueltos
    // (clase='tarea', no van al calendario). Cambia el prompt y el tipo de operación.
    modo?: "eventos" | "tareas";
  }) => {
    const form = new FormData();
    if (entrada.archivo) form.set("archivo", entrada.archivo);
    if (entrada.url) form.set("url", entrada.url);
    if (entrada.texto) form.set("texto", entrada.texto);
    if (entrada.marca) form.set("marca", entrada.marca);
    if (entrada.modo) form.set("modo", entrada.modo);
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
    // Apply PARCIAL: aplica lo nuevo y reporta lo omitido (`ya_existe` ya estaban,
    // `omitidas_conflicto` un turno a modificar que ya no existe). No es error.
    peticion<{
      aplicada?: boolean;
      ya_existe?: number;
      omitidas_conflicto?: number;
      turnos_creados?: number;
      eventos_creados?: number;
      mensaje?: string;
    }>(
      `/parrilla/propuestas/${encodeURIComponent(id)}/aplicar`,
      { metodo: "POST" },
    ),
  descartarPropuestaParrilla: (id: string) =>
    peticion<RespuestaMensaje>(`/parrilla/propuestas/${encodeURIComponent(id)}/descartar`, {
      metodo: "POST",
    }),

};

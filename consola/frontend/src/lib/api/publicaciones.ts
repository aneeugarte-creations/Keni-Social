// Fragmento del cliente API: dominio «publicaciones». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoActualizarPublicacion,
  CuerpoDuplicarPublicacion,
  FiltrosPublicaciones,
  FiltrosReciclaje,
  OpcionesPublicaciones,
  RespuestaAlertas,
  RespuestaColaAprobacion,
  RespuestaImportCalendario,
  RespuestaImportCalendarioPendiente,
  RespuestaImportPreview,
  RespuestaMensaje,
  RespuestaPublicacion,
  RespuestaPublicaciones,
  RespuestaReciclarPublicacion,
  RespuestaSugerenciasReciclaje,
} from "@/types";

export const apiPublicaciones = {
  // --- Publicaciones ---
  publicacionesOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesPublicaciones>("/publicaciones/opciones", { signal }),
  publicaciones: (filtros: FiltrosPublicaciones = {}, signal?: AbortSignal) =>
    peticion<RespuestaPublicaciones>(`/publicaciones${query(filtros)}`, {
      signal,
      validador: "RespuestaPublicaciones",
    }),
  /** Una publicación por id (= id de la fila `contenido_plataforma`). La usa el feed del
   *  tablero para abrir el editor rico a partir de una tarjeta por red. */
  publicacion: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}`, { signal }),
  actualizarPublicacion: (id: string, cuerpo: CuerpoActualizarPublicacion) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarPublicacion: (id: string) =>
    peticion<RespuestaMensaje>(`/publicaciones/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  duplicarPublicacion: (id: string, cuerpo: CuerpoDuplicarPublicacion = {}) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}/duplicar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  encolarPublicacion: (id: string) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}/encolar`, {
      metodo: "POST",
    }),
  reciclarPublicacion: (id: string) =>
    peticion<RespuestaReciclarPublicacion>(`/publicaciones/${encodeURIComponent(id)}/reciclar`, {
      metodo: "POST",
    }),
  /**
   * Integra una FOTO subida dentro de la plantilla de marca de la publicación (logo + copy-in +
   * pleca). Composición DETERMINISTA y SÍNCRONA en el backend (~<1s). Devuelve la imagen
   * resultante `{imagen, imagen_url}` para fijarla y guardarla con el resto de la edición. Para
   * marcas sin plantilla, devuelve la foto tal cual.
   */
  integrarFotoPublicacion: (id: string, imagen: string, copyIn?: string) =>
    peticion<{ imagen: string; imagen_url: string }>(
      `/publicaciones/${encodeURIComponent(id)}/integrar-foto`,
      { metodo: "POST", json: copyIn === undefined ? { imagen } : { imagen, copy_in: copyIn } },
    ),
  /** Aplica una plantilla del estudio a la pieza: renderiza con la foto+copy-in dados y persiste. */
  aplicarPlantillaPublicacion: (
    id: string,
    plantillaId: string,
    extra: { foto?: string; copy_in?: string; foto_encuadre?: string } = {},
  ) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}/aplicar-plantilla`, {
      metodo: "POST",
      json: { plantilla_id: plantillaId, ...extra },
    }),

  // --- Aprobación de PUBLICACIONES (#9): cola de revisión + decisión + programación ---
  // CONSOLIDACIÓN: la aprobación es ahora la MISMA cadena multinivel del tablero (una
  // publicación ES una fila `contenido_plataforma`). Estos endpoints se conservan y por
  // dentro FORWARDEAN a la cadena: `enviarARevision` crea una cadena SIMPLE (1 nivel) y deja
  // la pieza en revisión; `aprobar`/`rechazar` deciden el nivel actual de esa cadena.
  // Programar NO es aprobación (es programación) y NO publica de verdad: el posteo real
  // vía Metricool está gated por `KENI_PUBLICAR_REAL`.
  /** Cola de aprobación: publicaciones en revisión (FIFO). Lectura; cada item es una `Publicacion`. */
  colaAprobacion: (signal?: AbortSignal) =>
    peticion<RespuestaColaAprobacion>("/aprobacion/cola", { signal }),
  /** Envía una publicación a revisión: crea la cadena de aprobación simple (borrador → en revisión). */
  enviarARevision: (id: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/enviar-a-revision`, {
      metodo: "POST",
    }),
  /** Aprueba el nivel actual de la cadena de una publicación (revisor != autor, salvo admin). */
  aprobarPublicacion: (id: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/aprobar`, {
      metodo: "POST",
    }),
  /** Da un "dislike": rechaza el nivel actual. Dos dislikes (dos personas) vuelven a borrador. */
  rechazarPublicacion: (id: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
    }),
  /** Retira la decisión propia (quitar tu OK o tu dislike): tu nivel vuelve a pendiente. */
  deshacerAprobacion: (id: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/deshacer`, {
      metodo: "POST",
    }),
  /** FUERZA la aprobación (admin/coordinador): se salta la cadena y deja la pieza aprobada. */
  forzarAprobacion: (id: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/forzar`, {
      metodo: "POST",
    }),

  // --- Importar calendario (H1): sube un .xlsx/.csv al tablero (multipart). Con
  // `previsualizar` parsea sin escribir; sin él, crea el contenido y devuelve el resumen. ---
  importarCalendario: (
    archivo: File,
    opts: { marca?: string; previsualizar?: boolean } = {},
  ) => {
    const form = new FormData();
    form.set("archivo", archivo);
    if (opts.marca) form.set("marca", opts.marca);
    if (opts.previsualizar) form.set("previsualizar", "1");
    return peticion<
      RespuestaImportPreview | RespuestaImportCalendario | RespuestaImportCalendarioPendiente
    >("/contenido/importar", { metodo: "POST", form, timeoutMs: 120_000 });
  },

  // --- Alertas de rendimiento (bitácora editorial: reciclaje / bajo rendimiento) ---
  alertas: (params: { limite?: number } = {}, signal?: AbortSignal) =>
    peticion<RespuestaAlertas>(
      `/alertas${query({ limite: params.limite?.toString() })}`,
      { signal },
    ),

  // --- Reciclaje proactivo (sugerencias de archivo a retomar, #110) ---
  sugerenciasReciclaje: (filtros: FiltrosReciclaje = {}, signal?: AbortSignal) =>
    peticion<RespuestaSugerenciasReciclaje>(`/reciclaje/sugerencias${query(filtros)}`, { signal }),

};

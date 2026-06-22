// Fragmento del cliente API: dominio «piezas». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CuerpoActualizarPieza,
  FiltrosPiezas,
  OpcionesPiezas,
  RespuestaAlertas,
  RespuestaBorrarLotePiezas,
  RespuestaColaAprobacion,
  RespuestaGeneracion,
  RespuestaImportCalendario,
  RespuestaImportCalendarioPendiente,
  RespuestaImportPreview,
  RespuestaMensaje,
  RespuestaPieza,
  RespuestaPiezas,
} from "@/types";

export const apiPiezas = {
  // --- Piezas ---
  publicacionesOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesPiezas>("/piezas/opciones", { signal }),
  piezas: (filtros: FiltrosPiezas = {}, signal?: AbortSignal) =>
    peticion<RespuestaPiezas>(`/piezas${query(filtros)}`, {
      signal,
      validador: "RespuestaPiezas",
    }),
  /** Una publicación por id (= id de la fila `pieza`). La usa el feed del
   *  tablero para abrir el editor rico a partir de una tarjeta por red. */
  pieza: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPieza>(`/piezas/${encodeURIComponent(id)}`, { signal }),
  actualizarPieza: (id: string, cuerpo: CuerpoActualizarPieza) =>
    peticion<RespuestaPieza>(`/piezas/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarPieza: (id: string) =>
    peticion<RespuestaMensaje>(`/piezas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  /** Borrado BATCH (selección múltiple de la lista): un solo round-trip, fallos parciales en `fallos`. */
  borrarPiezasLote: (ids: string[]) =>
    peticion<RespuestaBorrarLotePiezas>("/piezas/borrar-lote", { metodo: "POST", json: { ids } }),
  /** Clona el CONTENIDO (copy, copy-in, foto/collage, plantilla) a OTRA RED de la misma idea:
   *  sobrescribe la pieza hermana de esa red o la crea si la idea no salía ahí. */
  clonarPieza: (id: string, red: string) =>
    peticion<RespuestaPieza>(`/piezas/${encodeURIComponent(id)}/clonar`, {
      metodo: "POST",
      json: { red },
    }),
  encolarPieza: (id: string) =>
    peticion<RespuestaPieza>(`/piezas/${encodeURIComponent(id)}/encolar`, {
      metodo: "POST",
    }),
  /**
   * Integra una FOTO subida dentro de la plantilla de marca de la publicación (logo + copy-in +
   * pleca). Composición DETERMINISTA y SÍNCRONA en el backend (~<1s). Devuelve la imagen
   * resultante `{imagen, imagen_url}` para fijarla y guardarla con el resto de la edición. Para
   * marcas sin plantilla, devuelve la foto tal cual.
   */
  integrarFotoPieza: (id: string, imagen: string, copyIn?: string) =>
    peticion<{ imagen: string; imagen_url: string }>(
      `/piezas/${encodeURIComponent(id)}/integrar-foto`,
      { metodo: "POST", json: copyIn === undefined ? { imagen } : { imagen, copy_in: copyIn } },
    ),
  /** Aplica una plantilla del estudio a la pieza: renderiza con la foto+copy-in dados y persiste. */
  aplicarPlantillaPieza: (
    id: string,
    plantillaId: string,
    extra: { foto?: string; copy_in?: string; foto_encuadre?: string } = {},
  ) =>
    peticion<RespuestaPieza>(`/piezas/${encodeURIComponent(id)}/aplicar-plantilla`, {
      metodo: "POST",
      json: { plantilla_id: plantillaId, ...extra },
    }),
  /**
   * Hornea la PLACA de UN slide del carrusel (foto+titular+plantilla) y devuelve su media
   * `{id, url}`. No toca la pieza: el SPA fija ese media como `objeto` del slide y guarda su
   * procedencia en el JSON `carrusel`. `plantilla_id` ausente = la plantilla EFECTIVA de la marca.
   */
  componerSlide: (
    id: string,
    datos: {
      foto?: string;
      titular?: string;
      plantilla_id?: string;
      foto_encuadre?: string;
      sin_plantilla?: boolean;
    },
  ) =>
    peticion<{ id: string; url: string }>(
      `/piezas/${encodeURIComponent(id)}/componer-slide`,
      { metodo: "POST", json: datos, timeoutMs: 120_000 },
    ),
  /**
   * Genera un CARRUSEL a partir del copy YA redactado del post: ENCOLA un `claude -p` que parte el
   * copy en titulares de slides y los hornea como placas de la marca, escritos en todas las piezas
   * gemelas (la portada se conserva). Responde al instante con `{generacion}` (estado "ejecutando");
   * el SPA la sondea con `useGeneracion` y recarga la pieza al terminar. El feed flip-ea el formato
   * a carrusel ANTES de llamar. `longitud` elige corto (4-5 slides) o largo (8-9).
   */
  generarCarrusel: (id: string, longitud: "corto" | "largo") =>
    peticion<RespuestaGeneracion>(`/piezas/${encodeURIComponent(id)}/generar-carrusel`, {
      metodo: "POST",
      json: { longitud },
    }),

  /**
   * Conversión NO DESTRUCTIVA a carrusel: crea una VARIANTE carrusel HERMANA junto a la foto en vez
   * de sobrescribir el post (la foto sigue viva; el feed muestra ambas como tarjetas aparte y el
   * equipo elige cuál publica). Responde al instante con `{generacion}`; el SPA la sondea y, al
   * terminar, refresca el feed (la tarjeta carrusel nueva aparece). NO flip-ea el formato del post.
   */
  convertirCarrusel: (id: string, longitud: "corto" | "largo") =>
    peticion<RespuestaGeneracion>(`/piezas/${encodeURIComponent(id)}/convertir-carrusel`, {
      metodo: "POST",
      json: { longitud },
    }),

  // --- Aprobación de PIEZAS (#9): cola de revisión + decisión + programación ---
  // Programar NO es aprobación (es programación) y NO publica de verdad: el posteo real
  // vía Metricool está gated por `KENI_PUBLICAR_REAL`.
  /** Cola de aprobación: piezas en revisión (FIFO). Lectura; cada item es una `Pieza`. */
  colaAprobacion: (signal?: AbortSignal) =>
    peticion<RespuestaColaAprobacion>("/aprobacion/cola", { signal }),
  /** Envía una publicación a revisión: crea la cadena de aprobación simple (borrador → en revisión). */
  enviarARevision: (id: string) =>
    peticion<RespuestaPieza>(`/aprobacion/${encodeURIComponent(id)}/enviar-a-revision`, {
      metodo: "POST",
    }),
  /** Aprueba el nivel actual de la cadena de una publicación (revisor != autor, salvo admin). */
  aprobarPieza: (id: string) =>
    peticion<RespuestaPieza>(`/aprobacion/${encodeURIComponent(id)}/aprobar`, {
      metodo: "POST",
    }),
  /** Da un "dislike": rechaza el nivel actual. Dos dislikes (dos personas) vuelven a borrador. */
  rechazarPieza: (id: string) =>
    peticion<RespuestaPieza>(`/aprobacion/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
    }),
  /** Retira la decisión propia (quitar tu OK o tu dislike): tu nivel vuelve a pendiente. */
  deshacerAprobacion: (id: string) =>
    peticion<RespuestaPieza>(`/aprobacion/${encodeURIComponent(id)}/deshacer`, {
      metodo: "POST",
    }),
  /** FUERZA la aprobación (admin/coordinador): se salta la cadena y deja la pieza aprobada. */
  forzarAprobacion: (id: string) =>
    peticion<RespuestaPieza>(`/aprobacion/${encodeURIComponent(id)}/forzar`, {
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
    >("/publicaciones/importar", { metodo: "POST", form, timeoutMs: 120_000 });
  },

  // --- Alertas de rendimiento (bitácora editorial: bajo rendimiento) ---
  alertas: (params: { limite?: number } = {}, signal?: AbortSignal) =>
    peticion<RespuestaAlertas>(
      `/alertas${query({ limite: params.limite?.toString() })}`,
      { signal },
    ),


};

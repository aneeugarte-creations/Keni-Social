/**
 * Cliente fetch tipado de la Consola Keni.
 *
 * - Mismo origen: todas las rutas cuelgan de `/api`. En `npm run dev`, Vite
 *   proxea `/api` a `http://127.0.0.1:8765` (ver vite.config.ts).
 * - Ante un status no-OK, lanza `ApiError` con el `mensaje`/`error` en espanol
 *   que devuelve el backend (o un fallback legible). React Query expone ese
 *   mensaje a la UI.
 * - Soporta JSON, multipart (FormData) y descargas (abre la URL en el navegador).
 */
import type {
  CompararMetricas,
  CuerpoActualizarPublicacion,
  CuerpoActualizarTarea,
  CuerpoConectarRed,
  CuerpoCrearCarpeta,
  CuerpoCrearFranja,
  CuerpoCrearProyecto,
  CuerpoCrearPublicacion,
  CuerpoCrearPublicacionesLote,
  CuerpoCrearTarea,
  CuerpoDuplicarPublicacion,
  CuerpoEjecutarSkill,
  CuerpoGenerarMedia,
  CuerpoGrupoHashtags,
  CuerpoGuardarClaudeMd,
  CuerpoGuardarConexionImagen,
  CuerpoGuardarConfig,
  CuerpoSugerirHashtags,
  DetalleHistorial,
  ErrorApi,
  FiltrosPublicaciones,
  OpcionesMetricas,
  OpcionesPublicaciones,
  ReporteMetricas,
  RespuestaCarpetas,
  RespuestaConectarRed,
  RespuestaConexionesRedes,
  RespuestaConexionImagen,
  RespuestaConfig,
  RespuestaCrearCarpeta,
  RespuestaCrearTarea,
  RespuestaEjecutarSkill,
  RespuestaEstado,
  RespuestaFranja,
  RespuestaFranjas,
  RespuestaGrupoHashtags,
  RespuestaHashtags,
  RespuestaHistorial,
  RespuestaMedia,
  RespuestaMensaje,
  RespuestaProyectos,
  RespuestaProbarConexionImagen,
  RespuestaGuardarConexionImagen,
  RespuestaPublicacion,
  RespuestaPublicaciones,
  RespuestaSkills,
  RespuestaSugerirHashtags,
  RespuestaTareas,
} from "@/types";

export const BASE_API = "/api";

/**
 * URL para servir una imagen del almacén de medios. Acepta tanto el nombre del
 * archivo (`foto.png`) como una `imagen_url` ya formada (`/api/media/foto.png`);
 * devuelve cadena vacía si no hay imagen.
 */
export function urlMedia(nombreOUrl: string | null | undefined): string {
  if (!nombreOUrl) return "";
  if (nombreOUrl.startsWith("/api/") || nombreOUrl.startsWith("http")) return nombreOUrl;
  return `${BASE_API}/media/${encodeURIComponent(nombreOUrl)}`;
}

/** Error de la API con el mensaje legible (en espanol) ya extraido. */
export class ApiError extends Error {
  readonly status: number;
  constructor(mensaje: string, status: number) {
    super(mensaje);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Extrae un mensaje legible del cuerpo de error (campo `mensaje` o `error`). */
async function mensajeDeError(res: Response): Promise<string> {
  try {
    const cuerpo = (await res.clone().json()) as ErrorApi;
    if (cuerpo?.mensaje) return cuerpo.mensaje;
    if (cuerpo?.error) return cuerpo.error;
  } catch {
    // El cuerpo no era JSON; intentamos texto plano abajo.
  }
  try {
    const texto = (await res.text()).trim();
    if (texto) return texto;
  } catch {
    // Sin cuerpo legible.
  }
  return `Algo salió mal (código ${res.status}). Vuelve a intentarlo.`;
}

async function parsear<T>(res: Response): Promise<T> {
  if (!res.ok) {
    throw new ApiError(await mensajeDeError(res), res.status);
  }
  // 204 No Content u otras respuestas sin cuerpo.
  if (res.status === 204) return undefined as T;
  const texto = await res.text();
  if (!texto) return undefined as T;
  return JSON.parse(texto) as T;
}

interface OpcionesPeticion {
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Cuerpo JSON (se serializa). Mutuamente excluyente con `form`. */
  json?: unknown;
  /** Cuerpo multipart (FormData) para subir archivos. */
  form?: FormData;
  signal?: AbortSignal;
}

/** Petición base: arma la URL, serializa el cuerpo y delega en `parsear`. */
async function peticion<T>(ruta: string, opciones: OpcionesPeticion = {}): Promise<T> {
  const { metodo = "GET", json, form, signal } = opciones;
  const headers: HeadersInit = {};
  let body: BodyInit | undefined;

  if (form) {
    // No fijamos Content-Type: el navegador pone el boundary del multipart.
    body = form;
  } else if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_API}${ruta}`, { method: metodo, headers, body, signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("No se pudo contactar con la consola. ¿Está corriendo el servidor local?", 0);
  }
  return parsear<T>(res);
}

/** Construye una query string a partir de pares clave/valor (omite vacios). */
function query(params: Record<string, string | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== "") sp.set(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Dispara la descarga de un archivo abriendo su URL (CSV/MD/JSON). */
function descargar(ruta: string): void {
  window.open(`${BASE_API}${ruta}`, "_blank", "noopener,noreferrer");
}

export const api = {
  // --- Estado ---
  estado: (signal?: AbortSignal) => peticion<RespuestaEstado>("/estado", { signal }),

  // --- Config ---
  config: (signal?: AbortSignal) => peticion<RespuestaConfig>("/config", { signal }),
  guardarConfig: (cuerpo: CuerpoGuardarConfig) =>
    peticion<RespuestaMensaje>("/config", { metodo: "POST", json: cuerpo }),

  // --- Proyectos ---
  proyectos: (signal?: AbortSignal) => peticion<RespuestaProyectos>("/proyectos", { signal }),
  crearProyecto: (cuerpo: CuerpoCrearProyecto) =>
    peticion<RespuestaMensaje>("/proyectos", { metodo: "POST", json: cuerpo }),
  guardarClaudeMd: (id: string, cuerpo: CuerpoGuardarClaudeMd) =>
    peticion<RespuestaMensaje>(`/proyectos/${encodeURIComponent(id)}/claude-md`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  abrirProyecto: (id: string) =>
    peticion<RespuestaMensaje>(`/proyectos/${encodeURIComponent(id)}/abrir`, { metodo: "POST" }),

  // --- Carpetas ---
  carpetas: (signal?: AbortSignal) => peticion<RespuestaCarpetas>("/carpetas", { signal }),
  crearCarpeta: (cuerpo: CuerpoCrearCarpeta) =>
    peticion<RespuestaCrearCarpeta>("/carpetas", { metodo: "POST", json: cuerpo }),

  // --- Skills (Generar copy) ---
  skills: (signal?: AbortSignal) => peticion<RespuestaSkills>("/skills", { signal }),
  ejecutarSkill: (cuerpo: CuerpoEjecutarSkill) =>
    peticion<RespuestaEjecutarSkill>("/skills/ejecutar", { metodo: "POST", json: cuerpo }),
  ejecutarSkillArchivo: (skill: string, marca: string, archivo: File, redes?: string[]) => {
    const form = new FormData();
    form.set("skill", skill);
    form.set("marca", marca);
    form.set("archivo", archivo);
    // Cada red va como un campo `redes` repetido (multivalor).
    for (const red of redes ?? []) form.append("redes", red);
    return peticion<RespuestaEjecutarSkill>("/skills/ejecutar-archivo", { metodo: "POST", form });
  },
  historial: (signal?: AbortSignal) => peticion<RespuestaHistorial>("/skills/historial", { signal }),
  detalleHistorial: (id: string, signal?: AbortSignal) =>
    peticion<DetalleHistorial>(`/skills/historial/${encodeURIComponent(id)}`, { signal }),

  // --- Publicaciones ---
  publicacionesOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesPublicaciones>("/publicaciones/opciones", { signal }),
  publicaciones: (filtros: FiltrosPublicaciones = {}, signal?: AbortSignal) =>
    peticion<RespuestaPublicaciones>(`/publicaciones${query(filtros)}`, { signal }),
  publicacion: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}`, { signal }),
  crearPublicacion: (cuerpo: CuerpoCrearPublicacion) =>
    peticion<RespuestaPublicacion>("/publicaciones", { metodo: "POST", json: cuerpo }),
  crearPublicacionesLote: (cuerpo: CuerpoCrearPublicacionesLote) =>
    peticion<RespuestaPublicaciones>("/publicaciones/lote", { metodo: "POST", json: cuerpo }),
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

  // --- Media (imágenes) ---
  subirMedia: (archivo: File) => {
    const form = new FormData();
    form.set("archivo", archivo);
    return peticion<RespuestaMedia>("/media", { metodo: "POST", form });
  },
  generarMedia: (cuerpo: CuerpoGenerarMedia) =>
    peticion<RespuestaMedia>("/media/generar", { metodo: "POST", json: cuerpo }),

  // --- Hashtags ---
  hashtags: (signal?: AbortSignal) => peticion<RespuestaHashtags>("/hashtags", { signal }),
  crearGrupoHashtags: (cuerpo: CuerpoGrupoHashtags) =>
    peticion<RespuestaGrupoHashtags>("/hashtags", { metodo: "POST", json: cuerpo }),
  actualizarGrupoHashtags: (id: string, cuerpo: CuerpoGrupoHashtags) =>
    peticion<RespuestaGrupoHashtags>(`/hashtags/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarGrupoHashtags: (id: string) =>
    peticion<RespuestaMensaje>(`/hashtags/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  sugerirHashtags: (cuerpo: CuerpoSugerirHashtags) =>
    peticion<RespuestaSugerirHashtags>("/hashtags/sugerir", { metodo: "POST", json: cuerpo }),

  // --- Franjas (colas) ---
  franjas: (signal?: AbortSignal) => peticion<RespuestaFranjas>("/franjas", { signal }),
  crearFranja: (cuerpo: CuerpoCrearFranja) =>
    peticion<RespuestaFranja>("/franjas", { metodo: "POST", json: cuerpo }),
  eliminarFranja: (id: string) =>
    peticion<RespuestaMensaje>(`/franjas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Tareas ---
  tareas: (signal?: AbortSignal) => peticion<RespuestaTareas>("/tareas", { signal }),
  crearTarea: (cuerpo: CuerpoCrearTarea) =>
    peticion<RespuestaCrearTarea>("/tareas", { metodo: "POST", json: cuerpo }),
  actualizarTarea: (id: string, cuerpo: CuerpoActualizarTarea) =>
    peticion<RespuestaCrearTarea>(`/tareas/${encodeURIComponent(id)}`, { metodo: "PATCH", json: cuerpo }),
  eliminarTarea: (id: string) =>
    peticion<RespuestaMensaje>(`/tareas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  abrirTarea: (id: string) =>
    peticion<RespuestaMensaje>(`/tareas/${encodeURIComponent(id)}/abrir`, { metodo: "POST" }),

  // --- Metricas ---
  metricasOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesMetricas>("/metricas/opciones", { signal }),
  metricasReporte: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<ReporteMetricas>(`/metricas/reporte${query(params)}`, { signal }),
  metricasComparar: (
    params: { rango_a?: string; rango_b?: string; marca?: string },
    signal?: AbortSignal,
  ) => peticion<CompararMetricas>(`/metricas/comparar${query(params)}`, { signal }),
  exportarMetricas: (formato: "csv" | "md" | "json", params: { rango?: string; marca?: string }) =>
    descargar(`/metricas/export.${formato}${query(params)}`),

  // --- Conexiones (imagen IA + tokens de redes) ---
  // Los secretos son write-only: solo se envían (PUT); del servidor llega
  // únicamente el estado y, para la imagen, una pista no sensible.
  conexionImagen: (signal?: AbortSignal) =>
    peticion<RespuestaConexionImagen>("/conexiones/imagen", { signal }),
  guardarConexionImagen: (cuerpo: CuerpoGuardarConexionImagen) =>
    peticion<RespuestaGuardarConexionImagen>("/conexiones/imagen", { metodo: "PUT", json: cuerpo }),
  probarConexionImagen: () =>
    peticion<RespuestaProbarConexionImagen>("/conexiones/imagen/probar", { metodo: "POST" }),
  eliminarConexionImagen: () =>
    peticion<RespuestaMensaje>("/conexiones/imagen", { metodo: "DELETE" }),

  conexionesRedes: (signal?: AbortSignal) =>
    peticion<RespuestaConexionesRedes>("/conexiones/redes", { signal }),
  conectarRed: (plataforma: string, cuerpo: CuerpoConectarRed) =>
    peticion<RespuestaConectarRed>(`/conexiones/redes/${encodeURIComponent(plataforma)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  desconectarRed: (plataforma: string) =>
    peticion<RespuestaMensaje>(`/conexiones/redes/${encodeURIComponent(plataforma)}`, {
      metodo: "DELETE",
    }),
};

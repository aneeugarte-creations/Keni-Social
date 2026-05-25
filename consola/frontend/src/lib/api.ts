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
  AgenteDetalle,
  CompararMetricas,
  CuerpoConectarAgente,
  CuerpoCrearAgente,
  CuerpoRenombrarAgente,
  CuerpoActualizarFuenteRss,
  CuerpoActualizarPlantilla,
  CuerpoActualizarPublicacion,
  CuerpoActualizarSkill,
  CuerpoActualizarTarea,
  CuerpoConectarRed,
  CuerpoCrearCarpeta,
  CuerpoCrearFranja,
  CuerpoCrearRun,
  CuerpoCrearFuenteRss,
  CuerpoCrearPlantilla,
  CuerpoCrearProyecto,
  CuerpoCrearPublicacion,
  CuerpoCrearPublicacionesLote,
  CuerpoCrearSkill,
  CuerpoCrearTarea,
  CuerpoDuplicarPublicacion,
  CuerpoEjecutarSkill,
  CuerpoGenerarDesdeItem,
  CuerpoGenerarMedia,
  CuerpoGrupoHashtags,
  CuerpoGuardarClaudeMd,
  CuerpoGuardarContexto,
  CuerpoGuardarHistorial,
  CuerpoGuardarConexionImagen,
  CuerpoGuardarConfig,
  CuerpoGuardarEsfuerzo,
  CuerpoMarcarItemUsado,
  CuerpoSugerirHashtags,
  CuerpoVerificar,
  CuerpoVistaPromptSkill,
  DetalleHistorial,
  ErrorApi,
  FiltrosPublicaciones,
  OpcionesMetricas,
  OpcionesPublicaciones,
  ReporteMetricas,
  RespuestaAgente,
  RespuestaAgentes,
  RespuestaCarpetas,
  RespuestaConectarRed,
  RespuestaConexionesRedes,
  RespuestaConexionImagen,
  RespuestaConfig,
  RespuestaCrearCarpeta,
  RespuestaCrearTarea,
  RespuestaEsfuerzo,
  RespuestaEstado,
  RespuestaFranja,
  RespuestaFranjas,
  RespuestaFuenteRss,
  RespuestaFuentesRss,
  RespuestaGeneracion,
  RespuestaGeneraciones,
  RespuestaGrupoHashtags,
  RespuestaHashtags,
  RespuestaHistorial,
  RespuestaItemsRss,
  RespuestaMedia,
  RespuestaMensaje,
  RespuestaPlantilla,
  RespuestaPlantillas,
  RespuestaProyectos,
  RespuestaProbarConexionImagen,
  RespuestaGuardarConexionImagen,
  RespuestaCatalogoSkills,
  RespuestaDetalleSkillDef,
  RespuestaPublicacion,
  RespuestaPublicaciones,
  RespuestaReciclarPublicacion,
  RespuestaRun,
  RespuestaRuns,
  RespuestaRunsAgregados,
  RespuestaSkillDef,
  RespuestaSkillMd,
  RespuestaSkills,
  RespuestaSubContextos,
  RespuestaTareas,
  RespuestaVistaPromptSkill,
  Run,
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
  esfuerzo: (signal?: AbortSignal) => peticion<RespuestaEsfuerzo>("/config/esfuerzo", { signal }),
  guardarEsfuerzo: (cuerpo: CuerpoGuardarEsfuerzo) =>
    peticion<RespuestaMensaje>("/config/esfuerzo", { metodo: "POST", json: cuerpo }),

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

  // --- Agentes (carpeta con CLAUDE.md, sub-contextos y runs) ---
  // Conjunto abierto: 5 marcas de serie (es_marca) + agentes genéricos
  // (crear/conectar/renombrar/borrar).
  agentes: (signal?: AbortSignal) => peticion<RespuestaAgentes>("/agentes", { signal }),
  agente: (id: string, signal?: AbortSignal) =>
    peticion<AgenteDetalle>(`/agentes/${encodeURIComponent(id)}`, { signal }),
  crearAgente: (cuerpo: CuerpoCrearAgente) =>
    peticion<RespuestaAgente>("/agentes", { metodo: "POST", json: cuerpo }),
  conectarAgente: (cuerpo: CuerpoConectarAgente) =>
    peticion<RespuestaAgente>("/agentes/conectar", { metodo: "POST", json: cuerpo }),
  renombrarAgente: (id: string, cuerpo: CuerpoRenombrarAgente) =>
    peticion<RespuestaAgente>(`/agentes/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarAgente: (id: string) =>
    peticion<RespuestaMensaje>(`/agentes/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  guardarClaudeMdAgente: (id: string, cuerpo: CuerpoGuardarClaudeMd) =>
    peticion<RespuestaMensaje>(`/agentes/${encodeURIComponent(id)}/claude-md`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  contextosAgente: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaSubContextos>(`/agentes/${encodeURIComponent(id)}/contextos`, { signal }),
  guardarContextoAgente: (id: string, nombre: string, cuerpo: CuerpoGuardarContexto) =>
    peticion<RespuestaMensaje>(
      `/agentes/${encodeURIComponent(id)}/contextos/${encodeURIComponent(nombre)}`,
      { metodo: "PUT", json: cuerpo },
    ),
  eliminarContextoAgente: (id: string, nombre: string) =>
    peticion<RespuestaMensaje>(
      `/agentes/${encodeURIComponent(id)}/contextos/${encodeURIComponent(nombre)}`,
      { metodo: "DELETE" },
    ),
  crearRunAgente: (id: string, cuerpo: CuerpoCrearRun) =>
    peticion<RespuestaRun>(`/agentes/${encodeURIComponent(id)}/runs`, {
      metodo: "POST",
      json: cuerpo,
    }),
  runsAgente: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaRuns>(`/agentes/${encodeURIComponent(id)}/runs`, { signal }),
  runAgente: (id: string, runId: string, signal?: AbortSignal): Promise<Run> =>
    peticion<Run>(`/agentes/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}`, {
      signal,
    }),

  // --- Monitor (actividad IA: runs de todos los agentes + agregados) ---
  runs: (signal?: AbortSignal) => peticion<RespuestaRuns>("/runs", { signal }),
  runsAgregados: (signal?: AbortSignal) =>
    peticion<RespuestaRunsAgregados>("/runs/agregados", { signal }),

  // --- Generaciones (sondeo de trabajos de IA en segundo plano) ---
  // Toda generación (copy/RSS/hashtags/imagen) responde de inmediato con `{generacion}`
  // (estado "ejecutando"); se sondea aquí hasta el estado terminal.
  generaciones: (signal?: AbortSignal) =>
    peticion<RespuestaGeneraciones>("/generaciones", { signal }),
  generacion: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaGeneracion>(`/generaciones/${encodeURIComponent(id)}`, { signal }),

  // --- Skills (Generar copy) ---
  skills: (signal?: AbortSignal) => peticion<RespuestaSkills>("/skills", { signal }),
  ejecutarSkill: (cuerpo: CuerpoEjecutarSkill) =>
    peticion<RespuestaGeneracion>("/skills/ejecutar", { metodo: "POST", json: cuerpo }),
  ejecutarSkillArchivo: (
    skill: string,
    marca: string,
    archivo: File,
    valores: Record<string, string>,
    redes?: string[],
  ) => {
    const form = new FormData();
    form.set("skill", skill);
    form.set("marca", marca);
    form.set("archivo", archivo);
    // El resto de campos de texto van como campos de formulario con su id.
    for (const [id, valor] of Object.entries(valores)) form.set(id, valor);
    // Cada red va como un campo `redes` repetido (multivalor).
    for (const red of redes ?? []) form.append("redes", red);
    return peticion<RespuestaGeneracion>("/skills/ejecutar-archivo", { metodo: "POST", form });
  },

  // --- Skills (catálogo editable: CRUD + vista previa del prompt) ---
  catalogoSkills: (signal?: AbortSignal) =>
    peticion<RespuestaCatalogoSkills>("/skills/catalogo", { signal }),
  crearSkill: (cuerpo: CuerpoCrearSkill) =>
    peticion<RespuestaSkillDef>("/skills/catalogo", { metodo: "POST", json: cuerpo }),
  skillCatalogo: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaDetalleSkillDef>(`/skills/catalogo/${encodeURIComponent(id)}`, { signal }),
  actualizarSkill: (id: string, cuerpo: CuerpoActualizarSkill) =>
    peticion<RespuestaSkillDef>(`/skills/catalogo/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  guardarSkillMd: (id: string, contenido: string) =>
    peticion<RespuestaSkillMd>(`/skills/catalogo/${encodeURIComponent(id)}/skill-md`, {
      metodo: "PUT",
      json: { contenido },
    }),
  eliminarSkill: (id: string) =>
    peticion<RespuestaMensaje>(`/skills/catalogo/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  vistaPromptSkill: (id: string, cuerpo: CuerpoVistaPromptSkill, signal?: AbortSignal) =>
    peticion<RespuestaVistaPromptSkill>(
      `/skills/catalogo/${encodeURIComponent(id)}/vista-prompt`,
      { metodo: "POST", json: cuerpo, signal },
    ),
  historial: (signal?: AbortSignal) => peticion<RespuestaHistorial>("/skills/historial", { signal }),
  detalleHistorial: (id: string, signal?: AbortSignal) =>
    peticion<DetalleHistorial>(`/skills/historial/${encodeURIComponent(id)}`, { signal }),
  guardarHistorial: (id: string, cuerpo: CuerpoGuardarHistorial = {}) =>
    peticion<RespuestaPublicaciones>(`/skills/historial/${encodeURIComponent(id)}/guardar`, {
      metodo: "POST",
      json: cuerpo,
    }),

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
  reciclarPublicacion: (id: string) =>
    peticion<RespuestaReciclarPublicacion>(`/publicaciones/${encodeURIComponent(id)}/reciclar`, {
      metodo: "POST",
    }),

  // --- Media (imágenes) ---
  subirMedia: (archivo: File) => {
    const form = new FormData();
    form.set("archivo", archivo);
    return peticion<RespuestaMedia>("/media", { metodo: "POST", form });
  },
  generarMedia: (cuerpo: CuerpoGenerarMedia) =>
    peticion<RespuestaGeneracion>("/media/generar", { metodo: "POST", json: cuerpo }),

  // --- Verificación de video (workflow propio, independiente de Generar copy) ---
  // Lanza el análisis de procedencia en segundo plano; se sondea como cualquier
  // generación (GET /api/generaciones/{id}) y completa con `resultado.verificacion`.
  verificar: (cuerpo: CuerpoVerificar) =>
    peticion<RespuestaGeneracion>("/verificar", { metodo: "POST", json: cuerpo }),

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
    peticion<RespuestaGeneracion>("/hashtags/sugerir", { metodo: "POST", json: cuerpo }),

  // --- Plantillas de post ---
  plantillas: (signal?: AbortSignal) => peticion<RespuestaPlantillas>("/plantillas", { signal }),
  crearPlantilla: (cuerpo: CuerpoCrearPlantilla) =>
    peticion<RespuestaPlantilla>("/plantillas", { metodo: "POST", json: cuerpo }),
  actualizarPlantilla: (id: string, cuerpo: CuerpoActualizarPlantilla) =>
    peticion<RespuestaPlantilla>(`/plantillas/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarPlantilla: (id: string) =>
    peticion<RespuestaMensaje>(`/plantillas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- RSS (fuentes + items) ---
  fuentesRss: (signal?: AbortSignal) => peticion<RespuestaFuentesRss>("/rss/fuentes", { signal }),
  crearFuenteRss: (cuerpo: CuerpoCrearFuenteRss) =>
    peticion<RespuestaFuenteRss>("/rss/fuentes", { metodo: "POST", json: cuerpo }),
  actualizarFuenteRss: (id: string, cuerpo: CuerpoActualizarFuenteRss) =>
    peticion<RespuestaFuenteRss>(`/rss/fuentes/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarFuenteRss: (id: string) =>
    peticion<RespuestaMensaje>(`/rss/fuentes/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  itemsRss: (fuente?: string, ocultarUsados?: boolean, signal?: AbortSignal) =>
    peticion<RespuestaItemsRss>(
      `/rss/items${query({ fuente, ocultar_usados: ocultarUsados ? "1" : undefined })}`,
      { signal },
    ),
  marcarItemRssUsado: (cuerpo: CuerpoMarcarItemUsado) =>
    peticion<RespuestaMensaje>("/rss/items/usado", { metodo: "POST", json: cuerpo }),
  generarDesdeItemRss: (cuerpo: CuerpoGenerarDesdeItem) =>
    peticion<RespuestaGeneracion>("/rss/generar", { metodo: "POST", json: cuerpo }),

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

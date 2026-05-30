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
  AnalisisDiario,
  CompararMetricas,
  AnaliticaPiezas,
  CuerpoConectarAgente,
  CuerpoCrearAgente,
  EstadoMetricas,
  TendenciaDiaria,
  CuerpoRenombrarAgente,
  CuerpoActualizarFuenteRss,
  CuerpoActualizarPublicacion,
  CuerpoActualizarSkill,
  CuerpoActualizarTarea,
  CuerpoActualizarTurnoRota,
  CuerpoActualizarEventoRota,
  CuerpoActualizarPiezaRota,
  CuerpoActualizarProgramaRota,
  CuerpoAprobarRota,
  CuerpoBorrarLoteIds,
  CuerpoCrearProgramaRota,
  CuerpoActualizarFranjaSemana,
  CuerpoCrearFranjaSemana,
  CuerpoCrearTurnoRota,
  CuerpoCrearTurnosLote,
  CuerpoDuplicarEventoRota,
  CuerpoDuplicarPiezaRota,
  CuerpoDuplicarTurnoRota,
  CuerpoPerfilesMetricool,
  CuerpoGuardarMetricool,
  CuerpoCrearCarpeta,
  CuerpoCrearFranja,
  CuerpoCrearRun,
  CuerpoCrearFuenteRss,
  CuerpoCrearProyecto,
  CuerpoCrearPublicacion,
  CuerpoCrearPublicacionesLote,
  CuerpoCrearSkill,
  CuerpoActualizarContenido,
  CuerpoActualizarEtiqueta,
  CuerpoActualizarPlataforma,
  CuerpoAsistenteContenido,
  CuerpoCrearContenido,
  CuerpoCrearEtiqueta,
  CuerpoCrearTarea,
  CuerpoDesdeRadar,
  CuerpoCrearEventoRota,
  CuerpoCrearPiezaRota,
  CuerpoDuplicarPublicacion,
  CuerpoEjecutarSkill,
  CuerpoEjecutarSkillUrl,
  CuerpoGenerarDesdeItem,
  CuerpoGenerarMedia,
  CuerpoGenerarTermometro,
  CuerpoGuardarTermometro,
  CuerpoGrupoHashtags,
  CuerpoGuardarClaudeMd,
  CuerpoGuardarContexto,
  CuerpoGuardarHistorial,
  CuerpoGuardarConexionImagen,
  CuerpoGuardarModeloImagen,
  CuerpoGuardarConfig,
  CuerpoGuardarEsfuerzo,
  CuerpoMarcarItemUsado,
  CuerpoReporteDeportes,
  CuerpoRevisarQaEditorial,
  CuerpoSugerirHashtags,
  CuerpoVerificar,
  CuerpoVistaPromptSkill,
  DetalleHistorial,
  ErrorApi,
  FiltrosPublicaciones,
  OpcionesMetricas,
  OpcionesPublicaciones,
  OpcionesQaEditorial,
  OpcionesReporteDeportes,
  RespuestaLimites,
  ReporteDeportes,
  ReporteMetricas,
  RespuestaAgente,
  RespuestaAgentes,
  RespuestaCarpetas,
  RespuestaCatalogo,
  RespuestaPerfilesMetricool,
  RespuestaMetricool,
  RespuestaGuardarMetricool,
  RespuestaProbarMetricool,
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
  CuerpoCrearPlantillaContenido,
  CuerpoActualizarPlantillaContenido,
  CuerpoAplicarPlantilla,
  RespuestaPlantillasContenido,
  RespuestaPlantillaContenido,
  RespuestaAplicarPlantilla,
  RespuestaMediosBiblioteca,
  RespuestaMedioBiblioteca,
  CuerpoActualizarMedioBiblioteca,
  RespuestaProyectos,
  RespuestaRadar,
  RespuestaParrilla,
  RespuestaProgramarMetricool,
  RespuestaProbarConexionImagen,
  RespuestaGuardarConexionImagen,
  RespuestaGuardarModeloImagen,
  RespuestaCatalogoSkills,
  RespuestaDetalleSkillDef,
  RespuestaPublicacion,
  RespuestaPublicaciones,
  RespuestaColaAprobacion,
  RespuestaPanel,
  RespuestaReciclarPublicacion,
  RespuestaSugerenciasReciclaje,
  FiltrosReciclaje,
  RespuestaRun,
  RespuestaRuns,
  RespuestaRunsAgregados,
  RespuestaSkillDef,
  RespuestaSkillMd,
  RespuestaSkills,
  RespuestaConfigTermometro,
  RespuestaTermometro,
  RespuestaSubContextos,
  RespuestaSugerencia,
  RespuestaSugerencias,
  CadenaAprobacion,
  RespuestaComentario,
  RespuestaComentarios,
  RespuestaContenido,
  RespuestaContenidoItem,
  RespuestaMetricasContenido,
  RespuestaCopyGuardado,
  RespuestaCopyVersiones,
  RespuestaDecisionAprobacion,
  RespuestaPlataforma,
  RespuestaWebhooks,
  RespuestaWebhook,
  RespuestaProbarWebhook,
  CuerpoCrearWebhook,
  CuerpoActualizarWebhook,
  RespuestaEtiquetas,
  RespuestaEtiqueta,
  RespuestaEtiquetasContenido,
  RespuestaPreviewContenido,
  RespuestaTareas,
  RespuestaEquipoRota,
  RespuestaEventosRota,
  RespuestaEventoRota,
  RespuestaTurnoRota,
  RespuestaCrearTurnosLote,
  RespuestaCoberturaSemana,
  RespuestaCoberturaEvento,
  RespuestaCoordinacionSemana,
  CoordinacionTurno,
  CuerpoSetCoordinador,
  CuerpoQuitarCoordinador,
  RotaSemana,
  MisTurnosRota,
  CuerpoCrearAusenciaRota,
  CuerpoActualizarAusenciaRota,
  RespuestaAusenciasRota,
  RespuestaAusenciaRota,
  FiltrosPiezasRota,
  RespuestaBorrarLote,
  RespuestaPiezaRota,
  RespuestaPiezasRota,
  RespuestaProgramaRota,
  RespuestaProgramasRota,
  RespuestaConfigFranjas,
  CuerpoGuardarConfigFranjas,
  FranjaSemana,
  RespuestaFranjasSemana,
  CuerpoActualizarLoteTurnos,
  RespuestaActualizarLoteTurnos,
  CuerpoCopiarSemana,
  RespuestaCopiarSemana,
  RespuestaCargaRota,
  CuerpoCrearSwap,
  CuerpoDecidirSwap,
  FiltrosSwaps,
  RespuestaSwap,
  RespuestaSwaps,
  RespuestaVistaPromptSkill,
  CuerpoActualizarSugerencia,
  CuerpoCrearSugerencia,
  CuerpoActualizarComercial,
  CuerpoCrearComercial,
  CuerpoActualizarUsuario,
  CuerpoCambiarPassword,
  CuerpoCrearUsuario,
  CuerpoLogin,
  RespuestaSesion,
  RespuestaUsuarios,
  UsuarioAdmin,
  FiltrosComercial,
  OpcionesComercial,
  RespuestaPublicacionComercial,
  RespuestaPublicacionesComercial,
  RespuestaRefrescarComercial,
  RespuestaReporteComercial,
  Run,
} from "@/types";

import { type NombreContrato, validarContrato } from "./contrato";

export const BASE_API = "/api";

/**
 * Token de sesion de la Consola (#134). El backend lo inyecta en el index del SPA
 * como `window.__KENI_TOKEN__` y tambien lo siembra como cookie `keni_consola_token`
 * (SameSite=Strict). Lo mandamos por cabecera cuando esta disponible (defensa en
 * profundidad); la cookie cubre las descargas por `window.open` y las `<img src>`,
 * que no pueden mandar cabeceras. Si no hay token inyectado, se devuelve cadena vacia
 * y se confia en la cookie.
 */
function tokenSesion(): string {
  const w = window as unknown as { __KENI_TOKEN__?: string };
  return typeof w.__KENI_TOKEN__ === "string" ? w.__KENI_TOKEN__ : "";
}

/** Cabeceras de autenticacion (token de sesion) si hay token inyectado. */
function cabecerasAuth(): Record<string, string> {
  const t = tokenSesion();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/**
 * Muestreo de validación para endpoints SONDEADOS (listas grandes que se refrescan
 * en bucle): en PROD validamos solo una fracción de las respuestas para que el coste
 * no se acumule en cada poll; en DEV validamos SIEMPRE (queremos cazar el drift). El
 * resultado de la validación es no fatal en PROD igualmente.
 */
const _MUESTREO_PROD = 0.1;

function _debeValidar(): boolean {
  return import.meta.env.DEV || Math.random() < _MUESTREO_PROD;
}

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
  /**
   * Cuerpo JSON del error (cuando el back lo envía). Útil para 409s que llevan
   * datos accionables (p. ej. `ids_que_requieren_override`).
   */
  readonly cuerpo: Record<string, unknown> | null;
  constructor(mensaje: string, status: number, cuerpo: Record<string, unknown> | null = null) {
    super(mensaje);
    this.name = "ApiError";
    this.status = status;
    this.cuerpo = cuerpo;
  }
}

/**
 * Extrae mensaje + cuerpo JSON de una respuesta de error. Devuelve `{mensaje, cuerpo}`:
 * `cuerpo` es el JSON crudo (o null si no era JSON), `mensaje` lo legible.
 */
async function infoDeError(
  res: Response,
): Promise<{ mensaje: string; cuerpo: Record<string, unknown> | null }> {
  try {
    const cuerpo = (await res.clone().json()) as ErrorApi & Record<string, unknown>;
    const mensaje =
      cuerpo?.mensaje ||
      cuerpo?.error ||
      `Algo salió mal (código ${res.status}). Vuelve a intentarlo.`;
    return { mensaje, cuerpo };
  } catch {
    // El cuerpo no era JSON; intentamos texto plano abajo.
  }
  try {
    const texto = (await res.text()).trim();
    // Si el back está caído/reiniciando, la petición a /api puede caer al nginx del
    // front, que responde una página HTML (p. ej. "405 Not Allowed"). No volcamos ese
    // HTML crudo en la UI: damos un mensaje legible. Igual para 502/503/504 del proxy.
    const pareceHtml = texto.startsWith("<");
    if (texto && !pareceHtml) return { mensaje: texto, cuerpo: null };
    if (pareceHtml || res.status === 405 || (res.status >= 502 && res.status <= 504)) {
      return {
        mensaje: "La consola no está disponible ahora mismo. Espera unos segundos y vuelve a intentarlo.",
        cuerpo: null,
      };
    }
  } catch {
    // Sin cuerpo legible.
  }
  return {
    mensaje: `Algo salió mal (código ${res.status}). Vuelve a intentarlo.`,
    cuerpo: null,
  };
}

/**
 * Parsea el body de una respuesta OK como JSON. Si se pasa `validador` (nombre de
 * un `$def` del contrato), valida el body contra ese esquema en el borde de fetch
 * (#120): DEV lanza ante mismatch; PROD avisa y devuelve igual. NUNCA transforma el
 * body. `muestrear` (def `true`) deja que los endpoints sondeados solo validen una
 * fracción en PROD; pásalo a `false` para validar siempre.
 */
async function parsear<T>(
  res: Response,
  validador?: NombreContrato,
  muestrear = true,
): Promise<T> {
  if (!res.ok) {
    const info = await infoDeError(res);
    throw new ApiError(info.mensaje, res.status, info.cuerpo);
  }
  // 204 No Content u otras respuestas sin cuerpo.
  if (res.status === 204) return undefined as T;
  const texto = await res.text();
  if (!texto) return undefined as T;
  const datos = JSON.parse(texto) as T;
  if (validador && (!muestrear || _debeValidar())) {
    return validarContrato(validador, datos);
  }
  return datos;
}

interface OpcionesPeticion {
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Cuerpo JSON (se serializa). Mutuamente excluyente con `form`. */
  json?: unknown;
  /** Cuerpo multipart (FormData) para subir archivos. */
  form?: FormData;
  signal?: AbortSignal;
  /**
   * Nombre del `$def` del contrato contra el que validar el body (opt-in, #120).
   * Solo se valida si el modelo existe en `esquema.gen.json`.
   */
  validador?: NombreContrato;
  /**
   * `false` para validar SIEMPRE (ignora el muestreo de PROD). Útil en endpoints de
   * detalle/escritura (no sondeados). Def `true` (muestrea en PROD).
   */
  muestrear?: boolean;
}

/** Petición base: arma la URL, serializa el cuerpo y delega en `parsear`. */
async function peticion<T>(ruta: string, opciones: OpcionesPeticion = {}): Promise<T> {
  const { metodo = "GET", json, form, signal, validador, muestrear } = opciones;
  const headers: Record<string, string> = { ...cabecerasAuth() };
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
  return parsear<T>(res, validador, muestrear);
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

/**
 * Query string para `/rota/eventos`: serializa arrays como params REPETIDOS
 * (`?prioridad=alta&prioridad=media`) y `cambiado` como tri-estado (true/false/omitir).
 * Mantiene compatibilidad con `cambiados=true` (atajo legado).
 */
function queryEventos(params: {
  desde?: string;
  hasta?: string;
  cambiados?: string;
  tipo_cobertura?: string | string[];
  prioridad?: string | string[];
  cambiado?: boolean | null;
  q?: string;
}): string {
  const sp = new URLSearchParams();
  const aniadir = (clave: string, valor?: string | string[]) => {
    if (valor === undefined) return;
    const arr = Array.isArray(valor) ? valor : [valor];
    for (const v of arr) if (v !== "") sp.append(clave, v);
  };
  if (params.desde) sp.set("desde", params.desde);
  if (params.hasta) sp.set("hasta", params.hasta);
  if (params.cambiados) sp.set("cambiados", params.cambiados);
  if (params.q && params.q.trim() !== "") sp.set("q", params.q.trim());
  if (params.cambiado === true) sp.set("cambiado", "true");
  else if (params.cambiado === false) sp.set("cambiado", "false");
  aniadir("tipo_cobertura", params.tipo_cobertura);
  aniadir("prioridad", params.prioridad);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Dispara la descarga de un archivo abriendo su URL (CSV/MD/JSON). */
function descargar(ruta: string): void {
  window.open(`${BASE_API}${ruta}`, "_blank", "noopener,noreferrer");
}

/**
 * Descarga un archivo binario devuelto por un POST (envia JSON en el cuerpo).
 * Necesario cuando los parametros no caben en la URL (p. ej. el deck lleva la
 * agenda). Lanza `ApiError` con el mensaje del backend si el status no es OK.
 */
async function descargarPost(ruta: string, json: unknown, nombrePorDefecto: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${BASE_API}${ruta}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...cabecerasAuth() },
      body: JSON.stringify(json),
    });
  } catch {
    throw new ApiError("No se pudo contactar con la consola. ¿Está corriendo el servidor local?", 0);
  }
  if (!res.ok) {
    const info = await infoDeError(res);
    throw new ApiError(info.mensaje, res.status, info.cuerpo);
  }

  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") ?? "";
  const nombre = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? nombrePorDefecto;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  // --- Catálogo de apps (ADR 0005): apps activas + navegación data-driven ---
  // El sidebar se hidrata de aquí en vez de hardcodear las entradas. Filtra por los
  // flags de activación del backend; desactivar una app la oculta sin tocar el front.
  catalogo: (signal?: AbortSignal) => peticion<RespuestaCatalogo>("/catalogo", { signal }),

  // --- Autenticación (sesión por cookie) ---
  // El login depende de la cookie de sesión que pone el backend; `api.ts` ya
  // manda las cabeceras de auth (#134) en cada petición para las mutaciones.
  // `me` se llama al cargar la app: 200 => sesión viva; 401 => mostrar login.
  login: (cuerpo: CuerpoLogin) =>
    peticion<RespuestaSesion>("/auth/login", { metodo: "POST", json: cuerpo }),
  logout: () => peticion<void>("/auth/logout", { metodo: "POST" }),
  me: (signal?: AbortSignal) => peticion<RespuestaSesion>("/auth/me", { signal }),
  cambiarPassword: (cuerpo: CuerpoCambiarPassword) =>
    peticion<void>("/auth/cambiar-password", { metodo: "POST", json: cuerpo }),

  // --- Usuarios (solo admin; 403 si no) ---
  usuarios: (signal?: AbortSignal) => peticion<RespuestaUsuarios>("/usuarios", { signal }),
  crearUsuario: (cuerpo: CuerpoCrearUsuario) =>
    peticion<UsuarioAdmin>("/usuarios", { metodo: "POST", json: cuerpo }),
  actualizarUsuario: (id: string, cuerpo: CuerpoActualizarUsuario) =>
    peticion<UsuarioAdmin>(`/usuarios/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarUsuario: (id: string) =>
    peticion<void>(`/usuarios/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

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
    peticion<RespuestaRuns>(`/agentes/${encodeURIComponent(id)}/runs`, {
      signal,
      validador: "RespuestaRuns",
    }),
  runAgente: (id: string, runId: string, signal?: AbortSignal): Promise<Run> =>
    peticion<Run>(`/agentes/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}`, {
      signal,
      validador: "Run",
    }),
  // Cancela un run de agente en vuelo (#152): el backend mata el árbol del subproceso
  // `claude` y devuelve el run en su estado terminal (error/motivo=cancelado). Idempotente;
  // un run aún pendiente se cancela sin spawnear. Espeja `cancelarGeneracion` (#137).
  cancelarRunAgente: (id: string, runId: string) =>
    peticion<RespuestaRun>(
      `/agentes/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/cancelar`,
      { metodo: "POST" },
    ),

  // --- Monitor (actividad IA: runs de todos los agentes + agregados) ---
  // `runs` admite paginacion offset-based (#121); sin params devuelve el conjunto
  // completo (retrocompat) y el backend igual incluye `paginacion`.
  runs: (params: { limite?: number; desplazamiento?: number } = {}, signal?: AbortSignal) =>
    peticion<RespuestaRuns>(
      `/runs${query({
        limite: params.limite != null ? String(params.limite) : undefined,
        desplazamiento:
          params.desplazamiento != null ? String(params.desplazamiento) : undefined,
      })}`,
      { signal, validador: "RespuestaRuns" },
    ),
  runsAgregados: (signal?: AbortSignal) =>
    peticion<RespuestaRunsAgregados>("/runs/agregados", {
      signal,
      validador: "RespuestaRunsAgregados",
    }),

  // --- Generaciones (sondeo de trabajos de IA en segundo plano) ---
  // Toda generación (copy/RSS/hashtags/imagen) responde de inmediato con `{generacion}`
  // (estado "ejecutando"); se sondea aquí hasta el estado terminal.
  generaciones: (signal?: AbortSignal) =>
    peticion<RespuestaGeneraciones>("/generaciones", { signal }),
  generacion: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaGeneracion>(`/generaciones/${encodeURIComponent(id)}`, { signal }),
  // Cancela un trabajo en vuelo (#137): el backend mata el árbol del subproceso `claude`
  // y devuelve el registro en su estado terminal (error/motivo=cancelado). Idempotente.
  cancelarGeneracion: (id: string) =>
    peticion<RespuestaGeneracion>(`/generaciones/${encodeURIComponent(id)}/cancelar`, {
      metodo: "POST",
    }),

  // --- Termómetro mundial ---
  termometro: (signal?: AbortSignal) => peticion<RespuestaTermometro>("/termometro", { signal }),
  guardarTermometro: (cuerpo: CuerpoGuardarTermometro) =>
    peticion<RespuestaConfigTermometro>("/termometro/config", { metodo: "PUT", json: cuerpo }),
  generarTermometro: (cuerpo: CuerpoGenerarTermometro) =>
    peticion<RespuestaGeneracion>("/termometro/generar", { metodo: "POST", json: cuerpo }),

  // --- Skills (Generar copy) ---
  skills: (signal?: AbortSignal) => peticion<RespuestaSkills>("/skills", { signal }),
  ejecutarSkill: (cuerpo: CuerpoEjecutarSkill) =>
    peticion<RespuestaGeneracion>("/skills/ejecutar", { metodo: "POST", json: cuerpo }),
  ejecutarSkillUrl: (cuerpo: CuerpoEjecutarSkillUrl) =>
    peticion<RespuestaGeneracion>("/skills/ejecutar-url", { metodo: "POST", json: cuerpo }),
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

  // --- Límites de caracteres por red (fuente única backend, #112) ---
  limites: (signal?: AbortSignal) => peticion<RespuestaLimites>("/limites", { signal }),

  // --- Publicaciones ---
  publicacionesOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesPublicaciones>("/publicaciones/opciones", { signal }),
  publicaciones: (filtros: FiltrosPublicaciones = {}, signal?: AbortSignal) =>
    peticion<RespuestaPublicaciones>(`/publicaciones${query(filtros)}`, {
      signal,
      validador: "RespuestaPublicaciones",
    }),
  publicacion: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPublicacion>(`/publicaciones/${encodeURIComponent(id)}`, {
      signal,
      validador: "RespuestaPublicacion",
      muestrear: false,
    }),
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

  // --- Aprobación de PUBLICACIONES (#9): cola de revisión + decisión + programación ---
  // CONSOLIDACIÓN: la aprobación es ahora la MISMA cadena multinivel del tablero (una
  // publicación ES una fila `contenido_plataforma`). Estos endpoints se conservan y por
  // dentro FORWARDEAN a la cadena: `enviarARevision` crea una cadena SIMPLE (1 nivel) y deja
  // la pieza en revisión; `aprobar`/`rechazar` deciden el nivel actual de esa cadena.
  // Programar NO es aprobación (es programación) y NO publica de verdad: gated por #5/#8.
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
  /** Rechaza el nivel actual de la cadena de una publicación (vuelve a borrador). */
  rechazarPublicacion: (id: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
    }),
  programarPublicacion: (id: string, fecha: string) =>
    peticion<RespuestaPublicacion>(`/aprobacion/${encodeURIComponent(id)}/programar`, {
      metodo: "POST",
      json: { fecha },
    }),

  // --- Panel ligero (#9): dashboard de un vistazo (métricas + cola + próximas) ---
  panel: (params: { rango?: string; marca?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaPanel>(`/panel${query(params)}`, { signal }),

  // --- Reciclaje proactivo (sugerencias de archivo a retomar, #110) ---
  sugerenciasReciclaje: (filtros: FiltrosReciclaje = {}, signal?: AbortSignal) =>
    peticion<RespuestaSugerenciasReciclaje>(`/reciclaje/sugerencias${query(filtros)}`, { signal }),

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

  // --- QA editorial (revisar el copy ya escrito por el community, ficha F3 / #143) ---
  // Lanza la revisión en segundo plano; se sondea como cualquier generación
  // (GET /api/generaciones/{id}) y completa con `resultado.informe`. NO publica ni reescribe.
  qaEditorialOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesQaEditorial>("/qa-editorial", { signal }),
  revisarQaEditorial: (cuerpo: CuerpoRevisarQaEditorial) =>
    peticion<RespuestaGeneracion>("/qa-editorial/revisar", { metodo: "POST", json: cuerpo }),

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

  // --- Plantillas: catálogo unificado (planas + de estructura) ---
  plantillasContenido: (
    filtros?: { marca?: string; tipo?: string; soloActivas?: boolean },
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaPlantillasContenido>(
      `/plantillas-contenido${query({
        marca: filtros?.marca || undefined,
        tipo: filtros?.tipo || undefined,
        solo_activas: filtros?.soloActivas ? "1" : undefined,
      })}`,
      { signal },
    ),
  crearPlantillaContenido: (cuerpo: CuerpoCrearPlantillaContenido) =>
    peticion<RespuestaPlantillaContenido>("/plantillas-contenido", {
      metodo: "POST",
      json: cuerpo,
    }),
  actualizarPlantillaContenido: (id: string, cuerpo: CuerpoActualizarPlantillaContenido) =>
    peticion<RespuestaPlantillaContenido>(`/plantillas-contenido/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarPlantillaContenido: (id: string) =>
    peticion<RespuestaMensaje>(`/plantillas-contenido/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
  aplicarPlantillaContenido: (id: string, cuerpo: CuerpoAplicarPlantilla) =>
    peticion<RespuestaAplicarPlantilla>(
      `/plantillas-contenido/${encodeURIComponent(id)}/aplicar`,
      { metodo: "POST", json: cuerpo },
    ),

  // --- Biblioteca de medios interna (activos reutilizables; no publica a redes) ---
  bibliotecaMedia: (
    filtros?: { marca?: string; tipo?: string; soloAprobados?: boolean },
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaMediosBiblioteca>(
      `/biblioteca-media${query({
        marca: filtros?.marca || undefined,
        tipo: filtros?.tipo || undefined,
        solo_aprobados: filtros?.soloAprobados ? "1" : undefined,
      })}`,
      { signal },
    ),
  subirMedioBiblioteca: (
    archivo: File,
    meta: {
      titulo?: string;
      descripcion?: string;
      marca?: string;
      tipo?: string;
      etiquetas?: string[];
      credito?: string;
    },
  ) => {
    const form = new FormData();
    form.set("archivo", archivo);
    if (meta.titulo) form.set("titulo", meta.titulo);
    if (meta.descripcion) form.set("descripcion", meta.descripcion);
    if (meta.marca) form.set("marca", meta.marca);
    if (meta.tipo) form.set("tipo", meta.tipo);
    if (meta.credito) form.set("credito", meta.credito);
    if (meta.etiquetas) form.set("etiquetas", JSON.stringify(meta.etiquetas));
    return peticion<RespuestaMedioBiblioteca>("/biblioteca-media", { metodo: "POST", form });
  },
  actualizarMedioBiblioteca: (id: string, cuerpo: CuerpoActualizarMedioBiblioteca) =>
    peticion<RespuestaMedioBiblioteca>(`/biblioteca-media/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarMedioBiblioteca: (id: string) =>
    peticion<RespuestaMensaje>(`/biblioteca-media/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),

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

  // --- Radar de tendencias (lo más viral del momento, multi-red · #147) ---
  // Solo lectura: consolida tendencias por tema con su estado HONESTO por fuente.
  radar: (geo?: string, feeds?: boolean, signal?: AbortSignal) =>
    peticion<RespuestaRadar>(
      `/radar${query({ geo, feeds: feeds === false ? "0" : undefined })}`,
      { signal },
    ),

  // --- Parrilla del día (clasifica 13 posteos + 6 editoriales y los jerarquiza) ---
  // Solo lectura: deriva del Radar. PROPONE el orden; publicar lo decide el humano.
  parrillaDia: (geo?: string, signal?: AbortSignal) =>
    peticion<RespuestaParrilla>(`/parrilla-dia${query({ geo })}`, { signal }),

  // --- Programar/previsualizar una pieza en Metricool (respeta KENI_PUBLICAR_REAL) ---
  // Con el gate OFF (default) es DRY-RUN: previsualiza el cuerpo, NO publica nada.
  programarEnMetricool: (publicacionId: string) =>
    peticion<RespuestaProgramarMetricool>(
      `/publicaciones/${encodeURIComponent(publicacionId)}/metricool`,
      { metodo: "POST" },
    ),

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

  // --- Tablero de contenido unificado (herramienta de community manager) ---
  contenido: (
    params: {
      flujo?: string;
      marca?: string;
      responsable_id?: string;
      estado?: string;
      clase?: string;
      etiqueta?: string;
      desde?: string;
      hasta?: string;
    } = {},
    signal?: AbortSignal,
  ) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const cola = qs.toString();
    return peticion<RespuestaContenido>(`/contenido${cola ? `?${cola}` : ""}`, { signal });
  },
  crearContenido: (cuerpo: CuerpoCrearContenido) =>
    peticion<RespuestaContenidoItem>("/contenido", { metodo: "POST", json: cuerpo }),
  actualizarContenido: (id: string, cuerpo: CuerpoActualizarContenido) =>
    peticion<RespuestaContenidoItem>(`/contenido/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarContenido: (id: string) =>
    peticion<RespuestaMensaje>(`/contenido/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  agregarPlataforma: (contenidoId: string, red: string) =>
    peticion<RespuestaPlataforma>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas`,
      { metodo: "POST", json: { red } },
    ),
  actualizarPlataforma: (
    contenidoId: string,
    plataformaId: string,
    cuerpo: CuerpoActualizarPlataforma,
  ) =>
    peticion<RespuestaPlataforma>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas/${encodeURIComponent(plataformaId)}`,
      { metodo: "PATCH", json: cuerpo },
    ),
  eliminarPlataforma: (contenidoId: string, plataformaId: string) =>
    peticion<RespuestaMensaje>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas/${encodeURIComponent(plataformaId)}`,
      { metodo: "DELETE" },
    ),
  contenidoDesdeRadar: (cuerpo: CuerpoDesdeRadar) =>
    peticion<RespuestaContenidoItem>("/contenido/desde-radar", { metodo: "POST", json: cuerpo }),
  asignarEtiquetaContenido: (contenidoId: string, etiqueta_id: string) =>
    peticion<RespuestaEtiquetasContenido>(
      `/contenido/${encodeURIComponent(contenidoId)}/etiquetas`,
      { metodo: "POST", json: { etiqueta_id } },
    ),
  quitarEtiquetaContenido: (contenidoId: string, etiquetaId: string) =>
    peticion<RespuestaEtiquetasContenido>(
      `/contenido/${encodeURIComponent(contenidoId)}/etiquetas/${encodeURIComponent(etiquetaId)}`,
      { metodo: "DELETE" },
    ),

  // --- Catálogo de etiquetas editoriales (campaña / vertical / tipo) ---
  etiquetas: (
    params: { marca?: string; clase?: string; activas?: boolean } = {},
    signal?: AbortSignal,
  ) => {
    const qs = new URLSearchParams();
    if (params.marca !== undefined) qs.set("marca", params.marca);
    if (params.clase) qs.set("clase", params.clase);
    if (params.activas) qs.set("activas", "1");
    const cola = qs.toString();
    return peticion<RespuestaEtiquetas>(`/etiquetas${cola ? `?${cola}` : ""}`, { signal });
  },
  crearEtiqueta: (cuerpo: CuerpoCrearEtiqueta) =>
    peticion<RespuestaEtiqueta>("/etiquetas", { metodo: "POST", json: cuerpo }),
  actualizarEtiqueta: (id: string, cuerpo: CuerpoActualizarEtiqueta) =>
    peticion<RespuestaEtiqueta>(`/etiquetas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarEtiqueta: (id: string) =>
    peticion<RespuestaMensaje>(`/etiquetas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Webhooks salientes + eventos internos del tablero ---
  webhooks: (signal?: AbortSignal) =>
    peticion<RespuestaWebhooks>("/webhooks", { signal }),
  crearWebhook: (cuerpo: CuerpoCrearWebhook) =>
    peticion<RespuestaWebhook>("/webhooks", { metodo: "POST", json: cuerpo }),
  actualizarWebhook: (id: string, cuerpo: CuerpoActualizarWebhook) =>
    peticion<RespuestaWebhook>(`/webhooks/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarWebhook: (id: string) =>
    peticion<RespuestaMensaje>(`/webhooks/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  probarWebhook: (id: string) =>
    peticion<RespuestaProbarWebhook>(`/webhooks/${encodeURIComponent(id)}/probar`, {
      metodo: "POST",
    }),
  /** Rendimiento real (Metricool) por pieza publicada del tablero. Mapa por `contenido_plataforma.id`. */
  metricasContenido: (signal?: AbortSignal) =>
    peticion<RespuestaMetricasContenido>("/contenido/metricas", { signal }),
  /** Previsualiza un copy con sus variables `{...}` ya sustituidas (no persiste). */
  previewContenido: (contenidoId: string, texto: string, signal?: AbortSignal) =>
    peticion<RespuestaPreviewContenido>(
      `/contenido/${encodeURIComponent(contenidoId)}/preview`,
      { metodo: "POST", json: { texto }, signal },
    ),
  /** Lanza el asistente IA sobre un contenido (genera/resume/3 variantes). */
  asistenteContenido: (contenidoId: string, cuerpo: CuerpoAsistenteContenido) =>
    peticion<RespuestaGeneracion>(
      `/contenido/${encodeURIComponent(contenidoId)}/asistente`,
      { metodo: "POST", json: cuerpo },
    ),

  // --- Ola COLABORACIÓN: comentarios + versiones de copy + aprobación multinivel ---
  comentarios: (contenidoId: string, plataformaId?: string, signal?: AbortSignal) => {
    const qs = plataformaId !== undefined ? `?plataforma_id=${encodeURIComponent(plataformaId)}` : "";
    return peticion<RespuestaComentarios>(
      `/contenido/${encodeURIComponent(contenidoId)}/comentarios${qs}`,
      { signal },
    );
  },
  crearComentario: (contenidoId: string, texto: string, plataformaId?: string) =>
    peticion<RespuestaComentario>(`/contenido/${encodeURIComponent(contenidoId)}/comentarios`, {
      metodo: "POST",
      json: { texto, plataforma_id: plataformaId ?? "" },
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

  // --- Rota de horarios del equipo (F4 · #144) ---
  rotaEquipo: (signal?: AbortSignal) =>
    peticion<RespuestaEquipoRota>("/rota/equipo", { signal }),
  /**
   * Equipo COMPLETO (incluye quienes no cubren, p. ej. coordinadores con
   * `cobertura=false`). Necesario para resolver candidatos a coordinador (ola "coord")
   * que pueden no estar en el equipo de rota habitual.
   */
  rotaEquipoTodos: (signal?: AbortSignal) =>
    peticion<RespuestaEquipoRota>("/rota/equipo?todos=1", { signal }),
  rotaEventos: (
    params: {
      desde?: string;
      hasta?: string;
      cambiados?: string;
      tipo_cobertura?: string | string[];
      prioridad?: string | string[];
      cambiado?: boolean | null;
      q?: string;
    } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaEventosRota>(`/rota/eventos${queryEventos(params)}`, { signal }),
  crearEventoRota: (cuerpo: CuerpoCrearEventoRota) =>
    peticion<RespuestaEventoRota>("/rota/eventos", { metodo: "POST", json: cuerpo }),
  actualizarEventoRota: (id: string, cuerpo: CuerpoActualizarEventoRota) =>
    peticion<RespuestaEventoRota>(`/rota/eventos/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarEventoRota: (id: string) =>
    peticion<RespuestaMensaje>(`/rota/eventos/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  duplicarEventoRota: (id: string, cuerpo: CuerpoDuplicarEventoRota = {}) =>
    peticion<RespuestaEventoRota>(`/rota/eventos/${encodeURIComponent(id)}/duplicar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  // --- Turnos (modelo nuevo: persona × día × franja, ola back3) ---
  // CRUD primario sobre los turnos. La cobertura de eventos es derivada (ver más
  // abajo). `listarTurnos` admite `?lunes=` para acotar a una semana (recomendado).
  listarTurnos: (params: { lunes?: string } = {}, signal?: AbortSignal) =>
    peticion<RotaSemana>(`/rota/turnos${query(params)}`, { signal }),
  crearTurno: (cuerpo: CuerpoCrearTurnoRota) =>
    peticion<RespuestaTurnoRota>("/rota/turnos", { metodo: "POST", json: cuerpo }),
  actualizarTurno: (id: string, cuerpo: CuerpoActualizarTurnoRota) =>
    peticion<RespuestaTurnoRota>(`/rota/turnos/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  borrarTurno: (id: string) =>
    peticion<RespuestaMensaje>(`/rota/turnos/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  crearTurnosLote: (cuerpo: CuerpoCrearTurnosLote) =>
    peticion<RespuestaCrearTurnosLote>("/rota/turnos/lote", {
      metodo: "POST",
      json: cuerpo,
    }),
  actualizarTurnosLote: (cuerpo: CuerpoActualizarLoteTurnos) =>
    peticion<RespuestaActualizarLoteTurnos>("/rota/turnos/lote", {
      metodo: "PATCH",
      json: cuerpo,
    }),
  borrarTurnosLote: (cuerpo: CuerpoBorrarLoteIds) =>
    peticion<RespuestaBorrarLote>("/rota/turnos/lote/borrar", {
      metodo: "POST",
      json: cuerpo,
    }),
  duplicarTurno: (id: string, cuerpo: CuerpoDuplicarTurnoRota = {}) =>
    peticion<RespuestaTurnoRota>(`/rota/turnos/${encodeURIComponent(id)}/duplicar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  aprobarTurnos: (cuerpo: CuerpoAprobarRota) =>
    peticion<RotaSemana>("/rota/turnos/aprobar", { metodo: "POST", json: cuerpo }),
  /** Revierte la semana publicada a borrador (solo admin). */
  despublicarTurnos: (cuerpo: CuerpoAprobarRota) =>
    peticion<RotaSemana>("/rota/turnos/despublicar", { metodo: "POST", json: cuerpo }),
  misTurnos: (params: { lunes?: string } = {}, signal?: AbortSignal) =>
    peticion<MisTurnosRota>(`/rota/mis-turnos${query(params)}`, { signal }),
  exportarRota: (formato: "xlsx" | "csv", params: { lunes?: string } = {}) =>
    descargar(`/rota/export.${formato}${query(params)}`),

  // --- Cobertura DERIVADA (no persistida): eventos × turnos ---
  cobertura: (params: { lunes: string }, signal?: AbortSignal) =>
    peticion<RespuestaCoberturaSemana>(`/rota/cobertura${query(params)}`, { signal }),
  coberturaEvento: (eventoId: string, signal?: AbortSignal) =>
    peticion<RespuestaCoberturaEvento>(
      `/rota/cobertura/evento/${encodeURIComponent(eventoId)}`,
      { signal },
    ),

  // --- Coordinador por turno (ola "coord") ---
  // Una celda (fecha, franja_id) puede tener UN coordinador entre los usuarios con
  // `puede_coordinar=true`. La coordinación es independiente del turno de CM.
  listarCoordinacionSemana: (lunes: string, signal?: AbortSignal) =>
    peticion<RespuestaCoordinacionSemana>(
      `/rota/semana/${encodeURIComponent(lunes)}/coordinacion`,
      { signal },
    ),
  setCoordinador: (cuerpo: CuerpoSetCoordinador) =>
    peticion<CoordinacionTurno>("/rota/coordinacion", { metodo: "PUT", json: cuerpo }),
  quitarCoordinador: (cuerpo: CuerpoQuitarCoordinador) =>
    peticion<{ ok: true; borrado: boolean }>("/rota/coordinacion", {
      metodo: "DELETE",
      json: cuerpo,
    }),

  // --- Gestión de turnos: ausencias / vacaciones (F4 · #144, ola A) ---
  rotaAusencias: (params: { miembro_id?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaAusenciasRota>(`/rota/ausencias${query(params)}`, { signal }),
  crearAusenciaRota: (cuerpo: CuerpoCrearAusenciaRota) =>
    peticion<RespuestaAusenciaRota>("/rota/ausencias", { metodo: "POST", json: cuerpo }),
  actualizarAusenciaRota: (id: string, cuerpo: CuerpoActualizarAusenciaRota) =>
    peticion<RespuestaAusenciaRota>(`/rota/ausencias/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarAusenciaRota: (id: string) =>
    peticion<RespuestaMensaje>(`/rota/ausencias/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Piezas de la parrilla (#150 PARRILLA 2026.xlsx) ---
  // Una pieza = un POST individual. Puede ir atada a un evento (`evento_id`) o ser
  // suelta (campaña evergreen). Filtros combinables: `evento_id=""` lista las sueltas.
  listarPiezasRota: (filtros: FiltrosPiezasRota = {}, signal?: AbortSignal) => {
    // Pasamos evento_id="" tal cual (para listar piezas sueltas) sin que `query`
    // lo descarte: `query` omite "" y undefined, así que añadimos el parametro a mano.
    const otros: Record<string, string | undefined> = {
      desde: filtros.desde,
      hasta: filtros.hasta,
      red: filtros.red,
      tipo: filtros.tipo,
      estado: filtros.estado,
      responsable_id: filtros.responsable_id,
      programa: filtros.programa,
    };
    let qs = query(otros);
    if (filtros.evento_id !== undefined) {
      const sep = qs ? "&" : "?";
      qs = `${qs}${sep}evento_id=${encodeURIComponent(filtros.evento_id)}`;
    }
    return peticion<RespuestaPiezasRota>(`/rota/piezas${qs}`, { signal });
  },
  crearPiezaRota: (cuerpo: CuerpoCrearPiezaRota) =>
    peticion<RespuestaPiezaRota>("/rota/piezas", { metodo: "POST", json: cuerpo }),
  actualizarPiezaRota: (id: string, cuerpo: CuerpoActualizarPiezaRota) =>
    peticion<RespuestaPiezaRota>(`/rota/piezas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarPiezaRota: (id: string) =>
    peticion<RespuestaMensaje>(`/rota/piezas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  duplicarPiezaRota: (id: string, cuerpo: CuerpoDuplicarPiezaRota = {}) =>
    peticion<RespuestaPiezaRota>(`/rota/piezas/${encodeURIComponent(id)}/duplicar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  borrarPiezasLote: (cuerpo: CuerpoBorrarLoteIds) =>
    peticion<RespuestaBorrarLote>("/rota/piezas/lote/borrar", {
      metodo: "POST",
      json: cuerpo,
    }),

  // --- Catálogo de programas (#150 PARRILLA 2026.xlsx) ---
  // Las piezas referencian programas por NOMBRE; renombrar hace cascada
  // transaccional sobre rota_piezas.programa. Borrar con piezas en uso requiere
  // ?forzar=true (el 409 incluye `piezas_afectadas` y `en_uso:true`).
  listarProgramasRota: (
    params: { activo?: boolean } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaProgramasRota>(
      `/rota/programas${query({ activo: params.activo === undefined ? undefined : String(params.activo) })}`,
      { signal },
    ),
  crearProgramaRota: (cuerpo: CuerpoCrearProgramaRota) =>
    peticion<RespuestaProgramaRota>("/rota/programas", { metodo: "POST", json: cuerpo }),
  actualizarProgramaRota: (id: string, cuerpo: CuerpoActualizarProgramaRota) =>
    peticion<RespuestaProgramaRota>(`/rota/programas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarProgramaRota: (id: string, params: { forzar?: boolean } = {}) =>
    peticion<RespuestaMensaje & { piezas_afectadas?: number }>(
      `/rota/programas/${encodeURIComponent(id)}${query({ forzar: params.forzar ? "true" : undefined })}`,
      { metodo: "DELETE" },
    ),

  // --- Copia de semana + panel de carga ---
  copiarSemana: (cuerpo: CuerpoCopiarSemana) =>
    peticion<RespuestaCopiarSemana>("/rota/copiar-semana", { metodo: "POST", json: cuerpo }),
  cargaRota: (params: { lunes: string }, signal?: AbortSignal) =>
    peticion<RespuestaCargaRota>(`/rota/carga${query(params)}`, { signal }),

  // --- Configuración editorial de franjas (#185) ---
  obtenerConfigFranjas: (signal?: AbortSignal) =>
    peticion<RespuestaConfigFranjas>("/rota/config/franjas", { signal }),
  guardarConfigFranjas: (cuerpo: CuerpoGuardarConfigFranjas) =>
    peticion<RespuestaConfigFranjas>("/rota/config/franjas", {
      metodo: "PATCH",
      json: cuerpo,
    }),

  // --- Franjas POR SEMANA (modelo "Mundial") ---
  // CRUD de `rota_franjas` (N franjas por semana, solapes permitidos, soporte cruce de
  // medianoche, franja Descanso explicita con `es_descanso=true`). GET siembra defaults
  // (Mañana/Tarde/Descanso) si la semana esta vacia. POST/PATCH/DELETE exigen admin.
  listarFranjasSemana: (lunes: string, signal?: AbortSignal) =>
    peticion<RespuestaFranjasSemana>(
      `/rota/semana/${encodeURIComponent(lunes)}/franjas`,
      { signal },
    ),
  crearFranjaSemana: (lunes: string, cuerpo: CuerpoCrearFranjaSemana) =>
    peticion<FranjaSemana>(
      `/rota/semana/${encodeURIComponent(lunes)}/franjas`,
      { metodo: "POST", json: cuerpo },
    ),
  actualizarFranjaSemana: (id: string, cuerpo: CuerpoActualizarFranjaSemana) =>
    peticion<FranjaSemana>(`/rota/franjas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  borrarFranjaSemana: (id: string, opts: { forzar?: boolean } = {}) =>
    peticion<{ ok: true; turnos_borrados?: number }>(
      `/rota/franjas/${encodeURIComponent(id)}${opts.forzar ? "?forzar=true" : ""}`,
      { metodo: "DELETE" },
    ),

  // --- Solicitudes de cambio de turno entre compañeros (#175) ---
  // Flujo: A crea -> B acepta/rechaza -> admin aprueba (ejecuta el swap sobre
  // rota_turnos_trabajo) o rechaza. A puede cancelar mientras no sea terminal.
  // El cliente solo informa; las validaciones de permisos y transiciones las
  // hace el backend (errores 400/403/404/409 con mensaje en español).
  listarSwaps: (filtros: FiltrosSwaps = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwaps>(
      `/rota/swaps${query({
        estado: filtros.estado,
        solicitante_id: filtros.solicitante_id,
        destinatario_id: filtros.destinatario_id,
        mio: filtros.mio ? "true" : undefined,
      })}`,
      { signal },
    ),
  crearSwap: (cuerpo: CuerpoCrearSwap, signal?: AbortSignal) =>
    peticion<RespuestaSwap>("/rota/swaps", { metodo: "POST", json: cuerpo, signal }),
  aceptarSwap: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/aceptar`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  rechazarSwap: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  aprobarSwap: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/aprobar`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  rechazarSwapAdmin: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/rechazar-admin`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  cancelarSwap: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/cancelar`, {
      metodo: "POST",
      signal,
    }),

  // --- Metricas ---
  metricasOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesMetricas>("/metricas/opciones", { signal }),
  metricasReporte: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<ReporteMetricas>(`/metricas/reporte${query(params)}`, { signal }),
  metricasComparar: (
    params: { rango_a?: string; rango_b?: string; marca?: string },
    signal?: AbortSignal,
  ) => peticion<CompararMetricas>(`/metricas/comparar${query(params)}`, { signal }),
  metricasAnalisis: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<AnalisisDiario>(`/metricas/analisis${query(params)}`, { signal }),
  // Analítica de piezas: estadísticas + top 5 + peores 5 + distribución del periodo.
  metricasPiezas: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<AnaliticaPiezas>(`/metricas/piezas${query(params)}`, { signal }),
  // Serie diaria del periodo (visualizaciones + interacciones) para la tendencia.
  metricasTendencia: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<TendenciaDiaria>(`/metricas/tendencia${query(params)}`, { signal }),
  // Estado del refresco + "última actualización" del combo (para el botón Actualizar y el polling).
  metricasEstado: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<EstadoMetricas>(`/metricas/estado${query(params)}`, { signal }),
  // Dispara un refresco en 2º plano (prioriza el combo visto). Idempotente: si ya corre, no arranca otro.
  metricasRefrescar: (params: { rango?: string; marca?: string }) =>
    peticion<EstadoMetricas>(`/metricas/refrescar${query(params)}`, { metodo: "POST" }),
  exportarMetricas: (formato: "csv" | "md" | "json", params: { rango?: string; marca?: string }) =>
    descargar(`/metricas/export.${formato}${query(params)}`),

  // --- Reporte de deportes (deck semanal de Claro Sports) ---
  reporteDeportesOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesReporteDeportes>("/reporte-deportes/opciones", { signal }),
  reporteDeportesPreview: (cuerpo: CuerpoReporteDeportes, signal?: AbortSignal) =>
    peticion<ReporteDeportes>("/reporte-deportes/preview", { metodo: "POST", json: cuerpo, signal }),
  descargarReporteDeportes: (cuerpo: CuerpoReporteDeportes) =>
    descargarPost("/reporte-deportes/export.pptx", cuerpo, `reporte-deportes-${cuerpo.rango}.pptx`),
  descargarReporteDeportesPdf: (cuerpo: CuerpoReporteDeportes) =>
    descargarPost("/reporte-deportes/export.pdf", cuerpo, `reporte-deportes-${cuerpo.rango}.pdf`),

  // --- Conexiones (imagen IA + tokens de redes) ---
  // Los secretos son write-only: solo se envían (PUT); del servidor llega
  // únicamente el estado y, para la imagen, una pista no sensible.
  conexionImagen: (signal?: AbortSignal) =>
    peticion<RespuestaConexionImagen>("/conexiones/imagen", { signal }),
  guardarConexionImagen: (cuerpo: CuerpoGuardarConexionImagen) =>
    peticion<RespuestaGuardarConexionImagen>("/conexiones/imagen", { metodo: "PUT", json: cuerpo }),
  guardarModeloImagen: (cuerpo: CuerpoGuardarModeloImagen) =>
    peticion<RespuestaGuardarModeloImagen>("/conexiones/imagen/modelo", {
      metodo: "PUT",
      json: cuerpo,
    }),
  probarConexionImagen: () =>
    peticion<RespuestaProbarConexionImagen>("/conexiones/imagen/probar", { metodo: "POST" }),
  eliminarConexionImagen: () =>
    peticion<RespuestaMensaje>("/conexiones/imagen", { metodo: "DELETE" }),

  // Metricool por marca: cada marca es una cuenta Metricool con su propio token.
  // El user_token es write-only: solo se envía (PUT); del servidor llega el estado.
  conexionesMetricool: (signal?: AbortSignal) =>
    peticion<RespuestaMetricool>("/conexiones/metricool", { signal }),
  // Descubre las marcas (blogId) de un token. NO persiste nada y el token nunca vuelve.
  descubrirPerfilesMetricool: (cuerpo: CuerpoPerfilesMetricool) =>
    peticion<RespuestaPerfilesMetricool>("/conexiones/metricool/perfiles", {
      metodo: "POST",
      json: cuerpo,
    }),
  guardarMetricool: (marca: string, cuerpo: CuerpoGuardarMetricool) =>
    peticion<RespuestaGuardarMetricool>(`/conexiones/metricool/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarMetricool: (marca: string) =>
    peticion<RespuestaMensaje>(`/conexiones/metricool/${encodeURIComponent(marca)}`, {
      metodo: "DELETE",
    }),
  probarMetricool: (marca: string) =>
    peticion<RespuestaProbarMetricool>(
      `/conexiones/metricool/${encodeURIComponent(marca)}/probar`,
      { metodo: "POST" },
    ),

  // --- Buzón de sugerencias ---
  sugerencias: (signal?: AbortSignal) =>
    peticion<RespuestaSugerencias>("/sugerencias", { signal }),
  crearSugerencia: (cuerpo: CuerpoCrearSugerencia) =>
    peticion<RespuestaSugerencia>("/sugerencias", { metodo: "POST", json: cuerpo }),
  actualizarSugerencia: (id: string, cuerpo: CuerpoActualizarSugerencia) =>
    peticion<RespuestaSugerencia>(`/sugerencias/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarSugerencia: (id: string) =>
    peticion<RespuestaMensaje>(`/sugerencias/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Comercial (seguimiento de publicaciones comerciales) ---
  comercialOpciones: (signal?: AbortSignal) =>
    peticion<OpcionesComercial>("/comercial/opciones", { signal }),
  comerciales: (filtros: FiltrosComercial = {}, signal?: AbortSignal) =>
    peticion<RespuestaPublicacionesComercial>(`/comercial/publicaciones${query(filtros)}`, {
      signal,
      validador: "RespuestaPublicacionesComercial",
    }),
  comercial: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPublicacionComercial>(`/comercial/publicaciones/${encodeURIComponent(id)}`, {
      signal,
      validador: "RespuestaPublicacionComercial",
      muestrear: false,
    }),
  crearComercial: (cuerpo: CuerpoCrearComercial) =>
    peticion<RespuestaPublicacionComercial>("/comercial/publicaciones", {
      metodo: "POST",
      json: cuerpo,
    }),
  actualizarComercial: (id: string, cuerpo: CuerpoActualizarComercial) =>
    peticion<RespuestaPublicacionComercial>(`/comercial/publicaciones/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  eliminarComercial: (id: string) =>
    peticion<RespuestaMensaje>(`/comercial/publicaciones/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
  refrescarComercial: (id: string) =>
    peticion<RespuestaPublicacionComercial>(
      `/comercial/publicaciones/${encodeURIComponent(id)}/refrescar`,
      { metodo: "POST" },
    ),
  refrescarComerciales: () =>
    peticion<RespuestaRefrescarComercial>("/comercial/refrescar", { metodo: "POST" }),
  reporteComercial: (
    params: { publicacion?: string; campania?: string; cliente?: string },
    signal?: AbortSignal,
  ) => peticion<RespuestaReporteComercial>(`/comercial/reporte${query(params)}`, { signal }),
  descargarReporteComercial: (params: { publicacion?: string; campania?: string; cliente?: string }) =>
    descargar(`/comercial/reporte${query({ ...params, formato: "md" })}`),
};

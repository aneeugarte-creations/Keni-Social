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
  Generacion,
  RespuestaInsumos,
  RespuestaDiasInsumos,
  InsumoLote,
  InsumoItem,
  RespuestaPresets,
  RespuestaActivarPresets,
  RespuestaNoticias,
  ResumenCobertura,
  SaludCobertura,
  Historia,
  RespuestaHistorias,
} from "@/types";

import type {
  RespuestaBiblioteca,
  RespuestaDocumento,
  RespuestaPapelera,
  RespuestaEditoriales,
  ValidacionEditorial,
  RespuestaAreas,
  RespuestaMarcasBiblioteca,
  RespuestaPipelinesBiblioteca,
  PreviewPipeline,
  RespuestaHistorialBiblioteca,
  CuerpoCrearDocumento,
  CuerpoGuardarDocumento,
  CuerpoLanzarBiblioteca,
  AnalisisDiario,
  CompararMetricas,
  AnaliticaPiezas,
  EstadoMetricas,
  TendenciaDiaria,
  PiezasRendimiento,
  PiezasListado,
  HistoricoPieza,
  PiezasPorEtiqueta,
  SerieSeguidores,
  DesgloseInteracciones,
  Crosstab,
  CorrelacionSeguidores,
  CuerpoActualizarFuenteRss,
  CuerpoActualizarPublicacion,
  CuerpoActualizarTurnoRota,
  CuerpoActualizarEventoRota,
  CuerpoActualizarProgramaRota,
  CuerpoAprobarRota,
  CuerpoBorrarLoteIds,
  CuerpoCrearProgramaRota,
  CuerpoActualizarFranjaSemana,
  CuerpoCrearFranjaSemana,
  CuerpoCrearTurnoRota,
  CuerpoCrearTurnosLote,
  CuerpoDuplicarEventoRota,
  EventoRota,
  CuerpoDuplicarTurnoRota,
  CuerpoPerfilesMetricool,
  CuerpoGuardarMetricool,
  CuerpoCrearFranja,
  CuerpoCrearFuenteRss,
  CuerpoActualizarContenido,
  CuerpoActualizarEtiqueta,
  CuerpoActualizarPlataforma,
  CuerpoAportarMaterial,
  CuerpoAsistenteContenido,
  CuerpoCrearContenido,
  CuerpoCrearEtiqueta,
  CuerpoSugerirHora,
  RespuestaSugerirHora,
  CuerpoCrearEventoRota,
  CuerpoDuplicarPublicacion,
  CuerpoGenerarMedia,
  CuerpoGenerarTermometro,
  CuerpoGuardarHistorial,
  CuerpoGuardarTermometro,
  CuerpoGrupoHashtags,
  CuerpoGuardarConexionImagen,
  CuerpoGuardarModeloImagen,
  CuerpoGuardarConfig,
  CuerpoGuardarEsfuerzo,
  CuerpoRevisarQaEditorial,
  CuerpoSugerirHashtags,
  CuerpoVerificar,
  ErrorApi,
  FiltrosPublicaciones,
  OpcionesMetricas,
  OpcionesPublicaciones,
  OpcionesQaEditorial,
  RespuestaLimites,
  ReporteMetricas,
  RespuestaCatalogo,
  RespuestaPerfilesMetricool,
  RespuestaMetricool,
  RespuestaGuardarMetricool,
  RespuestaProbarMetricool,
  RespuestaConexionImagen,
  RespuestaConfig,
  RespuestaEsfuerzo,
  RespuestaEstado,
  RespuestaFranja,
  RespuestaFranjas,
  RespuestaCadencia,
  RespuestaCadencias,
  CuerpoGuardarCadencia,
  RespuestaFuenteRss,
  RespuestaFuentesRss,
  RespuestaFuentesHub,
  CuerpoAportarFuente,
  RespuestaAportarFuente,
  RespuestaGeneracion,
  RespuestaGeneraciones,
  RespuestaGrupoHashtags,
  RespuestaHashtags,
  RespuestaMedia,
  CuerpoImagenesGenerar,
  CuerpoImagenesEditar,
  CuerpoImagenesExpandir,
  CuerpoImagenesRetocar,
  CuerpoImagenesRevisar,
  CuerpoImagenesComponer,
  CuerpoGuardarArte,
  RespuestaArte,
  RespuestaArtes,
  RespuestaPlantillasMarca,
  RespuestaPlantillaMarca,
  PlantillaMarca,
  RespuestaMensaje,
  RespuestaProgramarMetricool,
  RespuestaProbarConexionImagen,
  RespuestaGuardarConexionImagen,
  RespuestaGuardarModeloImagen,
  RespuestaPublicacion,
  RespuestaPublicaciones,
  RespuestaColaAprobacion,
  RespuestaAlgoritmos,
  RespuestaRefrescarAlgoritmos,
  RespuestaSembrarAlgoritmos,
  RespuestaFuenteAlgoritmo,
  RespuestaABibliotecaAlgoritmo,
  RespuestaArchivarAlgoritmo,
  FiltrosAlgoritmos,
  CuerpoFuenteAlgoritmo,
  RespuestaSugerenciasAlgoritmo,
  RespuestaAplicarSugerencia,
  RespuestaDescartarSugerencia,
  EstadoSugerenciaEditorial,
  RespuestaImportPreview,
  RespuestaImportCalendario,
  RespuestaImportCalendarioPendiente,
  RespuestaAjustes,
  RespuestaAjusteGuardado,
  RespuestaAlertas,
  RespuestaReciclarPublicacion,
  RespuestaSugerenciasReciclaje,
  FiltrosReciclaje,
  RespuestaConfigTermometro,
  RespuestaTermometro,
  RespuestaSugerencia,
  RespuestaSugerencias,
  CadenaAprobacion,
  RespuestaComentario,
  RespuestaComentarios,
  RespuestaNotificaciones,
  RespuestaContadorNotificaciones,
  RespuestaMencionesCandidatos,
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
  RespuestaIdeasGreen,
  RespuestaIdeaGreen,
  CuerpoCrearIdeaGreen,
  CuerpoActualizarIdeaGreen,
  CuerpoProponerGreen,
  CuerpoGenerarIdeaGreen,
  MetricasLineas,
  RespuestaPreviewContenido,
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
  RespuestaBorrarLote,
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
  EstadoPropuestaParrilla,
  PropuestaParrilla,
  RespuestaImportarParrilla,
  RespuestaPropuestasParrilla,
  CuerpoActualizarSugerencia,
  CuerpoCrearSugerencia,
  CuerpoActualizarComercial,
  CuerpoCrearComercial,
  CuerpoActualizarUsuario,
  CuerpoCambiarPassword,
  CuerpoCrearUsuario,
  CuerpoLogin,
  RespuestaSesion,
  RespuestaLoginMfa,
  OpcionesCeremoniaWebauthn,
  RespuestaMfaRegistro,
  RespuestaMfaCredenciales,
  RespuestaUsuarios,
  RespuestaRecursos,
  RespuestaS3,
  RespuestaProbarS3,
  RespuestaS3Objetos,
  RespuestaBorrarS3,
  RespuestaBorrarLoteS3,
  UsuarioAdmin,
  FiltrosComercial,
  OpcionesComercial,
  RespuestaPostsComercial,
  RespuestaPublicacionComercial,
  RespuestaPublicacionesComercial,
  RespuestaRefrescarComercial,
  RespuestaReporteComercial,
  RespuestaActividad,
  ActividadAgregados,
  RespuestaPipelines,
  RespuestaPipelineDetalle,
  RespuestaBreaking,
  CuerpoPreparar,
  RespuestaPreparar,
} from "@/types";

import { type NombreContrato, validarContrato } from "./contrato";
import type { PlantillaSpec } from "./specPlantilla";
import type {
  ComposicionVideo,
  EstadoSubtitulos,
  PresetFormatoVideo,
  SegmentoSub,
  Subtitulo,
} from "./video";

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

/**
 * URL para servir un objeto del bucket S3 a través del back (admin). El endpoint S3 de
 * Garage es interno; los bytes se proxean por el back. `descargar` fuerza `attachment`
 * (descarga) en vez de `inline` (previsualización). La cookie de sesión viaja sola en
 * peticiones same-origin (`<img src>` / `window.open`), así que basta con la URL.
 */
export function urlS3Objeto(key: string, descargar = false): string {
  const params = new URLSearchParams({ key });
  if (descargar) params.set("descargar", "1");
  return `${BASE_API}/sistema/s3/objeto?${params.toString()}`;
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
 * Mensaje legible (en español) para CUALQUIER error capturado en la UI. Fuente única que
 * reemplaza las ~30 copias locales que vivían en páginas y componentes:
 *   - `ApiError` con `status === 0` → fallo de red/servidor caído (sin respuesta HTTP);
 *     el `.message` ya trae un texto de red, con fallback explícito de "sin conexión".
 *   - `ApiError`/`Error` → su `.message` (el backend ya manda texto legible en español).
 *   - cualquier otra cosa → fallback genérico.
 */
export function mensajeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return (
        error.message ||
        "No hay conexión con el servidor. Espera unos segundos y vuelve a intentarlo."
      );
    }
    return error.message;
  }
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
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

/**
 * Tope por defecto de una petición (ms): un back colgado no debe dejar la UI girando
 * para siempre. Al vencer, abortamos y caemos a la ruta de error de red (`ApiError` con
 * `status 0`). Los endpoints conocidos como lentos (subidas, render de imagen) pueden
 * subir el techo con `timeoutMs`.
 */
const TIMEOUT_PETICION_MS = 30_000;

interface OpcionesPeticion {
  metodo?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** Cuerpo JSON (se serializa). Mutuamente excluyente con `form`. */
  json?: unknown;
  /** Cuerpo multipart (FormData) para subir archivos. */
  form?: FormData;
  signal?: AbortSignal;
  /**
   * Tope de tiempo de ESTA petición en ms (def 30s). Súbelo para endpoints
   * conocidos como lentos (subidas/render). `0` desactiva el timeout.
   */
  timeoutMs?: number;
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
  const { metodo = "GET", json, form, signal, validador, muestrear, timeoutMs } = opciones;
  const headers: Record<string, string> = { ...cabecerasAuth() };
  let body: BodyInit | undefined;

  if (form) {
    // No fijamos Content-Type: el navegador pone el boundary del multipart.
    body = form;
  } else if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  }

  // Timeout propio (AbortController + setTimeout, soporte universal): un back colgado no
  // debe dejar un spinner infinito. Combinamos el `signal` del llamante con el del timeout;
  // distinguimos "lo abortó el llamante" (re-lanzamos AbortError, lo gestiona react-query)
  // de "venció el timeout" (lo tratamos como fallo de red con mensaje claro).
  const ms = timeoutMs ?? TIMEOUT_PETICION_MS;
  const controlador = new AbortController();
  let vencido = false;
  const temporizador =
    ms > 0
      ? setTimeout(() => {
          vencido = true;
          controlador.abort();
        }, ms)
      : undefined;
  if (signal) {
    if (signal.aborted) controlador.abort();
    else signal.addEventListener("abort", () => controlador.abort(), { once: true });
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_API}${ruta}`, { method: metodo, headers, body, signal: controlador.signal });
  } catch (e) {
    if (vencido) {
      throw new ApiError("La solicitud tardó demasiado. Vuelve a intentarlo.", 0);
    }
    // El llamante (react-query) canceló: propagamos el AbortError tal cual.
    if (signal?.aborted) throw e;
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("No se pudo contactar con la consola. ¿Está corriendo el servidor local?", 0);
  } finally {
    if (temporizador !== undefined) clearTimeout(temporizador);
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
  marca?: string;
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
  if (params.marca) sp.set("marca", params.marca);
  aniadir("tipo_cobertura", params.tipo_cobertura);
  aniadir("prioridad", params.prioridad);
  const s = sp.toString();
  return s ? `?${s}` : "";
}

/** Dispara la descarga de un archivo abriendo su URL (CSV/MD/JSON). */
function descargar(ruta: string): void {
  window.open(`${BASE_API}${ruta}`, "_blank", "noopener,noreferrer");
}

// Activo de marca (biblioteca del editor): logo, tipografía, arte, infografía, icono, paleta o
// fondo, con sus metadatos y líneas. Espejo de `api/marca_activos.py::_activo_a_dict`.
export interface ActivoMarca {
  id: string;
  marca: string;
  tipo: "logo" | "tipografia" | "arte" | "infografia" | "icono" | "paleta" | "fondo";
  nombre: string;
  objeto: string;
  metadatos: Record<string, unknown>;
  lineas: string[];
  aprobado: boolean;
  url: string;
  marca_nombre: string;
  autor_id: string;
  autor_nombre: string;
  creado: string;
  actualizado: string;
}

// Plantilla de diseño: un Documento de capas reutilizable por marca (categoría + líneas).
// Espejo de `api/plantillas_diseno.py::_plantilla_a_dict`. `documento` es unknown aquí para no
// acoplar el cliente API a los tipos del editor (el editor lo castea a Documento).
export interface PlantillaDiseno {
  id: string;
  marca: string;
  nombre: string;
  categoria: string;
  /** Tipo de plantilla: "foto" (post de imagen) o "miniatura" (portada de video). Def "foto". */
  tipo: "foto" | "miniatura";
  documento: unknown;
  miniatura: string;
  miniatura_url: string;
  lineas: string[];
  activo: boolean;
  marca_nombre: string;
  autor_id: string;
  autor_nombre: string;
  creado: string;
  actualizado: string;
}

// Bloque: grupo de capas reutilizable (almacén de capas). `capas` es una lista de capas del editor
// (unknown[] aquí para no acoplar el cliente API a los tipos del editor; el editor lo castea).
export interface Bloque {
  id: string;
  marca: string;
  nombre: string;
  capas: unknown[];
  lineas: string[];
  miniatura: string;
  miniatura_url: string;
  marca_nombre: string;
  autor_id: string;
  autor_nombre: string;
  creado: string;
  actualizado: string;
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
  // Con MFA activo (flag `KENI_CONSOLA_MFA` ON), el login puede devolver `{mfa_required:true}`
  // en vez de `{usuario}`: el llamante debe entonces correr la ceremonia de passkey
  // (`mfaLoginOpciones` -> `startAuthentication` -> `mfaVerify`) o un código de recuperación.
  login: (cuerpo: CuerpoLogin) =>
    peticion<RespuestaSesion | RespuestaLoginMfa>("/auth/login", { metodo: "POST", json: cuerpo }),
  logout: () => peticion<void>("/auth/logout", { metodo: "POST" }),
  me: (signal?: AbortSignal) => peticion<RespuestaSesion>("/auth/me", { signal }),
  cambiarPassword: (cuerpo: CuerpoCambiarPassword) =>
    peticion<void>("/auth/cambiar-password", { metodo: "POST", json: cuerpo }),

  // --- MFA (segundo factor PASSKEYS / WebAuthn; gateado por `KENI_CONSOLA_MFA`) ---
  // Ceremonia de LOGIN (usa la cookie pre-auth + challenge que el backend gestiona):
  //   1) `mfaLoginOpciones` -> opciones spec-JSON para `startAuthentication({optionsJSON})`.
  //   2) `mfaVerify({assertion})` con la credencial que devuelve el navegador, O
  //      `mfaVerify({codigo})` con un código de recuperación.
  mfaLoginOpciones: () =>
    peticion<OpcionesCeremoniaWebauthn>("/auth/mfa/login/opciones", { metodo: "POST" }),
  mfaVerify: (cuerpo: { assertion?: unknown; codigo?: string }) =>
    peticion<RespuestaSesion>("/auth/mfa/verify", { metodo: "POST", json: cuerpo }),
  // Enrolamiento (requiere sesión completa): opciones de registro, verificar, listar, borrar.
  mfaRegistroOpciones: () =>
    peticion<OpcionesCeremoniaWebauthn>("/auth/mfa/registro/opciones", { metodo: "POST" }),
  mfaRegistroVerificar: (credential: unknown, nombre: string) =>
    peticion<RespuestaMfaRegistro>("/auth/mfa/registro/verificar", {
      metodo: "POST",
      json: { credential, nombre },
    }),
  mfaCredenciales: (signal?: AbortSignal) =>
    peticion<RespuestaMfaCredenciales>("/auth/mfa/credenciales", { signal }),
  mfaBorrarCredencial: (id: string) =>
    peticion<void>(`/auth/mfa/credenciales/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  mfaDisable: (passwordActual: string) =>
    peticion<void>("/auth/mfa/disable", {
      metodo: "POST",
      json: { password_actual: passwordActual },
    }),

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

  // --- Sistema (panel de admin; 403 si no) ---
  sistemaRecursos: (signal?: AbortSignal) =>
    peticion<RespuestaRecursos>("/sistema/recursos", { signal }),
  sistemaS3: (signal?: AbortSignal) => peticion<RespuestaS3>("/sistema/s3", { signal }),
  probarS3: () => peticion<RespuestaProbarS3>("/sistema/s3/probar", { metodo: "POST" }),
  s3Objetos: (prefijo?: string, signal?: AbortSignal) =>
    peticion<RespuestaS3Objetos>(
      `/sistema/s3/objetos${query({ prefijo: prefijo || "" })}`,
      { signal },
    ),
  borrarObjetoS3: (key: string) =>
    peticion<RespuestaBorrarS3>("/sistema/s3/borrar", {
      metodo: "POST",
      json: { key },
    }),
  borrarObjetosS3: (keys: string[]) =>
    peticion<RespuestaBorrarLoteS3>("/sistema/s3/borrar-lote", {
      metodo: "POST",
      json: { keys },
    }),

  // --- Config ---
  config: (signal?: AbortSignal) => peticion<RespuestaConfig>("/config", { signal }),
  guardarConfig: (cuerpo: CuerpoGuardarConfig) =>
    peticion<RespuestaMensaje>("/config", { metodo: "POST", json: cuerpo }),
  esfuerzo: (signal?: AbortSignal) => peticion<RespuestaEsfuerzo>("/config/esfuerzo", { signal }),
  guardarEsfuerzo: (cuerpo: CuerpoGuardarEsfuerzo) =>
    peticion<RespuestaMensaje>("/config/esfuerzo", { metodo: "POST", json: cuerpo }),

  // --- Ajustes de funcionalidad (admin): toggles + tuning, aplican en caliente ---
  ajustes: (signal?: AbortSignal) => peticion<RespuestaAjustes>("/ajustes", { signal }),
  guardarAjuste: (cuerpo: { clave: string; valor?: boolean | number | string; reset?: boolean }) =>
    peticion<RespuestaAjusteGuardado>("/ajustes", { metodo: "POST", json: cuerpo }),

  // --- Actividad IA unificada (feed de generaciones + runs de agentes) ---
  // Solo lectura: el backend fusiona ambas fuentes en un único feed con métricas
  // (tokens/coste/duración) y expone sus agregados (totales + por tipo + por día).
  actividad: (
    params: { limite?: number; offset?: number; fuente?: string; tipo?: string } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaActividad>(
      `/actividad${query({
        limite: params.limite != null ? String(params.limite) : undefined,
        offset: params.offset != null ? String(params.offset) : undefined,
        fuente: params.fuente,
        tipo: params.tipo,
      })}`,
      { signal },
    ),
  actividadAgregados: (signal?: AbortSignal) =>
    peticion<ActividadAgregados>("/actividad/agregados", { signal }),

  // --- Pipelines (vista CI/CD del pipeline de contenido) ---
  pipelines: (params: { marca?: string; limite?: number } = {}, signal?: AbortSignal) =>
    peticion<RespuestaPipelines>(
      `/pipelines${query({
        marca: params.marca,
        limite: params.limite != null ? String(params.limite) : undefined,
      })}`,
      { signal },
    ),
  pipelineDetalle: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaPipelineDetalle>(`/pipelines/${encodeURIComponent(id)}`, { signal }),

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

  // --- Historial de generaciones (NEUTRO; común a copy/documento) ---
  // Guardar una entrada del historial como publicaciones (borradores). El listado/detalle
  // del historial ya no tiene página propia; este "guardar" lo usa ResultadoDocumento.
  guardarHistorial: (id: string, cuerpo: CuerpoGuardarHistorial = {}) =>
    peticion<RespuestaPublicaciones>(`/prompts/historial/${encodeURIComponent(id)}/guardar`, {
      metodo: "POST",
      json: cuerpo,
    }),

  // --- Biblioteca de documentos (prompts + línea editorial) ---
  biblioteca: (
    filtros?: {
      tipo?: string;
      carpeta?: string;
      q?: string;
      estado?: string;
      etiqueta?: string;
      marca?: string;
      clase?: string;
      pipeline?: string;
    },
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaBiblioteca>(
      `/biblioteca${query({
        tipo: filtros?.tipo,
        carpeta: filtros?.carpeta,
        q: filtros?.q,
        estado: filtros?.estado,
        etiqueta: filtros?.etiqueta,
        marca: filtros?.marca,
        clase: filtros?.clase,
        pipeline: filtros?.pipeline,
      })}`,
      { signal },
    ),
  crearDocumento: (cuerpo: CuerpoCrearDocumento) =>
    peticion<RespuestaDocumento>("/biblioteca", { metodo: "POST", json: cuerpo }),
  // El id es una ruta con barras (p. ej. `prompt/x/y`); el backend lo casa con `{doc_id:path}`,
  // así que NO se codifica (los segmentos son slugs seguros [a-z0-9-]).
  documento: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}`, { signal }),
  guardarDocumento: (id: string, cuerpo: CuerpoGuardarDocumento) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}`, { metodo: "PUT", json: cuerpo }),
  eliminarDocumento: (id: string) =>
    peticion<RespuestaMensaje>(`/biblioteca/${id}`, { metodo: "DELETE" }),
  papeleraBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaPapelera>("/biblioteca/papelera", { signal }),
  restaurarDocumento: (id: string) =>
    peticion<RespuestaDocumento>(`/biblioteca/papelera/${encodeURIComponent(id)}/restaurar`, {
      metodo: "POST",
    }),
  editorialesBiblioteca: (marca: string, pipeline?: string, signal?: AbortSignal) =>
    peticion<RespuestaEditoriales>(`/biblioteca/editoriales${query({ marca, pipeline })}`, { signal }),
  // --- Pipelines: registro + preview del prompt ensamblado (atribución) ---
  pipelinesBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaPipelinesBiblioteca>("/biblioteca/pipelines", { signal }),
  previewPipeline: (pipeline: string, marca: string, contexto?: string, signal?: AbortSignal) =>
    peticion<PreviewPipeline>(
      `/biblioteca/pipelines/${pipeline}/preview${query({ marca, contexto })}`,
      { signal },
    ),
  // --- Versionado git: historial, una versión y rollback no destructivo ---
  historialBiblioteca: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaHistorialBiblioteca>(`/biblioteca/${id}/historial`, { signal }),
  versionBiblioteca: (id: string, sha: string, signal?: AbortSignal) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}/version/${sha}`, { signal }),
  revertirBiblioteca: (id: string, sha: string) =>
    peticion<RespuestaDocumento>(`/biblioteca/${id}/revertir/${sha}`, { metodo: "POST" }),
  validacionBiblioteca: (marca: string, signal?: AbortSignal) =>
    peticion<ValidacionEditorial>(`/biblioteca/validacion${query({ marca })}`, { signal }),
  areasBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaAreas>("/biblioteca/areas", { signal }),
  marcasBiblioteca: (signal?: AbortSignal) =>
    peticion<RespuestaMarcasBiblioteca>("/biblioteca/marcas", { signal }),
  lanzarBiblioteca: (cuerpo: CuerpoLanzarBiblioteca) =>
    peticion<RespuestaGeneracion>("/biblioteca/lanzar", { metodo: "POST", json: cuerpo }),
  lanzarBibliotecaArchivo: (
    archivo: File,
    marca: string,
    opts: {
      prompt_id?: string;
      texto?: string;
      titulo?: string;
      adjuntos?: string[];
      redes?: string[];
    } = {},
  ) => {
    const form = new FormData();
    form.set("archivo", archivo);
    form.set("marca", marca);
    if (opts.prompt_id) form.set("prompt_id", opts.prompt_id);
    if (opts.texto) form.set("texto", opts.texto);
    if (opts.titulo) form.set("titulo", opts.titulo);
    for (const a of opts.adjuntos ?? []) form.append("adjuntos", a);
    for (const r of opts.redes ?? []) form.append("redes", r);
    return peticion<RespuestaGeneracion>("/biblioteca/lanzar-archivo", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },

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

  // --- Media (imágenes) ---
  // `categoria` (opcional) = carpeta de destino en el almacén: `fotos` (def) para una foto de
  // pieza, `plantillas` para un asset del editor de plantillas. Así el bucket queda dividido por
  // tipo y se puede limpiar `fotos/` a mano sin tocar plantillas/logos reusables.
  subirMedia: (archivo: File, categoria?: "fotos" | "plantillas") => {
    const form = new FormData();
    form.set("archivo", archivo);
    if (categoria) form.set("categoria", categoria);
    return peticion<RespuestaMedia>("/media", { metodo: "POST", form, timeoutMs: 120_000 });
  },
  generarMedia: (cuerpo: CuerpoGenerarMedia) =>
    peticion<RespuestaGeneracion>("/media/generar", { metodo: "POST", json: cuerpo }),
  /** Ola F: sube un archivo de video a `POST /api/media/video` y devuelve `{id, url}`. */
  subirVideo: (archivo: File) => {
    const form = new FormData();
    form.set("archivo", archivo);
    return peticion<RespuestaMedia>("/media/video", { metodo: "POST", form, timeoutMs: 300_000 });
  },
  /** Descarga una imagen externa (p.ej. la original de un artículo RSS) al almacén y
   *  devuelve su `{id, url}` ya servible/publicable. */
  mediaDesdeUrl: (url: string) =>
    peticion<RespuestaMedia>("/media/desde-url", { metodo: "POST", json: { url } }),

  // --- Biblioteca de artes (objetos de media catalogados para reutilizar) ---
  // Guardar un arte lo PROTEGE del GC de media huérfana y lo hace seleccionable por marca
  // desde el editor de imagen de una pieza. El `objeto` es UNIQUE: `guardarArte` es idempotente.
  listarArtes: (
    filtros: { marca?: string; tipo?: string; q?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaArtes>(`/artes${query(filtros)}`, { signal }),
  guardarArte: (cuerpo: CuerpoGuardarArte) =>
    peticion<RespuestaArte>("/artes", { metodo: "POST", json: cuerpo }),
  borrarArte: (id: string, purgar = false) =>
    peticion<RespuestaMensaje>(
      `/artes/${encodeURIComponent(id)}${purgar ? "?purgar=1" : ""}`,
      { metodo: "DELETE" },
    ),

  // --- Estudio de imagen (generar variantes · editar determinista · expandir generativo) ---
  // Cada endpoint responde de inmediato con registro(s) de generación (tipo "imagen") que se
  // SONDEAN con `useGeneracion` (GET /api/generaciones/{id}); al completar dan `resultado`
  // con `{id, url}`. `imagenesGenerar` devuelve UNA generación por variante.
  imagenesGenerar: (cuerpo: CuerpoImagenesGenerar) =>
    peticion<RespuestaGeneraciones>("/imagenes/generar", { metodo: "POST", json: cuerpo }),
  imagenesEditar: (cuerpo: CuerpoImagenesEditar) =>
    peticion<RespuestaGeneracion>("/imagenes/editar", { metodo: "POST", json: cuerpo }),
  imagenesExpandir: (cuerpo: CuerpoImagenesExpandir) =>
    peticion<RespuestaGeneracion>("/imagenes/expandir", { metodo: "POST", json: cuerpo }),
  // Retoque generativo por instrucción ("oscurece el cielo"): reinterpreta toda la imagen.
  // Distinto de expandir (outpainting fiel). Generativo (con coste); se SONDEA con
  // `useGeneracion` y completa con `resultado` `{id, url}`.
  imagenesRetocar: (cuerpo: CuerpoImagenesRetocar) =>
    peticion<RespuestaGeneracion>("/imagenes/retocar", { metodo: "POST", json: cuerpo }),
  // Revisión legal/editorial de una imagen (gate humano, no bloquea publicar): job
  // "qa-editorial" que se SONDEA con `useGeneracion`; el checklist ✅/⚠️/❌ llega en vivo
  // en `generacion.salida`.
  imagenesRevisar: (cuerpo: CuerpoImagenesRevisar) =>
    peticion<RespuestaGeneracion>("/imagenes/revisar", { metodo: "POST", json: cuerpo }),
  // Componer/estampar la plantilla de marca (logo/pleca/titular) sobre una imagen:
  // composición DETERMINISTA en el backend. Responde con una generación de imagen que
  // se SONDEA con `useGeneracion` y completa con `resultado` `{id, url}` (igual que editar).
  imagenesComponer: (cuerpo: CuerpoImagenesComponer) =>
    peticion<RespuestaGeneracion>("/imagenes/componer", { metodo: "POST", json: cuerpo }),

  // --- Editor profesional (Documento de capas) ---
  // Re-render server-side de un documento de capas a PNG (fidelidad exacta de fuentes/cover/
  // degradados). El `documento` se valida en el backend (`motores/estudio_imagen/documento.py`).
  // `bindings` (opcional): titular/pleca REAL de la pieza (`copy_in`/`etiqueta_default`) para que
  // las capas con `binding` rendericen el texto real en vez del de muestra. Sin pieza no se pasa.
  editorRender: (documento: unknown, bindings?: Record<string, string>) =>
    peticion<{ id: string; url: string }>("/editor/render", {
      metodo: "POST",
      json: { documento, bindings },
      timeoutMs: 120_000,
    }),
  // Documento de capas editable derivado de la plantilla de una marca (punto de partida del editor).
  editorPlantilla: (marca: string, formato: string, signal?: AbortSignal) =>
    peticion<{ documento: unknown }>(
      `/editor/plantilla/${encodeURIComponent(marca)}/${encodeURIComponent(formato)}`,
      { signal },
    ),
  // Editor anclado a una pieza (historial/versionado): cargar el documento guardado de la pieza
  // y guardar (render + nueva versión + fija la imagen de la publicación).
  editorPieza: (contenidoId: string, plataformaId: string, signal?: AbortSignal) =>
    peticion<{ documento: unknown; versiones: number; bindings: Record<string, string> }>(
      `/editor/pieza/${encodeURIComponent(contenidoId)}/${encodeURIComponent(plataformaId)}`,
      { signal },
    ),
  editorPiezaGuardar: (
    contenidoId: string,
    plataformaId: string,
    documento: unknown,
    bindings?: Record<string, string>,
  ) =>
    peticion<{ id: string; url: string; version: number }>(
      `/editor/pieza/${encodeURIComponent(contenidoId)}/${encodeURIComponent(plataformaId)}`,
      { metodo: "POST", json: { documento, bindings }, timeoutMs: 120_000 },
    ),

  // --- Estudio de video (composición + render FFmpeg + subtítulos ASR) ---
  // CONTRATO: docs/maquina-contenido/G-video-engine.md. El documento de composición se valida
  // en el backend (`keni_shared.video.validar_composicion`). El render y la transcripción se
  // ENCOLAN como jobs de proceso (no-claude) y se SONDEAN con `useGeneracion` (tipos
  // "render-video" / "transcribir"); al completar dan `resultado` `{media_id, url}`.
  video: {
    /** Presets de formato + zonas seguras por preset (`GET /api/video/formatos`). */
    formatos: (signal?: AbortSignal) =>
      peticion<{ formatos: PresetFormatoVideo[] }>("/video/formatos", { signal }),
    /** Crea la composición. `marca` es obligatoria (del catálogo). Devuelve `{id}`. */
    crearComposicion: (cuerpo: {
      marca: string;
      documento: ComposicionVideo;
      contenido_id?: string;
    }) => peticion<{ id: string }>("/video/composiciones", { metodo: "POST", json: cuerpo }),
    composicion: (id: string, signal?: AbortSignal) =>
      peticion<{ composicion: { id: string; documento: ComposicionVideo } }>(
        `/video/composiciones/${encodeURIComponent(id)}`,
        { signal },
      ),
    guardarComposicion: (id: string, documento: ComposicionVideo) =>
      peticion<{ composicion: { id: string; documento: ComposicionVideo } }>(
        `/video/composiciones/${encodeURIComponent(id)}`,
        { metodo: "PUT", json: { documento } },
      ),
    /** Encola el render FFmpeg. Devuelve `{gen_id}` (sondear con `api.generacion`). */
    render: (id: string) =>
      peticion<{ gen_id: string }>(`/video/composiciones/${encodeURIComponent(id)}/render`, {
        metodo: "POST",
      }),
    /**
     * Encola el ASR (word-level) del `media_id` dado. Crea la fila de subtítulos si no existe.
     * Devuelve `{gen_id, subtitulo_id}` (sondear con `api.generacion`).
     */
    transcribir: (id: string, mediaId: string, idioma = "es-MX") =>
      peticion<{ gen_id: string; subtitulo_id: string }>(
        `/video/composiciones/${encodeURIComponent(id)}/transcribir`,
        { metodo: "POST", json: { media_id: mediaId, idioma } },
      ),
    /** Fila de subtítulos de una composición (`null` si aún no hay). */
    subtitulosDe: (composicionId: string, signal?: AbortSignal) =>
      peticion<{ subtitulo: Subtitulo | null }>(
        `/video/subtitulos${query({ composicion_id: composicionId })}`,
        { signal },
      ),
    /** Guarda la corrección humana de los segmentos. `estado` opcional ("editado"/"listo"). */
    guardarSubtitulo: (
      id: string,
      cuerpo: { segmentos: SegmentoSub[]; estado?: EstadoSubtitulos },
    ) =>
      peticion<{ subtitulo: Subtitulo }>(`/video/subtitulos/${encodeURIComponent(id)}`, {
        metodo: "PUT",
        json: cuerpo,
      }),
  },

  // --- Biblioteca de activos por marca (logos, tipografías, artes, infografías, …) ---
  marcaActivos: (
    filtros: { marca?: string; tipo?: string; linea?: string; q?: string } = {},
    signal?: AbortSignal,
  ) => {
    const qp = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v) qp.set(k, v);
    const cola = qp.toString();
    return peticion<{ activos: ActivoMarca[] }>(`/marca-activos${cola ? `?${cola}` : ""}`, { signal });
  },
  crearMarcaActivo: (cuerpo: {
    tipo: string;
    marca?: string;
    nombre?: string;
    objeto?: string;
    metadatos?: Record<string, unknown>;
    lineas?: string[];
  }) => peticion<{ activo: ActivoMarca }>("/marca-activos", { metodo: "POST", json: cuerpo }),
  actualizarMarcaActivo: (id: string, cuerpo: Record<string, unknown>) =>
    peticion<{ activo: ActivoMarca }>(`/marca-activos/${encodeURIComponent(id)}`, { metodo: "PATCH", json: cuerpo }),
  borrarMarcaActivo: (id: string, purgar?: boolean) =>
    peticion<{ mensaje: string }>(
      `/marca-activos/${encodeURIComponent(id)}${purgar ? "?purgar=1" : ""}`,
      { metodo: "DELETE" },
    ),

  // --- Biblioteca de plantillas de diseño (N por marca, etiquetadas por línea) ---
  // `tipo` filtra por "foto" (plantillas de imagen) o "miniatura" (portadas de video).
  plantillasDiseno: (
    filtros: { marca?: string; categoria?: string; linea?: string; q?: string; tipo?: "foto" | "miniatura" } = {},
    signal?: AbortSignal,
  ) => {
    const qp = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v) qp.set(k, v);
    const cola = qp.toString();
    return peticion<{ plantillas: PlantillaDiseno[] }>(`/plantillas-diseno${cola ? `?${cola}` : ""}`, { signal });
  },
  crearPlantillaDiseno: (cuerpo: {
    marca?: string;
    nombre?: string;
    categoria?: string;
    /** "foto" (default) | "miniatura" (portada de video). */
    tipo?: "foto" | "miniatura";
    documento: unknown;
    miniatura?: string;
    lineas?: string[];
  }) => peticion<{ plantilla: PlantillaDiseno }>("/plantillas-diseno", { metodo: "POST", json: cuerpo }),
  // Actualiza una plantilla existente (PATCH): «Guardar» sobre la plantilla ya creada.
  actualizarPlantillaDiseno: (
    id: string,
    cuerpo: { nombre?: string; categoria?: string; tipo?: "foto" | "miniatura"; documento?: unknown; miniatura?: string; lineas?: string[]; activo?: boolean },
  ) => peticion<{ plantilla: PlantillaDiseno }>(`/plantillas-diseno/${encodeURIComponent(id)}`, { metodo: "PATCH", json: cuerpo }),
  borrarPlantillaDiseno: (id: string) =>
    peticion<{ mensaje: string }>(`/plantillas-diseno/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Almacén de bloques (grupos de capas reutilizables) ---
  bloques: (filtros: { marca?: string; q?: string } = {}, signal?: AbortSignal) => {
    const qp = new URLSearchParams();
    for (const [k, v] of Object.entries(filtros)) if (v) qp.set(k, v);
    const cola = qp.toString();
    return peticion<{ bloques: Bloque[] }>(`/bloques${cola ? `?${cola}` : ""}`, { signal });
  },
  crearBloque: (cuerpo: { marca?: string; nombre?: string; capas: unknown[]; lineas?: string[]; miniatura?: string }) =>
    peticion<{ bloque: Bloque }>("/bloques", { metodo: "POST", json: cuerpo }),
  borrarBloque: (id: string) =>
    peticion<{ mensaje: string }>(`/bloques/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Plantillas de marca (identidad visual con la que se estampa una imagen) ---
  // Solo lectura del catálogo + edición de la plantilla de una marca (logo, colores,
  // etiqueta/pleca, posición del logo, wordmark de respaldo). El logo se sube antes con
  // `subirMedia` y aquí se guarda su id en `logo`.
  plantillasMarca: (signal?: AbortSignal) =>
    peticion<RespuestaPlantillasMarca>("/plantillas-marca", { signal }),
  plantillaMarca: (marca: string, signal?: AbortSignal) =>
    peticion<RespuestaPlantillaMarca>(`/plantillas-marca/${encodeURIComponent(marca)}`, { signal }),
  guardarPlantillaMarca: (marca: string, datos: Partial<PlantillaMarca>) =>
    peticion<RespuestaPlantillaMarca>(`/plantillas-marca/${encodeURIComponent(marca)}`, {
      metodo: "PUT",
      json: datos,
    }),
  // SPEC de capas del editor visual: leer / guardar / previsualizar (render real del servidor).
  specPlantilla: (marca: string, signal?: AbortSignal) =>
    peticion<{ spec: PlantillaSpec }>(`/plantillas-marca/${encodeURIComponent(marca)}/spec`, { signal }),
  guardarSpecPlantilla: (marca: string, spec: PlantillaSpec) =>
    peticion<{ spec: PlantillaSpec }>(`/plantillas-marca/${encodeURIComponent(marca)}/spec`, {
      metodo: "PUT",
      json: { spec },
    }),
  // La previa del diseñador es EFÍMERA: el back devuelve los BYTES del PNG (no persiste nada) y
  // aquí construimos un object URL para el <img>. El llamante debe revocar el URL anterior.
  previewPlantilla: async (
    marca: string, spec: PlantillaSpec, formato: string, titular?: string,
  ): Promise<string> => {
    let res: Response;
    try {
      res = await fetch(`${BASE_API}/plantillas-marca/${encodeURIComponent(marca)}/preview`, {
        method: "POST",
        headers: { ...cabecerasAuth(), "Content-Type": "application/json" },
        body: JSON.stringify({ spec, formato, titular: titular ?? "" }),
      });
    } catch {
      throw new ApiError("No se pudo contactar con la consola.", 0);
    }
    if (!res.ok) {
      let mensaje = "No se pudo previsualizar la plantilla.";
      try {
        const j = await res.json();
        if (j?.error) mensaje = j.error;
      } catch {
        /* cuerpo no-JSON: mensaje por defecto */
      }
      throw new ApiError(mensaje, res.status);
    }
    return URL.createObjectURL(await res.blob());
  },

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

  // --- RSS (solo gestión de fuentes/feeds; los items viven en el pool de Noticias) ---
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

  // --- Catálogo de fuentes: la vista "Todas" lista los feeds (desde fuentes_rss, tipo='rss')
  // + el estado honesto de agencias (Reuters/AFP). Solo lectura. ---
  fuentesHub: (tipo?: string, signal?: AbortSignal) =>
    peticion<RespuestaFuentesHub>(`/fuentes${query({ tipo })}`, { signal }),
  // APORTACION MANUAL (idea / enlace pegado / contenido interno): crea un item REAL en el
  // tablero (`flujo='importante'`) con su `origen` y, best-effort, le lanza copy de fondo.
  aportarFuente: (cuerpo: CuerpoAportarFuente) =>
    peticion<RespuestaAportarFuente>("/fuentes/aportar", { metodo: "POST", json: cuerpo }),

  // --- Catálogo de presets (Ola 4: Fuentes externas + idiomas) ---
  // Lista el catálogo curado de feeds listos para activar, opcionalmente filtrado por categoría.
  // Marca cada preset con `activa: bool` si ya existe una `fuentes_rss` con esa URL.
  fuentesPresets: (categoria?: string, signal?: AbortSignal) =>
    peticion<RespuestaPresets>(
      `/fuentes/presets${query({ categoria })}`,
      { signal },
    ),
  // Activa los presets elegidos: crea `fuentes_rss` de forma idempotente por URL.
  activarPresets: (cuerpo: { ids: string[]; marca?: string }) =>
    peticion<RespuestaActivarPresets>("/fuentes/presets/activar", { metodo: "POST", json: cuerpo }),

  // --- Algoritmos (inteligencia de plataforma: cambios de algoritmo + tendencias) ---
  // Solo lectura + curación ligera. Las noticias ya vienen clasificadas/ordenadas por
  // importancia; refrescar ingiere los feeds; las fuentes se gestionan como el RSS.
  algoritmos: (filtros: FiltrosAlgoritmos = {}, signal?: AbortSignal) =>
    peticion<RespuestaAlgoritmos>(
      `/algoritmos${query({
        plataforma: filtros.plataforma,
        nivel: filtros.nivel,
        solo_cambios: filtros.solo_cambios ? "1" : undefined,
        incluir_archivadas: filtros.incluir_archivadas ? "1" : undefined,
        limite: filtros.limite?.toString(),
      })}`,
      { signal },
    ),
  refrescarAlgoritmos: (fuente?: string) =>
    peticion<RespuestaRefrescarAlgoritmos>("/algoritmos/refrescar", {
      metodo: "POST",
      json: fuente ? { fuente } : {},
    }),
  sembrarAlgoritmos: () =>
    peticion<RespuestaSembrarAlgoritmos>("/algoritmos/sembrar", { metodo: "POST" }),
  crearFuenteAlgoritmo: (cuerpo: CuerpoFuenteAlgoritmo) =>
    peticion<RespuestaFuenteAlgoritmo>("/algoritmos/fuentes", { metodo: "POST", json: cuerpo }),
  actualizarFuenteAlgoritmo: (id: string, cuerpo: CuerpoFuenteAlgoritmo) =>
    peticion<RespuestaFuenteAlgoritmo>(`/algoritmos/fuentes/${encodeURIComponent(id)}`, {
      metodo: "PUT",
      json: cuerpo,
    }),
  borrarFuenteAlgoritmo: (id: string) =>
    peticion<RespuestaMensaje>(`/algoritmos/fuentes/${encodeURIComponent(id)}`, {
      metodo: "DELETE",
    }),
  algoritmoABiblioteca: (id: string) =>
    peticion<RespuestaABibliotecaAlgoritmo>(`/algoritmos/${encodeURIComponent(id)}/biblioteca`, {
      metodo: "POST",
    }),
  archivarAlgoritmo: (id: string, archivada = true) =>
    peticion<RespuestaArchivarAlgoritmo>(`/algoritmos/${encodeURIComponent(id)}/archivar`, {
      metodo: "POST",
      json: { archivada },
    }),

  // --- Sugerencias editoriales (digest diario: cambios a fichas/límites de plataforma) ---
  sugerenciasAlgoritmo: (estado?: EstadoSugerenciaEditorial, signal?: AbortSignal) =>
    peticion<RespuestaSugerenciasAlgoritmo>(
      `/algoritmos/sugerencias${query({ estado })}`,
      { signal },
    ),
  generarSugerenciasAlgoritmo: () =>
    peticion<RespuestaMensaje>("/algoritmos/sugerencias/generar", { metodo: "POST" }),
  aplicarSugerenciaAlgoritmo: (id: string) =>
    peticion<RespuestaAplicarSugerencia>(
      `/algoritmos/sugerencias/${encodeURIComponent(id)}/aplicar`,
      { metodo: "POST" },
    ),
  descartarSugerenciaAlgoritmo: (id: string) =>
    peticion<RespuestaDescartarSugerencia>(
      `/algoritmos/sugerencias/${encodeURIComponent(id)}/descartar`,
      { metodo: "POST" },
    ),

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

  // --- Cadencia por red (margen entre posts) ---
  cadencias: (signal?: AbortSignal) =>
    peticion<RespuestaCadencias>("/cadencias", { signal }),
  guardarCadencia: (cuerpo: CuerpoGuardarCadencia) =>
    peticion<RespuestaCadencia>("/cadencias", { metodo: "PUT", json: cuerpo }),
  eliminarCadencia: (id: string) =>
    peticion<RespuestaMensaje>(`/cadencias/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

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
  // Genera una imagen adaptada por red (recorte al formato + plantilla de marca) a partir de
  // `imagen` y la asigna a CADA plataforma de la pieza, de forma determinista.
  adaptarImagenContenido: (contenidoId: string, imagen: string) =>
    peticion<{ adaptadas: number }>(
      `/contenido/${encodeURIComponent(contenidoId)}/adaptar-imagen`,
      { metodo: "POST", json: { imagen } },
    ),
  eliminarPlataforma: (contenidoId: string, plataformaId: string) =>
    peticion<RespuestaMensaje>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas/${encodeURIComponent(plataformaId)}`,
      { metodo: "DELETE" },
    ),
  // PUERTA CREATIVA (Fase 1 / Flujo A): el equipo "postea" material ORIGINAL (foto/nota/idea/
  // url) con marca. Crea un contenido con origen='equipo' que ENCIENDE la auto-generación de
  // copy automáticamente. Multipart porque puede llevar la foto que el equipo trae de fuera.
  aportarMaterial: (cuerpo: CuerpoAportarMaterial) => {
    const form = new FormData();
    form.set("titulo", cuerpo.titulo);
    form.set("marca", cuerpo.marca);
    if (cuerpo.material) form.set("material", cuerpo.material);
    if (cuerpo.url) form.set("url", cuerpo.url);
    if (cuerpo.intencion) form.set("intencion", cuerpo.intencion);
    if (cuerpo.redes?.length) form.set("redes", cuerpo.redes.join(","));
    if (cuerpo.imagen) form.set("imagen", cuerpo.imagen);
    // Vídeo/audio: se transcribe EN LOCAL en el back y el texto alimenta el auto-copy.
    if (cuerpo.clip) form.set("clip", cuerpo.clip);
    return peticion<RespuestaContenidoItem>("/contenido/aportar", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },
  // Fase3 auto-planificación: sugerir la mejor hora de publicación (1 clic en la UI).
  sugerirHora: (cuerpo: CuerpoSugerirHora) =>
    peticion<RespuestaSugerirHora>("/planificacion/sugerir-hora", { metodo: "POST", json: cuerpo }),
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

  // --- Green: banco de ideas de contenido evergreen (perenne) por marca ---
  // Las ideas se proponen a mano o con IA (`proponerGreen` lanza un trabajo en 2º plano que
  // se SONDEA con `useGeneracion`); al aprobar una idea se puede generar la pieza evergreen.
  ideasGreen: (
    params: { marca?: string; estado?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaIdeasGreen>(`/green/ideas${query(params)}`, { signal }),
  crearIdeaGreen: (cuerpo: CuerpoCrearIdeaGreen) =>
    peticion<RespuestaIdeaGreen>("/green/ideas", { metodo: "POST", json: cuerpo }),
  actualizarIdeaGreen: (id: string, cuerpo: CuerpoActualizarIdeaGreen) =>
    peticion<RespuestaIdeaGreen>(`/green/ideas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarIdeaGreen: (id: string) =>
    peticion<RespuestaMensaje>(`/green/ideas/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  proponerGreen: (cuerpo: CuerpoProponerGreen) =>
    peticion<RespuestaGeneracion>("/green/proponer", { metodo: "POST", json: cuerpo }),
  generarIdeaGreen: (id: string, cuerpo: CuerpoGenerarIdeaGreen = {}) =>
    peticion<RespuestaGeneracion>(`/green/ideas/${encodeURIComponent(id)}/generar`, {
      metodo: "POST",
      json: cuerpo,
    }),

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
      /** Id canónico de marca; ausente/vacío = todas las marcas. */
      marca?: string;
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
  metricasPiezas: (params: { rango?: string; marca?: string; red?: string }, signal?: AbortSignal) =>
    peticion<AnaliticaPiezas>(`/metricas/piezas${query(params)}`, { signal }),
  // Serie diaria del periodo (visualizaciones + interacciones) para la tendencia.
  metricasTendencia: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<TendenciaDiaria>(`/metricas/tendencia${query(params)}`, { signal }),
  // Drill-down marca -> pieza: piezas publicadas con su rendimiento REAL (Metricool),
  // enlazables al tablero. Sin rango (es por pieza publicada, no por periodo).
  metricasPiezasRendimiento: (params: { marca?: string }, signal?: AbortSignal) =>
    peticion<PiezasRendimiento>(`/metricas/piezas-rendimiento${query(params)}`, { signal }),
  // Listado COMPLETO de piezas del periodo (todas, no solo top/peores), tal como las
  // emite la fuente única; insumo de la tabla "Todas las piezas del periodo".
  metricasPiezasListado: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<PiezasListado>(`/metricas/piezas-listado${query(params)}`, { signal }),
  // Histórico por pieza (snapshots acumulados, ADR 0007) + velocidad. `puntos` vacío =
  // la pieza aún no se sigue (sin histórico todavía). Se carga perezosamente por id.
  metricasPiezaHistorico: (params: { id: string }, signal?: AbortSignal) =>
    peticion<HistoricoPieza>(`/metricas/pieza-historico${query(params)}`, { signal }),
  // Rendimiento del periodo agrupado por serie/tipo (Item C): cruza piezas de Metricool
  // con el contenido de la BD para resolver tipo_contenido + etiquetas.
  metricasPiezasPorEtiqueta: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<PiezasPorEtiqueta>(`/metricas/piezas-por-etiqueta${query(params)}`, { signal }),
  // Rendimiento del periodo agregado por LÍNEA de contenido (vertical) y por ORIGEN.
  // `marca` viaja en forma `id_metricas` (guion_bajo), igual que el resto de Métricas.
  metricasLineas: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<MetricasLineas>(`/metricas/lineas${query(params)}`, { signal }),
  // --- Estrategia digital ---
  // Evolución de seguidores del periodo (total + por red) con el neto ganado/perdido.
  metricasSeguidores: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<SerieSeguidores>(`/metricas/seguidores${query(params)}`, { signal }),
  // Desglose de interacciones (likes/comentarios/compartidos/guardados/video_views) por marca×red.
  metricasDesglose: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<DesgloseInteracciones>(`/metricas/desglose${query(params)}`, { signal }),
  // Rendimiento cruzado marca×red×formato (n_piezas, engagement, rendimiento relativo medio).
  metricasCrosstab: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<Crosstab>(`/metricas/crosstab${query(params)}`, { signal }),
  // Correlación seguidores ganados ↔ piezas publicadas por día (con la pieza estrella).
  metricasCorrelacion: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<CorrelacionSeguidores>(`/metricas/correlacion${query(params)}`, { signal }),
  // Estado del refresco + "última actualización" del combo (para el botón Actualizar y el polling).
  metricasEstado: (params: { rango?: string; marca?: string }, signal?: AbortSignal) =>
    peticion<EstadoMetricas>(`/metricas/estado${query(params)}`, { signal }),
  // Dispara un refresco en 2º plano (prioriza el combo visto). Idempotente: si ya corre, no arranca otro.
  metricasRefrescar: (params: { rango?: string; marca?: string }) =>
    peticion<EstadoMetricas>(`/metricas/refrescar${query(params)}`, { metodo: "POST" }),
  exportarMetricas: (formato: "csv" | "md" | "json", params: { rango?: string; marca?: string }) =>
    descargar(`/metricas/export.${formato}${query(params)}`),
  // Descarga del Top 5 / Peores 5 de piezas del periodo (Item B): mismo dato que la
  // analítica de piezas, serializado en csv|md|json. `fmt` viaja como query param.
  exportarPiezas: (formato: "csv" | "md" | "json", params: { rango?: string; marca?: string }) =>
    descargar(`/metricas/piezas-export${query({ fmt: formato, ...params })}`),

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
  comercialPosts: (
    params: { marca?: string; red?: string; rango?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaPostsComercial>(`/comercial/posts${query(params)}`, { signal }),
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

  // --- Notificaciones in-app (el "cajón" de la campana, acotado a la marca activa) ---
  notificaciones: (marcaId?: string, signal?: AbortSignal) =>
    peticion<RespuestaNotificaciones>(`/notificaciones${query({ marca_id: marcaId })}`, { signal }),
  contadorNotificaciones: (marcaId?: string, signal?: AbortSignal) =>
    peticion<RespuestaContadorNotificaciones>(
      `/notificaciones/contador${query({ marca_id: marcaId })}`,
      { signal },
    ),
  marcarNotificacionLeida: (id: string) =>
    peticion<{ ok: boolean }>(`/notificaciones/${encodeURIComponent(id)}/leer`, { metodo: "POST" }),
  marcarNotificacionesLeidas: (marcaId?: string) =>
    peticion<{ marcadas: number }>(`/notificaciones/leer-todas${query({ marca_id: marcaId })}`, {
      metodo: "POST",
    }),
  mencionesCandidatos: (marcaId?: string, signal?: AbortSignal) =>
    peticion<RespuestaMencionesCandidatos>(
      `/notificaciones/menciones-candidatos${query({ marca_id: marcaId })}`,
      { signal },
    ),

  // --- Insumos del día (cajones) ---
  // El equipo vuelca material diario en 4 cajones; Haiku lo parsea y produce
  // ítems listos para llevar al tablero. Contrato: docs/maquina-contenido/01-insumos-del-dia.md.
  insumos: {
    /** Lista los 4 cajones con sus lotes e ítems para `fecha` (def: hoy en el servidor).
     *
     * `soloFrescos=true` activa `solo_frescos=1` en la query: los ítems caducados se ocultan
     * (no se borran). Útil para UnoTV donde publicar noticias de ayer es perjudicial.
     */
    listar: (fecha?: string, signal?: AbortSignal, soloFrescos?: boolean, marca?: string) =>
      peticion<RespuestaInsumos>(
        `/insumos${query({ fecha, ...(soloFrescos ? { solo_frescos: "1" } : {}), ...(marca ? { marca } : {}) })}`,
        { signal },
      ),

    /** Días con insumos registrados (orden: fecha desc). Para el selector de historial. */
    dias: (signal?: AbortSignal) =>
      peticion<RespuestaDiasInsumos>("/insumos/dias", { signal }),

    /**
     * Aporta material a un cajón. ASÍNCRONO: crea el lote en estado `parseando` y ENCOLA un
     * job (Haiku) que el WORKER ejecuta (el back no tiene `claude`). Devuelve el lote +
     * la `generacion` para sondear; los ítems aparecen al recargar el cajón cuando el lote
     * pasa a `listo`. Acepta texto pegado y/o archivo.
     */
    aportar: (form: FormData) =>
      peticion<{ lote: InsumoLote; generacion: Generacion | null }>("/insumos/aportar", {
        metodo: "POST",
        form,
      }),

    /** Detalle de un lote con sus ítems. */
    lote: (id: string, signal?: AbortSignal) =>
      peticion<{ lote: InsumoLote; items: InsumoItem[] }>(
        `/insumos/lote/${encodeURIComponent(id)}`,
        { signal },
      ),

    /** Edición parcial de un ítem (título, resumen, marca, línea, hora, lugar, etc.). */
    editarItem: (
      id: string,
      campos: Partial<Pick<InsumoItem, "titulo" | "resumen" | "marca" | "linea" | "hora" | "lugar" | "estado_material" | "tipo">>,
    ) =>
      peticion<{ item: InsumoItem }>(`/insumos/item/${encodeURIComponent(id)}`, {
        metodo: "PATCH",
        json: campos,
        muestrear: false,
      }),

    /**
     * Lleva un ítem al tablero: crea contenido con `origen="insumo"` y marca el ítem
     * como `usado`. Acepta `redes` y `generar` (lanza copy si `true` y hay marca).
     */
    usarItem: (id: string, body: { redes?: string[]; generar?: boolean }) =>
      peticion<{ item: InsumoItem; contenido_id: string }>(
        `/insumos/item/${encodeURIComponent(id)}/usar`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /**
     * Convierte un ítem del cajón `eventos_claro` (tipo='evento') en un evento de la
     * rota (`/api/rota/eventos`): mapea titulo/fecha/hora/resumen→nota y marca el ítem
     * como usado guardando el id del evento en `contenido_id`. Devuelve el evento creado.
     */
    crearEvento: (
      id: string,
      body: { tipo_cobertura?: string; prioridad?: string } = {},
    ) =>
      peticion<{ item: InsumoItem; evento: EventoRota; evento_id: string }>(
        `/insumos/item/${encodeURIComponent(id)}/crear-evento`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /** Borra un lote y todos sus ítems. */
    borrarLote: (id: string) =>
      peticion<{ ok: boolean }>(`/insumos/lote/${encodeURIComponent(id)}`, {
        metodo: "DELETE",
        muestrear: false,
      }),
  },

  // --- Carril Rápido de Breaking (Claro Sports) ---
  breaking: {
    /**
     * Lista los temas del Radar marcados como breaking para la marca, con su estado de borrador.
     * GET /api/breaking?marca=claro-sports
     */
    listar: (marca?: string, signal?: AbortSignal) =>
      peticion<RespuestaBreaking>(
        `/breaking${marca ? `?marca=${encodeURIComponent(marca)}` : ""}`,
        { signal },
      ),
    /**
     * Prepara un borrador de copy para un tema breaking (DRAFT, nunca publica).
     * POST /api/breaking/preparar
     */
    preparar: (cuerpo: CuerpoPreparar) =>
      peticion<RespuestaPreparar>("/breaking/preparar", { metodo: "POST", json: cuerpo }),
  },


  // --- Motor de ingesta persistente (Ola A): archivo a nivel de artículo ---
  // Contrato: docs/maquina-contenido/A-motor-ingesta.md
  noticias: {
    /**
     * Lista el archivo de noticias ingeridas, newest-first (`capturado_en` desc).
     * `marca` = '' / ausente → todas (admin); en caso contrario filtra por marca.
     * `estado` = 'nuevo' | 'usado' | 'descartado' | ausente → todos.
     * `desde` es una fecha ISO (YYYY-MM-DD) de corte mínimo de `capturado_en`.
     * `q` es búsqueda libre sobre título.
     * `limit`/`offset` para paginación.
     */
    listar: (
      params: {
        marca?: string;
        categoria?: string;
        desde?: string;
        q?: string;
        estado?: string;
        limit?: number;
        offset?: number;
      } = {},
      signal?: AbortSignal,
    ) =>
      peticion<RespuestaNoticias>(
        `/noticias${query({
          marca: params.marca,
          categoria: params.categoria,
          desde: params.desde,
          q: params.q,
          estado: params.estado,
          limit: params.limit != null ? String(params.limit) : undefined,
          offset: params.offset != null ? String(params.offset) : undefined,
        })}`,
        { signal },
      ),

    /**
     * Lleva una noticia al tablero como pieza de contenido.
     * `redes` y `generar` son opcionales (igual que `insumos.usarItem`).
     * Marca `estado=usado` y guarda el `contenido_id`.
     * POST /api/noticias/{id}/usar
     */
    usar: (
      id: string,
      body: { redes?: string[]; generar?: boolean } = {},
    ) =>
      peticion<{ ok: boolean; contenido_id: string }>(
        `/noticias/${encodeURIComponent(id)}/usar`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /**
     * Descarta una noticia (estado=descartado). No se borra del archivo.
     * POST /api/noticias/{id}/descartar
     */
    descartar: (id: string) =>
      peticion<{ ok: boolean }>(
        `/noticias/${encodeURIComponent(id)}/descartar`,
        { metodo: "POST", muestrear: false },
      ),

    /**
     * Resumen básico de salud del motor de ingesta:
     * nº feeds activos/con error, items últimas 24h por categoría, último sondeo.
     * GET /api/noticias/cobertura
     */
    cobertura: (signal?: AbortSignal) =>
      peticion<ResumenCobertura>("/noticias/cobertura", { signal }),

    // --- Ola B: clusters de historias ---

    /**
     * Lista los clusters de historias (misma noticia, múltiples fuentes).
     * Orden: score desc. marca-aware.
     * GET /api/noticias/historias
     */
    historias: (
      params: {
        marca?: string;
        categoria?: string;
        desde?: string;
        estado?: string;
        limit?: number;
        offset?: number;
      } = {},
      signal?: AbortSignal,
    ) =>
      peticion<RespuestaHistorias>(
        `/noticias/historias${query({
          marca: params.marca,
          categoria: params.categoria,
          desde: params.desde,
          estado: params.estado,
          limit: params.limit != null ? String(params.limit) : undefined,
          offset: params.offset != null ? String(params.offset) : undefined,
        })}`,
        { signal },
      ),

    /**
     * Detalle de un cluster: la historia + sus artículos corroborantes.
     * GET /api/noticias/historias/{id}
     */
    historia: (id: string, signal?: AbortSignal) =>
      peticion<{ historia: Historia; items: unknown[] }>(
        `/noticias/historias/${encodeURIComponent(id)}`,
        { signal },
      ),

    /**
     * Lleva una historia al tablero como pieza de contenido.
     * Marca el cluster + sus ítems como `usado`.
     * POST /api/noticias/historias/{id}/usar
     */
    usarHistoria: (
      id: string,
      body: { redes?: string[]; generar?: boolean } = {},
    ) =>
      peticion<{ ok: boolean; contenido_id: string }>(
        `/noticias/historias/${encodeURIComponent(id)}/usar`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /**
     * Descarta una historia (estado=descartado). No se borra del archivo.
     * POST /api/noticias/historias/{id}/descartar
     */
    descartarHistoria: (id: string) =>
      peticion<{ ok: boolean }>(
        `/noticias/historias/${encodeURIComponent(id)}/descartar`,
        { metodo: "POST", muestrear: false },
      ),

    // --- Ola D: salud de fuentes ---

    /**
     * Salud detallada del motor de ingesta: resumen + detalle por feed.
     * Marca-aware (?marca=).
     * GET /api/noticias/salud
     */
    salud: (marca?: string, signal?: AbortSignal) =>
      peticion<SaludCobertura>(
        `/noticias/salud${query({ marca })}`,
        { signal },
      ),
  },

  // --- Ola D: acciones sobre fuentes RSS ---
  fuentes: {
    /**
     * Reactiva un feed desactivado automáticamente:
     * activo=1, desactivado_auto=0, errores_seguidos=0, proximo_sondeo='' (reintentar ya).
     * POST /api/fuentes/{id}/reactivar
     */
    reactivar: (id: string) =>
      peticion<{ ok: boolean }>(
        `/fuentes/${encodeURIComponent(id)}/reactivar`,
        { metodo: "POST", muestrear: false },
      ),
  },
};

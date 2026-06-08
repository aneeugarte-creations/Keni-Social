/**
 * Núcleo compartido del cliente fetch tipado de la Consola Keni.
 *
 * - Mismo origen: todas las rutas cuelgan de `/api`. En `npm run dev`, Vite
 *   proxea `/api` a `http://127.0.0.1:8765` (ver vite.config.ts).
 * - Ante un status no-OK, lanza `ApiError` con el `mensaje`/`error` en espanol
 *   que devuelve el backend (o un fallback legible). React Query expone ese
 *   mensaje a la UI.
 * - Soporta JSON, multipart (FormData) y descargas (abre la URL en el navegador).
 *
 * Aquí viven las piezas COMPARTIDAS por todos los fragmentos de dominio
 * (`./<dominio>.ts`): el wrapper `peticion`, los helpers de URL/query, la clase
 * `ApiError`, `mensajeError` y las interfaces locales del cliente. El objeto `api`
 * compuesto se arma en `./index.ts`.
 */
import type { ErrorApi } from "@/types";

import { type NombreContrato, validarContrato } from "../contrato";

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
export function cabecerasAuth(): Record<string, string> {
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

export interface OpcionesPeticion {
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
export async function peticion<T>(ruta: string, opciones: OpcionesPeticion = {}): Promise<T> {
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
export function query(params: Record<string, string | undefined>): string {
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
export function queryEventos(params: {
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
export function descargar(ruta: string): void {
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

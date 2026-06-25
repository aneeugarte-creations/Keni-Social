/**
 * Detección de versión nueva del SPA tras un deploy, y recarga AUTOMÁTICA y suave.
 *
 * Contexto: los assets llevan hash en el nombre y se cachean inmutables; `index.html`
 * es `no-store`. Tras un deploy, una pestaña abierta sigue con el bundle viejo en
 * memoria y, al navegar a una página cuyo chunk cambió de hash, el `import()` falla
 * (404). Este código lo resuelve detectando automáticamente la nueva versión y
 * recargando en silencio.
 *
 * Detección (preferente → alterna):
 *  1) `/version.json` (lo escribe Vite en cada build con un `buildId` único; nginx lo
 *     sirve `no-store`). Comparamos su `buildId` con `__BUILD_ID__`, horneado en ESTE
 *     bundle. Distinto ⇒ hay deploy nuevo. Es lo más preciso (un id por build).
 *  2) Si `version.json` no está disponible (build/instancia sin él), caemos al `src` del
 *     <script type="module"> de entrada del `/index.html` desplegado: si su hash cambió,
 *     también es un deploy nuevo.
 *
 * Reacción:
 *  - SIN aviso: recargamos solos y en silencio en la SIGUIENTE navegación de ruta
 *    (momento menos molesto: el usuario ya cambia de sección, el refresco es transparente
 *    y no se pierde nada a medio escribir). No mostramos toast ni pedimos confirmación.
 *  - `FronteraError` usa `recargaSegura()` como red de seguridad si el chunk ya no existe
 *    antes de que el poll lo detecte.
 *
 * `recargaSegura()` lleva un guard anti-bucle: si algo recarga en bucle (p. ej. un chunk
 * que falla por un bug real, no por un deploy), tras la primera recarga deja de insistir
 * para no atrapar al usuario en un ciclo.
 */
import * as React from "react";
import { useLocation } from "react-router-dom";

/** Clave en sessionStorage del instante de la última recarga automática (anti-bucle). */
const CLAVE_ULTIMA_RECARGA = "keni:ultima-recarga-auto";
/** Ventana mínima entre recargas automáticas (ms). Dos recargas más juntas = bucle. */
const VENTANA_ANTIBUCLE_MS = 20_000;

/** Id de ESTE bundle, horneado por Vite (`define`). "dev" o ausente fuera de build. */
const ID_LOCAL: string =
  typeof __BUILD_ID__ === "string" && __BUILD_ID__ ? __BUILD_ID__ : "dev";

/**
 * Recarga la página de forma segura (una sola vez por ventana anti-bucle). Devuelve
 * `true` si disparó la recarga; `false` si la suprimió por sospecha de bucle (en ese
 * caso el llamante debe ofrecer una recarga manual). Nunca lanza.
 */
export function recargaSegura(): boolean {
  let ultima = 0;
  try {
    ultima = Number(sessionStorage.getItem(CLAVE_ULTIMA_RECARGA)) || 0;
  } catch {
    ultima = 0;
  }
  const ahora = Date.now();
  if (ahora - ultima < VENTANA_ANTIBUCLE_MS) return false; // recargó hace nada: no insistas
  try {
    sessionStorage.setItem(CLAVE_ULTIMA_RECARGA, String(ahora));
  } catch {
    // sessionStorage no disponible (modo privado): seguimos; el guard simplemente no persiste.
  }
  try {
    window.location.reload();
  } catch {
    // jsdom/tests: `reload` no está implementado. No es fatal.
    return false;
  }
  return true;
}

/** `src` del <script type="module"> de entrada que arrancó la app (o null). */
function entradaActual(): string | null {
  const s = document.querySelector<HTMLScriptElement>('script[type="module"][src]');
  return s?.getAttribute("src") ?? null;
}

/**
 * ¿Hay una versión nueva desplegada? Prefiere `/version.json` (preciso por build) y, si no
 * está, cae al hash del <script> de entrada del `/index.html` desplegado. No lanza.
 */
async function hayVersionNueva(entrada: string | null, signal?: AbortSignal): Promise<boolean> {
  // 1) version.json (preciso). Exigimos JSON real: si nginx cae al fallback SPA (HTML)
  //    o no existe (404), ignoramos y probamos el método alterno.
  try {
    const res = await fetch("/version.json", { cache: "no-store", signal });
    if (res.ok && (res.headers.get("content-type") ?? "").includes("json")) {
      const datos: unknown = await res.json();
      const buildId = (datos as { buildId?: unknown } | null)?.buildId;
      if (typeof buildId === "string" && ID_LOCAL !== "dev") {
        return buildId !== ID_LOCAL;
      }
    }
  } catch {
    // Sin version.json (o red caída): probamos el método alterno.
  }
  // 2) Alterno: el <script> de entrada del index.html desplegado cambió de hash.
  //    Solo aplica en producción (entrada = /assets/index-<hash>.js); en dev no.
  if (!entrada || !entrada.includes("/assets/")) return false;
  try {
    const res = await fetch("/index.html", { cache: "no-store", signal });
    if (!res.ok) return false;
    const m = (await res.text()).match(/<script[^>]+type="module"[^>]+src="([^"]+)"/i);
    return !!m && m[1] !== entrada;
  } catch {
    return false;
  }
}

/**
 * ¿Hay un deploy más reciente que ESTE bundle? Pensado para llamarlo JUSTO ANTES de una
 * operación cliente cara que depende del código actual (p. ej. generar el PDF del Informe):
 * si la pestaña lleva el bundle viejo en memoria, el resultado saldría con el diseño antiguo.
 * No lanza; en desarrollo (sin `buildId` horneado) devuelve `false`.
 */
export function comprobarVersionNueva(signal?: AbortSignal): Promise<boolean> {
  return hayVersionNueva(entradaActual(), signal);
}

/**
 * Hook (móntalo UNA vez en el cascarón): vigila si hay una versión nueva desplegada y,
 * cuando la hay, recarga sola y EN SILENCIO en la siguiente navegación de ruta (sin toast
 * ni confirmación). No hace nada en desarrollo.
 */
export function useDetectorActualizacion(): void {
  const location = useLocation();
  const entrada = React.useRef<string | null>(null);
  const pendiente = React.useRef(false);
  const detectada = React.useRef(false);

  // Captura la entrada actual una sola vez, al montar (para el método alterno).
  React.useEffect(() => {
    entrada.current = entradaActual();
  }, []);

  const marcarActualizable = React.useCallback(() => {
    if (detectada.current) return;
    detectada.current = true;
    // Sin aviso: solo dejamos la recarga PENDIENTE; ocurre sola al cambiar de ruta.
    pendiente.current = true;
  }, []);

  const comprobar = React.useCallback(
    async (signal?: AbortSignal) => {
      if (detectada.current) return; // ya detectada: no hace falta seguir sondeando
      if (await hayVersionNueva(entrada.current, signal)) marcarActualizable();
    },
    [marcarActualizable],
  );

  // Poll periódico + comprobación al recuperar foco/visibilidad (un usuario que vuelve
  // a la pestaña es el caso típico tras un deploy).
  React.useEffect(() => {
    const ac = new AbortController();
    const id = window.setInterval(() => void comprobar(), 120_000);
    const alVolver = () => {
      if (!document.hidden) void comprobar();
    };
    window.addEventListener("focus", alVolver);
    document.addEventListener("visibilitychange", alVolver);
    void comprobar(ac.signal);
    return () => {
      ac.abort();
      window.clearInterval(id);
      window.removeEventListener("focus", alVolver);
      document.removeEventListener("visibilitychange", alVolver);
    };
  }, [comprobar]);

  // Recarga SUAVE: al cambiar de ruta, si ya hay versión nueva, recargamos ahora (el
  // usuario está navegando de todos modos, así que trae los chunks nuevos sin fricción).
  React.useEffect(() => {
    if (pendiente.current) recargaSegura();
  }, [location.pathname]);
}

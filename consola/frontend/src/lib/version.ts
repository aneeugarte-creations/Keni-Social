/**
 * Detección de versión nueva del SPA tras un deploy, y recarga AUTOMÁTICA y suave.
 *
 * Contexto: los assets llevan hash en el nombre y se cachean inmutables; `index.html`
 * es `no-store`. Tras un deploy, una pestaña abierta sigue con el bundle viejo en
 * memoria y, al navegar a una página cuyo chunk cambió de hash, el `import()` falla
 * (404) y `FronteraError` tenía que pedir al usuario que recargara A MANO. Eso es la UX
 * fea que queremos eliminar.
 *
 * Estrategia (sin service worker, sin endpoint nuevo):
 *  1) Al arrancar guardamos el `src` del <script type="module"> de entrada
 *     (en producción: `/assets/index-<hash>.js`).
 *  2) Periódicamente (y al volver el foco a la pestaña) pedimos `/index.html` fresco
 *     y extraemos su script de entrada. Si el hash cambió => hay una versión nueva.
 *  3) Recargamos en el MOMENTO MENOS molesto: en la siguiente navegación de ruta
 *     (el usuario ya está cambiando de sección, así que el refresco es transparente).
 *  4) `FronteraError` usa `recargaSegura()` como red de seguridad para el caso en que
 *     el chunk ya no exista antes de que el poll lo detecte.
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

/** Pide `/index.html` fresco y extrae el `src` de su <script type="module"> de entrada. */
async function entradaDesplegada(signal?: AbortSignal): Promise<string | null> {
  const res = await fetch("/index.html", { cache: "no-store", signal });
  if (!res.ok) return null;
  const html = await res.text();
  const m = html.match(/<script[^>]+type="module"[^>]+src="([^"]+)"/i);
  return m?.[1] ?? null;
}

/**
 * Hook (móntalo UNA vez en el cascarón): vigila si hay una versión nueva desplegada y,
 * cuando la hay, recarga en la siguiente navegación de ruta (transparente). No hace nada
 * en desarrollo (la entrada es `/src/main.tsx`, no un asset con hash).
 */
export function useDetectorActualizacion(): void {
  const location = useLocation();
  const base = React.useRef<string | null>(null);
  const pendiente = React.useRef(false);

  // Captura la entrada actual una sola vez, al montar.
  React.useEffect(() => {
    base.current = entradaActual();
  }, []);

  const comprobar = React.useCallback(async (signal?: AbortSignal) => {
    const actual = base.current;
    // Solo aplica a builds de producción (assets con hash). En dev no hay nada que hacer.
    if (!actual || !actual.includes("/assets/")) return;
    try {
      const desplegada = await entradaDesplegada(signal);
      if (desplegada && desplegada !== actual) pendiente.current = true;
    } catch {
      // Red caída / offline / petición abortada: reintentaremos en el próximo ciclo.
    }
  }, []);

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

  // Recarga SUAVE: al cambiar de ruta, si ya detectamos versión nueva, recargamos ahora
  // (el usuario está navegando de todos modos, así que trae los chunks nuevos sin fricción).
  React.useEffect(() => {
    if (pendiente.current) recargaSegura();
  }, [location.pathname]);
}

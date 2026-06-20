import * as React from "react";

/**
 * Detector GLOBAL de conexión degradada DURANTE el uso (la app ya montada, a diferencia del
 * arranque que cubre `PuertaSesion`). Cuenta los fallos de RED consecutivos —sin respuesta
 * (`ApiError` status 0) o 502/503/504 del proxy (back desplegando/caído)— que reportan los
 * callbacks del `QueryCache` (en `main.tsx`). Al pasar el umbral marca el estado degradado,
 * que el `AppShell` muestra como un banner sticky; el primer éxito de cualquier query lo
 * limpia (la app sigue reintentando de fondo). Vive FUERA de React (el `QueryClient` se crea
 * fuera del árbol) con un store mínimo + `useSyncExternalStore`.
 */

/** Fallos de red SEGUIDOS antes de avisar: evita parpadear el banner ante un blip puntual. */
const UMBRAL_BANNER = 2;

let fallosConsecutivos = 0;
let degradada = false;
const oyentes = new Set<() => void>();

function emitir(): void {
  for (const oyente of oyentes) oyente();
}

/** Un fetch falló por red/proxy. Suma al contador y enciende el banner al cruzar el umbral. */
export function registrarFalloRed(): void {
  fallosConsecutivos += 1;
  if (fallosConsecutivos >= UMBRAL_BANNER && !degradada) {
    degradada = true;
    emitir();
  }
}

/** Un fetch volvió a responder: reinicia el contador y apaga el banner si estaba encendido. */
export function registrarExitoRed(): void {
  fallosConsecutivos = 0;
  if (degradada) {
    degradada = false;
    emitir();
  }
}

function suscribir(cb: () => void): () => void {
  oyentes.add(cb);
  return () => {
    oyentes.delete(cb);
  };
}

function leer(): boolean {
  return degradada;
}

/** `true` cuando hay conexión degradada sostenida (varios fallos de red sin éxito de por medio). */
export function useConexionDegradada(): boolean {
  return React.useSyncExternalStore(suscribir, leer, leer);
}

/**
 * Uso de las cuentas de Claude del servidor, AISLADO en un solo módulo (cliente + hook).
 *
 * El indicador sutil del sidebar (`IndicadorUso`) consume esto. La llamada de red vive aquí y solo
 * aquí: cliente tipado + hook de react-query + la ruta como constante.
 *
 * Forma de respuesta ACORDADA con el backend (`GET /api/sistema/uso`, cualquier autenticado):
 *   { cuentas: [{ cuenta, etiqueta, marcas, conectada, semana_pct, sesion_5h_pct, sonnet_pct,
 *       reset_semana_iso, reset_semana_txt, actualizado_ts, al_100, alerta_roja }, ...] }
 * El back devuelve SOLO las cuentas que el usuario puede ver (suelo de autorización por marcas);
 * el frontend elige cuál(es) MOSTRAR según el selector de marca activo. El back cachea (no ejecuta
 * `claude` por request), así que sondeamos con holgura.
 */
import { useQuery } from "@tanstack/react-query";

import { peticion } from "@/lib/api/_core";

// Relativa a `BASE_API` (`/api`), así que la URL servida es `/api/sistema/uso` (el endpoint que
// LEE el último snapshot de `cuenta_uso` por cuenta). Centralizada aquí a propósito.
export const RUTA_USO_CUENTA = "/sistema/uso";

/** Cadencia del sondeo (ms). Moderada: el back ya cachea el medidor. */
const INTERVALO_MS = 150_000;

/** Clave de caché del uso de la cuenta. */
export const CLAVE_USO_CUENTA = ["uso-cuenta"] as const;

/**
 * Lectura del medidor de uso de UNA cuenta de Claude del servidor. Porcentajes en 0–100 o `null`
 * cuando no hay dato (cuenta sin medidor todavía / lectura aún sin resolver).
 */
export interface UsoCuenta {
  /** Selector de la cuenta de Claude ('a' | 'b'). */
  cuenta: string;
  /** Nombre legible de la cuenta = sus marcas unidas (p. ej. "UnoTV · Nación Gamer"). */
  etiqueta: string;
  /** Ids canónicos de las marcas que sirve la cuenta (para casar el selector de marca activo). */
  marcas: string[];
  /** ¿Hay una cuenta de Claude conectada en el servidor? */
  conectada: boolean;
  /** % usado de la ventana SEMANAL (all models). `null` si no hay dato. */
  semana_pct: number | null;
  /** % usado de la ventana de SESIÓN de 5 h. `null` si no hay dato. */
  sesion_5h_pct: number | null;
  /** % usado de la cuota específica de Sonnet, si el plan la reporta. `null` si no. */
  sonnet_pct: number | null;
  /** Instante UTC ISO del reset de la ventana semanal. `null` si no se conoce. */
  reset_semana_iso: string | null;
  /** Texto crudo del reset semanal tal cual lo da el CLI. `null` si no hay. */
  reset_semana_txt: string | null;
  /** Epoch (segundos) de cuándo se capturó el medidor mostrado. `null` si nunca. */
  actualizado_ts: number | null;
  /** `true` si alguna ventana está al 100 %. */
  al_100: boolean;
  /** `true` si hay que pintar la cuenta en ROJO (sin cuenta o al 100 %). */
  alerta_roja: boolean;
  /** Cupo del DÍA (gate diario) del límite que primero se agota -> barra «24h». */
  dia: UsoCuentaDia;
}

/** Cupo del día (gate diario) de una cuenta: el límite que PRIMERO se agota y su margen de hoy. */
export interface UsoCuentaDia {
  /** % del cupo SEMANAL de ese límite consumido HOY (jornada CDMX). `null` si no hay dato. */
  consumo_pct: number | null;
  /** Umbral del día de ese límite (cupo base + los +10 % aceptados). */
  umbral_pct: number;
  /** Cuál ata: "semanal" (all models) o "sonnet". */
  limite: string;
  /** `true` si el consumo de hoy ya alcanzó el umbral (gate pausando). */
  pausado: boolean;
}

/** Respuesta del endpoint: las cuentas que el usuario puede ver (puede ir vacía). */
export interface RespuestaUsoCuentas {
  cuentas: UsoCuenta[];
}

/** Cliente tipado del endpoint de uso. Único punto de red del indicador. */
export function obtenerUsoCuenta(signal?: AbortSignal): Promise<RespuestaUsoCuentas> {
  return peticion<RespuestaUsoCuentas>(RUTA_USO_CUENTA, { signal });
}

/**
 * Hook del uso de las cuentas. `enabled` permite no sondear cuando el indicador no se muestra: el
 * componente lo gobierna. Reintenta poco y refresca al volver el foco.
 */
export function useUsoCuenta(enabled = true) {
  return useQuery({
    queryKey: CLAVE_USO_CUENTA,
    queryFn: ({ signal }) => obtenerUsoCuenta(signal),
    enabled,
    refetchInterval: INTERVALO_MS,
    refetchOnWindowFocus: true,
    retry: false,
  });
}

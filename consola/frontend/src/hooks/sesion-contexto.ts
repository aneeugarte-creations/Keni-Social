import * as React from "react";

import type { MotivoCaida } from "@/lib/api";
import type { UsuarioSesion } from "@/types";

/**
 * Contexto de sesión de la Consola. El `SesionProvider` (en `use-sesion.tsx`)
 * resuelve el usuario actual con `GET /api/auth/me` al cargar la app y expone
 * las acciones de sesión. Las páginas leen el usuario y su rol con `useSesion`.
 *
 * Se separa el contexto (este archivo) del provider (el .tsx) para cumplir la
 * regla `react-refresh/only-export-components` del repo, igual que el tema.
 */
export interface ValorSesion {
  /** Usuario autenticado, o `null` si no hay sesión (mostrar login). */
  usuario: UsuarioSesion | null;
  /** `true` mientras se resuelve el `me` inicial (pantalla de carga). */
  cargando: boolean;
  /**
   * `true` cuando el `me` inicial NO pudo resolverse por un fallo que NO es "sin sesión"
   * (red caída, timeout, 502/503/504 del proxy): el back puede estar desplegándose o caído.
   * La puerta muestra una pantalla de estado degradado honesto (reintento), no el login: un
   * 401 limpio sí lleva al login. Se apaga en cuanto un `me` vuelve a responder (200 o 401).
   */
  errorConexion: boolean;
  /**
   * Por qué cayó la conexión, cuando `errorConexion` es `true`: `deploy` (actualización
   * transitoria, vuelve sola) o `incidente` (avería). Lo dicta el campo `motivo` del 503 del
   * front. La pantalla degradada elige con esto entre la barra de progreso (deploy) y el aviso
   * honesto "no disponible, equipo avisado" (incidente). `null`/ausente cuando no hay caída.
   * Opcional para no obligar a cada mock de test a declararlo (los consumidores leen `?? null`).
   */
  motivoCaida?: MotivoCaida | null;
  /**
   * Inicia sesión; el backend pone la cookie. Lanza `ApiError` (401 genérico).
   * Devuelve `{ mfaRequerido: true }` cuando el backend pide un segundo factor (MFA ON y
   * cuenta con ≥1 passkey): en ese caso NO hay sesión todavía y la UI debe correr la ceremonia
   * de passkey (`verificarConPasskey`).
   * `{ mfaRequerido: false }` => sesión iniciada (flujo de hoy).
   */
  iniciarSesion: (usuario: string, password: string) => Promise<{ mfaRequerido: boolean }>;
  /**
   * Completa el login con la LLAVE DE ACCESO (passkey): pide opciones, corre la ceremonia
   * WebAuthn (Face ID / huella / llave) y verifica la assertion contra el backend.
   */
  verificarConPasskey: () => Promise<void>;
  /**
   * Inicia sesión SIN contraseña con la LLAVE DE ACCESO (passkey passwordless): pide opciones
   * públicas, corre la ceremonia WebAuthn y verifica la assertion; si casa, abre la sesión.
   * Lanza `ApiError` (401 si ninguna llave es reconocida) o `DOMException` si se cancela.
   */
  entrarConPasskey: () => Promise<void>;
  /** Cierra sesión (POST /api/auth/logout) y vuelve al login. */
  cerrarSesion: () => Promise<void>;
  /** Refresca el usuario actual desde el backend (tras cambiar contraseña). */
  refrescar: () => Promise<void>;
}

export const SesionContexto = React.createContext<ValorSesion | null>(null);

/** Hook para leer la sesión actual. Debe usarse dentro del `SesionProvider`. */
export function useSesion(): ValorSesion {
  const valor = React.useContext(SesionContexto);
  if (!valor) {
    throw new Error("useSesion debe usarse dentro de <SesionProvider>.");
  }
  return valor;
}

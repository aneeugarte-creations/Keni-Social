import * as React from "react";

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
   * Inicia sesión; el backend pone la cookie. Lanza `ApiError` (401 genérico).
   * Devuelve `{ mfaRequerido: true }` cuando el backend pide un segundo factor (MFA ON y
   * cuenta con ≥1 passkey): en ese caso NO hay sesión todavía y la UI debe correr la ceremonia
   * de passkey (`verificarConPasskey`) o pedir un código de recuperación (`verificarConCodigo`).
   * `{ mfaRequerido: false }` => sesión iniciada (flujo de hoy).
   */
  iniciarSesion: (usuario: string, password: string) => Promise<{ mfaRequerido: boolean }>;
  /**
   * Completa el login con la LLAVE DE ACCESO (passkey): pide opciones, corre la ceremonia
   * WebAuthn (Face ID / huella / llave) y verifica la assertion contra el backend.
   */
  verificarConPasskey: () => Promise<void>;
  /** Completa el login con un código de recuperación (fallback sin passkey). */
  verificarConCodigo: (codigo: string) => Promise<void>;
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

import * as React from "react";

import { api, ApiError } from "@/lib/api";
import type { UsuarioSesion } from "@/types";

import { SesionContexto, type ValorSesion } from "./sesion-contexto";

/**
 * Puente Sesión ↔ QueryClient. El `QueryClient` se crea FUERA de React (en `main.tsx`),
 * así que no puede leer el contexto de sesión. El provider registra aquí un callback que
 * limpia la sesión; el manejador global de errores 401 lo invoca para devolver la app al
 * login cuando la sesión expira a mitad de uso. Module-level y mono-instancia (un solo
 * provider en el árbol).
 */
let limpiarSesionGlobal: (() => void) | null = null;

/** Llama el manejador global de 401: limpia la sesión (vuelve al login). No-op si no hay provider. */
export function marcarSesionExpirada(): void {
  limpiarSesionGlobal?.();
}

/**
 * Provider de sesión. Al montar, llama `GET /api/auth/me`:
 *   - 200 → hay sesión viva: guarda el usuario y entra a la app.
 *   - 401 → no hay sesión: deja `usuario` en `null` (se muestra el login).
 *
 * `iniciarSesion` delega en `POST /api/auth/login` (el backend pone la cookie de
 * sesión); con la respuesta guardamos el usuario. `cerrarSesion` hace logout y
 * limpia el estado. La autenticación va por cookie; las mutaciones siguen
 * mandando las cabeceras de auth que ya añade `api.ts` (#134).
 */
export function SesionProvider({ children }: { children: React.ReactNode }) {
  const [usuario, setUsuario] = React.useState<UsuarioSesion | null>(null);
  const [cargando, setCargando] = React.useState(true);

  const cargarMe = React.useCallback(async () => {
    try {
      const { usuario } = await api.me();
      setUsuario(usuario);
    } catch (e) {
      // 401 = sin sesión (esperado): mostramos el login sin ruido. Cualquier
      // otro error también cae al login (no podemos afirmar que haya sesión).
      if (!(e instanceof ApiError)) {
        // Error inesperado de red: lo dejamos sin sesión igualmente.
      }
      setUsuario(null);
    }
  }, []);

  React.useEffect(() => {
    let vivo = true;
    void (async () => {
      await cargarMe();
      if (vivo) setCargando(false);
    })();
    return () => {
      vivo = false;
    };
  }, [cargarMe]);

  // Registra el puente para que el manejador global de 401 (en `main.tsx`) pueda
  // limpiar la sesión y devolver la app al login cuando una sesión expira a media sesión.
  React.useEffect(() => {
    limpiarSesionGlobal = () => setUsuario(null);
    return () => {
      limpiarSesionGlobal = null;
    };
  }, []);

  const iniciarSesion = React.useCallback(async (nombre: string, password: string) => {
    const { usuario } = await api.login({ usuario: nombre, password });
    setUsuario(usuario);
  }, []);

  const cerrarSesion = React.useCallback(async () => {
    try {
      await api.logout();
    } finally {
      // Aunque el logout falle, limpiamos el estado local: la cookie ya no nos
      // sirve para mutar y el usuario espera volver al login.
      setUsuario(null);
    }
  }, []);

  const refrescar = React.useCallback(async () => {
    await cargarMe();
  }, [cargarMe]);

  const valor = React.useMemo<ValorSesion>(
    () => ({ usuario, cargando, iniciarSesion, cerrarSesion, refrescar }),
    [usuario, cargando, iniciarSesion, cerrarSesion, refrescar],
  );

  return <SesionContexto.Provider value={valor}>{children}</SesionContexto.Provider>;
}

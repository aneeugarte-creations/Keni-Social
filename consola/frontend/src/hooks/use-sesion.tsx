import { startAuthentication } from "@simplewebauthn/browser";
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
 * mandando las cabeceras de auth que ya añade `api.ts`.
 */
export function SesionProvider({ children }: { children: React.ReactNode }) {
  const [usuario, setUsuario] = React.useState<UsuarioSesion | null>(null);
  const [cargando, setCargando] = React.useState(true);
  const [errorConexion, setErrorConexion] = React.useState(false);

  const cargarMe = React.useCallback(async () => {
    try {
      const { usuario } = await api.me();
      setUsuario(usuario);
      setErrorConexion(false);
    } catch (e) {
      // 401 = sin sesión (esperado): mostramos el login sin alarmas y limpiamos el
      // estado degradado (el back respondió). Cualquier OTRO fallo (red/timeout =>
      // `ApiError` status 0, o 502/503/504 del proxy mientras el back despliega/cae)
      // NO es "sin sesión": no mandamos al login, encendemos el estado degradado
      // honesto para que la puerta ofrezca reintento en vez de un login engañoso.
      if (e instanceof ApiError && e.status === 401) {
        setUsuario(null);
        setErrorConexion(false);
      } else {
        setErrorConexion(true);
      }
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
    const respuesta = await api.login({ usuario: nombre, password });
    // Con MFA activo el backend devuelve `{mfa_required:true}` y NO una sesión: dejamos el
    // usuario en `null` (sigue fuera) y avisamos a la UI para que corra la ceremonia de passkey.
    // Estrechamos por la presencia de `usuario` (discrimina la unión sesión vs MFA-pendiente).
    if (!("usuario" in respuesta)) {
      return { mfaRequerido: true };
    }
    setUsuario(respuesta.usuario);
    return { mfaRequerido: false };
  }, []);

  const verificarConPasskey = React.useCallback(async () => {
    // 2º paso (passkey): pedimos opciones (el backend fija la cookie de challenge), corremos
    // la ceremonia WebAuthn en el navegador y enviamos la assertion. py_webauthn la verifica
    // contra el challenge de la cookie y, si cuadra, emite la sesión real y devuelve el usuario.
    const optionsJSON = await api.mfaLoginOpciones();
    const assertion = await startAuthentication({
      // py_webauthn ya devuelve JSON spec-compliant; lo pasamos tal cual.
      optionsJSON: optionsJSON as unknown as Parameters<typeof startAuthentication>[0]["optionsJSON"],
    });
    const { usuario } = await api.mfaVerify({ assertion });
    setUsuario(usuario);
  }, []);

  const entrarConPasskey = React.useCallback(async () => {
    // Login passwordless: pedimos opciones públicas (el backend fija la cookie de challenge),
    // corremos la ceremonia WebAuthn y enviamos la assertion. Si una credencial conocida casa,
    // el backend abre la sesión real y devuelve el usuario.
    const optionsJSON = await api.passkeyOpciones();
    const assertion = await startAuthentication({
      optionsJSON: optionsJSON as unknown as Parameters<typeof startAuthentication>[0]["optionsJSON"],
    });
    const { usuario } = await api.passkeyVerify(assertion);
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
    () => ({
      usuario,
      cargando,
      errorConexion,
      iniciarSesion,
      verificarConPasskey,
      entrarConPasskey,
      cerrarSesion,
      refrescar,
    }),
    [
      usuario,
      cargando,
      errorConexion,
      iniciarSesion,
      verificarConPasskey,
      entrarConPasskey,
      cerrarSesion,
      refrescar,
    ],
  );

  return <SesionContexto.Provider value={valor}>{children}</SesionContexto.Provider>;
}

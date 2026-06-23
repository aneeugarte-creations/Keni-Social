// Fragmento del cliente API: dominio «auth». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoCambiarPassword,
  CuerpoLogin,
  OpcionesCeremoniaWebauthn,
  RespuestaLoginMfa,
  RespuestaMfaCredenciales,
  RespuestaMfaRegistro,
  RespuestaSesion,
} from "@/types";

export const apiAuth = {
  // --- Autenticación (sesión por cookie) ---
  // El login depende de la cookie de sesión que pone el backend; `api.ts` ya
  // manda las cabeceras de auth en cada petición para las mutaciones.
  // `me` se llama al cargar la app: 200 => sesión viva; 401 => mostrar login.
  // Con MFA activo (flag `KENI_CONSOLA_MFA` ON), el login puede devolver `{mfa_required:true}`
  // en vez de `{usuario}`: el llamante debe entonces correr la ceremonia de passkey
  // (`mfaLoginOpciones` -> `startAuthentication` -> `mfaVerify`).
  login: (cuerpo: CuerpoLogin) =>
    peticion<RespuestaSesion | RespuestaLoginMfa>("/auth/login", { metodo: "POST", json: cuerpo }),
  logout: () => peticion<void>("/auth/logout", { metodo: "POST" }),

  // --- Login PASSWORDLESS con llave de acceso (passkey) ---
  // Atajo sin contraseña: el backend abre una ceremonia de autenticación sin sesión previa.
  //   1) `passkeyOpciones` -> optionsJSON para `startAuthentication({optionsJSON})` (fija la
  //      cookie de challenge). 503 si la maquinaria MFA está apagada.
  //   2) `passkeyVerify(assertion)` con lo que devuelve el navegador -> abre la sesión y
  //      devuelve `{usuario}`. 401 si ninguna llave casa; 429 si hay rate-limit por IP.
  passkeyOpciones: () =>
    peticion<OpcionesCeremoniaWebauthn>("/auth/passkey/opciones", { metodo: "POST" }),
  passkeyVerify: (assertion: unknown) =>
    peticion<RespuestaSesion>("/auth/passkey/verify", { metodo: "POST", json: { assertion } }),
  me: (signal?: AbortSignal) => peticion<RespuestaSesion>("/auth/me", { signal }),
  cambiarPassword: (cuerpo: CuerpoCambiarPassword) =>
    peticion<void>("/auth/cambiar-password", { metodo: "POST", json: cuerpo }),
  // Edita SOLO el nombre humano propio (nunca rol/login/marcas). 400 si es inválido (>120
  // caracteres o no-texto); 401 sin sesión real.
  actualizarMiPerfil: (nombre: string) =>
    peticion<{ nombre: string }>("/auth/me", { metodo: "PATCH", json: { nombre } }),
  // Cambia la ZONA HORARIA de display propia (IANA, p. ej. "Europe/Madrid"). 400 si no es una
  // zona tzdb válida; 401 sin sesión real. Devuelve la zona ya guardada.
  actualizarMiZona: (zona_horaria: string) =>
    peticion<{ zona_horaria: string }>("/auth/me", { metodo: "PATCH", json: { zona_horaria } }),

  // --- MFA (segundo factor PASSKEYS / WebAuthn; gateado por `KENI_CONSOLA_MFA`) ---
  // Ceremonia de LOGIN (usa la cookie pre-auth + challenge que el backend gestiona):
  //   1) `mfaLoginOpciones` -> opciones spec-JSON para `startAuthentication({optionsJSON})`.
  //   2) `mfaVerify({assertion})` con la credencial que devuelve el navegador.
  mfaLoginOpciones: () =>
    peticion<OpcionesCeremoniaWebauthn>("/auth/mfa/login/opciones", { metodo: "POST" }),
  mfaVerify: (cuerpo: { assertion: unknown }) =>
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
  mfaRenombrarCredencial: (id: string, nombre: string) =>
    peticion<void>(`/auth/mfa/credenciales/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: { nombre },
    }),
  mfaBorrarCredencial: (id: string) =>
    peticion<void>(`/auth/mfa/credenciales/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  mfaDisable: (passwordActual: string) =>
    peticion<void>("/auth/mfa/disable", {
      metodo: "POST",
      json: { password_actual: passwordActual },
    }),

};

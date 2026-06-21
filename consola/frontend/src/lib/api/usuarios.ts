// Fragmento del cliente API: dominio «usuarios». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarUsuario,
  CuerpoConfiguracionUsuarios,
  CuerpoCrearTokenMcp,
  CuerpoCrearUsuario,
  OpcionesCeremoniaWebauthn,
  RespuestaActualizarConfiguracion,
  RespuestaConfiguracionUsuarios,
  RespuestaCrearTokenMcp,
  RespuestaMfaCredenciales,
  RespuestaMfaRegistro,
  RespuestaTokensMcp,
  RespuestaUsuarios,
  UsuarioAdmin,
} from "@/types";

export const apiUsuarios = {
  // --- Usuarios (solo admin; 403 si no) ---
  usuarios: (signal?: AbortSignal) => peticion<RespuestaUsuarios>("/usuarios", { signal }),
  crearUsuario: (cuerpo: CuerpoCrearUsuario) =>
    peticion<UsuarioAdmin>("/usuarios", { metodo: "POST", json: cuerpo }),
  actualizarUsuario: (id: string, cuerpo: CuerpoActualizarUsuario) =>
    peticion<UsuarioAdmin>(`/usuarios/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarUsuario: (id: string) =>
    peticion<void>(`/usuarios/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Llaves de acceso (passkeys) de OTRA persona (solo superadmin) ---
  // Lista las llaves de una cuenta (sin secretos) y borra una concreta: rescate cuando alguien
  // pierde un dispositivo o no puede usar su passkey en un equipo. El reset total va por el PATCH
  // de usuario (`mfa_reset`).
  usuarioPasskeys: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaMfaCredenciales>(`/usuarios/${encodeURIComponent(id)}/passkeys`, { signal }),
  borrarPasskeyUsuario: (id: string, credId: string) =>
    peticion<void>(
      `/usuarios/${encodeURIComponent(id)}/passkeys/${encodeURIComponent(credId)}`,
      { metodo: "DELETE" },
    ),

  // Alta ASISTIDA: el superadmin LANZA la ceremonia (QR) para registrar una passkey en el
  // teléfono de la persona (Face ID/huella). El backend fuerza «otro dispositivo» (cross-platform)
  // para que salga el QR y la clave nazca en el móvil de la persona, no en el equipo del superadmin.
  //   1) opciones -> optionsJSON para `startRegistration({optionsJSON})` (muestra el QR).
  //   2) verificar(credential) -> guarda la llave CONTRA la cuenta destino.
  usuarioPasskeyAsistidaOpciones: (id: string) =>
    peticion<OpcionesCeremoniaWebauthn>(
      `/auth/passkey-asistida/${encodeURIComponent(id)}/opciones`,
      { metodo: "POST" },
    ),
  usuarioPasskeyAsistidaVerificar: (id: string, credential: unknown, nombre: string) =>
    peticion<RespuestaMfaRegistro>(
      `/auth/passkey-asistida/${encodeURIComponent(id)}/verificar`,
      { metodo: "POST", json: { credential, nombre } },
    ),

  // --- Tokens del MCP por identidad (self-service de la cuenta en sesión) ---
  // Cada quien emite/lista/revoca SUS propios tokens del MCP (bearer para `/mcp`). El listado
  // nunca trae el secreto; `crear` lo devuelve UNA sola vez; `revocar` lo recibe por su valor.
  tokensMcp: (signal?: AbortSignal) =>
    peticion<RespuestaTokensMcp>("/usuarios/tokens-mcp", { signal }),
  crearTokenMcp: (cuerpo: CuerpoCrearTokenMcp) =>
    peticion<RespuestaCrearTokenMcp>("/usuarios/tokens-mcp", { metodo: "POST", json: cuerpo }),
  revocarTokenMcp: (token: string) =>
    peticion<void>(`/usuarios/tokens-mcp/${encodeURIComponent(token)}`, { metodo: "DELETE" }),

  // --- Configuración GLOBAL de seguridad (solo superadmin) ---
  configuracionUsuarios: (signal?: AbortSignal) =>
    peticion<RespuestaConfiguracionUsuarios>("/usuarios/configuracion", { signal }),
  actualizarConfiguracionUsuarios: (cuerpo: CuerpoConfiguracionUsuarios) =>
    peticion<RespuestaActualizarConfiguracion>("/usuarios/configuracion", {
      metodo: "PATCH",
      json: cuerpo,
    }),
};

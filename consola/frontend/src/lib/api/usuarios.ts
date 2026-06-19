// Fragmento del cliente API: dominio «usuarios». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarUsuario,
  CuerpoConfiguracionUsuarios,
  CuerpoCrearUsuario,
  RespuestaActualizarConfiguracion,
  RespuestaConfiguracionUsuarios,
  RespuestaMfaCredenciales,
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
  // pierde un dispositivo o no puede usar su passkey en un equipo. Crear una por otro NO existe
  // (la clave privada vive en el dispositivo del propio usuario); el reset total va por el PATCH
  // de usuario (`mfa_reset`).
  usuarioPasskeys: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaMfaCredenciales>(`/usuarios/${encodeURIComponent(id)}/passkeys`, { signal }),
  borrarPasskeyUsuario: (id: string, credId: string) =>
    peticion<void>(
      `/usuarios/${encodeURIComponent(id)}/passkeys/${encodeURIComponent(credId)}`,
      { metodo: "DELETE" },
    ),

  // --- Configuración GLOBAL de seguridad (solo superadmin) ---
  configuracionUsuarios: (signal?: AbortSignal) =>
    peticion<RespuestaConfiguracionUsuarios>("/usuarios/configuracion", { signal }),
  actualizarConfiguracionUsuarios: (cuerpo: CuerpoConfiguracionUsuarios) =>
    peticion<RespuestaActualizarConfiguracion>("/usuarios/configuracion", {
      metodo: "PATCH",
      json: cuerpo,
    }),
};

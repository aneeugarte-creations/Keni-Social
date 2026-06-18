// Fragmento del cliente API: dominio «usuarios». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarUsuario,
  CuerpoConfiguracionUsuarios,
  CuerpoCrearUsuario,
  RespuestaActualizarConfiguracion,
  RespuestaConfiguracionUsuarios,
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

  // --- Configuración GLOBAL de seguridad (solo superadmin) ---
  configuracionUsuarios: (signal?: AbortSignal) =>
    peticion<RespuestaConfiguracionUsuarios>("/usuarios/configuracion", { signal }),
  actualizarConfiguracionUsuarios: (cuerpo: CuerpoConfiguracionUsuarios) =>
    peticion<RespuestaActualizarConfiguracion>("/usuarios/configuracion", {
      metodo: "PATCH",
      json: cuerpo,
    }),
};

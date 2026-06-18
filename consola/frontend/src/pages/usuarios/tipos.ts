import { ApiError } from "@/lib/api";
import type { RolUsuario } from "@/types";

export const CLAVE_USUARIOS = ["usuarios"] as const;
export const CLAVE_OPCIONES_MARCAS = ["usuarios", "opciones", "marcas"] as const;
export const CLAVE_CONFIG_USUARIOS = ["usuarios", "configuracion"] as const;

export const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

export const ROLES: RolUsuario[] = ["editor", "admin"];

/** Centinelas de Select (shadcn no admite SelectItem con value=""). */
export const SIN_CARGO = "__sin_cargo__";
export const SIN_SUPERIOR = "__sin_superior__";

/**
 * Claves de la configuración GLOBAL de seguridad (`/api/usuarios/configuracion`). Espejo de las
 * vars del backend; la página de configuración las mapea a sus secciones y el detalle de usuario
 * lee de aquí el mínimo de contraseña efectivo.
 */
export const CLAVE_MFA = "KENI_CONSOLA_MFA";
export const CLAVE_MFA_ADMIN = "KENI_CONSOLA_MFA_ADMIN";
export const CLAVE_SESION_HORAS = "KENI_CONSOLA_SESION_HORAS";
export const CLAVE_SESION_MAX_HORAS = "KENI_CONSOLA_SESION_MAX_HORAS";
export const CLAVE_PASSWORD_MIN = "KENI_CONSOLA_PASSWORD_MIN";

// Mínimo de contraseña: única fuente compartida (espejo del backend, que exige 12).
export { MIN_PASSWORD } from "@/lib/password";

/**
 * Código del 403 que devuelve `POST/PATCH/DELETE /api/usuarios` cuando un admin SIN passkey
 * intenta gestionar usuarios (solo con MFA configurado). El error trae mensaje en español.
 */
export const CODIGO_MFA_INSCRIPCION = "mfa_inscripcion_requerida";

/** `true` si el error es ese 403: hay que inscribir una llave de acceso antes de gestionar usuarios. */
export function esInscripcionMfaRequerida(e: unknown): boolean {
  return (
    e instanceof ApiError &&
    e.status === 403 &&
    (e.cuerpo?.codigo as string | undefined) === CODIGO_MFA_INSCRIPCION
  );
}

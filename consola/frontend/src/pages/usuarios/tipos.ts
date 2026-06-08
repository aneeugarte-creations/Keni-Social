import type { RolUsuario } from "@/types";

export const CLAVE_USUARIOS = ["usuarios"] as const;
export const CLAVE_OPCIONES_MARCAS = ["usuarios", "opciones", "marcas"] as const;

export const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

export const ROLES: RolUsuario[] = ["editor", "admin"];

/** Centinelas de Select (shadcn no admite SelectItem con value=""). */
export const SIN_CARGO = "__sin_cargo__";
export const SIN_SUPERIOR = "__sin_superior__";

export const MIN_PASSWORD = 8;

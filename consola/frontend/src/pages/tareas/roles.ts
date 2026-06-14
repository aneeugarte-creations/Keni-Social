/**
 * ROLES de cobertura de un evento (Ola 2: «cobertura por roles tipados»). Cada cubridor cubre
 * UN rol del evento; el reparto find-or-create es por (evento, persona, ROL). Los roles REUSAN
 * el campo `formato` del contenido (sin migración): 'foto'/'video' ya son formatos del catálogo
 * y 'texto'/'live' son texto libre que la columna admite. El backend valida el mismo conjunto
 * (`keni_consola.estados.ROLES_COBERTURA`).
 */
export const ROLES_COBERTURA = ["foto", "video", "texto", "live"] as const;
export type RolCobertura = (typeof ROLES_COBERTURA)[number];

const ETIQUETA: Record<string, string> = {
  foto: "Foto",
  video: "Video",
  texto: "Texto",
  live: "Live",
};

/** Etiqueta humana de un rol/`formato` ("Foto"/"Video"/…). Vacío/desconocido -> "Foto" (defecto). */
export function etiquetaRol(formato: string | null | undefined): string {
  return ETIQUETA[(formato || "").toLowerCase()] ?? "Foto";
}

/**
 * Roles DISTINTOS cubiertos en un evento, en orden canónico (para el semáforo agregado por rol).
 * El `formato` vacío cuenta como 'foto' (su defecto en BD), igual que `etiquetaRol`.
 */
export function rolesCubiertos(cubridores: { formato?: string | null }[]): string[] {
  const presentes = new Set(cubridores.map((t) => (t.formato || "foto").toLowerCase()));
  return ROLES_COBERTURA.filter((r) => presentes.has(r));
}

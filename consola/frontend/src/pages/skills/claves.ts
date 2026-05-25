/**
 * Claves de React Query y helpers compartidos por la sección Skills.
 *
 * Vive en su propio módulo (sin componentes) para no romper el fast-refresh de
 * los `.tsx` y centralizar las claves de caché.
 */
import { ApiError } from "@/lib/api";
import type { TipoCampo } from "@/types";

/** Clave del catálogo de skills (gestión). */
export const CLAVE_CATALOGO_SKILLS = ["skills", "catalogo"] as const;

/** Clave del detalle de una skill del catálogo. */
export function claveSkill(id: string): readonly string[] {
  return ["skills", "catalogo", id] as const;
}

/** Texto legible del error de la API (o un fallback en español). */
export function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Etiqueta legible del grupo de una skill. */
export function etiquetaGrupo(grupo: string): string {
  return grupo === "experimentales" ? "Experimentales" : "Validadas";
}

/** Tipos de campo disponibles, con su etiqueta legible (es-MX). */
export const TIPOS_CAMPO: { id: TipoCampo; nombre: string }[] = [
  { id: "textarea", nombre: "Texto largo" },
  { id: "texto", nombre: "Texto corto" },
  { id: "select", nombre: "Selección" },
  { id: "fecha", nombre: "Fecha" },
  { id: "archivo", nombre: "Archivo" },
];

/** Etiqueta legible de un tipo de campo. */
export function etiquetaTipoCampo(tipo: TipoCampo): string {
  return TIPOS_CAMPO.find((t) => t.id === tipo)?.nombre ?? tipo;
}

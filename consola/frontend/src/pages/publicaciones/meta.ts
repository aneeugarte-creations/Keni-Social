/**
 * Metadatos compartidos de redes y estados de publicación.
 *
 * Fuente única de verdad para iconos, nombres canónicos, límites de caracteres
 * y estilos de badge, reutilizada por "Generar copy" y "Publicaciones". El
 * catálogo real (qué redes/estados/marcas hay) llega del backend vía
 * `/api/publicaciones/opciones`; aquí solo añadimos la capa visual.
 */
import { AtSign, Facebook, Instagram, Music2, Twitter, Youtube, type LucideIcon } from "lucide-react";

import type { EstadoPublicacion, Veredicto } from "@/types";

/** Metadatos visuales de una red. */
export interface MetaRed {
  /** Nombre legible por defecto (si el backend no manda otro). */
  nombre: string;
  /** Límite de caracteres canónico; `null` si no tiene. */
  limite: number | null;
  icono: LucideIcon;
}

/**
 * Catálogo canónico de redes (id -> metadatos). Los límites siguen el contrato:
 * x=280, instagram=2200, facebook=∞, tiktok=2200, youtube=∞.
 */
export const META_REDES: Record<string, MetaRed> = {
  x: { nombre: "X", limite: 280, icono: Twitter },
  instagram: { nombre: "Instagram", limite: 2200, icono: Instagram },
  facebook: { nombre: "Facebook", limite: null, icono: Facebook },
  tiktok: { nombre: "TikTok", limite: 2200, icono: Music2 },
  youtube: { nombre: "YouTube", limite: null, icono: Youtube },
};

/** Orden canónico de las redes para selección y pestañas. */
export const ORDEN_REDES = ["x", "instagram", "facebook", "tiktok", "youtube"] as const;

/** Devuelve los metadatos de una red, con un fallback razonable. */
export function metaRed(id: string): MetaRed {
  return META_REDES[id] ?? { nombre: id, limite: null, icono: AtSign };
}

/** Nombre legible de una red (con fallback al id). */
export function nombreRed(id: string): string {
  return metaRed(id).nombre;
}

/** Icono de una red (con fallback genérico). */
export function iconoRed(id: string): LucideIcon {
  return metaRed(id).icono;
}

// --- Estados ---

/** Orden de avance del ciclo de vida de una publicación. */
export const ORDEN_ESTADOS: EstadoPublicacion[] = [
  "borrador",
  "aprobado",
  "programado",
  "publicado",
];

export interface MetaEstado {
  nombre: string;
  /** Clases Tailwind para el badge (claro/oscuro). */
  clase: string;
}

export const META_ESTADOS: Record<EstadoPublicacion, MetaEstado> = {
  borrador: {
    nombre: "Borrador",
    clase: "border-transparent bg-muted text-muted-foreground",
  },
  aprobado: {
    nombre: "Aprobado",
    clase: "border-transparent bg-blue-500/15 text-blue-700 dark:text-blue-300",
  },
  programado: {
    nombre: "Programado",
    clase: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
  },
  publicado: {
    nombre: "Publicado",
    clase: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  },
};

export function metaEstado(estado: string): MetaEstado {
  return META_ESTADOS[estado as EstadoPublicacion] ?? { nombre: estado, clase: "border-transparent bg-muted text-muted-foreground" };
}

/** Estado siguiente en el ciclo de vida, o `null` si ya es el último. */
export function siguienteEstado(estado: string): EstadoPublicacion | null {
  const i = ORDEN_ESTADOS.indexOf(estado as EstadoPublicacion);
  if (i < 0 || i >= ORDEN_ESTADOS.length - 1) return null;
  return ORDEN_ESTADOS[i + 1];
}

// --- Veredictos ---

export interface MetaVeredicto {
  nombre: string;
  variante: "ok" | "aviso" | "error";
}

export const META_VEREDICTOS: Record<Exclude<Veredicto, "">, MetaVeredicto> = {
  listo: { nombre: "Listo", variante: "ok" },
  revisar: { nombre: "Revisar", variante: "aviso" },
  no_publicar: { nombre: "No publicar", variante: "error" },
};

export function metaVeredicto(veredicto: Veredicto): MetaVeredicto | null {
  if (!veredicto) return null;
  return META_VEREDICTOS[veredicto] ?? null;
}

/** Formatea una fecha ISO en es-MX (corto, con hora); tolera valores inválidos. */
export function formatearFechaHora(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

/** Formatea solo la fecha (sin hora). */
export function formatearFecha(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d);
}

/** Formatea solo la hora (HH:mm) en es-MX. */
export function formatearHora(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat("es-MX", { hour: "2-digit", minute: "2-digit" }).format(d);
}

/**
 * Convierte un ISO a un valor para `<input type="datetime-local">`
 * (`YYYY-MM-DDTHH:mm`) en hora local. Cadena vacía si no hay fecha válida.
 */
export function isoADatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/**
 * Convierte un valor de `datetime-local` (hora local) a ISO 8601. Devuelve
 * `null` para cadena vacía o valor inválido.
 */
export function datetimeLocalAIso(valor: string): string | null {
  if (!valor) return null;
  const d = new Date(valor);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

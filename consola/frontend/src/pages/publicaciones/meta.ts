/**
 * Metadatos compartidos de redes y estados de publicación.
 *
 * Capa VISUAL (iconos, nombres legibles, estilos de badge) reutilizada por
 * "Generar copy" y "Publicaciones". El catálogo real (qué redes/estados/marcas
 * hay) llega del backend vía `/api/publicaciones/opciones`; aquí solo añadimos
 * lo visual.
 *
 * LÍMITES DE CARACTERES (#112): la fuente ÚNICA de verdad de los topes es el
 * backend (`GET /api/limites`, módulo `limites_plataforma`). Este módulo NO los
 * define: mantiene una inicial (`_LIMITES_BASE`, espejo del backend) para que
 * `metaRed().limite` funcione síncronamente antes de que la app hidrate, y se
 * corrige al arrancar con `hidratarLimites(...)` (lo llama el `AppShell`). Así un
 * cambio de tope se edita en un solo sitio (el backend) sin tocar este archivo.
 */
import { AtSign, Facebook, Instagram, Music2, Youtube, type LucideIcon } from "lucide-react";

import type { EstadoPublicacion, LimiteRed, Veredicto } from "@/types";

import { IconoX } from "./IconoX";

/** Metadatos visuales de una red. */
export interface MetaRed {
  /** Nombre legible por defecto (si el backend no manda otro). */
  nombre: string;
  /** Límite de caracteres canónico; `null` si no tiene. */
  limite: number | null;
  icono: LucideIcon;
}

/** Solo la capa VISUAL de cada red (nombre por defecto + icono). */
interface VisualRed {
  nombre: string;
  icono: LucideIcon;
}

/** Capa visual canónica (id -> nombre + icono). Sin límites: esos van aparte. */
const _VISUAL_REDES: Record<string, VisualRed> = {
  x: { nombre: "X", icono: IconoX as unknown as LucideIcon },
  instagram: { nombre: "Instagram", icono: Instagram },
  facebook: { nombre: "Facebook", icono: Facebook },
  tiktok: { nombre: "TikTok", icono: Music2 },
  youtube: { nombre: "YouTube", icono: Youtube },
};

/**
 * Inicial de límites, ESPEJO de `limites_plataforma.LIMITES` en el backend. Solo
 * sirve antes de que `hidratarLimites()` traiga los valores reales de la API. Es
 * la copia que el guard de CI mantiene alineada con el backend.
 */
const _LIMITES_BASE: Record<string, number | null> = {
  x: 25000,
  instagram: 2200,
  facebook: null,
  tiktok: 4000,
  youtube: null,
};

/**
 * Caché mutable de límites (se hidrata desde `GET /api/limites` al arrancar).
 * Empieza con la inicial para que `metaRed().limite` no sea nunca incorrecto por
 * defecto; al hidratar, queda exactamente lo que diga el backend.
 */
const _limites: Record<string, number | null> = { ..._LIMITES_BASE };

/**
 * Sobrescribe la caché de límites con lo que devuelve `GET /api/limites`.
 * Idempotente: lo llama el `AppShell` una vez al arrancar la app. Tolera redes
 * nuevas que el backend añada sin tocar este archivo.
 */
export function hidratarLimites(limites: LimiteRed[]): void {
  for (const l of limites) {
    _limites[l.id] = l.limite;
  }
}

/** Límite de caracteres de una red (de la caché hidratada); `null` si no tiene. */
export function limiteRed(id: string): number | null {
  return _limites[id] ?? null;
}

/** Orden canónico de las redes para selección y pestañas. */
export const ORDEN_REDES = ["x", "instagram", "facebook", "tiktok", "youtube"] as const;

/**
 * Relación de aspecto del LIENZO de imagen de cada red, como clase Tailwind, para que
 * la vista previa del feed se parezca a cómo se ve el post en esa plataforma.
 * Regla de producto: todo POST DE FOTO es 4:5 sea cual sea la red, así que la previa va
 * en 4:5 para todas las redes de foto (ig/fb/x/yt). Solo TikTok (video vertical) es 9:16.
 * Fallback 4:5 para redes desconocidas.
 */
const _ASPECTO_REDES: Record<string, string> = {
  instagram: "aspect-[4/5]",
  facebook: "aspect-[4/5]",
  x: "aspect-[4/5]",
  tiktok: "aspect-[9/16]",
  youtube: "aspect-[4/5]",
};

/** Clase Tailwind de relación de aspecto del lienzo de imagen de una red. */
export function aspectoRed(id: string): string {
  return _ASPECTO_REDES[id] ?? "aspect-[4/5]";
}

/**
 * Tamaño de imagen recomendado por red (relación de aspecto + píxeles sugeridos), para
 * guiar al usuario. Regla de producto: el post de foto es 4:5 (1080×1350) en todas las
 * redes; solo el video vertical de TikTok usa 9:16.
 */
const _TAMANO_REDES: Record<string, { ratio: string; px: string }> = {
  instagram: { ratio: "4:5", px: "1080×1350" },
  facebook: { ratio: "4:5", px: "1080×1350" },
  x: { ratio: "4:5", px: "1080×1350" },
  tiktok: { ratio: "9:16", px: "1080×1920" },
  youtube: { ratio: "4:5", px: "1080×1350" },
};

/** Relación de aspecto y píxeles recomendados de la imagen de una red (o `null`). */
export function tamanoRed(id: string): { ratio: string; px: string } | null {
  return _TAMANO_REDES[id] ?? null;
}

/**
 * Devuelve los metadatos de una red (visual + límite vigente), con un fallback
 * razonable. El `limite` proviene de la caché hidratada desde el backend (fuente
 * única, #112), no de un valor hardcodeado en este archivo.
 */
export function metaRed(id: string): MetaRed {
  const visual = _VISUAL_REDES[id];
  if (!visual) return { nombre: id, limite: limiteRed(id), icono: AtSign };
  return { ...visual, limite: limiteRed(id) };
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

/** Orden de avance del ciclo de vida de una publicación.
 *
 * El flujo de aprobación de equipo (#9) intercala `en_revision` entre el borrador y
 * la salida: borrador → en revisión → programado → publicado. Ya no hay estado de
 * reposo `aprobado` (juntar los 2 likes auto-programa, no crea un estado intermedio).
 */
export const ORDEN_ESTADOS: EstadoPublicacion[] = [
  "borrador",
  "en_revision",
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
  en_revision: {
    nombre: "En revisión",
    clase: "border-transparent bg-violet-500/15 text-violet-700 dark:text-violet-300",
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

// --- Revisiones ---

export interface MetaRevision {
  nombre: string;
  variante: "ok" | "aviso" | "error";
}

export const META_REVISIONES: Record<Exclude<Veredicto, "">, MetaRevision> = {
  listo: { nombre: "Listo", variante: "ok" },
  revisar: { nombre: "Revisar", variante: "aviso" },
  no_publicar: { nombre: "No publicar", variante: "error" },
  // Rediseño QPC: fuente apta en la verificación permisiva pero NO verificada a fondo (aviso ⚠️).
  no_verificado: { nombre: "No verificado", variante: "aviso" },
};

/**
 * Insignia de un revision editorial. El revision de una PUBLICACIÓN es TEXTO LIBRE
 * (lo escribe el auto-verificador: "ok — confirmar marcador…", "marcar como rumor",
 * "pendiente resultado real…"); el enum cerrado solo cubría tres valores. Derivamos la
 * variante de un PREFIJO normalizado y conservamos el texto íntegro como `nombre`:
 *   - "no publicar" / "no_publicar"        → error
 *   - "marcar" / "revisar" / "pendiente"   → aviso
 *   - "ok" / "listo"                        → ok
 *   - resto (no vacío)                      → aviso (señala que hay que leerlo)
 * Devuelve `null` solo si el revision está vacío.
 */
export function metaRevision(revision: string): MetaRevision | null {
  if (!revision) return null;
  const canon = META_REVISIONES[revision as Exclude<Veredicto, "">];
  if (canon) return canon;
  const t = revision
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  let variante: MetaRevision["variante"] = "aviso";
  if (t.startsWith("no publicar") || t.startsWith("no_publicar")) variante = "error";
  else if (t.startsWith("ok") || t.startsWith("listo")) variante = "ok";
  // El nombre conserva el texto íntegro del revision (la UI lo recorta/tooltipea).
  return { nombre: revision, variante };
}

// Fechas/horas en hora CDMX: el formateo y la conversión del picker viven en
// `@/lib/fecha` (única fuente de la zona de operación). Se re-exportan aquí para
// no tocar los imports existentes (`./meta`) de las páginas de publicaciones.
export {
  datetimeLocalAIso,
  formatearFecha,
  formatearFechaHora,
  formatearHora,
  isoADatetimeLocal,
  tiempoRelativo,
} from "@/lib/fecha";

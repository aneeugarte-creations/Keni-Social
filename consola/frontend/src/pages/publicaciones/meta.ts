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
 * define: mantiene una semilla (`_LIMITES_SEMILLA`, espejo del backend) para que
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
 * Semilla de límites, ESPEJO de `limites_plataforma.LIMITES` en el backend. Solo
 * sirve antes de que `hidratarLimites()` traiga los valores reales de la API. Es
 * la copia que el guard de CI mantiene alineada con el backend.
 */
const _LIMITES_SEMILLA: Record<string, number | null> = {
  x: 280,
  instagram: 2200,
  facebook: null,
  tiktok: 4000,
  youtube: null,
};

/**
 * Caché mutable de límites (se hidrata desde `GET /api/limites` al arrancar).
 * Empieza con la semilla para que `metaRed().limite` no sea nunca incorrecto por
 * defecto; al hidratar, queda exactamente lo que diga el backend.
 */
const _limites: Record<string, number | null> = { ..._LIMITES_SEMILLA };

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
 * la vista previa del feed se parezca a cómo se ve el post en esa plataforma:
 *   - Instagram: 1:1 (feed clásico cuadrado).
 *   - Facebook:  1.91:1 (enlace/imagen horizontal).
 *   - X:         16:9.
 *   - TikTok:    9:16 (vertical).
 *   - YouTube:   16:9 (miniatura).
 * Fallback 1:1 para redes desconocidas.
 */
const _ASPECTO_REDES: Record<string, string> = {
  instagram: "aspect-square",
  facebook: "aspect-[1.91/1]",
  x: "aspect-[16/9]",
  tiktok: "aspect-[9/16]",
  youtube: "aspect-video",
};

/** Clase Tailwind de relación de aspecto del lienzo de imagen de una red. */
export function aspectoRed(id: string): string {
  return _ASPECTO_REDES[id] ?? "aspect-square";
}

/**
 * Tamaño de imagen recomendado por red (relación de aspecto + píxeles sugeridos), para
 * guiar al usuario a adaptar la foto a cada plataforma. Cada red recorta a su propio
 * formato, así que conviene subir una imagen ya pensada para ese tamaño.
 */
const _TAMANO_REDES: Record<string, { ratio: string; px: string }> = {
  instagram: { ratio: "1:1", px: "1080×1080" },
  facebook: { ratio: "1.91:1", px: "1200×630" },
  x: { ratio: "16:9", px: "1600×900" },
  tiktok: { ratio: "9:16", px: "1080×1920" },
  youtube: { ratio: "16:9", px: "1280×720" },
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
 * el aprobado: borrador → en revisión → aprobado → programado → publicado.
 */
export const ORDEN_ESTADOS: EstadoPublicacion[] = [
  "borrador",
  "en_revision",
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
  en_revision: {
    nombre: "En revisión",
    clase: "border-transparent bg-violet-500/15 text-violet-700 dark:text-violet-300",
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
  // Rediseño QPC: fuente apta en la criba permisiva pero NO verificada a fondo (aviso ⚠️).
  no_verificado: { nombre: "No verificado", variante: "aviso" },
};

/**
 * Insignia de un veredicto editorial. El veredicto de una PUBLICACIÓN es TEXTO LIBRE
 * (lo escribe el auto-verificador: "ok — confirmar marcador…", "marcar como rumor",
 * "pendiente resultado real…"); el enum cerrado solo cubría tres valores. Derivamos la
 * variante de un PREFIJO normalizado y conservamos el texto íntegro como `nombre`:
 *   - "no publicar" / "no_publicar"        → error
 *   - "marcar" / "revisar" / "pendiente"   → aviso
 *   - "ok" / "listo"                        → ok
 *   - resto (no vacío)                      → aviso (señala que hay que leerlo)
 * Devuelve `null` solo si el veredicto está vacío.
 */
export function metaVeredicto(veredicto: string): MetaVeredicto | null {
  if (!veredicto) return null;
  const canon = META_VEREDICTOS[veredicto as Exclude<Veredicto, "">];
  if (canon) return canon;
  const t = veredicto
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  let variante: MetaVeredicto["variante"] = "aviso";
  if (t.startsWith("no publicar") || t.startsWith("no_publicar")) variante = "error";
  else if (t.startsWith("ok") || t.startsWith("listo")) variante = "ok";
  // El nombre conserva el texto íntegro del veredicto (la UI lo recorta/tooltipea).
  return { nombre: veredicto, variante };
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
 * Tiempo relativo legible en es-MX (p. ej. "hace 5 min", "en 2 h"). Usa
 * `Intl.RelativeTimeFormat`; tolera valores vacíos/inválidos devolviendo "".
 */
export function tiempoRelativo(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const seg = Math.round((d.getTime() - Date.now()) / 1000);
  const abs = Math.abs(seg);
  const rtf = new Intl.RelativeTimeFormat("es-MX", { numeric: "auto" });
  const divisiones: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [3600, "minute"],
    [86400, "hour"],
    [604800, "day"],
    [2629800, "week"],
    [31557600, "month"],
    [Infinity, "year"],
  ];
  const factores: Record<string, number> = {
    second: 1,
    minute: 60,
    hour: 3600,
    day: 86400,
    week: 604800,
    month: 2629800,
    year: 31557600,
  };
  for (const [umbral, unidad] of divisiones) {
    if (abs < umbral) {
      return rtf.format(Math.round(seg / factores[unidad]), unidad);
    }
  }
  return rtf.format(Math.round(seg / factores.year), "year");
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

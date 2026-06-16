/**
 * Metadatos visuales de las plataformas del dashboard de Marcas y de la conexión
 * Postproxy. El catálogo visual de publicaciones (`pages/publicaciones/meta.ts`)
 * solo cubre las 5 redes que el equipo PUBLICA (x/instagram/facebook/tiktok/
 * youtube); Postproxy soporta más (linkedin, threads, pinterest, bluesky,
 * telegram, google_business, twitter). Aquí completamos nombre + icono para TODAS
 * con un fallback razonable, sin duplicar la capa de límites/aspecto.
 */
import {
  AtSign,
  Building2,
  Cloud,
  Facebook,
  Hash,
  Instagram,
  Linkedin,
  type LucideIcon,
  MessageCircle,
  Music2,
  Send,
  Twitter,
  Youtube,
} from "lucide-react";

interface VisualPlataforma {
  nombre: string;
  icono: LucideIcon;
}

/** Capa visual por plataforma (id de Postproxy → nombre + icono lucide). */
const VISUAL: Record<string, VisualPlataforma> = {
  facebook: { nombre: "Facebook", icono: Facebook },
  instagram: { nombre: "Instagram", icono: Instagram },
  tiktok: { nombre: "TikTok", icono: Music2 },
  linkedin: { nombre: "LinkedIn", icono: Linkedin },
  youtube: { nombre: "YouTube", icono: Youtube },
  twitter: { nombre: "X (Twitter)", icono: Twitter },
  // Métricas (Metricool) usa el id "x"; publicación (Postproxy) usa "twitter". Ambos → X.
  x: { nombre: "X (Twitter)", icono: Twitter },
  threads: { nombre: "Threads", icono: AtSign },
  pinterest: { nombre: "Pinterest", icono: Hash },
  bluesky: { nombre: "Bluesky", icono: Cloud },
  telegram: { nombre: "Telegram", icono: Send },
  google_business: { nombre: "Google Business", icono: Building2 },
};

/** Nombre legible de una plataforma (fallback al id). */
export function nombrePlataforma(id: string): string {
  return VISUAL[id]?.nombre ?? id;
}

/** Icono de una plataforma (fallback genérico). */
export function iconoPlataforma(id: string): LucideIcon {
  return VISUAL[id]?.icono ?? MessageCircle;
}

/** Plataformas que Postproxy permite conectar, en orden de pintado. */
export const PLATAFORMAS_POSTPROXY = [
  "facebook",
  "instagram",
  "tiktok",
  "linkedin",
  "youtube",
  "twitter",
  "threads",
  "pinterest",
  "bluesky",
  "telegram",
  "google_business",
] as const;

/** Formatea un número compacto (1.2k, 3.4M) o «—» si es null/undefined. */
export function formatearNumero(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-MX", { notation: "compact", maximumFractionDigits: 1 }).format(n);
}

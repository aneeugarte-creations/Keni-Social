/**
 * Primitivas COMPARTIDAS del calendario de la rota (turnos + eventos): constantes de
 * color por cobertura/prioridad y utilidades de fecha (semana lunes→domingo). Viven
 * aquí para ser una ÚNICA fuente de verdad entre la rejilla editable (`pages/Rota.tsx`)
 * y la previsualización de import (`components/parrilla/*`), evitando duplicar el mapeo
 * de colores que hace que el preview se vea idéntico al calendario real.
 */
import { Camera, CalendarOff, Radio } from "lucide-react";

import { diaCDMX, ZONA_CDMX } from "@/lib/fecha";
import type { PrioridadEvento, TipoCoberturaEvento } from "@/types";

/**
 * Presentación de cada tipo de cobertura: etiqueta, icono y clases de color (chips/leyenda).
 * Tropicalización MX y consistente con la voz del producto (Elías decide qué se cubre).
 */
export const COBERTURA: Record<
  TipoCoberturaEvento,
  { etiqueta: string; icono: typeof Radio; chip: string; punto: string }
> = {
  transmision: {
    etiqueta: "Transmisión",
    icono: Radio,
    chip: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300",
    punto: "bg-sky-500",
  },
  imagenes: {
    etiqueta: "Solo imágenes",
    icono: Camera,
    chip: "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300",
    punto: "bg-violet-500",
  },
  no_cubrir: {
    etiqueta: "No cubrir",
    icono: CalendarOff,
    chip: "border-zinc-300 bg-zinc-100 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-400",
    punto: "bg-zinc-400",
  },
};

/** Color del texto de la prioridad (sutil; la alta resalta). */
export const COLOR_PRIORIDAD: Record<PrioridadEvento, string> = {
  alta: "text-red-600 dark:text-red-400",
  media: "text-muted-foreground",
  baja: "text-muted-foreground",
};

// CONVENCIÓN de fechas (la misma que lib/fecha.ts): un `YYYY-MM-DD` se ANCLA a mediodía
// UTC (`anclar`) —así el día calendario no se desplaza en ninguna zona— y la aritmética
// usa los getters/setters UTC. "Hoy"/el día de un instante real se resuelve en zona CDMX
// (`diaCDMX`), no en la del navegador: antes se parseaba `T00:00:00` en zona LOCAL y un
// navegador fuera de CDMX podía descuadrar la semana alrededor de la medianoche.

/** Ancla un `YYYY-MM-DD` a mediodía UTC (inválido → Date inválido, como antes). */
function anclar(fechaIso: string): Date {
  return new Date(`${fechaIso}T12:00:00Z`);
}

/** ISO (AAAA-MM-DD) del día calendario de un Date ANCLADO (aritmética UTC). */
function isoAnclado(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Día calendario (AAAA-MM-DD) de un instante real, en zona CDMX. */
export function iso(d: Date): string {
  return diaCDMX(d);
}

/** Lunes (ISO AAAA-MM-DD) de la semana CDMX que contiene el instante `d`. */
export function lunesDeSemana(d: Date): string {
  const base = anclar(diaCDMX(d));
  const dia = (base.getUTCDay() + 6) % 7; // lunes=0 ... domingo=6
  base.setUTCDate(base.getUTCDate() - dia);
  return isoAnclado(base);
}

/** El lunes `semanas` después (o antes, si negativo) de `lunesIso`. */
export function lunesSiguiente(lunesIso: string, semanas: number): string {
  const d = anclar(lunesIso);
  d.setUTCDate(d.getUTCDate() + semanas * 7);
  const dia = (d.getUTCDay() + 6) % 7;
  d.setUTCDate(d.getUTCDate() - dia);
  return isoAnclado(d);
}

/** Las 7 fechas ISO (lun→dom) de la semana que arranca en `lunesIso`. */
export function diasDeSemana(lunesIso: string): string[] {
  const base = anclar(lunesIso);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(base);
    d.setUTCDate(d.getUTCDate() + i);
    return isoAnclado(d);
  });
}

/** Día corto localizado (p. ej. "lun"). */
export function diaCorto(fechaIso: string): string {
  const d = anclar(fechaIso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { weekday: "short", timeZone: ZONA_CDMX });
}

/** `true` si la fecha cae en sábado o domingo. */
export function esFinDeSemana(fechaIso: string): boolean {
  const d = anclar(fechaIso);
  if (Number.isNaN(d.getTime())) return false;
  const dia = d.getUTCDay();
  return dia === 0 || dia === 6;
}

/** Rango legible "12 may – 18 may". */
export function formatearRango(inicio: string, fin: string): string {
  if (!inicio || !fin) return "";
  const fmt = (s: string) =>
    anclar(s).toLocaleDateString("es-MX", {
      day: "numeric",
      month: "short",
      timeZone: ZONA_CDMX,
    });
  return `${fmt(inicio)} – ${fmt(fin)}`;
}

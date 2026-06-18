import { Radio, ShieldAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import { resumenCobertura } from "@/lib/cobertura";
import type { EventoRota, FranjaSemana, Publicacion, TurnoRota } from "@/types";

/** Cuántos segmentos pinta la barra de progreso del KPI (▰▰▰▱▱). */
const SEGMENTOS = 8;

/**
 * CABECERA-KPI de la pestaña Cobertura: una barra compacta de «cómo va la cobertura del rango
 * visible» derivada del MISMO selector canónico que las tarjetas (`resumenCobertura`), sin fetches
 * nuevos. Lee los eventos + claims (tareas clase=tarea) + la rota (turnos/franjas) que la vista ya
 * tiene cargados.
 *
 * Estética del equipo: recuadro outline gris; el color SOLO con significado y SIEMPRE con texto
 * (daltonismo): huecos en rojo, en vivo en ámbar, cubiertos en verde. La barra de progreso es
 * cubiertos/total. En móvil cae a la versión mínima (`▰▰▰ 5/8 cubiertos`).
 */
export function KpiCobertura({
  eventos,
  claims,
  turnos,
  franjas,
}: {
  eventos: EventoRota[];
  claims: Publicacion[];
  turnos: TurnoRota[];
  franjas: FranjaSemana[];
}) {
  const r = resumenCobertura(eventos, claims, turnos, franjas);
  if (r.total === 0) return null;

  const llenos = Math.round((r.cubiertos / r.total) * SEGMENTOS);
  const etiqueta = `Cobertura: ${r.cubiertos} de ${r.total} cubiertos, ${r.enVivo} en vivo, ${r.sinCubrir} sin cubrir`;

  return (
    <div
      role="status"
      aria-label={etiqueta}
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm shadow-sm"
    >
      <span className="shrink-0 font-medium">Cobertura de hoy</span>

      {/* Barra de progreso (cubiertos/total) en segmentos ▰▱, neutra; el significado va en los
          números. Marcada `aria-hidden`: el conteo accesible vive en `aria-label` del recuadro. */}
      <span aria-hidden className="flex shrink-0 items-center gap-px">
        {Array.from({ length: SEGMENTOS }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "h-1.5 w-2.5 rounded-[1px]",
              i < llenos ? "bg-foreground/70" : "bg-muted",
            )}
          />
        ))}
      </span>

      <span className="shrink-0 tabular-nums font-medium text-foreground">
        {r.cubiertos}
        <span className="text-muted-foreground">/{r.total}</span>
      </span>

      {/* Cortes con color de significado (rojo=hueco, ámbar=en vivo), SIEMPRE con icono+texto. La
          versión larga (separadores ·) se oculta en móvil para no apretar la barra. */}
      <span className="hidden items-center gap-3 text-xs sm:flex">
        {r.enVivo > 0 && (
          <span className="inline-flex items-center gap-1 font-medium text-amber-700 dark:text-amber-300">
            <Radio className="h-3.5 w-3.5" aria-hidden />
            {r.enVivo} en vivo
          </span>
        )}
        {r.sinCubrir > 0 ? (
          <span className="inline-flex items-center gap-1 font-medium text-red-700 dark:text-red-300">
            <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
            {r.sinCubrir} sin cubrir
          </span>
        ) : (
          <span className="font-medium text-emerald-700 dark:text-emerald-300">Todo cubierto</span>
        )}
      </span>

      {/* Móvil: solo el corte que pide decisión (huecos en rojo) o «cubiertos» si no hay ninguno. */}
      <span className="shrink-0 text-xs sm:hidden">
        {r.sinCubrir > 0 ? (
          <span className="font-medium text-red-700 dark:text-red-300">{r.sinCubrir} sin cubrir</span>
        ) : (
          <span className="font-medium text-emerald-700 dark:text-emerald-300">cubiertos</span>
        )}
      </span>
    </div>
  );
}

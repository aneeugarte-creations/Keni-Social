import { Check, Radio, ShieldAlert } from "lucide-react";

import { resumenCobertura } from "@/lib/cobertura";
import { COBERTURA_TEXTO } from "@/lib/estado-color";
import { cn } from "@/lib/utils";
import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  Publicacion,
  TurnoRota,
} from "@/types";

/** Cuántos segmentos pinta la barra de progreso del KPI (▰▰▰▱▱). */
const SEGMENTOS = 8;

/**
 * Colores de los cortes del KPI desde la fuente CENTRAL de la taxonomía (`lib/estado-color`):
 *  - VERDE para «en vivo» y «todo cubierto» (mismo lenguaje que el semáforo de las tarjetas: ámbar
 *    queda reservado a «empieza pronto», que el KPI no muestra).
 *  - ROJO para «sin cubrir» (el hueco que pide decisión).
 */
const TEXTO_VERDE = COBERTURA_TEXTO["cubierto-turno"];
const TEXTO_ROJO = COBERTURA_TEXTO["sin-cubrir"];

/**
 * CABECERA-KPI de la pestaña Cobertura: una barra compacta de «cómo va la cobertura del rango
 * visible» derivada del MISMO selector canónico que las tarjetas (`resumenCobertura`), sin fetches
 * nuevos. Lee los eventos + claims (tareas clase=tarea) + la rota (turnos/franjas) que la vista ya
 * tiene cargados.
 *
 * Estética del equipo: recuadro outline gris; el color SOLO con significado y SIEMPRE con texto
 * (daltonismo): huecos en rojo, en vivo en verde (mismo lenguaje que el semáforo de las tarjetas),
 * cubiertos en verde. La barra de progreso es cubiertos/total. En móvil cae a la versión mínima
 * (`▰▰▰ 5/8 cubiertos`).
 */
export function KpiCobertura({
  eventos,
  claims,
  turnos,
  franjas,
  ausencias = [],
  hechas = 0,
  onIrASinCubrir,
  variant = "tarjeta",
}: {
  eventos: EventoRota[];
  claims: Publicacion[];
  turnos: TurnoRota[];
  franjas: FranjaSemana[];
  /** Ausencias activas: una persona ausente no cuenta como cobertura por turno. */
  ausencias?: AusenciaRota[];
  /** Trabajo del día ya resuelto (partidos pasados + encargos en «hecha»). Dato NEUTRO secundario:
   *  «· N hechas» en gris al final de la línea, no una segunda barra ni más color. */
  hechas?: number;
  /** Si se pasa, el corte «N sin cubrir» se vuelve un botón que filtra el Panorama a «Por cubrir». */
  onIrASinCubrir?: () => void;
  /** "tarjeta" (recuadro con barra de progreso) o "linea": lectura inline, sin recuadro ni barra de
   *  segmentos, para colgarla del margen de la fila de pestañas («4/4 · N en vivo · Todo cubierto»). */
  variant?: "tarjeta" | "linea";
}) {
  const r = resumenCobertura(eventos, claims, turnos, franjas, undefined, ausencias);
  if (r.total === 0) return null;

  const llenos = Math.round((r.cubiertos / r.total) * SEGMENTOS);
  const etiqueta = `Cobertura de hoy: ${r.cubiertos} de ${r.total} cubiertos, ${r.enVivo} en vivo, ${r.sinCubrir} sin cubrir${hechas > 0 ? `, ${hechas} hechas` : ""}`;

  // Cortes con color de significado (verde=en vivo/cubierto, rojo=hueco), SIEMPRE con icono+texto:
  // compartidos por la tarjeta y la línea (mismo lenguaje que el semáforo de las tarjetas).
  const enVivo = r.enVivo > 0 && (
    <span className={cn("inline-flex items-center gap-1 font-medium", TEXTO_VERDE)}>
      <Radio className="h-3.5 w-3.5" aria-hidden />
      {r.enVivo} en vivo
    </span>
  );
  const corteDecision =
    r.sinCubrir > 0 ? (
      onIrASinCubrir ? (
        // «N sin cubrir» como botón: filtra el Panorama a «Por cubrir» (el único hueco accionable).
        <button
          type="button"
          onClick={onIrASinCubrir}
          className={cn(
            "inline-flex items-center gap-1 rounded font-medium underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none",
            TEXTO_ROJO,
          )}
        >
          <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
          {r.sinCubrir} sin cubrir
        </button>
      ) : (
        <span className={cn("inline-flex items-center gap-1 font-medium", TEXTO_ROJO)}>
          <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
          {r.sinCubrir} sin cubrir
        </span>
      )
    ) : (
      <span className={cn("font-medium", TEXTO_VERDE)}>Todo cubierto</span>
    );

  // LÍNEA: la misma lectura, sin recuadro ni barra de segmentos, para colgarla del margen de la fila
  // de pestañas. Sin la etiqueta «Cobertura de hoy» (el contexto es la cabecera): el conteo accesible
  // vive en el `aria-label`.
  if (variant === "linea") {
    return (
      <span
        role="status"
        aria-label={etiqueta}
        className="flex shrink-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-xs"
      >
        <span className="tabular-nums text-sm font-medium text-foreground">
          {r.cubiertos}
          <span className="text-muted-foreground">/{r.total}</span>
        </span>
        {enVivo}
        {corteDecision}
        {hechas > 0 && <span className="text-muted-foreground">· {hechas} hechas</span>}
      </span>
    );
  }

  return (
    <div
      role="status"
      aria-label={etiqueta}
      className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-xl border bg-card px-3 py-2 text-sm"
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

      {/* La versión larga (separadores ·) se oculta en móvil para no apretar la barra. */}
      <span className="hidden items-center gap-3 text-xs sm:flex">
        {enVivo}
        {corteDecision}
      </span>

      {/* «Hechas hoy»: dato NEUTRO secundario (gris, solo texto) al final de la línea —no otra
          barra ni color de marca—. Solo si hay alguna; preserva el «cómo va el día» sin un segundo
          chrome de progreso. */}
      {hechas > 0 && (
        <span className="shrink-0 text-xs text-muted-foreground">· {hechas} hechas</span>
      )}

      {/* Móvil: solo el corte que pide decisión (huecos en rojo) o «✓ Todo cubierto» si no hay
          ninguno (icono+texto, igual que la versión desktop, no una palabra suelta). */}
      <span className="shrink-0 text-xs sm:hidden">
        {r.sinCubrir > 0 ? (
          <span className={cn("font-medium", TEXTO_ROJO)}>{r.sinCubrir} sin cubrir</span>
        ) : (
          <span className={cn("inline-flex items-center gap-1 font-medium", TEXTO_VERDE)}>
            <Check className="h-3.5 w-3.5" aria-hidden />
            Todo cubierto
          </span>
        )}
      </span>
    </div>
  );
}

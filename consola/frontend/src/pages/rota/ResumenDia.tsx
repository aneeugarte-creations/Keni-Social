// «Resumen del día»: un panel que reúne TODO lo de una jornada (eventos + cobertura, personal de
// turno, huecos/tareas, horas asignadas y avisos) para cualquier fecha del calendario. Reusa la
// misma derivación de cobertura del cockpit (`useTablero`) y las primitivas de la rota; no añade
// chrome nuevo: outline gris de plataforma y color solo con significado (amarillo = sin cubrir).
import { AlertTriangle, CalendarOff, Clock, Hand } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { KpiCobertura } from "@/pages/tareas/KpiCobertura";
import { FilaAgenda } from "@/pages/tareas/PanoramaAgenda";
import type { Item } from "@/pages/tareas/tipos";
import { useTablero } from "@/pages/tareas/useTablero";
import type { AusenciaRota, FranjaSemana, TurnoRota } from "@/types";

import { ausenciaTocaDia, formatearFechaCorta, franjasSolapan } from "./comun";
import { aMinutos24 } from "./DialogoAsignarTurnos";
import { useTiempoLibreActivo } from "./useConfigRota";

/**
 * Horario EFECTIVO de un turno ("HH:MM"–"HH:MM"): sus horas a medida si las tiene; si no, las de
 * su franja. El modelo ya resuelve `turno.inicio`/`turno.fin` al horario efectivo, pero un turno
 * sin horas propias y cuya franja no se encuentra cae a "" (se ignora en los cálculos).
 */
export function horarioEfectivo(
  turno: TurnoRota,
  franjaPorId: Map<string, FranjaSemana>,
): { inicio: string; fin: string } {
  if (turno.inicio && turno.fin) return { inicio: turno.inicio, fin: turno.fin };
  const f = franjaPorId.get(turno.franja_id);
  return { inicio: f?.inicio ?? "", fin: f?.fin ?? "" };
}

/**
 * Minutos que dura un turno (soporta cruce de medianoche: `fin <= inicio` → +24h). `0` si alguna
 * hora no parsea o el rango es degenerado. Usa `aMinutos24` (la misma fuente que «Asignar turnos»).
 */
export function minutosTurno(inicio: string, fin: string): number {
  const i = aMinutos24(inicio);
  const f = aMinutos24(fin);
  if (i === null || f === null) return 0;
  const dur = f > i ? f - i : f < i ? 1440 - i + f : 0;
  return dur;
}

/**
 * Suma de minutos de TODOS los turnos del día (su horario efectivo). La franja de descanso no
 * cuenta como horas trabajadas. Pensado para mostrar «N h M min asignadas» ese día.
 */
export function horasTotalesDelDia(
  turnos: TurnoRota[],
  franjaPorId: Map<string, FranjaSemana>,
): number {
  let total = 0;
  for (const t of turnos) {
    if (franjaPorId.get(t.franja_id)?.es_descanso) continue;
    const { inicio, fin } = horarioEfectivo(t, franjaPorId);
    total += minutosTurno(inicio, fin);
  }
  return total;
}

/** "N h M min" / "N h" / "M min" a partir de minutos (compacto, para un chip de cabecera). */
export function formatearMinutos(min: number): string {
  if (min <= 0) return "0 min";
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return `${m} min`;
  if (m === 0) return `${h} h`;
  return `${h} h ${m} min`;
}

/** Un aviso (no bloqueante) de la jornada: un solape de turnos o una persona de turno ausente. */
export interface IncidenciaDia {
  tipo: "solape" | "ausencia";
  miembroNombre: string;
  /** Detalle legible (franjas que solapan / tipo de ausencia). */
  detalle: string;
}

/**
 * Incidencias de la jornada (avisos, no bloqueos):
 *  - `solape`: la MISMA persona con dos turnos ese día en franjas que comparten horas
 *    (`franjasSolapan` sobre su horario efectivo). Un par solo se reporta una vez.
 *  - `ausencia`: una persona que está de turno ese día y a la vez tiene una ausencia que toca
 *    el día (`ausenciaTocaDia`): su turno no cubre de verdad.
 * La franja de descanso no genera solape (no son horas de trabajo).
 */
export function conflictosDelDia(
  fecha: string,
  turnos: TurnoRota[],
  franjaPorId: Map<string, FranjaSemana>,
  ausencias: AusenciaRota[],
): IncidenciaDia[] {
  const avisos: IncidenciaDia[] = [];

  // Solapes: agrupa los turnos del día por persona y compara cada par de franjas laborales.
  const porMiembro = new Map<string, TurnoRota[]>();
  for (const t of turnos) {
    const lista = porMiembro.get(t.miembro_id) ?? [];
    lista.push(t);
    porMiembro.set(t.miembro_id, lista);
  }
  for (const lista of porMiembro.values()) {
    for (let a = 0; a < lista.length; a++) {
      for (let b = a + 1; b < lista.length; b++) {
        const ta = lista[a]!;
        const tb = lista[b]!;
        if (ta.franja_id === tb.franja_id) continue;
        if (franjaPorId.get(ta.franja_id)?.es_descanso) continue;
        if (franjaPorId.get(tb.franja_id)?.es_descanso) continue;
        const ha = horarioEfectivo(ta, franjaPorId);
        const hb = horarioEfectivo(tb, franjaPorId);
        if (!ha.inicio || !ha.fin || !hb.inicio || !hb.fin) continue;
        if (franjasSolapan(ha, hb)) {
          avisos.push({
            tipo: "solape",
            miembroNombre: ta.miembro_nombre,
            detalle: `${ta.franja_nombre} y ${tb.franja_nombre} se solapan`,
          });
        }
      }
    }
  }

  // Ausencias: personas con turno ese día que a la vez están de ausencia. Una sola entrada por
  // persona aunque tenga varios turnos.
  const ausentesYaVistos = new Set<string>();
  for (const t of turnos) {
    if (ausentesYaVistos.has(t.miembro_id)) continue;
    const aus = ausencias.find(
      (a) => a.miembro_id === t.miembro_id && ausenciaTocaDia(a, fecha),
    );
    if (aus) {
      ausentesYaVistos.add(t.miembro_id);
      avisos.push({
        tipo: "ausencia",
        miembroNombre: t.miembro_nombre,
        detalle: `de ${aus.tipo} y aún con turno`,
      });
    }
  }

  return avisos;
}

/** Un aviso de la semana: la incidencia de un día más la fecha (ISO) en que ocurre. */
export interface IncidenciaSemana extends IncidenciaDia {
  fecha: string;
}

/**
 * Incidencias de TODA la semana: aplica `conflictosDelDia` a cada uno de `dias` y anota la fecha.
 * Los turnos se reparten por su `fecha` antes de evaluar cada día, así un solape solo se reporta
 * dentro del mismo día (la misma persona con dos franjas que comparten horas ESE día). Misma
 * derivación que el «Resumen del día», agregada para el panel de coordinación.
 */
export function conflictosDeLaSemana(
  dias: string[],
  turnos: TurnoRota[],
  franjaPorId: Map<string, FranjaSemana>,
  ausencias: AusenciaRota[],
): IncidenciaSemana[] {
  const porFecha = new Map<string, TurnoRota[]>();
  for (const t of turnos) {
    const lista = porFecha.get(t.fecha) ?? [];
    lista.push(t);
    porFecha.set(t.fecha, lista);
  }
  const out: IncidenciaSemana[] = [];
  for (const fecha of dias) {
    const delDia = porFecha.get(fecha) ?? [];
    if (delDia.length === 0) continue;
    for (const inc of conflictosDelDia(fecha, delDia, franjaPorId, ausencias)) {
      out.push({ ...inc, fecha });
    }
  }
  return out;
}

/**
 * Panel «Resumen del día»: abre desde la cabecera de un día del calendario y muestra, en UNA vista,
 * todo lo de esa jornada para `fecha`. Reusa `useTablero(marca, usuarioId, fecha)` —la MISMA
 * derivación de cobertura del cockpit— para no reconstruir nada a mano.
 */
export function ResumenDia({
  fecha,
  marca,
  usuarioId,
  onClose,
}: {
  /** Día a resumir (ISO AAAA-MM-DD). */
  fecha: string;
  /** Marca activa (acota eventos/turnos); `undefined` = «Todas». */
  marca: string | undefined;
  /** Usuario actual (para «Lo mío»); puede ser `null`. */
  usuarioId: string | null;
  onClose: () => void;
}) {
  const t = useTablero(marca, usuarioId, fecha);
  // Si el tiempo libre está apagado por marca, el resumen del día ignora las ausencias (ni KPI de
  // cobertura penalizada por ausente ni incidencias «con turno pero ausente»). El motor de cobertura
  // del cockpit sigue intacto; aquí solo se omite su presentación.
  const tiempoLibreActivo = useTiempoLibreActivo();
  const ausenciasDia = tiempoLibreActivo ? t.ausencias : [];
  const [abiertas, setAbiertas] = React.useState<Set<string>>(() => new Set());
  const toggle = (clave: string) =>
    setAbiertas((prev) => {
      const n = new Set(prev);
      if (n.has(clave)) n.delete(clave);
      else n.add(clave);
      return n;
    });

  const franjaPorId = React.useMemo(() => {
    const m = new Map<string, FranjaSemana>();
    for (const f of t.franjasHoy) m.set(f.id, f);
    return m;
  }, [t.franjasHoy]);

  // Ítems del día (orden = su fecha): los huecos por cubrir y lo asignado.
  const itemsDia = t.items.filter((i) => i.orden === fecha);
  const porCubrir = itemsDia.filter(t.esPorCubrir);
  const asignados = itemsDia.filter((i) => !t.esPorCubrir(i));

  // Personal de turno ese día, ordenado por hora de entrada y nombre. La franja de descanso se
  // marca aparte (no son horas de trabajo) pero se lista: es información de la jornada.
  const personal = [...t.turnosHoy].sort((a, b) => {
    const ha = horarioEfectivo(a, franjaPorId).inicio;
    const hb = horarioEfectivo(b, franjaPorId).inicio;
    return ha.localeCompare(hb) || a.miembro_nombre.localeCompare(b.miembro_nombre);
  });

  const minutosTotales = horasTotalesDelDia(t.turnosHoy, franjaPorId);
  const incidencias = conflictosDelDia(fecha, t.turnosHoy, franjaPorId, ausenciasDia);

  const fila = (i: Item, asignarResaltado = false) => (
    <FilaAgenda
      key={i.clave}
      item={i}
      abierta={abiertas.has(i.clave)}
      onToggle={() => toggle(i.clave)}
      catalogos={t.catalogos}
      asignarResaltado={asignarResaltado}
    />
  );

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[85vh] gap-4 overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="first-letter:uppercase">
            {formatearFechaCorta(fecha) || fecha}
          </DialogTitle>
        </DialogHeader>

        {t.cargando ? (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-md" />
            ))}
          </div>
        ) : (
          <div className="space-y-5">
            {/* KPI de cobertura del día (cubiertos / en vivo / sin cubrir), misma fuente que el cockpit. */}
            <KpiCobertura
              eventos={t.eventosHoy}
              claims={t.claimsCobertura}
              turnos={t.turnosHoy}
              franjas={t.franjasHoy}
              ausencias={ausenciasDia}
              hechas={t.hechasHoy}
            />

            {/* Personal de turno ese día + horas totales asignadas. */}
            <section className="space-y-2">
              <h3 className="flex flex-wrap items-center gap-2 text-sm font-medium text-muted-foreground">
                <Clock className="h-3.5 w-3.5" /> De turno
                <span className="tabular-nums">({personal.length})</span>
                <Badge variant="outline" className="font-normal tabular-nums">
                  {formatearMinutos(minutosTotales)} asignadas
                </Badge>
              </h3>
              {personal.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nadie de turno ese día.</p>
              ) : (
                <ul className="space-y-1">
                  {personal.map((tn) => {
                    const { inicio, fin } = horarioEfectivo(tn, franjaPorId);
                    const descanso = franjaPorId.get(tn.franja_id)?.es_descanso;
                    return (
                      <li
                        key={tn.id}
                        className="flex flex-wrap items-baseline justify-between gap-x-2 rounded-xl border bg-card px-2.5 py-1.5 text-sm"
                      >
                        <span className="font-medium">{tn.miembro_nombre}</span>
                        <span className="flex items-baseline gap-2 text-xs text-muted-foreground">
                          <span>{tn.franja_nombre}</span>
                          {descanso ? (
                            <span>(descanso)</span>
                          ) : inicio && fin ? (
                            <span className="tabular-nums">
                              {inicio}–{fin}
                            </span>
                          ) : null}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            {/* Avisos del día (solapes / ausentes con turno): atención, no bloqueo → amarillo. */}
            {incidencias.length > 0 && (
              <section className="space-y-2">
                <h3 className="flex items-center gap-1.5 text-sm font-medium text-yellow-700 dark:text-yellow-300">
                  <AlertTriangle className="h-3.5 w-3.5" /> Avisos
                  <span className="tabular-nums">({incidencias.length})</span>
                </h3>
                <ul className="space-y-1">
                  {incidencias.map((inc, idx) => (
                    <li
                      key={`${inc.tipo}-${inc.miembroNombre}-${idx}`}
                      className="flex items-center gap-2 rounded-xl border border-yellow-500/50 bg-yellow-50/50 px-2.5 py-1.5 text-sm text-yellow-800 dark:bg-yellow-950/20 dark:text-yellow-300"
                    >
                      {inc.tipo === "ausencia" ? (
                        <CalendarOff className="h-3.5 w-3.5 shrink-0" />
                      ) : (
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                      )}
                      <span>
                        <span className="font-medium">{inc.miembroNombre}</span> {inc.detalle}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {/* Por cubrir (huecos) + tareas del día. */}
            <section className="space-y-2">
              <h3 className="flex items-center gap-1.5 text-sm font-medium text-muted-foreground">
                <Hand className="h-3.5 w-3.5" /> Por cubrir
                <span className="tabular-nums">({porCubrir.length})</span>
              </h3>
              {porCubrir.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nada pendiente: todo lo del día tiene quien lo cubra.
                </p>
              ) : (
                <div className="space-y-1.5">{porCubrir.map((i) => fila(i, true))}</div>
              )}
            </section>

            {/* Eventos/tareas ya con dueño o cubiertos por turno. */}
            <section className="space-y-2">
              <h3 className="text-sm font-medium text-muted-foreground">
                Cubierto y asignado <span className="tabular-nums">({asignados.length})</span>
              </h3>
              {asignados.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nada asignado ese día.</p>
              ) : (
                <div className="space-y-1.5">{asignados.map((i) => fila(i))}</div>
              )}
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

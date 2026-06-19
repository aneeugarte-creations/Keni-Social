/**
 * Calendario de la rota en modo PREVISUALIZACIÓN (solo lectura) con las operaciones
 * propuestas por un import SUPERPUESTAS y codificadas por color:
 *   - verde  = nuevo      (crear_evento / crear_turno)
 *   - ámbar  = cambio     (modificar_turno)
 *   - rojo   = conflicto  (cualquier operación con `conflicto: true`)
 *
 * Una propuesta puede abarcar MUCHAS semanas (hasta un año): este componente recibe TODAS
 * las operaciones (cada una con su `fecha`) y muestra UNA semana a la vez con un navegador
 * prev/next IDÉNTICO al de la rota real (`pages/Rota.tsx`). La semana por defecto es la de
 * la operación MÁS TEMPRANA; la navegación se acota al rango de semanas con cambios (±1 de
 * holgura) para que el usuario no se pierda lejos de los datos.
 *
 * Renderiza la MISMA rejilla día × franja que el calendario real, reusando sus primitivas
 * visuales (`@/lib/rota-calendario`). La diferencia clave con la rota real: las FILAS son
 * NOMBRES de franja (plantilla), no `franja_id` — porque una propuesta multi-semana no
 * puede referirse a `franja_id` (que son por-semana). Cada `crear_turno`/`modificar_turno`
 * trae el NOMBRE de su franja y lo casamos contra las filas-plantilla (normalizado).
 *
 * No hace CRUD: es un espejo del resultado del merge. Por eso vive como componente propio
 * en vez de añadir un `modoPreview` a la rejilla editable (que arrastra dropdowns,
 * mutaciones y menús contextuales que aquí no aplican y solo añadirían riesgo).
 */
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarDays,
  CalendarPlus,
  ChevronLeft,
  ChevronRight,
  Pencil,
  Sunrise,
  Sunset,
  User,
} from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
  diaCorto,
  diasDeSemana,
  esFinDeSemana,
  formatearRango,
  lunesDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import { cn } from "@/lib/utils";
import type {
  CoberturaEvento,
  FranjaSemana,
  OperacionCrearEvento,
  OperacionCrearTurno,
  OperacionModificarTurno,
  OperacionPropuesta,
  TurnoRota,
} from "@/types";

/** Color semántico de cada categoría del overlay. */
type Categoria = "nuevo" | "cambio" | "conflicto";

const ESTILO_CATEGORIA: Record<Categoria, { borde: string; chip: string; etiqueta: string }> = {
  nuevo: {
    borde: "border-emerald-400 ring-1 ring-emerald-400/40",
    chip: "border-emerald-400 bg-emerald-50 text-emerald-800 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
    etiqueta: "Nuevo",
  },
  cambio: {
    borde: "border-amber-400 ring-1 ring-amber-400/40",
    chip: "border-amber-400 bg-amber-50 text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
    etiqueta: "Cambio",
  },
  conflicto: {
    borde: "border-red-400 ring-1 ring-red-400/40",
    chip: "border-red-400 bg-red-50 text-red-800 dark:border-red-700 dark:bg-red-950/40 dark:text-red-300",
    etiqueta: "Conflicto",
  },
};

/** Un conflicto pinta SIEMPRE rojo, gane sobre su categoría base. */
function categoriaDe(op: OperacionPropuesta): Categoria {
  if (op.conflicto) return "conflicto";
  return op.tipo === "modificar_turno" ? "cambio" : "nuevo";
}

// --- Helpers de franja (espejo de la lógica de Rota.tsx, sin CRUD) ----------

function horaAMinutos(s: string | null | undefined): number | null {
  if (typeof s !== "string") return null;
  const m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (!Number.isFinite(h) || !Number.isFinite(mi)) return null;
  if (h < 0 || h > 23 || mi < 0 || mi > 59) return null;
  return h * 60 + mi;
}

function horaEnRangoFranja(hora: string, inicio: string, fin: string): boolean {
  const h = horaAMinutos(hora);
  const ini = horaAMinutos(inicio);
  const f = horaAMinutos(fin);
  if (h === null || ini === null || f === null) return false;
  if (ini === f) return false;
  if (ini < f) return h >= ini && h < f;
  return h >= ini || h < f;
}

/** El NOMBRE de la franja de la semana que contiene la hora del evento, o `null`.
 * Devuelve `null` si no hay franjas o si la hora es nula/ inválida (un evento SIN hora —caso
 * habitual en imports— lo coloca el caller en la primera fila laboral, sin reventar). */
function franjaNombreParaHoraEvento(
  hora: string | null | undefined,
  franjas: FranjaSemana[],
): string | null {
  if (franjas.length === 0) return null;
  if (horaAMinutos(hora) === null) return null; // sin hora válida: que decida el caller
  for (const f of franjas.filter((x) => !x.es_descanso)) {
    if (horaEnRangoFranja(hora as string, f.inicio, f.fin)) return f.nombre;
  }
  return franjas.find((f) => f.es_descanso)?.nombre ?? franjas[0]?.nombre ?? null;
}

/** Normaliza un nombre de franja para casar filas (lower + trim, sin acentos para robustez). */
function normFranja(nombre: string): string {
  return nombre
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

// Plantilla por defecto de filas (NOMBRES de franja), en el orden de la rota real. Las
// operaciones cuyo nombre de franja no caiga en esta plantilla añaden su propia fila.
const PLANTILLA_FRANJAS_DEFECTO = ["Mañana", "Tarde", "Descanso"] as const;

/** ¿Esta fila-plantilla es la franja de descanso (heurística por nombre)? */
function esDescansoNombre(nombre: string): boolean {
  return normFranja(nombre).includes("descanso");
}

const BANDAS_FRANJA_LABORAL = [
  "border-l-amber-400",
  "border-l-sky-400",
  "border-l-violet-400",
  "border-l-teal-400",
];

// --- Estructura de una celda del preview ------------------------------------

interface ChipPreviewEvento {
  clave: string;
  titulo: string;
  hora: string;
  prioridad?: OperacionCrearEvento["prioridad"];
  tipoCobertura?: OperacionCrearEvento["tipo_cobertura"];
  /** Categoría del overlay, o `null` si es una fila REAL preexistente (atenuada). */
  categoria: Categoria | null;
}

interface ChipPreviewPersona {
  clave: string;
  nombre: string;
  /** Categoría del overlay, o `null` para personas reales preexistentes. */
  categoria: Categoria | null;
  /** Resumen del cambio (solo para modificar_turno). */
  detalle?: string;
}

interface CeldaPreview {
  personas: ChipPreviewPersona[];
  eventos: ChipPreviewEvento[];
}

/** Resumen legible de los `cambios` de un modificar_turno. */
function resumirCambios(op: OperacionModificarTurno): string {
  const partes: string[] = [];
  const c = op.cambios ?? {};
  if (typeof c.fecha === "string") partes.push(`fecha → ${c.fecha}`);
  // El backend puede mandar la nueva franja como nombre (`franja`) o id (`franja_id`).
  if (typeof (c as Record<string, unknown>).franja === "string" || typeof c.franja_id === "string")
    partes.push("cambia de franja");
  if (typeof c.miembro_id === "string") partes.push("reasigna persona");
  if (typeof c.motivo === "string") partes.push("motivo");
  if (typeof c.nota_relevo === "string") partes.push("nota de relevo");
  if (typeof c.override === "boolean") partes.push(`override → ${c.override ? "sí" : "no"}`);
  return partes.length > 0 ? partes.join(" · ") : "modificación";
}

/** La `fecha` (ISO) que ubica una operación en el calendario, o `null` si no parsea. */
function fechaDeOperacion(op: OperacionPropuesta): string | null {
  if (op.tipo === "crear_evento" || op.tipo === "crear_turno") {
    return typeof op.fecha === "string" && op.fecha ? op.fecha : null;
  }
  // crear_tarea: la ubica su deadline opcional (puede no traerla).
  if (op.tipo === "crear_tarea") {
    return typeof op.fecha_objetivo === "string" && op.fecha_objetivo ? op.fecha_objetivo : null;
  }
  // modificar_turno: la fecha actual (o la nueva si la mueve).
  const c = op.cambios ?? {};
  const nueva = typeof c.fecha === "string" ? c.fecha : null;
  const actual = typeof op.actual?.fecha === "string" ? op.actual.fecha : null;
  return nueva ?? actual;
}

export function CalendarioPreview({
  operaciones: todasLasOperaciones,
}: {
  /** TODAS las operaciones de la propuesta (cada una con su `fecha`). */
  operaciones: OperacionPropuesta[];
}) {
  // Las operaciones IDEMPOTENTES («ya está en el calendario») NO se superponen: el calendario
  // real ya las muestra en gris. Aquí solo pintamos los CAMBIOS reales (nuevo/cambio/conflicto),
  // así una propuesta re-subida sobre una semana ya hecha no se llena de rojos falsos.
  const operaciones = React.useMemo(
    () => todasLasOperaciones.filter((op) => !op.ya_existe),
    [todasLasOperaciones],
  );

  // Semanas (lunes ISO) que contienen alguna operación, ordenadas ascendente.
  const semanasConCambios = React.useMemo(() => {
    const set = new Set<string>();
    for (const op of operaciones) {
      const f = fechaDeOperacion(op);
      if (!f) continue;
      // Anclado a mediodía UTC (convención de lib/fecha): el día calendario no se
      // desplaza aunque el navegador no esté en CDMX.
      const d = new Date(`${f}T12:00:00Z`);
      if (Number.isNaN(d.getTime())) continue;
      set.add(lunesDeSemana(d));
    }
    return Array.from(set).sort();
  }, [operaciones]);

  const primeraSemana = semanasConCambios[0] ?? lunesDeSemana(new Date());
  const ultimaSemana = semanasConCambios[semanasConCambios.length - 1] ?? primeraSemana;
  // Holgura de ±1 semana alrededor del rango con cambios (clamp de la navegación).
  const minLunes = lunesSiguiente(primeraSemana, -1);
  const maxLunes = lunesSiguiente(ultimaSemana, 1);

  // Semana mostrada: por defecto la PRIMERA con cambios. Se re-ancla si cambian las ops.
  const [lunes, setLunes] = React.useState(primeraSemana);
  React.useEffect(() => {
    setLunes(primeraSemana);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [primeraSemana]);

  const irA = (nuevo: string) => {
    if (nuevo < minLunes) return setLunes(minLunes);
    if (nuevo > maxLunes) return setLunes(maxLunes);
    setLunes(nuevo);
  };
  const puedeAnterior = lunes > minLunes;
  const puedeSiguiente = lunes < maxLunes;

  // El estado REAL de la semana mostrada: turnos + cobertura (los endpoints del calendario).
  const turnosQ = useQuery({
    queryKey: ["rota", "turnos", lunes],
    queryFn: ({ signal }) => api.listarTurnos({ lunes }, signal),
  });
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes],
    queryFn: ({ signal }) => api.cobertura({ lunes }, signal),
  });

  const dias = React.useMemo(() => diasDeSemana(lunes), [lunes]);
  const finDias = lunesSiguiente(lunes, 1); // exclusivo

  const franjasSemana = React.useMemo<FranjaSemana[]>(
    () =>
      (turnosQ.data?.franjas ?? coberturaQ.data?.franjas ?? [])
        .slice()
        .sort((a, b) => a.orden - b.orden),
    [turnosQ.data?.franjas, coberturaQ.data?.franjas],
  );

  // Operaciones que caen en la semana mostrada (filtro por fecha).
  const opsSemana = React.useMemo(
    () =>
      operaciones.filter((op) => {
        const f = fechaDeOperacion(op);
        return !!f && f >= dias[0]! && f < finDias;
      }),
    [operaciones, dias, finDias],
  );

  // FILAS de la rejilla = NOMBRES de franja. Plantilla por defecto (orden rota) UNIÓN los
  // nombres reales de la semana UNIÓN los nombres que aparecen en las operaciones. Cada
  // fila lleva su orden/horario si lo conocemos por la franja real homónima.
  const filasFranja = React.useMemo(() => {
    // Índice de franja real por nombre normalizado (para horario + es_descanso + orden).
    const realPorNombre = new Map<string, FranjaSemana>();
    for (const f of franjasSemana) realPorNombre.set(normFranja(f.nombre), f);

    // Nombres a mostrar, preservando el primer "display name" visto.
    const orden: string[] = [];
    const vistos = new Set<string>();
    const anadir = (nombre: string) => {
      const k = normFranja(nombre);
      if (!k || vistos.has(k)) return;
      vistos.add(k);
      orden.push(nombre);
    };
    // 1) franjas reales de la semana (en su orden), 2) plantilla por defecto, 3) ops.
    for (const f of franjasSemana) anadir(f.nombre);
    for (const n of PLANTILLA_FRANJAS_DEFECTO) anadir(n);
    for (const op of opsSemana) {
      if (op.tipo === "crear_turno") anadir((op as OperacionCrearTurno).franja);
      else if (op.tipo === "modificar_turno") {
        const a = (op as OperacionModificarTurno).actual;
        if (typeof a?.franja === "string") anadir(a.franja);
      }
    }

    return orden.map((nombre) => {
      const real = realPorNombre.get(normFranja(nombre));
      return {
        clave: normFranja(nombre),
        nombre: real?.nombre ?? nombre,
        inicio: real?.inicio ?? "",
        fin: real?.fin ?? "",
        es_descanso: real?.es_descanso ?? esDescansoNombre(nombre),
      };
    });
  }, [franjasSemana, opsSemana]);

  // Mapa `franjaClave|fecha` → CeldaPreview a partir del estado REAL + overlay.
  const celdas = React.useMemo(() => {
    const m = new Map<string, CeldaPreview>();
    const obtener = (clave: string): CeldaPreview => {
      let c = m.get(clave);
      if (!c) {
        c = { personas: [], eventos: [] };
        m.set(clave, c);
      }
      return c;
    };
    // Índice de franja real (id → nombre) para casar turnos/eventos reales por nombre.
    const nombrePorId = new Map<string, string>();
    for (const f of franjasSemana) nombrePorId.set(f.id, f.nombre);

    // 1) Personas reales (turnos existentes), atenuadas. Casamos por NOMBRE de franja.
    for (const t of (turnosQ.data?.turnos ?? []) as TurnoRota[]) {
      const nombre = t.franja_nombre || nombrePorId.get(t.franja_id) || "";
      if (!nombre) continue;
      obtener(`${normFranja(nombre)}|${t.fecha}`).personas.push({
        clave: `real-${t.id}`,
        nombre: t.miembro_nombre,
        categoria: null,
      });
    }

    // 2) Eventos reales con cobertura, atenuados.
    for (const ev of (coberturaQ.data?.eventos ?? []) as CoberturaEvento[]) {
      if (ev.fecha < dias[0]! || ev.fecha > dias[6]!) continue;
      const franjaId = ev.cobertura[0]?.franja_id;
      const nombre =
        (franjaId && nombrePorId.get(franjaId)) ||
        franjaNombreParaHoraEvento(ev.hora, franjasSemana);
      if (!nombre) continue;
      obtener(`${normFranja(nombre)}|${ev.fecha}`).eventos.push({
        clave: `real-ev-${ev.id}`,
        titulo: ev.titulo,
        hora: ev.hora,
        prioridad: ev.prioridad,
        tipoCobertura: ev.tipo_cobertura,
        categoria: null,
      });
    }

    // 3) Overlay: cada operación propuesta de la semana mostrada.
    opsSemana.forEach((op, i) => {
      const categoria = categoriaDe(op);
      if (op.tipo === "crear_evento") {
        const o = op as OperacionCrearEvento;
        const nombre = franjaNombreParaHoraEvento(o.hora, franjasSemana);
        // Sin franjas reales en la semana caemos a la primera fila-plantilla laboral.
        const clave = nombre
          ? normFranja(nombre)
          : filasFranja.find((f) => !f.es_descanso)?.clave ?? filasFranja[0]?.clave;
        if (!clave) return;
        obtener(`${clave}|${o.fecha}`).eventos.push({
          clave: `op-${i}`,
          titulo: o.titulo,
          hora: o.hora,
          prioridad: o.prioridad,
          tipoCobertura: o.tipo_cobertura,
          categoria,
        });
      } else if (op.tipo === "crear_turno") {
        const o = op as OperacionCrearTurno;
        const clave = normFranja(o.franja ?? "");
        if (!clave) return;
        obtener(`${clave}|${o.fecha}`).personas.push({
          clave: `op-${i}`,
          nombre: o.miembro_nombre,
          categoria,
        });
      } else if (op.tipo === "modificar_turno") {
        const o = op as OperacionModificarTurno;
        // El turno modificado se ubica donde está HOY (valores `actual`); si el cambio
        // mueve fecha/franja, lo reflejamos en el detalle del chip.
        const fecha = (typeof o.actual?.fecha === "string" && o.actual.fecha) || dias[0]!;
        const nombre =
          (typeof o.actual?.franja === "string" && o.actual.franja) ||
          filasFranja[0]?.nombre ||
          "";
        const clave = normFranja(nombre);
        if (!clave) return;
        obtener(`${clave}|${fecha}`).personas.push({
          clave: `op-${i}`,
          nombre: (typeof o.actual?.miembro_nombre === "string" && o.actual.miembro_nombre) || "Turno",
          categoria,
          detalle: resumirCambios(o),
        });
      }
    });

    return m;
  }, [turnosQ.data?.turnos, coberturaQ.data?.eventos, opsSemana, dias, franjasSemana, filasFranja]);

  const cargando = turnosQ.isPending || coberturaQ.isPending;
  const error = turnosQ.error || coberturaQ.error;

  const finInclusivo = dias[6] ?? lunes;
  const navegador = (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Semana anterior"
          onClick={() => irA(lunesSiguiente(lunes, -1))}
          disabled={!puedeAnterior}
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-[12rem] text-center text-sm font-medium">
          <CalendarDays className="mr-1.5 inline h-4 w-4 text-muted-foreground" />
          {formatearRango(lunes, finInclusivo) || "Semana"}
        </div>
        <Button
          type="button"
          variant="outline"
          size="icon"
          aria-label="Semana siguiente"
          onClick={() => irA(lunesSiguiente(lunes, 1))}
          disabled={!puedeSiguiente}
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
      <span className="text-xs text-muted-foreground">
        {opsSemana.length === 0
          ? "Sin cambios esta semana"
          : `${opsSemana.length} cambio${opsSemana.length === 1 ? "" : "s"} esta semana`}
        {semanasConCambios.length > 1 && ` · ${semanasConCambios.length} semanas con cambios`}
      </span>
    </div>
  );

  if (cargando)
    return (
      <div className="space-y-3">
        {navegador}
        <Skeleton className="h-[40vh] w-full rounded-md" />
      </div>
    );
  if (error) {
    return (
      <div className="space-y-3">
        {navegador}
        <BloqueError
          titulo="No se pudo cargar el calendario para previsualizar"
          mensaje={error instanceof Error ? error.message : "Error inesperado."}
          onReintentar={() => {
            void turnosQ.refetch();
            void coberturaQ.refetch();
          }}
          cargando={turnosQ.isFetching}
        />
      </div>
    );
  }

  let indiceLaboral = 0;
  return (
    <div className="space-y-3">
      {navegador}
      <Card className="overflow-hidden">
        <CardContent className="p-0">
          <div className="overflow-auto" style={{ maxHeight: "calc(100dvh - 26rem)" }}>
            <div className="min-w-[56rem]">
              {/* Cabecera de días (sticky). */}
              <div className="sticky top-0 z-10 grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px border-b bg-background">
                <div className="bg-background px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Franja
                </div>
                {dias.map((fecha) => (
                  <div
                    key={fecha}
                    className={cn(
                      "flex items-baseline justify-between px-2 py-2",
                      esFinDeSemana(fecha)
                        ? "bg-muted/60 dark:bg-muted/30"
                        : "bg-background",
                    )}
                  >
                    <span className="text-xs font-semibold capitalize">{diaCorto(fecha)}</span>
                    <span className="text-xs text-muted-foreground">{fecha.slice(8, 10)}</span>
                  </div>
                ))}
              </div>

              {filasFranja.map((franja, idx) => {
                const idxLab = franja.es_descanso ? -1 : indiceLaboral++;
                const banda = franja.es_descanso
                  ? "border-l-zinc-300 dark:border-l-zinc-700"
                  : BANDAS_FRANJA_LABORAL[idxLab % BANDAS_FRANJA_LABORAL.length]!;
                return (
                  <div
                    key={franja.clave}
                    className={cn(
                      "grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px",
                      idx > 0 && "border-t-4 border-t-border",
                    )}
                  >
                    <div
                      className={cn(
                        "sticky left-0 z-[1] flex flex-col justify-center border-l-4 bg-background px-3 py-3 text-sm font-semibold",
                        banda,
                      )}
                    >
                      <span className="flex items-center gap-1.5">
                        {franja.es_descanso || idxLab > 0 ? (
                          <Sunset className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <Sunrise className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                        {franja.nombre}
                      </span>
                      <span className="text-xs font-normal text-muted-foreground">
                        {franja.es_descanso
                          ? ""
                          : franja.inicio && franja.fin
                            ? `${franja.inicio}–${franja.fin}`
                            : ""}
                      </span>
                    </div>
                    {dias.map((fecha) => {
                      const celda = celdas.get(`${franja.clave}|${fecha}`);
                      return (
                        <CeldaDePreview
                          key={`${franja.clave}-${fecha}`}
                          celda={celda}
                          finde={esFinDeSemana(fecha)}
                        />
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function CeldaDePreview({ celda, finde }: { celda?: CeldaPreview; finde: boolean }) {
  const personas = celda?.personas ?? [];
  const eventos = celda?.eventos ?? [];
  return (
    <div
      className={cn(
        "flex min-h-[6rem] flex-col gap-1.5 border-l p-2",
        finde && "bg-muted/40 dark:bg-muted/20",
      )}
    >
      {personas.length === 0 && eventos.length === 0 && (
        <span className="px-0.5 text-[10px] text-muted-foreground/50">—</span>
      )}
      {personas.map((p) => (
        <PersonaPreviewChip key={p.clave} persona={p} />
      ))}
      {eventos.map((e) => (
        <EventoPreviewChip key={e.clave} evento={e} />
      ))}
    </div>
  );
}

function PersonaPreviewChip({ persona }: { persona: ChipPreviewPersona }) {
  const estilo = persona.categoria ? ESTILO_CATEGORIA[persona.categoria] : null;
  return (
    <div
      className={cn(
        "flex flex-col gap-0.5 rounded-md border px-1.5 py-1 text-xs",
        estilo
          ? estilo.borde
          : "border-border bg-background opacity-60",
      )}
    >
      <span className="flex items-center gap-1">
        {persona.categoria === "cambio" ? (
          <Pencil className="h-3 w-3 shrink-0" />
        ) : (
          <User className="h-3 w-3 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate font-medium">{persona.nombre}</span>
        {estilo && (
          <Badge variant="outline" className={cn("ml-auto h-4 px-1 text-[9px]", estilo.chip)}>
            {estilo.etiqueta}
          </Badge>
        )}
      </span>
      {persona.detalle && (
        <span className="text-[10px] text-muted-foreground">{persona.detalle}</span>
      )}
    </div>
  );
}

function EventoPreviewChip({ evento }: { evento: ChipPreviewEvento }) {
  const estilo = evento.categoria ? ESTILO_CATEGORIA[evento.categoria] : null;
  const cob = evento.tipoCobertura ? COBERTURA[evento.tipoCobertura] : null;
  const Icono = evento.categoria === "nuevo" ? CalendarPlus : cob?.icono;
  return (
    <div
      className={cn(
        "flex flex-col gap-0.5 rounded-sm border px-1.5 py-1 text-left text-[11px] leading-tight",
        estilo ? estilo.chip : cn(cob?.chip ?? "border-border", "opacity-60"),
      )}
    >
      <span className="flex items-start gap-1">
        {Icono && <Icono className="mt-0.5 h-2.5 w-2.5 shrink-0" />}
        <span className="min-w-0 break-words font-medium">{evento.titulo}</span>
        {evento.categoria === "conflicto" && (
          <AlertTriangle className="ml-auto mt-0.5 h-2.5 w-2.5 shrink-0" />
        )}
      </span>
      <span className="flex flex-wrap items-center gap-x-1.5 opacity-90">
        {evento.hora && <span>{evento.hora}</span>}
        {evento.prioridad && (
          <span className={COLOR_PRIORIDAD[evento.prioridad]}>· {evento.prioridad}</span>
        )}
        {estilo && <span className="font-semibold uppercase">· {estilo.etiqueta}</span>}
      </span>
    </div>
  );
}

/** Leyenda de colores del preview (verde nuevo · ámbar cambio · rojo conflicto). */
export function LeyendaPreview() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      {(Object.keys(ESTILO_CATEGORIA) as Categoria[]).map((cat) => (
        <span key={cat} className="inline-flex items-center gap-1.5">
          <span
            className={cn(
              "inline-block h-2.5 w-2.5 rounded-full",
              cat === "nuevo"
                ? "bg-emerald-500"
                : cat === "cambio"
                  ? "bg-amber-500"
                  : "bg-red-500",
            )}
          />
          {ESTILO_CATEGORIA[cat].etiqueta}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5 opacity-60">
        <span className="inline-block h-2.5 w-2.5 rounded-full border border-border bg-background" />
        Ya en el calendario
      </span>
    </div>
  );
}

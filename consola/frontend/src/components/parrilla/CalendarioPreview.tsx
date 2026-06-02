/**
 * Calendario de la rota en modo PREVISUALIZACIÓN (solo lectura) con las operaciones
 * propuestas por un import SUPERPUESTAS y codificadas por color:
 *   - verde  = nuevo      (crear_evento / crear_turno)
 *   - ámbar  = cambio     (modificar_turno)
 *   - rojo   = conflicto  (cualquier operación con `conflicto: true`)
 *
 * Renderiza la MISMA rejilla día × franja que el calendario real (`pages/Rota.tsx`),
 * reusando sus primitivas visuales (`@/lib/rota-calendario`: COBERTURA, COLOR_PRIORIDAD,
 * diaCorto, esFinDeSemana…). El usuario ve exactamente el calendario que resultaría tras
 * aceptar la propuesta: las filas reales aparecen atenuadas y las propuestas resaltadas.
 *
 * No hace CRUD: es un espejo del resultado del merge. Por eso vive como componente propio
 * en vez de añadir un `modoPreview` a la rejilla editable (que arrastra dropdowns,
 * mutaciones y menús contextuales que aquí no aplican y solo añadirían riesgo).
 */
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarPlus,
  Pencil,
  Sunrise,
  Sunset,
  User,
} from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
  diaCorto,
  diasDeSemana,
  esFinDeSemana,
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

function horaAMinutos(s: string): number | null {
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

function franjaIdParaHoraEvento(hora: string, franjas: FranjaSemana[]): string | null {
  if (franjas.length === 0) return null;
  for (const f of franjas.filter((x) => !x.es_descanso)) {
    if (horaEnRangoFranja(hora, f.inicio, f.fin)) return f.id;
  }
  return franjas.find((f) => f.es_descanso)?.id ?? franjas[0]?.id ?? null;
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
  if (typeof c.franja_id === "string") partes.push("cambia de franja");
  if (typeof c.miembro_id === "string") partes.push("reasigna persona");
  if (typeof c.motivo === "string") partes.push("motivo");
  if (typeof c.nota_relevo === "string") partes.push("nota de relevo");
  if (typeof c.override === "boolean") partes.push(`override → ${c.override ? "sí" : "no"}`);
  return partes.length > 0 ? partes.join(" · ") : "modificación";
}

export function CalendarioPreview({
  semana,
  operaciones,
}: {
  /** Lunes ISO de la semana destino de la propuesta. */
  semana: string;
  operaciones: OperacionPropuesta[];
}) {
  // El estado REAL de la semana: turnos + cobertura (los mismos endpoints del calendario).
  const turnosQ = useQuery({
    queryKey: ["rota", "turnos", semana],
    queryFn: ({ signal }) => api.listarTurnos({ lunes: semana }, signal),
  });
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", semana],
    queryFn: ({ signal }) => api.cobertura({ lunes: semana }, signal),
  });

  const dias = React.useMemo(() => diasDeSemana(semana), [semana]);

  const franjasSemana = React.useMemo<FranjaSemana[]>(
    () =>
      (turnosQ.data?.franjas ?? coberturaQ.data?.franjas ?? [])
        .slice()
        .sort((a, b) => a.orden - b.orden),
    [turnosQ.data?.franjas, coberturaQ.data?.franjas],
  );

  // Construye el mapa `franja_id|fecha` → CeldaPreview a partir del estado REAL + overlay.
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

    // 1) Personas reales (turnos existentes), atenuadas.
    for (const t of (turnosQ.data?.turnos ?? []) as TurnoRota[]) {
      obtener(`${t.franja_id}|${t.fecha}`).personas.push({
        clave: `real-${t.id}`,
        nombre: t.miembro_nombre,
        categoria: null,
      });
    }

    // 2) Eventos reales con cobertura, atenuados.
    for (const ev of (coberturaQ.data?.eventos ?? []) as CoberturaEvento[]) {
      if (ev.fecha < dias[0]! || ev.fecha > dias[6]!) continue;
      const franjaId =
        ev.cobertura[0]?.franja_id ?? franjaIdParaHoraEvento(ev.hora, franjasSemana);
      if (!franjaId) continue;
      obtener(`${franjaId}|${ev.fecha}`).eventos.push({
        clave: `real-ev-${ev.id}`,
        titulo: ev.titulo,
        hora: ev.hora,
        prioridad: ev.prioridad,
        tipoCobertura: ev.tipo_cobertura,
        categoria: null,
      });
    }

    // 3) Overlay: cada operación propuesta.
    operaciones.forEach((op, i) => {
      const categoria = categoriaDe(op);
      if (op.tipo === "crear_evento") {
        const o = op as OperacionCrearEvento;
        const franjaId = franjaIdParaHoraEvento(o.hora, franjasSemana);
        if (!franjaId) return;
        obtener(`${franjaId}|${o.fecha}`).eventos.push({
          clave: `op-${i}`,
          titulo: o.titulo,
          hora: o.hora,
          prioridad: o.prioridad,
          tipoCobertura: o.tipo_cobertura,
          categoria,
        });
      } else if (op.tipo === "crear_turno") {
        const o = op as OperacionCrearTurno;
        obtener(`${o.franja_id}|${o.fecha}`).personas.push({
          clave: `op-${i}`,
          nombre: o.miembro_nombre,
          categoria,
        });
      } else if (op.tipo === "modificar_turno") {
        const o = op as OperacionModificarTurno;
        // El turno modificado se ubica donde está HOY (valores `actual`); si el cambio
        // mueve fecha/franja, lo reflejamos en el detalle del chip.
        const fecha = (o.actual.fecha as string) ?? dias[0]!;
        const franjaId = (o.actual.franja_id as string) ?? franjasSemana[0]?.id ?? "";
        obtener(`${franjaId}|${fecha}`).personas.push({
          clave: `op-${i}`,
          nombre: (o.actual.miembro_nombre as string) ?? "Turno",
          categoria,
          detalle: resumirCambios(o),
        });
      }
    });

    return m;
  }, [turnosQ.data?.turnos, coberturaQ.data?.eventos, operaciones, dias, franjasSemana]);

  const cargando = turnosQ.isPending || coberturaQ.isPending;
  const error = turnosQ.error || coberturaQ.error;

  if (cargando) return <Skeleton className="h-[50vh] w-full rounded-md" />;
  if (error) {
    return (
      <BloqueError
        titulo="No se pudo cargar el calendario para previsualizar"
        mensaje={error instanceof Error ? error.message : "Error inesperado."}
        onReintentar={() => {
          void turnosQ.refetch();
          void coberturaQ.refetch();
        }}
        cargando={turnosQ.isFetching}
      />
    );
  }

  let indiceLaboral = 0;
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="overflow-auto" style={{ maxHeight: "calc(100vh - 24rem)" }}>
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
                      ? "bg-amber-50/40 dark:bg-amber-950/10"
                      : "bg-background",
                  )}
                >
                  <span className="text-xs font-semibold capitalize">{diaCorto(fecha)}</span>
                  <span className="text-xs text-muted-foreground">{fecha.slice(8, 10)}</span>
                </div>
              ))}
            </div>

            {franjasSemana.map((franja, idx) => {
              const idxLab = franja.es_descanso ? -1 : indiceLaboral++;
              const banda = franja.es_descanso
                ? "border-l-zinc-300 dark:border-l-zinc-700"
                : BANDAS_FRANJA_LABORAL[idxLab % BANDAS_FRANJA_LABORAL.length]!;
              return (
                <div
                  key={franja.id}
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
                      {franja.es_descanso ? "(descanso)" : `${franja.inicio}–${franja.fin}`}
                    </span>
                  </div>
                  {dias.map((fecha) => {
                    const celda = celdas.get(`${franja.id}|${fecha}`);
                    return (
                      <CeldaDePreview
                        key={`${franja.id}-${fecha}`}
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
  );
}

function CeldaDePreview({ celda, finde }: { celda?: CeldaPreview; finde: boolean }) {
  const personas = celda?.personas ?? [];
  const eventos = celda?.eventos ?? [];
  return (
    <div
      className={cn(
        "flex min-h-[6rem] flex-col gap-1.5 border-l p-2",
        finde && "bg-amber-50/20 dark:bg-amber-950/5",
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

// Pestaña MIS TURNOS de la rota. Partido mecánicamente de pages/Rota.tsx.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Clock,
  Coffee,
  Loader2,
  Sunrise,
  Sunset,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";
import {
  esFinDeSemana,
  mesDeFecha,
  mesSiguiente,
  mismoMes,
  nombreMes,
  semanasDelMes,
} from "@/lib/rota-calendario";
import { CLAVE_TAREAS } from "@/pages/tareas/claves";
import { agrupar } from "@/pages/tareas/tipos";
import type {
  TurnoRota,
} from "@/types";

import {
  NavegadorSemana,
  eventosPorTurno,
  formatearFechaCorta,
  type CubridorEvento,
  type ItemEventoCalendario,
} from "./comun";


// --- Pestaña: Mis turnos ----------------------------------------------------
//
// Dos vistas del MISMO dato (los turnos propios), con un selector arriba:
//   • «Mes»    — calendario mensual limpio: SOLO el horario propio, sin eventos ni
//                cobertura. Es la vista por defecto («ver mi mes de un vistazo»).
//   • «Semana» — la lista detallada de la semana, con los eventos que caen en cada
//                franja y el botón «Coger» (self-claim).

export function MisTurnos({
  lunes,
  setLunes,
  esAdmin = false,
  onVerCalendario,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  /** El admin no suele estar en la rota; el vacío le ofrece saltar al Calendario. */
  esAdmin?: boolean;
  onVerCalendario?: () => void;
}) {
  const [vista, setVista] = React.useState<"mes" | "semana">("mes");
  const [mes, setMes] = React.useState(() => mesDeFecha(new Date()));
  return (
    <div className="space-y-4">
      <SelectorVista vista={vista} setVista={setVista} />
      {vista === "mes" ? (
        <VistaMes
          mes={mes}
          setMes={setMes}
          esAdmin={esAdmin}
          onVerCalendario={onVerCalendario}
        />
      ) : (
        <VistaSemana
          lunes={lunes}
          setLunes={setLunes}
          esAdmin={esAdmin}
          onVerCalendario={onVerCalendario}
        />
      )}
    </div>
  );
}

/** Conmutador Mes/Semana, al estilo de la plataforma (segmentado sobrio). */
function SelectorVista({
  vista,
  setVista,
}: {
  vista: "mes" | "semana";
  setVista: (v: "mes" | "semana") => void;
}) {
  return (
    <div className="inline-flex rounded-md border p-0.5">
      {(
        [
          ["mes", "Mes"],
          ["semana", "Semana"],
        ] as const
      ).map(([valor, etiqueta]) => (
        <button
          key={valor}
          type="button"
          onClick={() => setVista(valor)}
          aria-pressed={vista === valor}
          className={`rounded px-3 py-1 text-sm font-medium transition-colors ${
            vista === valor
              ? "bg-muted text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {etiqueta}
        </button>
      ))}
    </div>
  );
}

// --- Vista MES: calendario mensual limpio (solo turnos propios) -------------

function VistaMes({
  mes,
  setMes,
  esAdmin = false,
  onVerCalendario,
}: {
  mes: string;
  setMes: (m: string) => void;
  esAdmin?: boolean;
  onVerCalendario?: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "mis-turnos-mes", mes, marcaActiva],
    queryFn: ({ signal }) =>
      api.misTurnosMes({ mes, marca: marcaActiva ?? undefined }, signal),
  });
  const datos = q.data;
  const turnos = React.useMemo(() => datos?.mis_turnos ?? [], [datos?.mis_turnos]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorMes mes={mes} setMes={setMes} />
        {datos?.miembro_nombre && (
          <Badge variant="secondary" className="font-normal">
            <User className="mr-1 h-3.5 w-3.5" /> {datos.miembro_nombre}
          </Badge>
        )}
      </div>

      {q.isPending ? (
        <Skeleton className="h-[28rem] w-full rounded-lg" />
      ) : q.isError ? (
        <BloqueError
          titulo="No se pudo cargar tu mes"
          mensaje={mensajeError(q.error)}
          onReintentar={() => void q.refetch()}
          cargando={q.isFetching}
        />
      ) : datos?.aviso ? (
        <EstadoVacio icono={User} titulo="Inicia sesión" texto={datos.aviso} />
      ) : turnos.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin turnos este mes"
          texto={
            esAdmin
              ? "Si gestionas el equipo, abre el Calendario para ver los turnos de todos."
              : "Aquí verás tu horario del mes en cuanto se publique."
          }
          accion={
            esAdmin && onVerCalendario ? (
              <Button variant="outline" size="sm" onClick={onVerCalendario}>
                Ver el calendario del equipo
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <RejillaMes mes={mes} turnos={turnos} />
          <p className="text-xs text-muted-foreground">
            Solo tus turnos del mes. Sin eventos ni cobertura.
          </p>
        </>
      )}
    </div>
  );
}

/** Navegador de mes (‹ junio de 2026 ›) con atajo «Hoy». */
function NavegadorMes({
  mes,
  setMes,
}: {
  mes: string;
  setMes: (m: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="icon"
        aria-label="Mes anterior"
        onClick={() => setMes(mesSiguiente(mes, -1))}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <div className="min-w-[11rem] text-center text-sm font-medium capitalize">
        <CalendarDays className="mr-1.5 inline h-4 w-4 text-muted-foreground" />
        {nombreMes(mes)}
      </div>
      <Button
        variant="outline"
        size="icon"
        aria-label="Mes siguiente"
        onClick={() => setMes(mesSiguiente(mes, 1))}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-muted-foreground"
        onClick={() => setMes(mesDeFecha(new Date()))}
      >
        Hoy
      </Button>
    </div>
  );
}

const DIAS_CABECERA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/** Rejilla mensual lun→dom. Cada día pinta las franjas propias con su horario. */
function RejillaMes({ mes, turnos }: { mes: string; turnos: TurnoRota[] }) {
  const hoy = hoyCDMX();
  const dias = React.useMemo(() => semanasDelMes(mes).flat(), [mes]);
  const porFecha = React.useMemo(() => {
    const m = new Map<string, TurnoRota[]>();
    for (const t of turnos) {
      const arr = m.get(t.fecha);
      if (arr) arr.push(t);
      else m.set(t.fecha, [t]);
    }
    return m;
  }, [turnos]);

  return (
    <div className="overflow-hidden rounded-lg border">
      <div className="grid grid-cols-7 border-b bg-muted/40 text-center text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {DIAS_CABECERA.map((d) => (
          <div key={d} className="py-2">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-px bg-border">
        {dias.map((fecha) => {
          const delMes = mismoMes(fecha, mes);
          const finde = esFinDeSemana(fecha);
          const esHoy = fecha === hoy;
          const delDia = porFecha.get(fecha) ?? [];
          return (
            <div
              key={fecha}
              className={`min-h-[5.25rem] bg-background p-1.5 ${
                !delMes ? "bg-muted/20" : finde ? "bg-muted/30" : ""
              } ${esHoy ? "ring-1 ring-inset ring-keni-500/50" : ""}`}
            >
              <div
                className={`mb-1 text-right text-xs tabular-nums ${
                  esHoy
                    ? "font-semibold text-keni-700 dark:text-keni-300"
                    : delMes
                      ? "text-muted-foreground"
                      : "text-muted-foreground/50"
                }`}
              >
                {Number(fecha.slice(8, 10))}
              </div>
              <div className="space-y-1">
                {delDia.map((t) => (
                  <ChipTurnoMes key={t.id} turno={t} atenuado={!delMes} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Chip de un turno dentro de una celda del mes: franja + horario (o «Descanso»). */
function ChipTurnoMes({ turno, atenuado }: { turno: TurnoRota; atenuado?: boolean }) {
  const esDescanso = turno.franja === "descanso";
  if (esDescanso) {
    return (
      <div
        className={`truncate rounded px-1.5 py-0.5 text-[11px] text-muted-foreground ${
          atenuado ? "opacity-50" : ""
        }`}
      >
        Descanso
      </div>
    );
  }
  return (
    <div
      className={`rounded bg-keni-50 px-1.5 py-0.5 text-[11px] leading-tight text-keni-800 dark:bg-keni-900/30 dark:text-keni-200 ${
        atenuado ? "opacity-50" : ""
      }`}
    >
      <div className="truncate font-medium">{turno.franja_nombre}</div>
      {turno.inicio && (
        <div className="tabular-nums text-keni-700/80 dark:text-keni-300/80">
          {turno.inicio}–{turno.fin}
        </div>
      )}
    </div>
  );
}

// --- Vista SEMANA: lista detallada (con eventos y «Coger») -------------------

function VistaSemana({
  lunes,
  setLunes,
  esAdmin = false,
  onVerCalendario,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  /** El admin no suele estar en la rota; el vacío le ofrece saltar al Calendario. */
  esAdmin?: boolean;
  onVerCalendario?: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const { usuario } = useSesion();
  const queryClient = useQueryClient();
  const q = useQuery({
    queryKey: ["rota", "mis-turnos", lunes, marcaActiva],
    queryFn: ({ signal }) =>
      api.misTurnos({ lunes, marca: marcaActiva ?? undefined }, signal),
  });
  const datos = q.data;
  const mios = React.useMemo(() => datos?.mis_turnos ?? [], [datos?.mis_turnos]);

  // Eventos de la semana + sus claims (titularidad), para colgar bajo cada turno los
  // eventos que caen en esa franja. MISMA fuente que el Calendario y el Panorama (queryKeys
  // compartidas), así coger desde aquí se refleja al instante en las tres vistas.
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes, marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.cobertura({ lunes, marca: marcaActiva ?? undefined }, signal),
  });
  const tareasQ = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marcaActiva ?? "todas"],
    queryFn: ({ signal }) =>
      api.contenido({ clase: "tarea", marca: marcaActiva ?? undefined }, signal),
  });

  // Franjas vivas de la semana, ordenadas por `orden` (las trae la propia respuesta de
  // mis-turnos): el bucketing hora→franja necesita los rangos.
  const franjasOrdenadas = React.useMemo(
    () => (datos?.franjas ?? []).slice().sort((a, b) => a.orden - b.orden),
    [datos?.franjas],
  );
  const eventos = React.useMemo(
    () => coberturaQ.data?.eventos ?? [],
    [coberturaQ.data?.eventos],
  );
  const tareas = React.useMemo(
    () => tareasQ.data?.contenidos ?? [],
    [tareasQ.data?.contenidos],
  );
  const cubridoresPorEvento = React.useMemo(() => {
    const m = new Map<string, CubridorEvento[]>();
    for (const c of agrupar(tareas, eventos).coberturas) {
      m.set(
        c.eventoId,
        c.cubridores.map((t) => ({ id: t.responsable_id, nombre: t.responsable_nombre })),
      );
    }
    return m;
  }, [tareas, eventos]);
  const eventosTurno = React.useMemo(
    () => eventosPorTurno(mios, eventos, cubridoresPorEvento, franjasOrdenadas),
    [mios, eventos, cubridoresPorEvento, franjasOrdenadas],
  );
  const eventosListos = !coberturaQ.isPending && !tareasQ.isPending;

  // Coger un evento por cubrir desde mi turno (self-claim, sin rol). Invalida las tareas →
  // las tres vistas (Mis turnos / Calendario / Panorama) lo reflejan.
  const coger = useMutation({
    mutationFn: (eventoId: string) => api.cubrirEvento(eventoId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success("Evento cogido: queda a tu nombre.");
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana
          lunes={lunes}
          setLunes={setLunes}
          inicio={datos?.inicio ?? ""}
          fin={datos?.fin ?? ""}
        />
        {datos?.miembro_nombre && (
          <Badge variant="secondary" className="font-normal">
            <User className="mr-1 h-3.5 w-3.5" /> {datos.miembro_nombre}
          </Badge>
        )}
      </div>

      {q.isPending ? (
        <Skeleton className="h-40 w-full rounded-md" />
      ) : q.isError ? (
        <BloqueError
          titulo="No se pudieron cargar tus turnos"
          mensaje={mensajeError(q.error)}
          onReintentar={() => void q.refetch()}
          cargando={q.isFetching}
        />
      ) : datos?.aviso ? (
        <EstadoVacio icono={User} titulo="Inicia sesión" texto={datos.aviso} />
      ) : mios.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin turnos esta semana"
          texto={
            esAdmin
              ? "Si gestionas el equipo, abre el Calendario para ver los turnos de todos."
              : undefined
          }
          accion={
            esAdmin && onVerCalendario ? (
              <Button variant="outline" size="sm" onClick={onVerCalendario}>
                Ver el calendario del equipo
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          {!datos?.aprobada && (
            <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
              Este horario es un borrador; puede cambiar antes de aprobarse
            </p>
          )}
          <ListaMisTurnos
            turnos={mios}
            eventosPorTurno={eventosTurno}
            eventosListos={eventosListos}
            miId={usuario?.id ?? ""}
            onCoger={(eventoId) => coger.mutate(eventoId)}
            cogiendoId={coger.isPending ? coger.variables ?? null : null}
          />
        </>
      )}
    </div>
  );
}

// Icono por franja para escanear la lista de un vistazo (móvil-first). Mismo criterio que
// la rejilla del Calendario: amanecer = mañana, atardecer = tarde, café = descanso.
const ICONO_FRANJA: Record<string, typeof Sunrise> = {
  matutino: Sunrise,
  vespertino: Sunset,
  descanso: Coffee,
};

export function ListaMisTurnos({
  turnos,
  eventosPorTurno,
  eventosListos = true,
  miId = "",
  onCoger,
  cogiendoId,
}: {
  turnos: TurnoRota[];
  /** Eventos que caen en cada turno (clave = `turno.id`). Sin él no se pinta el bloque. */
  eventosPorTurno?: Map<string, ItemEventoCalendario[]>;
  /** `false` mientras cargan eventos/claims (muestra un esqueleto en vez de «sin eventos»). */
  eventosListos?: boolean;
  /** Id del usuario actual: para marcar «Lo cubres tú». */
  miId?: string;
  /** Coger un evento por cubrir (self-claim). Sin él, la columna es de solo lectura. */
  onCoger?: (eventoId: string) => void;
  /** Id del evento que se está cogiendo (deshabilita su botón). */
  cogiendoId?: string | null;
}) {
  // Orden cronológico (fecha, franja).
  const ordenados = React.useMemo(
    () =>
      [...turnos].sort(
        (a, b) => a.fecha.localeCompare(b.fecha) || a.franja.localeCompare(b.franja),
      ),
    [turnos],
  );
  // Móvil-first: una tarjeta por turno, apilada en vertical. El dato primario (franja +
  // día) manda con tipografía grande y un icono de franja; los matices (sábado / override /
  // motivo / relevo) van debajo, legibles sin disparar el auto-zoom de iOS (nada < 16px en
  // los textos de acción; los matices son secundarios y deliberadamente pequeños).
  return (
    <ul className="space-y-3">
      {ordenados.map((t) => {
        // El icono se elige por si es descanso (café) o trabajo (sol). `TurnoRota` no trae
        // `es_descanso`, pero el backend mapea de forma fiable las franjas de descanso al
        // literal legacy `franja === "descanso"`; para el resto reusamos el literal cuando lo
        // hay (mañana/tarde) y caemos a Sunset para franjas custom (p. ej. "Cobertura nocturna").
        const esDescanso = t.franja === "descanso";
        const IconoFranja = esDescanso ? Coffee : ICONO_FRANJA[t.franja] ?? Sunset;
        const eventosDelTurno = eventosPorTurno?.get(t.id) ?? [];
        return (
          <li key={t.id}>
            <Card>
              <CardContent className="space-y-2 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-base font-semibold">
                    <IconoFranja
                      className="h-4 w-4 text-muted-foreground"
                      aria-hidden="true"
                    />
                    {t.franja_nombre}
                    {!esDescanso && t.inicio && (
                      <span className="font-normal tabular-nums text-muted-foreground">
                        · {t.inicio}–{t.fin}
                      </span>
                    )}
                  </span>
                  {t.horario_propio && !esDescanso && (
                    <Badge variant="outline" className="font-normal">
                      Horario a medida
                    </Badge>
                  )}
                  {t.es_sabado && (
                    <Badge variant="outline" className="font-normal">
                      Sábado
                    </Badge>
                  )}
                  {t.override && (
                    <Badge variant="aviso" className="font-normal">
                      Override
                    </Badge>
                  )}
                </div>
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <CalendarDays className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span className="capitalize">{formatearFechaCorta(t.fecha)}</span>
                </div>
                {t.motivo && (
                  <div className="text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Motivo: </span>
                    {t.motivo}
                  </div>
                )}
                {t.nota_relevo && (
                  <div className="rounded-md bg-muted/50 px-2.5 py-1.5 text-sm">
                    <span className="font-medium">Relevo: </span>
                    {t.nota_relevo}
                  </div>
                )}
                {/* Eventos que caen en esta franja ese día: «qué me toca cubrir en mi turno».
                    Solo en franjas laborales (en descanso no hay cobertura). */}
                {!esDescanso && eventosPorTurno !== undefined && (
                  <div className="space-y-1.5 border-t pt-2.5">
                    <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" aria-hidden="true" /> En tu franja
                    </p>
                    {!eventosListos ? (
                      <Skeleton className="h-4 w-40 rounded" />
                    ) : eventosDelTurno.length === 0 ? (
                      <p className="text-sm text-muted-foreground">
                        Sin eventos en esta franja.
                      </p>
                    ) : (
                      <ul className="space-y-1.5">
                        {eventosDelTurno.map(({ evento, cubridores }) => {
                          const loCubroYo = cubridores.some((c) => c.id === miId);
                          const otros = cubridores.filter((c) => c.id !== miId);
                          return (
                            <li
                              key={evento.id}
                              className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
                            >
                              <span className="tabular-nums text-muted-foreground">
                                {evento.hora || "—"}
                              </span>
                              <span className="font-medium">{evento.titulo}</span>
                              {loCubroYo ? (
                                <Badge variant="ok" className="font-normal">
                                  Lo cubres tú
                                </Badge>
                              ) : cubridores.length > 0 ? (
                                <Badge variant="secondary" className="font-normal">
                                  Lo cubre {cubridores.map((c) => c.nombre).join(", ")}
                                </Badge>
                              ) : (
                                <>
                                  <Badge variant="aviso" className="font-normal">
                                    Por cubrir
                                  </Badge>
                                  {onCoger && (
                                    <Button
                                      size="sm"
                                      variant="outline"
                                      className="h-7 px-2.5 text-xs"
                                      onClick={() => onCoger(evento.id)}
                                      disabled={cogiendoId === evento.id}
                                    >
                                      {cogiendoId === evento.id ? (
                                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                      ) : (
                                        "Coger"
                                      )}
                                    </Button>
                                  )}
                                </>
                              )}
                              {loCubroYo && otros.length > 0 && (
                                <span className="text-xs text-muted-foreground">
                                  · también {otros.map((c) => c.nombre).join(", ")}
                                </span>
                              )}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </li>
        );
      })}
    </ul>
  );
}


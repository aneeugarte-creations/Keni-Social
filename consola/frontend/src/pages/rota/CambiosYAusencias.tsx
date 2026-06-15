// Pestaña CAMBIOS Y AUSENCIAS (swaps de turno #175 + ausencias). Partido de pages/Rota.tsx.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CalendarOff,
  Check,
  Circle,
  Clock,
  Loader2,
  Plus,
  Send,
  Shield,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import {
  iso,
  lunesDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import type {
  AusenciaRota,
  EstadoSwap,
  FiltrosSwaps,
  SwapTurno,
  TurnoRota,
} from "@/types";

import { NuevaAusencia, TarjetaAusencia } from "./Ausencias";
import { ChipToggle, ETIQUETA_FRANJA, filtrarEquipoPorMarca, formatearFechaCorta } from "./comun";


// --- Flujo (todo lo orquesta el backend; el cliente solo informa) -----------
//   A (solicitante) crea -> B (destinatario) acepta/rechaza -> admin aprueba
//   (ejecuta el swap sobre `rota_turnos_trabajo`) o rechaza. A puede cancelar
//   mientras el estado no sea terminal (terminales: aplicado, rechazado,
//   rechazado_admin, cancelado).

/** Etiqueta legible para cada estado del swap (es-MX, voz del producto). */
export const ETIQUETA_ESTADO_SWAP: Record<EstadoSwap, string> = {
  propuesto: "Pendiente de su respuesta",
  aceptado: "Aceptado · espera a Elías",
  aprobado: "Aprobado por Elías",
  aplicado: "Aplicado al horario",
  rechazado: "Rechazado por el compañero",
  rechazado_admin: "Rechazado por Elías",
  cancelado: "Cancelado",
};

/** Variante visual del Badge para cada estado del swap. */
export const VARIANTE_ESTADO_SWAP: Record<
  EstadoSwap,
  "aviso" | "secondary" | "ok" | "error"
> = {
  propuesto: "aviso",
  aceptado: "secondary",
  aprobado: "ok",
  aplicado: "ok",
  rechazado: "error",
  rechazado_admin: "error",
  // Cancelar es una salida NEUTRA (el solicitante retiró su petición), no un fallo: gris,
  // no rojo. El rojo se reserva a rechazos reales.
  cancelado: "secondary",
};

/** Estados terminales: el swap ya no admite más acciones (solo historial). */
export const ESTADOS_TERMINALES_SWAP: ReadonlySet<EstadoSwap> = new Set([
  "aplicado",
  "rechazado",
  "rechazado_admin",
  "cancelado",
]);

/** Timestamp ISO ("2026-05-25T18:42:11", UTC) como fecha-hora corta en CDMX. */
export const formatearMomentoCorto = (s: string): string => formatearFechaHoraCorta(s);

/** Estado de cada nodo del progreso de un swap (la cadena solicitante→compañero→el coordinador de la rota). */
type EstadoPasoSwap = "hecho" | "actual" | "pendiente" | "rechazado";

interface PasoSwap {
  etiqueta: string;
  detalle: string;
  estado: EstadoPasoSwap;
}

/**
 * Deriva los 3 nodos del progreso de un swap (solicitante → compañero → el coordinador de la rota) a partir
 * SOLO de su estado. Hace VISIBLE en qué punto de la cadena está la solicitud sin tocar el
 * backend: es la misma máquina de estados que `ETIQUETA_ESTADO_SWAP`, vista como recorrido.
 *
 * No hay estado "caducado" en el backend; los terminales que sí existen (rechazado del
 * compañero / del admin / cancelado) se reflejan en el nodo donde la cadena se detuvo.
 */
export function pasosSwap(swap: SwapTurno): PasoSwap[] {
  const e = swap.estado;
  const companeroRespondio = Boolean(swap.decidido_destinatario);

  // Nodo del compañero (destinatario): acepta o rechaza la propuesta.
  let compania: EstadoPasoSwap;
  let detalleCompania: string;
  if (e === "propuesto") {
    compania = "actual";
    detalleCompania = "Pendiente de responder";
  } else if (e === "rechazado") {
    compania = "rechazado";
    detalleCompania = "Rechazó";
  } else if (e === "cancelado") {
    compania = companeroRespondio ? "hecho" : "pendiente";
    detalleCompania = companeroRespondio ? "Aceptó" : "Sin responder";
  } else {
    // aceptado / aprobado / aplicado / rechazado_admin: el compañero ya aceptó.
    compania = "hecho";
    detalleCompania = "Aceptó";
  }

  // Nodo del coordinador de la rota (admin): aprueba (y aplica) o rechaza.
  let elias: EstadoPasoSwap;
  let detalleElias: string;
  if (e === "aprobado" || e === "aplicado") {
    elias = "hecho";
    detalleElias = e === "aplicado" ? "Aplicado" : "Aprobó";
  } else if (e === "rechazado_admin") {
    elias = "rechazado";
    detalleElias = "Rechazó";
  } else if (e === "aceptado") {
    elias = "actual";
    detalleElias = "Pendiente de aprobar";
  } else {
    elias = "pendiente";
    detalleElias = e === "cancelado" ? "Cancelado" : "En espera";
  }

  return [
    { etiqueta: swap.solicitante_nombre, detalle: "Solicitó", estado: "hecho" },
    { etiqueta: swap.destinatario_nombre, detalle: detalleCompania, estado: compania },
    { etiqueta: "Elías", detalle: detalleElias, estado: elias },
  ];
}

const ICONO_PASO_SWAP: Record<EstadoPasoSwap, typeof Check> = {
  hecho: Check,
  actual: Clock,
  pendiente: Circle,
  rechazado: X,
};

const COLOR_PASO_SWAP: Record<EstadoPasoSwap, string> = {
  hecho: "text-emerald-600 dark:text-emerald-400",
  actual: "text-amber-600 dark:text-amber-400",
  pendiente: "text-muted-foreground/50",
  rechazado: "text-red-600 dark:text-red-400",
};

/**
 * Indicador de progreso legible de un swap: solicitante → compañero → el coordinador de la rota. Cada nodo
 * lleva icono (hecho ✓ / pendiente ⏳ / en espera ○ / rechazado ✕) + nombre + un detalle
 * corto, para que de un vistazo se vea en qué eslabón está la cadena.
 */
export function ProgresoSwap({ swap }: { swap: SwapTurno }) {
  const pasos = pasosSwap(swap);
  return (
    <ol
      className="flex flex-wrap items-center gap-x-1 gap-y-2"
      aria-label="Progreso de la solicitud"
    >
      {pasos.map((p, i) => {
        const Icono = ICONO_PASO_SWAP[p.estado];
        return (
          <React.Fragment key={i}>
            {i > 0 && <span className="h-px w-3 shrink-0 bg-border" aria-hidden="true" />}
            <li className="flex items-center gap-1">
              <Icono className={`h-3.5 w-3.5 shrink-0 ${COLOR_PASO_SWAP[p.estado]}`} />
              <span className="flex flex-col leading-tight">
                <span
                  className={`text-xs font-medium ${
                    p.estado === "pendiente" ? "text-muted-foreground" : ""
                  }`}
                >
                  {p.etiqueta}
                </span>
                <span className="text-[10px] text-muted-foreground">{p.detalle}</span>
              </span>
            </li>
          </React.Fragment>
        );
      })}
    </ol>
  );
}

/**
 * Vista FUSIONADA de Cambios de turno + Ausencias en una sola lista cronologica.
 * Una unica cabecera, un boton "Nueva solicitud" que abre un formulario colapsable
 * con selector de tipo, una banda de chips para filtrar (tipo + estado) y una lista
 * mezclada de tarjetas (cada una con su badge de tipo: "Cambio" o "Ausencia").
 *
 * Sigue habiendo dos consultas backend (swaps y ausencias) porque cada recurso es
 * independiente; la fusion ocurre en cliente. Conserva el contrato actual de los
 * endpoints REST.
 */
export function CambiosYAusencias({ esAdmin }: { esAdmin: boolean }) {
  const { usuario } = useSesion();
  const { marcaActiva } = useMarcaActiva();
  const queryClient = useQueryClient();

  // Filtros locales (sin URL, solo estado): tipo y estado.
  const [filtroTipo, setFiltroTipo] = React.useState<"todo" | "cambios" | "ausencias">("todo");
  const [filtroEstado, setFiltroEstado] = React.useState<"activos" | "historial">("activos");
  const [formAbierto, setFormAbierto] = React.useState(false);
  const [tipoSolicitud, setTipoSolicitud] = React.useState<"cambio" | "ausencia">("cambio");

  // El usuario admin ve todos los swaps (incluyendo "Para aprobar" donde no es
  // parte). El resto solo ve los swaps en los que participa (`mio=true`).
  // GRID POR MARCA: los swaps se acotan a la rejilla activa; "Todas" (null) muestra todos.
  const filtrosSwaps: FiltrosSwaps = {
    ...(esAdmin ? {} : { mio: true }),
    ...(marcaActiva ? { marca: marcaActiva } : {}),
  };
  const swapsQ = useQuery({
    enabled: usuario !== null,
    queryKey: ["rota", "swaps", filtrosSwaps] as const,
    queryFn: ({ signal }) => api.listarSwaps(filtrosSwaps, signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? [], marcaActiva);

  const invalidarSwaps = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota", "swaps"] });
  const invalidarAusencias = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota", "ausencias"] });

  // Cargando: si AMBOS estan pendientes (mostramos skeleton); de lo contrario
  // mezclamos lo que tengamos (evitamos parpadeos al cambiar de filtro).
  const cargandoTodo =
    (usuario !== null && swapsQ.isPending) || ausenciasQ.isPending;
  const errorSwaps = swapsQ.isError;
  const errorAusencias = ausenciasQ.isError;

  // Lista cronologica unificada: cada item es discriminado por `tipo` para que
  // el render decida que tarjeta usar. Orden DESC: el mas reciente primero.
  // - Swaps tienen `creado` (timestamp ISO).
  // - Ausencias NO tienen timestamp de creacion en el backend; usamos `desde`
  //   como proxy de "cuando entra en juego" (tradeoff conocido: si en futuro el
  //   backend persiste `creado_en`, se reemplaza por ese campo).
  type ItemSwap = { tipo: "cambio"; orden: string; swap: SwapTurno };
  type ItemAusencia = { tipo: "ausencia"; orden: string; ausencia: AusenciaRota };
  type ItemSolicitud = ItemSwap | ItemAusencia;

  const items: ItemSolicitud[] = React.useMemo(() => {
    const lista: ItemSolicitud[] = [];
    const swaps = swapsQ.data?.swaps ?? [];
    const ausencias = ausenciasQ.data?.ausencias ?? [];

    const esSwapActivo = (s: SwapTurno) => !ESTADOS_TERMINALES_SWAP.has(s.estado);
    // Heuristica para ausencias: "activa" = aun no ha terminado (hasta >= hoy).
    const hoy = iso(new Date());
    const esAusenciaActiva = (a: AusenciaRota) => (a.hasta || "") >= hoy;

    if (filtroTipo !== "ausencias") {
      for (const s of swaps) {
        const activo = esSwapActivo(s);
        if (filtroEstado === "activos" && !activo) continue;
        if (filtroEstado === "historial" && activo) continue;
        lista.push({ tipo: "cambio", orden: s.creado || s.actualizado || "", swap: s });
      }
    }
    if (filtroTipo !== "cambios") {
      for (const a of ausencias) {
        const activa = esAusenciaActiva(a);
        if (filtroEstado === "activos" && !activa) continue;
        if (filtroEstado === "historial" && activa) continue;
        lista.push({ tipo: "ausencia", orden: a.desde || "", ausencia: a });
      }
    }
    lista.sort((x, y) => (y.orden || "").localeCompare(x.orden || ""));
    return lista;
  }, [swapsQ.data, ausenciasQ.data, filtroTipo, filtroEstado]);

  // Sin sesion no hay "yo": el backend devuelve [] para `mio=true` y la creacion
  // de swap requiere usuario logueado. Avisamos honestamente.
  const sinSesion = usuario === null;

  return (
    <div className="space-y-4">
      {/* Cabecera SLIM, misma estetica que las pestañas Calendario / Mis turnos: sin Card de
          titulo (la pestaña ya rotula "Cambios y ausencias"), los filtros viven a la izquierda
          y la accion primaria a la derecha. El boton usa el gris de plataforma (secondary), el
          mismo que "Aprobar y publicar" del Calendario — no el negro de antes. */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Tipo
          </span>
          <ChipToggle activo={filtroTipo === "todo"} onClick={() => setFiltroTipo("todo")}>
            Todo
          </ChipToggle>
          <ChipToggle activo={filtroTipo === "cambios"} onClick={() => setFiltroTipo("cambios")}>
            Cambios
          </ChipToggle>
          <ChipToggle
            activo={filtroTipo === "ausencias"}
            onClick={() => setFiltroTipo("ausencias")}
          >
            Ausencias
          </ChipToggle>
          <span className="ml-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Estado
          </span>
          <ChipToggle
            activo={filtroEstado === "activos"}
            onClick={() => setFiltroEstado("activos")}
          >
            Activos
          </ChipToggle>
          <ChipToggle
            activo={filtroEstado === "historial"}
            onClick={() => setFiltroEstado("historial")}
          >
            Historial
          </ChipToggle>
        </div>
        <Button
          type="button"
          size="sm"
          variant={formAbierto ? "outline" : "secondary"}
          onClick={() => setFormAbierto((v) => !v)}
          disabled={sinSesion && !equipo.length}
        >
          {formAbierto ? (
            <>
              <X className="h-4 w-4" /> Cerrar
            </>
          ) : (
            <>
              <Plus className="h-4 w-4" /> Nueva solicitud
            </>
          )}
        </Button>
      </div>

      {formAbierto && (
        <Card>
          <CardContent className="space-y-4 p-6">
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Tipo
              </Label>
              <div className="flex flex-wrap gap-2">
                <ChipToggle
                  activo={tipoSolicitud === "cambio"}
                  onClick={() => setTipoSolicitud("cambio")}
                >
                  <ArrowLeftRight className="mr-1 h-3.5 w-3.5" /> Cambio de turno
                </ChipToggle>
                <ChipToggle
                  activo={tipoSolicitud === "ausencia"}
                  onClick={() => setTipoSolicitud("ausencia")}
                >
                  <CalendarOff className="mr-1 h-3.5 w-3.5" /> Ausencia
                </ChipToggle>
              </div>
            </div>
            {tipoSolicitud === "cambio" ? (
              sinSesion ? (
                <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
                  Inicia sesión para continuar.
                </div>
              ) : (
                <FormularioNuevoSwap
                  miId={usuario.id}
                  onCreado={() => {
                    invalidarSwaps();
                    setFormAbierto(false);
                  }}
                />
              )
            ) : (
              <NuevaAusencia
                equipo={equipo}
                esAdmin={esAdmin}
                miId={usuario?.id ?? ""}
                onCreada={() => {
                  invalidarAusencias();
                  setFormAbierto(false);
                }}
              />
            )}
          </CardContent>
        </Card>
      )}

      {errorSwaps && (
        <BloqueError
          titulo="No se pudieron cargar los cambios de turno"
          mensaje={mensajeError(swapsQ.error)}
          onReintentar={() => void swapsQ.refetch()}
          cargando={swapsQ.isFetching}
        />
      )}
      {errorAusencias && (
        <BloqueError
          titulo="No se pudieron cargar las ausencias"
          mensaje={mensajeError(ausenciasQ.error)}
          onReintentar={() => void ausenciasQ.refetch()}
          cargando={ausenciasQ.isFetching}
        />
      )}

      {cargandoTodo ? (
        // Skeleton con la FORMA de la lista (tarjetas), no un bloque suelto: la carga
        // "promete" el contenido real y evita el salto al aparecer.
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-28 w-full rounded-lg" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EstadoVacio
          icono={filtroTipo === "ausencias" ? CalendarOff : ArrowLeftRight}
          titulo={
            filtroEstado === "historial"
              ? "Sin historial todavía"
              : "Nada pendiente por ahora"
          }
          texto={
            filtroEstado === "historial"
              ? "Aquí aparecerán los cambios y ausencias ya cerrados."
              : "Pide cambiar un turno con un compañero o registra una ausencia."
          }
          accion={
            filtroEstado === "historial" ? undefined : (
              <Button variant="secondary" size="sm" onClick={() => setFormAbierto(true)}>
                <Plus className="h-4 w-4" /> Nueva solicitud
              </Button>
            )
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((it) =>
            it.tipo === "cambio" ? (
              <TarjetaSwap
                key={`swap-${it.swap.id}`}
                swap={it.swap}
                miId={usuario?.id ?? ""}
                esAdmin={esAdmin}
              />
            ) : (
              <TarjetaAusencia
                key={`au-${it.ausencia.id}`}
                ausencia={it.ausencia}
                puedeGestionar={esAdmin || it.ausencia.miembro_id === (usuario?.id ?? "")}
                onCambio={invalidarAusencias}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Formulario para pedir un cambio de turno.
 *
 * "Mi turno" (Select sobre los turnos REALES del solicitante en la semana actual
 * y la siguiente), "Turno deseado" (Select sobre los turnos de los demas CMs en el
 * mismo rango) y motivo opcional. De cada Select derivamos `fecha`/`franja_id`
 * (y `destinatario_id` del segundo). El backend sigue recibiendo el mismo cuerpo `crearSwap`.
 *
 * Rango: hardcoded a "semana actual + siguiente" (14 dias). Si la lista queda
 * vacia avisamos al usuario en lugar de saltar a otra ventana.
 */
export function FormularioNuevoSwap({
  miId,
  onCreado,
}: {
  miId: string;
  onCreado?: () => void;
}) {
  // Semana actual y la siguiente: dos consultas, una por semana, para reusar el
  // cache compartido con la pestaña Calendario. GRID POR MARCA: acotadas a la rejilla activa
  // (un swap vive dentro de la rejilla de una marca); la marca entra en la queryKey.
  const { marcaActiva } = useMarcaActiva();
  const lunesActual = React.useMemo(() => lunesDeSemana(new Date()), []);
  const lunesProxima = React.useMemo(() => lunesSiguiente(lunesActual, 1), [lunesActual]);

  const semana1Q = useQuery({
    queryKey: ["rota", "turnos", lunesActual, marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.listarTurnos({ lunes: lunesActual, marca: marcaActiva ?? undefined }, signal),
  });
  const semana2Q = useQuery({
    queryKey: ["rota", "turnos", lunesProxima, marcaActiva] as const,
    queryFn: ({ signal }) =>
      api.listarTurnos({ lunes: lunesProxima, marca: marcaActiva ?? undefined }, signal),
  });

  const turnos: TurnoRota[] = React.useMemo(
    () => [...(semana1Q.data?.turnos ?? []), ...(semana2Q.data?.turnos ?? [])],
    [semana1Q.data, semana2Q.data],
  );

  // Hoy en ISO: filtramos turnos pasados (no tiene sentido pedir cambio sobre
  // un dia que ya paso). La franja descanso si la permitimos: el backend valida.
  const hoyIso = React.useMemo(() => iso(new Date()), []);
  const turnosFuturos = React.useMemo(
    () => turnos.filter((t) => t.fecha >= hoyIso),
    [turnos, hoyIso],
  );

  const turnosMios = React.useMemo(
    () =>
      turnosFuturos
        .filter((t) => t.miembro_id === miId)
        .slice()
        .sort((a, b) => a.fecha.localeCompare(b.fecha) || a.franja_nombre.localeCompare(b.franja_nombre)),
    [turnosFuturos, miId],
  );
  const turnosOtros = React.useMemo(
    () =>
      turnosFuturos
        .filter((t) => t.miembro_id !== miId)
        .slice()
        .sort(
          (a, b) =>
            a.fecha.localeCompare(b.fecha) ||
            a.franja_nombre.localeCompare(b.franja_nombre) ||
            a.miembro_nombre.localeCompare(b.miembro_nombre),
        ),
    [turnosFuturos, miId],
  );

  // Las opciones del Select 1 codifican `${id}` y leemos el TurnoRota completo
  // por busqueda en la lista. Idem el Select 2.
  const [miTurnoId, setMiTurnoId] = React.useState("");
  const [turnoDeseadoId, setTurnoDeseadoId] = React.useState("");
  const [motivo, setMotivo] = React.useState("");

  const miTurno = turnosMios.find((t) => t.id === miTurnoId);
  const turnoDeseado = turnosOtros.find((t) => t.id === turnoDeseadoId);

  const crear = useMutation({
    mutationFn: () => {
      if (!miTurno || !turnoDeseado) throw new Error("Falta seleccionar los turnos.");
      return api.crearSwap({
        destinatario_id: turnoDeseado.miembro_id,
        fecha_a: miTurno.fecha,
        franja_a: miTurno.franja_id,
        fecha_b: turnoDeseado.fecha,
        franja_b: turnoDeseado.franja_id,
        motivo: motivo.trim(),
      });
    },
    onSuccess: () => {
      toast.success("Solicitud enviada. Tu compañero la vera en la lista.");
      setMiTurnoId("");
      setTurnoDeseadoId("");
      setMotivo("");
      onCreado?.();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cargando = semana1Q.isPending || semana2Q.isPending;
  const motivoExcedido = motivo.length > 500;
  const puedeCrear =
    miTurnoId !== "" &&
    turnoDeseadoId !== "" &&
    !motivoExcedido &&
    !crear.isPending;

  // Etiqueta de cada opcion: "Lun 8 jun · Mañana" o "Lun 8 jun · Mañana · un community manager"
  // segun si es opcion propia o de un compañero.
  const etiquetaTurnoPropio = (t: TurnoRota) =>
    `${formatearFechaCorta(t.fecha)} · ${t.franja_nombre}`;
  const etiquetaTurnoOtros = (t: TurnoRota) =>
    `${formatearFechaCorta(t.fecha)} · ${t.franja_nombre} · ${t.miembro_nombre}`;

  if (cargando) {
    return <Skeleton className="h-40 w-full rounded-md" />;
  }
  if (turnosMios.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
        No tienes turnos en este rango.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Mi turno</Label>
        <Select value={miTurnoId} onValueChange={setMiTurnoId}>
          <SelectTrigger aria-label="Mi turno">
            <SelectValue placeholder="Elige uno de tus turnos" />
          </SelectTrigger>
          <SelectContent>
            {turnosMios.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {etiquetaTurnoPropio(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Turno deseado</Label>
        <Select value={turnoDeseadoId} onValueChange={setTurnoDeseadoId}>
          <SelectTrigger aria-label="Turno deseado">
            <SelectValue placeholder="Elige el turno con el que quieres cambiar" />
          </SelectTrigger>
          <SelectContent>
            {turnosOtros.length === 0 ? (
              <div className="p-2 text-xs text-muted-foreground">
                No hay turnos de otros compañeros en este rango.
              </div>
            ) : (
              turnosOtros.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {etiquetaTurnoOtros(t)}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="swap-motivo">Motivo</Label>
        <Textarea
          id="swap-motivo"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Opcional: cita médica, evento familiar, examen…"
          rows={2}
          maxLength={500}
        />
        {motivoExcedido && (
          <div className="text-xs text-destructive">
            El motivo no puede pasar de 500 caracteres.
          </div>
        )}
      </div>
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => crear.mutate()} disabled={!puedeCrear}>
          {crear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Solicitar cambio
        </Button>
      </div>
    </div>
  );
}

/** Una tarjeta con los datos de un swap y los botones de acción según contexto. */
export function TarjetaSwap({
  swap,
  miId,
  esAdmin,
}: {
  swap: SwapTurno;
  miId: string;
  esAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota", "swaps"] });

  const soyDestinatario = swap.destinatario_id === miId;
  const soySolicitante = swap.solicitante_id === miId;
  const esTerminal = ESTADOS_TERMINALES_SWAP.has(swap.estado);

  // Qué acciones puede ejecutar el usuario en este swap, en este estado.
  // El backend revalida; aquí solo decidimos qué BOTONES enseñar.
  const puedeAceptarRechazarDestinatario =
    soyDestinatario && swap.estado === "propuesto";
  const puedeAprobarAdmin = esAdmin && swap.estado === "aceptado";
  const puedeCancelar = soySolicitante && !esTerminal;

  const cancelar = useMutation({
    mutationFn: () => api.cancelarSwap(swap.id),
    onSuccess: () => {
      toast.success("Solicitud cancelada.");
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="rounded-lg border bg-card p-4 shadow-sm space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Badge variant="outline" className="font-normal">
              <ArrowLeftRight className="mr-1 h-3 w-3" /> Cambio
            </Badge>
            <span className="font-medium">{swap.solicitante_nombre}</span>
            <ArrowLeftRight className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium">{swap.destinatario_nombre}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            <span>
              {formatearFechaCorta(swap.fecha_a)} ·{" "}
              {swap.franja_a_nombre ?? ETIQUETA_FRANJA[swap.franja_a]}
            </span>
            <span className="mx-1.5">↔</span>
            <span>
              {formatearFechaCorta(swap.fecha_b)} ·{" "}
              {swap.franja_b_nombre ?? ETIQUETA_FRANJA[swap.franja_b]}
            </span>
          </div>
        </div>
        <Badge variant={VARIANTE_ESTADO_SWAP[swap.estado]}>
          {ETIQUETA_ESTADO_SWAP[swap.estado]}
        </Badge>
      </div>

      {/* Indicador de progreso de la cadena (solicitante → compañero → el coordinador de la rota): hace
          inequívoco en qué punto está la solicitud, complementando el badge de estado. */}
      <ProgresoSwap swap={swap} />

      {/* Mientras el swap sigue abierto, el turno NO ha cambiado de manos: lo dejamos claro
          para que nadie lo confunda con un turno ya cubierto/cedido. */}
      {!esTerminal && (
        <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-2.5 py-1.5 text-xs text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
          {soySolicitante || soyDestinatario
            ? "Este turno sigue siendo tuyo hasta que se aplique el cambio."
            : "Cada quien conserva su turno hasta que se aplique el cambio."}
        </p>
      )}

      {swap.motivo && (
        <div className="text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Motivo ·{" "}
          </span>
          <span className="text-foreground">{swap.motivo}</span>
        </div>
      )}
      {swap.respuesta_destinatario && (
        <div className="text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Respuesta de {swap.destinatario_nombre} ·{" "}
          </span>
          <span className="text-foreground">{swap.respuesta_destinatario}</span>
        </div>
      )}
      {swap.respuesta_admin && (
        <div className="text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Nota de Elías ·{" "}
          </span>
          <span className="text-foreground">{swap.respuesta_admin}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>Creado: {formatearMomentoCorto(swap.creado)}</span>
        {swap.decidido_destinatario && (
          <span>· Respondió el compañero: {formatearMomentoCorto(swap.decidido_destinatario)}</span>
        )}
        {swap.decidido_admin && (
          <span>· Decisión admin: {formatearMomentoCorto(swap.decidido_admin)}</span>
        )}
        {swap.aplicado && (
          <span>· Aplicado: {formatearMomentoCorto(swap.aplicado)}</span>
        )}
      </div>

      {(puedeAceptarRechazarDestinatario || puedeAprobarAdmin || puedeCancelar) && (
        <div className="flex flex-wrap justify-end gap-2 pt-1">
          {puedeAceptarRechazarDestinatario && (
            <>
              <DialogAccionSwap
                swapId={swap.id}
                accion="aceptar"
                onCambio={invalidar}
                trigger={
                  <Button size="sm" variant="secondary">
                    <Check className="h-4 w-4" /> Aceptar
                  </Button>
                }
              />
              <DialogAccionSwap
                swapId={swap.id}
                accion="rechazar"
                onCambio={invalidar}
                trigger={
                  <Button size="sm" variant="outline">
                    <X className="h-4 w-4" /> Rechazar
                  </Button>
                }
              />
            </>
          )}
          {puedeAprobarAdmin && (
            <>
              <DialogAccionSwap
                swapId={swap.id}
                accion="aprobar"
                onCambio={invalidar}
                trigger={
                  <Button size="sm" variant="secondary">
                    <ShieldCheck className="h-4 w-4" /> Aprobar y aplicar
                  </Button>
                }
              />
              <DialogAccionSwap
                swapId={swap.id}
                accion="rechazar_admin"
                onCambio={invalidar}
                trigger={
                  <Button size="sm" variant="outline">
                    <Shield className="h-4 w-4" /> Rechazar
                  </Button>
                }
              />
            </>
          )}
          {puedeCancelar && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => cancelar.mutate()}
              disabled={cancelar.isPending}
            >
              {cancelar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Cancelar solicitud
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Diálogo de confirmación para aceptar/rechazar/aprobar/rechazar-admin un swap.
 * Pide una nota opcional ("respuesta") antes de mandar la mutación. El backend
 * valida estado, identidad y rol; aquí solo informamos.
 */
export function DialogAccionSwap({
  swapId,
  accion,
  onCambio,
  trigger,
}: {
  swapId: string;
  accion: "aceptar" | "rechazar" | "aprobar" | "rechazar_admin";
  onCambio: () => void;
  trigger: React.ReactNode;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const [respuesta, setRespuesta] = React.useState("");

  // Cada acción tiene su título, llamada API y texto del botón confirmar.
  const META: Record<
    typeof accion,
    {
      titulo: string;
      descripcion: string;
      botonConfirmar: string;
      llamar: (cuerpo: { respuesta?: string }) => Promise<unknown>;
      toastOk: string;
      placeholder: string;
    }
  > = {
    aceptar: {
      titulo: "Aceptar el cambio",
      descripcion:
        "Aceptar: tu compañero recibirá tu respuesta",
      botonConfirmar: "Aceptar",
      llamar: (cuerpo) => api.aceptarSwap(swapId, cuerpo),
      toastOk: "Cambio aceptado. Espera la aprobación de Elías.",
      placeholder: "Sin problema, yo te cubro…",
    },
    rechazar: {
      titulo: "Rechazar el cambio",
      descripcion: "Rechazas el cambio. Opcionalmente, explica por qué.",
      botonConfirmar: "Rechazar",
      llamar: (cuerpo) => api.rechazarSwap(swapId, cuerpo),
      toastOk: "Cambio rechazado.",
      placeholder: "No puedo ese día porque…",
    },
    aprobar: {
      titulo: "Aprobar y aplicar el cambio",
      descripcion:
        "Los turnos se intercambiarán en el horario del equipo",
      botonConfirmar: "Aprobar y aplicar",
      llamar: (cuerpo) => api.aprobarSwap(swapId, cuerpo),
      toastOk: "Cambio aprobado y aplicado al horario.",
      placeholder: "Ojo con el relevo / nota interna…",
    },
    rechazar_admin: {
      titulo: "Rechazar el cambio",
      descripcion: "Rechazarás el cambio acordado por el equipo.",
      botonConfirmar: "Rechazar",
      llamar: (cuerpo) => api.rechazarSwapAdmin(swapId, cuerpo),
      toastOk: "Cambio rechazado.",
      placeholder: "Ese día necesitamos a… en transmisión.",
    },
  };
  const meta = META[accion];

  const mutar = useMutation({
    mutationFn: () => meta.llamar({ respuesta: respuesta.trim() }),
    onSuccess: () => {
      toast.success(meta.toastOk);
      setRespuesta("");
      setAbierto(false);
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <>
      <span onClick={() => setAbierto(true)}>{trigger}</span>
      <Dialog open={abierto} onOpenChange={setAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{meta.titulo}</DialogTitle>
            <DialogDescription>{meta.descripcion}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor={`resp-${swapId}-${accion}`}>Respuesta</Label>
            <Textarea
              id={`resp-${swapId}-${accion}`}
              value={respuesta}
              onChange={(e) => setRespuesta(e.target.value)}
              placeholder={meta.placeholder}
              rows={3}
              maxLength={500}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAbierto(false)}>
              Cancelar
            </Button>
            <Button variant="secondary" onClick={() => mutar.mutate()} disabled={mutar.isPending}>
              {mutar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              {meta.botonConfirmar}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}


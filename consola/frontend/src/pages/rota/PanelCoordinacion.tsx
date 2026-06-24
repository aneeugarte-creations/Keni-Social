// «Panel de coordinación» (admin): reúne en UN sitio las señales de la semana visible que piden la
// decisión de un coordinador y que hoy viven repartidas por varias pestañas (huecos sin cubrir,
// cambios/ausencias pendientes, conflictos de turno). Es ADITIVO y de solo
// lectura: reusa los mismos endpoints y derivaciones que el resto de Turnos; no añade backend ni
// chrome nuevo (outline gris de plataforma, color solo con significado: amarillo = pide decisión).
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeftRight, ArrowRight, UserPlus } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { resumenCobertura } from "@/lib/cobertura";
import { diasDeSemana, lunesSiguiente } from "@/lib/rota-calendario";
import { CLAVE_TAREAS } from "@/pages/tareas/claves";
import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  Publicacion,
  SwapTurno,
  TurnoRota,
} from "@/types";

import { contarSwapsPendientes } from "./comun";
import { conflictosDeLaSemana } from "./ResumenDia";
import { useTiempoLibreActivo } from "./useConfigRota";

/** Las cuatro señales agregadas del panel para una semana. Conteos puros (sin presentación). */
export interface SenalesCoordinacion {
  /** Huecos reales de la semana: eventos ni cogidos ni cubiertos por turno (sin-cubrir). */
  sinCubrir: number;
  /** Cambios de turno que esperan la acción del coordinador (`propuesto` a mí / `aceptado` a aprobar). */
  cambiosPendientes: number;
  /** Conflictos de la semana: solapes de turno por persona + personas de turno ausentes ese día. */
  conflictos: number;
}

/**
 * Deriva las cuatro señales del panel a partir de los datos YA disponibles en Turnos. Pura (sin
 * fetch ni React) para poder testearla aislada. Cada señal reusa la MISMA fuente que su vista:
 *  - `sinCubrir`: `resumenCobertura` (selector canónico `lib/cobertura`) sobre los eventos+claims+
 *    turnos+franjas+ausencias de la semana, idéntico al «N sin cubrir» del Calendario.
 *  - `cambiosPendientes`: `contarSwapsPendientes`, el mismo contador del badge de «Cambios y ausencias».
 *  - `conflictos`: `conflictosDeLaSemana` (agrega `conflictosDelDia` del «Resumen del día»).
 */
export function derivarPanelCoordinacion(
  lunes: string,
  eventos: EventoRota[],
  claims: Publicacion[],
  turnos: TurnoRota[],
  franjas: FranjaSemana[],
  ausencias: AusenciaRota[],
  swaps: SwapTurno[],
  usuarioId: string,
  esAdmin: boolean,
): SenalesCoordinacion {
  const dias = diasDeSemana(lunes);
  const desde = lunes;
  const hasta = lunesSiguiente(lunes, 1); // exclusivo
  const eventosSemana = eventos.filter((e) => e.fecha >= desde && e.fecha < hasta);
  const ausenciasSemana = ausencias.filter((a) => a.desde <= dias[6]! && a.hasta >= desde);

  const sinCubrir = resumenCobertura(
    eventosSemana,
    claims,
    turnos,
    franjas,
    undefined,
    ausenciasSemana,
  ).sinCubrir;

  const franjaPorId = new Map<string, FranjaSemana>(franjas.map((f) => [f.id, f]));
  const conflictos = conflictosDeLaSemana(dias, turnos, franjaPorId, ausenciasSemana).length;

  return {
    sinCubrir,
    cambiosPendientes: contarSwapsPendientes(swaps, usuarioId, esAdmin),
    conflictos,
  };
}

/** Una fila del panel: icono + conteo + etiqueta + (acción a donde se actúa). */
function Fila({
  icono,
  texto,
  accion,
  destacar = false,
}: {
  icono: React.ReactNode;
  texto: React.ReactNode;
  accion?: React.ReactNode;
  /** `true` = señal que pide decisión (borde/fondo amarillo); `false` = neutro. */
  destacar?: boolean;
}) {
  return (
    <li
      className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm ${
        destacar
          ? "border-yellow-300 bg-yellow-50/60 dark:border-yellow-800 dark:bg-yellow-950/20"
          : "border-border bg-card"
      }`}
    >
      <span className="flex items-center gap-2">
        {icono}
        {texto}
      </span>
      {accion}
    </li>
  );
}

/**
 * Hook: deriva las señales de coordinación de la semana (huecos sin cubrir, cambios/ausencias
 * pendientes, conflictos) desde los MISMOS endpoints que el resto de Turnos (cache compartida por
 * queryKey, sin tráfico extra). `activo` lo gatea junto a `esAdmin` para que solo corra en la
 * pestaña «Gestión». Lo consume index.tsx para, con una sola derivación, alimentar el
 * `PanelCoordinacion` Y decidir el marcador ✓ «Al día» de la cabecera del calendario.
 */
export function useSenalesCoordinacion({
  lunes,
  marcaActiva,
  usuarioId,
  esAdmin,
  activo,
}: {
  lunes: string;
  /** Marca activa del workspace; `null` = «Todas» (sin filtro). */
  marcaActiva: string | null;
  usuarioId: string;
  esAdmin: boolean;
  /** Solo dispara las queries cuando la vista que lo necesita (Gestión) está activa. */
  activo: boolean;
}): { senales: SenalesCoordinacion; todoEnOrden: boolean; cargando: boolean } {
  const marca = marcaActiva ?? undefined;
  const habilitado = esAdmin && activo;
  // Con el tiempo libre apagado no se cuentan conflictos por ausencia (sí los solapes de turno).
  const tiempoLibreActivo = useTiempoLibreActivo();

  // Misma queryKey que el Calendario (turnos/franjas/aprobada de la semana) y que el tablero de
  // Cobertura (tareas + eventos): la cache se comparte y el panel late con el resto de Turnos.
  const turnosQ = useQuery({
    queryKey: ["rota", "turnos", lunes, marcaActiva] as const,
    queryFn: ({ signal }) => api.listarTurnos({ lunes, marca }, signal),
    enabled: habilitado,
  });
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes, marcaActiva] as const,
    queryFn: ({ signal }) => api.cobertura({ lunes, marca }, signal),
    enabled: habilitado,
  });
  const tareasQ = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    enabled: habilitado,
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
    enabled: habilitado && tiempoLibreActivo,
  });
  const swapsQ = useQuery({
    queryKey: ["rota", "swaps", marca ? { marca } : {}] as const,
    queryFn: ({ signal }) => api.listarSwaps(marca ? { marca } : {}, signal),
    enabled: habilitado,
  });

  const semana = turnosQ.data;
  const senales = React.useMemo(
    () =>
      derivarPanelCoordinacion(
        lunes,
        coberturaQ.data?.eventos ?? [],
        tareasQ.data?.contenidos ?? [],
        semana?.turnos ?? [],
        semana?.franjas ?? [],
        tiempoLibreActivo ? (ausenciasQ.data?.ausencias ?? []) : [],
        swapsQ.data?.swaps ?? [],
        usuarioId,
        esAdmin,
      ),
    [
      lunes,
      coberturaQ.data?.eventos,
      tareasQ.data?.contenidos,
      semana?.turnos,
      semana?.franjas,
      ausenciasQ.data?.ausencias,
      swapsQ.data?.swaps,
      usuarioId,
      esAdmin,
      tiempoLibreActivo,
    ],
  );

  const cargando = turnosQ.isPending || coberturaQ.isPending || tareasQ.isPending;
  const todoEnOrden =
    senales.sinCubrir === 0 && senales.cambiosPendientes === 0 && senales.conflictos === 0;
  return { senales, todoEnOrden, cargando };
}

/**
 * Panel de coordinación de la semana (PRESENTACIONAL): pinta solo las señales que PIDEN decisión
 * (huecos sin cubrir, cambios pendientes, conflictos). SOSIEGO: cuando no hay NADA pendiente no
 * pinta nada —el cockpit desaparece y el calendario sube—; la confirmación «al día» la da el
 * marcador ✓ de la cabecera del calendario, no una banda. Las señales y el estado de carga los
 * trae el llamante (index.tsx) vía {@link useSenalesCoordinacion}.
 */
export function PanelCoordinacion({
  senales,
  cargando,
  onIr,
}: {
  senales: SenalesCoordinacion;
  cargando: boolean;
  /** Salta a otra pestaña de Turnos (p. ej. «cambios-ausencias»). */
  onIr: (pestania: string) => void;
}) {
  if (cargando) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full rounded-lg" />
        <Skeleton className="h-9 w-full rounded-lg" />
      </div>
    );
  }

  const { sinCubrir, cambiosPendientes, conflictos } = senales;
  // SOSIEGO: en orden el cockpit desaparece por completo (el ✓ «Al día» de la cabecera basta).
  if (sinCubrir === 0 && cambiosPendientes === 0 && conflictos === 0) return null;

  return (
    <section aria-label="Panel de coordinación" className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">Necesita tu decisión</h3>
      <ul className="space-y-2">
          {sinCubrir > 0 && (
            <Fila
              destacar
              icono={<UserPlus className="h-4 w-4 text-yellow-700 dark:text-yellow-300" />}
              texto={
                <span>
                  <span className="font-semibold tabular-nums">{sinCubrir}</span> sin cubrir esta
                  semana
                </span>
              }
              accion={
                <Button variant="ghost" size="sm" onClick={() => onIr("cobertura")}>
                  Ver cobertura <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              }
            />
          )}
          {cambiosPendientes > 0 && (
            <Fila
              destacar
              icono={<ArrowLeftRight className="h-4 w-4 text-yellow-700 dark:text-yellow-300" />}
              texto={
                <span>
                  <span className="font-semibold tabular-nums">{cambiosPendientes}</span> cambio
                  {cambiosPendientes === 1 ? "" : "s"} de turno pendiente
                  {cambiosPendientes === 1 ? "" : "s"}
                </span>
              }
              accion={
                <Button variant="ghost" size="sm" onClick={() => onIr("cambios-ausencias")}>
                  Revisar <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              }
            />
          )}
          {conflictos > 0 && (
            <Fila
              destacar
              icono={<AlertTriangle className="h-4 w-4 text-yellow-700 dark:text-yellow-300" />}
              texto={
                <span>
                  <span className="font-semibold tabular-nums">{conflictos}</span> conflicto
                  {conflictos === 1 ? "" : "s"} de turno (solapes o ausentes con turno)
                </span>
              }
              accion={
                <Button variant="ghost" size="sm" onClick={() => onIr("calendario")}>
                  Ver calendario <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              }
            />
          )}
        </ul>
    </section>
  );
}

// «Panel de coordinación» (admin): reúne en UN sitio las señales de la semana visible que piden la
// decisión de un coordinador y que hoy viven repartidas por varias pestañas (huecos sin cubrir,
// semana en borrador, cambios/ausencias pendientes, conflictos de turno). Es ADITIVO y de solo
// lectura: reusa los mismos endpoints y derivaciones que el resto de Turnos; no añade backend ni
// chrome nuevo (outline gris de plataforma, color solo con significado: amarillo = pide decisión).
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowLeftRight, ArrowRight, CheckCircle2, FileEdit, UserPlus } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
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

/** Las cuatro señales agregadas del panel para una semana. Conteos puros (sin presentación). */
export interface SenalesCoordinacion {
  /** Huecos reales de la semana: eventos ni cogidos ni cubiertos por turno (sin-cubrir). */
  sinCubrir: number;
  /** `true` si la semana NO está publicada (sigue en borrador y hay turnos que publicar). */
  semanaEnBorrador: boolean;
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
 *  - `semanaEnBorrador`: `aprobada` de la rota de la semana (lo expone `api.listarTurnos`), con
 *    turnos que publicar.
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
  aprobada: boolean,
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
    semanaEnBorrador: !aprobada && turnos.length > 0,
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
 * Panel de coordinación de la semana en vista. Solo se usa en la pestaña «Gestión» (admin-only),
 * encima del panel de la semana. `lunes`/`marcaActiva` los comparte con el Calendario para mirar la
 * MISMA semana; `onIr` cambia de pestaña dentro de Turnos (sin inventar rutas). Si no es admin no
 * pinta nada (defensa en profundidad: la pestaña ya está gateada).
 */
export function PanelCoordinacion({
  lunes,
  marcaActiva,
  esAdmin,
  usuarioId,
  onIr,
}: {
  lunes: string;
  /** Marca activa del workspace; `null` = «Todas» (sin filtro). */
  marcaActiva: string | null;
  esAdmin: boolean;
  usuarioId: string;
  /** Salta a otra pestaña de Turnos (p. ej. «cambios-ausencias»). */
  onIr: (pestania: string) => void;
}) {
  const marca = marcaActiva ?? undefined;

  // Misma queryKey que el Calendario (turnos/franjas/aprobada de la semana) y que el tablero de
  // Cobertura (tareas + eventos): la cache se comparte y el panel late con el resto de Turnos.
  const turnosQ = useQuery({
    queryKey: ["rota", "turnos", lunes, marcaActiva] as const,
    queryFn: ({ signal }) => api.listarTurnos({ lunes, marca }, signal),
    enabled: esAdmin,
  });
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes, marcaActiva] as const,
    queryFn: ({ signal }) => api.cobertura({ lunes, marca }, signal),
    enabled: esAdmin,
  });
  const tareasQ = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    enabled: esAdmin,
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
    enabled: esAdmin,
  });
  const swapsQ = useQuery({
    queryKey: ["rota", "swaps", marca ? { marca } : {}] as const,
    queryFn: ({ signal }) => api.listarSwaps(marca ? { marca } : {}, signal),
    enabled: esAdmin,
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
        ausenciasQ.data?.ausencias ?? [],
        swapsQ.data?.swaps ?? [],
        Boolean(semana?.aprobada),
        usuarioId,
        esAdmin,
      ),
    [
      lunes,
      coberturaQ.data?.eventos,
      tareasQ.data?.contenidos,
      semana?.turnos,
      semana?.franjas,
      semana?.aprobada,
      ausenciasQ.data?.ausencias,
      swapsQ.data?.swaps,
      usuarioId,
      esAdmin,
    ],
  );

  if (!esAdmin) return null;

  const cargando =
    turnosQ.isPending || coberturaQ.isPending || tareasQ.isPending;
  if (cargando) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full rounded-lg" />
        <Skeleton className="h-9 w-full rounded-lg" />
      </div>
    );
  }

  const { sinCubrir, semanaEnBorrador, cambiosPendientes, conflictos } = senales;
  const todoEnOrden =
    sinCubrir === 0 && !semanaEnBorrador && cambiosPendientes === 0 && conflictos === 0;

  return (
    <section aria-label="Panel de coordinación" className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">Necesita tu decisión</h3>
      {todoEnOrden ? (
        <p className="flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground">
          <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
          Todo en orden esta semana: nada pendiente de tu decisión.
        </p>
      ) : (
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
          {semanaEnBorrador && (
            <Fila
              destacar
              icono={<FileEdit className="h-4 w-4 text-yellow-700 dark:text-yellow-300" />}
              texto={<span>La semana está en borrador, sin publicar al equipo</span>}
              accion={
                <Badge
                  variant="outline"
                  className="border-yellow-300 font-normal text-yellow-700 dark:border-yellow-800 dark:text-yellow-300"
                >
                  Aprobar abajo
                </Badge>
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
      )}
    </section>
  );
}

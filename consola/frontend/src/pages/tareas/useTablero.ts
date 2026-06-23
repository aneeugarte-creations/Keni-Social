import { useQueries, useQuery } from "@tanstack/react-query";

import { useRelojVivo } from "@/hooks/use-reloj-vivo";
import { api } from "@/lib/api";
import { derivarCoberturaEvento, type CubridorPorTurno } from "@/lib/cobertura";
import { hoyCDMX, posicionTemporal } from "@/lib/fecha";
import { lunesSiguiente } from "@/lib/rota-calendario";
import type { RotaSemana } from "@/types";

import { CLAVE_TAREAS } from "./claves";
import { agrupar, type Item } from "./tipos";

// El tablero es COMPARTIDO: late al mismo pulso para que el claim/asignación de un compañero
// se vea sin recargar (igual que el reparto del feed que esto sustituye).
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/**
 * Derivación ÚNICA del tablero de cobertura (eventos + tareas + cobertura por turno), compartida
 * por el cuerpo «Cobertura» (TareasBoard) y la home «Hoy». Centraliza el fetch y la derivación
 * cubierto-por-turno / sin-cubrir vía el selector canónico (`lib/cobertura`), para que ningún
 * consumidor la reconstruya a mano. Incluye `useRelojVivo` para que los semáforos avancen.
 *
 * `fecha` (por defecto HOY en CDMX) es el día del que salen los cortes `eventosHoy`/`turnosHoy`/
 * `franjasHoy`/`hechasHoy` (y `esDeHoy`): pasándola se obtiene el mismo «resumen» de CUALQUIER
 * día sin que los consumidores que la omiten (Cobertura, home «Hoy») cambien. `hoy` en el retorno
 * sigue siendo HOY real (es el ancla temporal de la agenda), independiente de `fecha`.
 */
export function useTablero(
  marca: string | undefined,
  usuarioId: string | null,
  fecha: string = hoyCDMX(),
) {
  useRelojVivo();
  const hoy = hoyCDMX();

  const tareasQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
  });
  // La ventana de fetch arranca en el más temprano de HOY y el día seleccionado: así un resumen de
  // un día PASADO trae igualmente sus eventos (la agenda sigue mostrando de HOY en adelante).
  const desdeEventos = fecha < hoy ? fecha : hoy;
  const eventosQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "eventos", marca ?? "todas", desdeEventos],
    queryFn: ({ signal }) => api.rotaEventos({ desde: desdeEventos, marca }, signal),
    ...REFRESCO,
  });
  // Ausencias (vacaciones/descanso/baja): una persona ausente NO cubre por turno. Global (sin
  // marca), suplementaria: si falla, la cobertura simplemente no resta (no tumba el tablero).
  const ausenciasQuery = useQuery({
    queryKey: ["rota", "ausencias"],
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
    ...REFRESCO,
  });

  const tareas = tareasQuery.data?.contenidos ?? [];
  const catalogos = tareasQuery.data?.catalogos;
  const cargando = tareasQuery.isLoading || eventosQuery.isLoading;
  const hayError = tareasQuery.isError || eventosQuery.isError;
  const sinDatos = !tareasQuery.data || !eventosQuery.data;
  const reintentar = () => {
    void tareasQuery.refetch();
    void eventosQuery.refetch();
    void ausenciasQuery.refetch();
  };

  const eventosCoverables = eventosQuery.data?.eventos ?? [];
  const ausencias = ausenciasQuery.data?.ausencias ?? [];
  const { coberturas, encargos, eventosLibres, recuperables } = agrupar(tareas, eventosCoverables);

  const semanasEventos = Array.from(
    new Set(eventosCoverables.filter((e) => e.fecha).map((e) => lunesSiguiente(e.fecha, 0))),
  );
  const semanasTurnos = useQueries({
    queries: semanasEventos.map((lunes) => ({
      queryKey: ["rota", "turnos", lunes, marca ?? "todas"],
      queryFn: ({ signal }: { signal?: AbortSignal }) => api.listarTurnos({ lunes, marca }, signal),
      ...REFRESCO,
    })),
  });
  const porLunes = new Map<string, RotaSemana>();
  semanasTurnos.forEach((q, i) => {
    if (q.data) porLunes.set(semanasEventos[i], q.data);
  });
  const rotaDe = (e: { fecha: string }): RotaSemana | undefined =>
    e.fecha ? porLunes.get(lunesSiguiente(e.fecha, 0)) : undefined;
  // Evento → personas de turno que lo cubren. `Map` (no `Set`): además de marcar qué eventos cubre
  // un turno (`.has(id)`, como antes), guarda QUIÉN para poder revelarlo al pulsar el badge.
  const cubiertosPorTurno = new Map<string, CubridorPorTurno[]>();
  for (const e of eventosLibres) {
    const semana = rotaDe(e);
    if (!semana) continue;
    const d = derivarCoberturaEvento(e, [], semana.turnos, semana.franjas, undefined, ausencias);
    if (d.estado === "cubierto-turno") cubiertosPorTurno.set(e.id, d.porTurno);
  }

  // Cortes del DÍA SELECCIONADO (`fecha`, por defecto HOY). Las claves del retorno conservan el
  // sufijo «Hoy» por contrato con los consumidores; su contenido sale de `fecha`.
  const eventosHoy = eventosCoverables.filter((e) => e.fecha === fecha);
  const claimsCobertura = tareas.filter((t) => t.evento_id);
  const semanaHoy = porLunes.get(lunesSiguiente(fecha, 0));
  const turnosHoy = (semanaHoy?.turnos ?? []).filter((t) => t.fecha === fecha);
  const franjasHoy = semanaHoy?.franjas ?? [];

  const esDeHoy = (f?: string | null) => (f || "").slice(0, 10) === fecha;
  const hechasHoy =
    coberturas.filter((c) => esDeHoy(c.orden) && posicionTemporal(c.orden, c.hora) === "despues")
      .length +
    [...encargos, ...recuperables].filter(
      (t) => esDeHoy(t.fecha_objetivo) && t.estado === "hecha",
    ).length;

  const conOrden = (f: string) => f || "9999-99-99";
  const items: Item[] = [
    ...coberturas.map((c) => ({
      kind: "cobertura" as const,
      clave: `c-${c.eventoId}`,
      orden: conOrden(c.orden),
      cobertura: c,
    })),
    ...[...encargos, ...recuperables].map((t) => ({
      kind: "tarea" as const,
      clave: `t-${t.id}`,
      orden: conOrden(t.fecha_objetivo),
      tarea: t,
    })),
    ...eventosLibres.map((e) => ({
      kind: "evento" as const,
      clave: `e-${e.id}`,
      orden: conOrden(e.fecha),
      evento: e,
      cubiertoPorTurno: cubiertosPorTurno.has(e.id),
      cubridoresPorTurno: cubiertosPorTurno.get(e.id) ?? [],
    })),
  ].sort((a, b) => a.orden.localeCompare(b.orden));

  const esPorCubrir = (i: Item) =>
    (i.kind === "evento" && !i.cubiertoPorTurno) || (i.kind === "tarea" && !i.tarea.responsable_id);
  const esMio = (i: Item) => {
    if (!usuarioId) return false;
    return i.kind === "cobertura"
      ? i.cobertura.cubridores.some((t) => t.responsable_id === usuarioId)
      : i.kind === "tarea" && i.tarea.responsable_id === usuarioId;
  };

  return {
    hoy, fecha, cargando, hayError, sinDatos, reintentar,
    error: tareasQuery.error ?? eventosQuery.error,
    isFetching: tareasQuery.isFetching || eventosQuery.isFetching,
    catalogos, tareas, eventosCoverables, cubiertosPorTurno, ausencias,
    eventosHoy, claimsCobertura, turnosHoy, franjasHoy, hechasHoy,
    items, esPorCubrir, esMio,
  };
}

import { useQueries, useQuery } from "@tanstack/react-query";

import { useRelojVivo } from "@/hooks/use-reloj-vivo";
import { api } from "@/lib/api";
import { derivarCoberturaEvento } from "@/lib/cobertura";
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
 */
export function useTablero(marca: string | undefined, usuarioId: string | null) {
  useRelojVivo();
  const hoy = hoyCDMX();

  const tareasQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
  });
  const eventosQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "eventos", marca ?? "todas"],
    queryFn: ({ signal }) => api.rotaEventos({ desde: hoy, marca }, signal),
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
  };

  const eventosCoverables = eventosQuery.data?.eventos ?? [];
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
  const cubiertosPorTurno = new Set<string>();
  for (const e of eventosLibres) {
    const semana = rotaDe(e);
    if (!semana) continue;
    const d = derivarCoberturaEvento(e, [], semana.turnos, semana.franjas);
    if (d.estado === "cubierto-turno") cubiertosPorTurno.add(e.id);
  }

  const eventosHoy = eventosCoverables.filter((e) => e.fecha === hoy);
  const claimsCobertura = tareas.filter((t) => t.evento_id);
  const semanaHoy = porLunes.get(lunesSiguiente(hoy, 0));
  const turnosHoy = semanaHoy?.turnos ?? [];
  const franjasHoy = semanaHoy?.franjas ?? [];

  const esDeHoy = (fecha?: string | null) => (fecha || "").slice(0, 10) === hoy;
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
    hoy, cargando, hayError, sinDatos, reintentar,
    error: tareasQuery.error ?? eventosQuery.error,
    isFetching: tareasQuery.isFetching || eventosQuery.isFetching,
    catalogos, tareas, eventosCoverables, cubiertosPorTurno,
    eventosHoy, claimsCobertura, turnosHoy, franjasHoy, hechasHoy,
    items, esPorCubrir, esMio,
  };
}

// Cobertura del MES para la rejilla mensual de Turnos: superpone eventos + estado de cobertura
// sobre la jornada (turnos) que ya muestra la vista. Replica a escala de MES el fetch+derivación
// del cockpit (`pages/tareas/useTablero`), aislado en un hook propio para no tocar esa infra
// compartida (Hoy/Cobertura). Deriva, por cada día del mes, cuántos eventos hay y cuántos están
// SIN CUBRIR (hueco real), reusando el selector canónico `resumenCobertura` de `lib/cobertura`.
import { useQueries, useQuery } from "@tanstack/react-query";
import * as React from "react";

import { useRelojVivo } from "@/hooks/use-reloj-vivo";
import { api } from "@/lib/api";
import { resumenCobertura } from "@/lib/cobertura";
import { lunesDeSemana, lunesSiguiente, semanasDelMes } from "@/lib/rota-calendario";
import { CLAVE_TAREAS } from "@/pages/tareas/claves";
import type {
  AusenciaRota,
  EventoRota,
  Publicacion,
  RotaSemana,
} from "@/types";

import { ausenciaTocaDia } from "./comun";

// Mismo pulso compartido que el cockpit: el claim/asignación de un compañero se ve sin recargar.
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/** Resumen de cobertura de UN día de la rejilla mensual (para el indicador compacto de la celda). */
export interface ResumenDiaCobertura {
  /** Total de eventos coverables ese día. */
  nEventos: number;
  /** Huecos reales (ni cogidos ni cubiertos por turno): «sin cubrir». */
  nSinCubrir: number;
  /** Eventos en vivo ahora (corte del semáforo). */
  nEnVivo: number;
  /** Hay ≥1 ausencia que toca el día (vacaciones/descanso/baja). */
  hayAusencia: boolean;
}

/** Lunes (ISO) de la semana CDMX que contiene `fecha` (AAAA-MM-DD), sin instanciar un Date real. */
function lunesDeFecha(fecha: string): string {
  return lunesDeSemana(new Date(`${fecha}T12:00:00Z`));
}

/**
 * Deriva, por DÍA, el resumen de cobertura (función PURA, testeable). Recorre los días del mes
 * `mes` (sus 4–6 semanas lun→dom); para cada uno agrupa sus eventos, su rota (turnos+franjas de la
 * semana que lo contiene) y resuelve el estado con `resumenCobertura` —la MISMA derivación del
 * cockpit—, pasando las ausencias para que un ausente no cuente como cubierto. Solo emite entradas
 * para días CON eventos o CON ausencia: un día sin nada queda fuera del Map (la celda lo distingue
 * como «día sin eventos»).
 *
 * `ahora` está en la firma por determinismo de tests; con `new Date()` coincide con el reloj real.
 */
export function derivarCoberturaPorDia(
  mes: string,
  eventos: EventoRota[],
  claims: Publicacion[],
  porLunes: Map<string, RotaSemana>,
  ausencias: AusenciaRota[],
  ahora: Date = new Date(),
): Map<string, ResumenDiaCobertura> {
  const eventosPorDia = new Map<string, EventoRota[]>();
  for (const e of eventos) {
    if (!e.fecha || e.tipo_cobertura === "no_cubrir") continue;
    const lista = eventosPorDia.get(e.fecha) ?? [];
    lista.push(e);
    eventosPorDia.set(e.fecha, lista);
  }

  const salida = new Map<string, ResumenDiaCobertura>();
  for (const fecha of semanasDelMes(mes).flat()) {
    const lista = eventosPorDia.get(fecha) ?? [];
    const hayAusencia = ausencias.some((a) => ausenciaTocaDia(a, fecha));
    if (lista.length === 0 && !hayAusencia) continue;

    const semana = porLunes.get(lunesDeFecha(fecha));
    const r = resumenCobertura(
      lista,
      claims,
      semana?.turnos ?? [],
      semana?.franjas ?? [],
      ahora,
      ausencias,
    );
    salida.set(fecha, {
      nEventos: r.total,
      nSinCubrir: r.sinCubrir,
      nEnVivo: r.enVivo,
      hayAusencia,
    });
  }
  return salida;
}

/**
 * Hook de cobertura del MES para la rejilla mensual de Turnos. Fetchea eventos del mes, claims
 * (tareas clase=tarea), las rotas de cada semana que toca el mes (`useQueries`) y las ausencias;
 * deriva un `Map<fecha, ResumenDiaCobertura>` con `derivarCoberturaPorDia`. Incluye `useRelojVivo`
 * para que el corte «en vivo» avance solo. NO reusa `useTablero` (infra del cockpit): es un hook
 * aislado a escala de mes.
 */
export function useTableroMes(mes: string, marca: string | undefined, enabled = true) {
  useRelojVivo();

  const semanas = React.useMemo(() => semanasDelMes(mes).map((s) => s[0]!), [mes]);
  const desde = semanas[0]!;
  // Fin EXCLUSIVO: el día siguiente al último de la rejilla (cubre toda la cola del mes vecino).
  const hasta = lunesSiguiente(semanas[semanas.length - 1]!, 1);

  // `enabled=false` (p. ej. el «Horario» de turnos puro, sin cobertura) no dispara NINGÚN fetch.
  const eventosQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "mes-eventos", marca ?? "todas", desde, hasta],
    queryFn: ({ signal }) => api.rotaEventos({ desde, hasta, marca }, signal),
    ...REFRESCO,
    enabled,
  });
  const claimsQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
    enabled,
  });
  const ausenciasQuery = useQuery({
    queryKey: ["rota", "ausencias"],
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
    ...REFRESCO,
    enabled,
  });

  // Una rota por cada lunes que toca la rejilla del mes (4–6); fetch en paralelo con `useQueries`.
  const turnosQueries = useQueries({
    queries: semanas.map((lunes) => ({
      queryKey: ["rota", "turnos", lunes, marca ?? "todas"],
      queryFn: ({ signal }: { signal?: AbortSignal }) =>
        api.listarTurnos({ lunes, marca }, signal),
      ...REFRESCO,
      enabled,
    })),
  });
  const porLunes = new Map<string, RotaSemana>();
  turnosQueries.forEach((q, i) => {
    if (q.data) porLunes.set(semanas[i]!, q.data);
  });

  const eventos = eventosQuery.data?.eventos ?? [];
  const claims = (claimsQuery.data?.contenidos ?? []).filter((t) => t.evento_id);
  const ausencias = ausenciasQuery.data?.ausencias ?? [];

  const porDia = derivarCoberturaPorDia(mes, eventos, claims, porLunes, ausencias);

  return {
    porDia,
    cargando: eventosQuery.isLoading || claimsQuery.isLoading,
    hayError: eventosQuery.isError || claimsQuery.isError,
  };
}

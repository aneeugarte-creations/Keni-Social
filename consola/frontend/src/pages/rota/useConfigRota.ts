import { useQuery } from "@tanstack/react-query";

import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

/**
 * Flag por marca: ¿está activa la funcionalidad de TIEMPO LIBRE / AUSENCIAS (vacaciones, baja,
 * descanso)? Lo configura el admin en «Ajustes de turnos». Comparte la misma queryKey que el
 * editor de franjas (cache única, se invalida con `invalidateQueries(["rota"])`), así las distintas
 * superficies que esconden/muestran el tiempo libre leen un solo valor coherente.
 *
 * Por defecto `true` (visible) mientras carga o si no hay config: la feature ya estaba desplegada;
 * el admin la apaga por excepción.
 */
export function useTiempoLibreActivo(): boolean {
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "config", "franjas", marcaActiva] as const,
    queryFn: ({ signal }) => api.obtenerConfigFranjas(marcaActiva ?? undefined, signal),
  });
  return q.data?.tiempo_libre_activo ?? true;
}

/**
 * Sondeo de NOTIFICACIONES in-app (el "cajón" de la campana). Coherente con `use-generacion`:
 * preferimos un SONDEO simple y robusto antes que WebSocket/SSE (el backend ya es la fuente de
 * verdad; el sondeo sobrevive a recargas y cambios de pestaña sin reconexión).
 *
 * Dos consultas separadas para no traer la lista entera cada 20 s:
 *   - `useContadorNotificaciones`  → solo el número de no leídas (alimenta el badge, sondea).
 *   - `useNotificaciones(abierto)` → la lista (se pide solo al ABRIR el cajón).
 *
 * Ambas están ACOTADAS a la marca activa (el switch de la barra superior): el cajón solo
 * muestra la marca seleccionada. `null` (vista "Todas" de admin) = sin filtro de marca.
 */
import { useQuery } from "@tanstack/react-query";

import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

/** Cadencia del sondeo del badge (ms). Ligero: solo cuenta no leídas. */
const INTERVALO_MS = 20_000;

/** Centinela de marca para la clave de caché cuando es "Todas" (null). */
const MARCA_TODAS = "__todas__";

/** Clave de caché del contador, por marca (para invalidar tras marcar leídas). */
export function claveContadorNotificaciones(marca: string | null): readonly [string, string] {
  return ["notificaciones-contador", marca ?? MARCA_TODAS] as const;
}

/** Clave de caché de la lista, por marca. */
export function claveNotificaciones(marca: string | null): readonly [string, string] {
  return ["notificaciones-lista", marca ?? MARCA_TODAS] as const;
}

/** Contador de no leídas de la marca activa (sondea cada 20 s). Alimenta el badge. */
export function useContadorNotificaciones() {
  const { marcaActiva } = useMarcaActiva();
  return useQuery({
    queryKey: claveContadorNotificaciones(marcaActiva),
    queryFn: ({ signal }) => api.contadorNotificaciones(marcaActiva ?? undefined, signal),
    refetchInterval: INTERVALO_MS,
    refetchOnWindowFocus: true,
  });
}

/** Lista de notificaciones de la marca activa. Se pide solo cuando el cajón está `abierto`. */
export function useNotificaciones(abierto: boolean) {
  const { marcaActiva } = useMarcaActiva();
  return useQuery({
    queryKey: claveNotificaciones(marcaActiva),
    queryFn: ({ signal }) => api.notificaciones(marcaActiva ?? undefined, signal),
    enabled: abierto,
  });
}

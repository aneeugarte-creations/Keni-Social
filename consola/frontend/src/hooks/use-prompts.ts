/**
 * Hooks del flujo de publicación de el almacén de prompts:
 *   - `useVariables`: catálogo de variables `{{NOMBRE}}` (GET /api/prompts/variables) con
 *     fallback elegante: si el endpoint aún no existe o falla, devuelve catálogo vacío
 *     (los chips se pintan sin tooltip y el autocompletado no ofrece nada).
 *   - `useEsAdmin`: ¿puede esta persona PUBLICAR a producción? Lee `es_admin` de la
 *     sesión (`GET /api/auth/me`); mientras el backend no lo mande, cae al rol clásico.
 *   - `useSolicitudes`: solicitudes de publicación (GET /api/prompts/solicitudes).
 */
import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import type { VariableCatalogo } from "@/types";

/** Clave de query del catálogo de variables (compartida por chips y autocompletado). */
export const CLAVE_VARIABLES = ["prompts-variables"] as const;

/** Clave de query de las solicitudes de publicación. */
export const claveSolicitudes = (estado: string) => ["prompts-solicitudes", estado] as const;

export interface CatalogoVariables {
  /** Variables del catálogo ([] mientras carga o si el endpoint no responde). */
  variables: VariableCatalogo[];
  /** Índice por nombre (sin llaves) para lookups O(1) desde los chips. */
  porNombre: Map<string, VariableCatalogo>;
  cargando: boolean;
}

/**
 * Catálogo de variables `{{NOMBRE}}`. Cacheado y compartido (staleTime alto: el catálogo
 * sale de código del backend, no cambia en caliente). `retry: 1` y sin throw: un 404
 * (backend aún sin desplegar) degrada a catálogo vacío sin romper la UI.
 */
export function useVariables(habilitado = true): CatalogoVariables {
  const query = useQuery({
    queryKey: CLAVE_VARIABLES,
    queryFn: ({ signal }) => api.variablesPrompts(signal),
    enabled: habilitado,
    staleTime: 5 * 60_000,
    retry: 1,
  });
  const variables = React.useMemo(() => query.data?.variables ?? [], [query.data]);
  const porNombre = React.useMemo(
    () => new Map(variables.map((v) => [v.nombre, v])),
    [variables],
  );
  return { variables, porNombre, cargando: habilitado && query.isPending };
}

/**
 * `true` si la persona puede publicar a producción en la Prompts. Fuente: `es_admin`
 * del endpoint de identidad; fallback al rol clásico (`rol === "admin"`) mientras el
 * backend del flujo de publicación no lo añada. Sin sesión => `false`.
 */
export function useEsAdmin(): boolean {
  const { usuario } = useSesion();
  if (!usuario) return false;
  return usuario.es_admin ?? usuario.rol === "admin";
}

/** Solicitudes de publicación por estado (def. `abierta`: la bandeja de pendientes). */
export function useSolicitudes(estado = "abierta") {
  return useQuery({
    queryKey: claveSolicitudes(estado),
    queryFn: ({ signal }) => api.solicitudesPrompts(estado, signal),
  });
}

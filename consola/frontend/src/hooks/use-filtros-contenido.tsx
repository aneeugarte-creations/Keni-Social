import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import type { RedPieza } from "@/types";

import {
  claveRedActiva,
  FILTRO_TODOS,
  FiltrosPublicacionContexto,
  type ValorFiltrosPublicacion,
} from "./filtros-contenido-contexto";

/** Lee un filtro persistido de este usuario (o `FILTRO_TODOS` si no hay / falla). */
function leerPersistido(clave: string): string {
  try {
    return localStorage.getItem(clave) ?? FILTRO_TODOS;
  } catch {
    return FILTRO_TODOS;
  }
}

/** Persiste un filtro de este usuario de forma tolerante (modo privado: solo en memoria). */
function guardarPersistido(clave: string, valor: string): void {
  try {
    localStorage.setItem(clave, valor);
  } catch {
    // localStorage no disponible (modo privado): el filtro vive solo en memoria.
  }
}

/**
 * Provider del FILTRO GLOBAL de RED, hermano del de marca. Deriva el catálogo de redes del
 * canónico (`/api/piezas/opciones`, que ya consumen las páginas, así que no añade carga) y
 * persiste la elección por usuario. Por defecto "Todas" → no cambia el comportamiento inicial.
 *
 * La LÍNEA del plan NO se gestiona aquí: se filtra por página (chips del Feed / dropdown de
 * Categoría de la Lista) sobre el eje `categoria` con el catálogo de `opciones.categorias`.
 */
export function FiltrosPublicacionProvider({ children }: { children: React.ReactNode }) {
  const { usuario } = useSesion();
  const usuarioId = usuario?.id ?? "";

  // Catálogo de redes. Se cachea (mismo queryKey que las páginas), así se resuelve una sola vez.
  // Mientras carga, el selector queda con solo "Todas".
  const opcionesQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    staleTime: Infinity,
  });
  const redes = React.useMemo<RedPieza[]>(
    () => opcionesQuery.data?.redes ?? [],
    [opcionesQuery.data],
  );

  // Estado inicial: preferencia persistida por usuario (o "Todas").
  const [red, setRed] = React.useState<string>(() =>
    usuarioId ? leerPersistido(claveRedActiva(usuarioId)) : FILTRO_TODOS,
  );

  // Re-inicializa al cambiar de usuario (login distinto): cada quien arranca en SU filtro
  // persistido, no heredando el del usuario anterior.
  const refUsuario = React.useRef(usuarioId);
  React.useEffect(() => {
    if (refUsuario.current !== usuarioId) {
      refUsuario.current = usuarioId;
      setRed(usuarioId ? leerPersistido(claveRedActiva(usuarioId)) : FILTRO_TODOS);
    }
  }, [usuarioId]);

  const cambiarRed = React.useCallback(
    (id: string) => {
      setRed(id);
      if (usuarioId) guardarPersistido(claveRedActiva(usuarioId), id);
    },
    [usuarioId],
  );

  const valor = React.useMemo<ValorFiltrosPublicacion>(
    () => ({ red, redes, cambiarRed }),
    [red, redes, cambiarRed],
  );

  return (
    <FiltrosPublicacionContexto.Provider value={valor}>{children}</FiltrosPublicacionContexto.Provider>
  );
}

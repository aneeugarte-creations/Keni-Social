import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import type { LineaEditorialOpcion, RedPublicacion } from "@/types";

import {
  claveLineaActiva,
  claveRedActiva,
  FILTRO_TODOS,
  FiltrosContenidoContexto,
  type ValorFiltrosContenido,
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
 * Provider de los FILTROS GLOBALES de contenido (Red + Línea), hermano del de marca.
 * Deriva las opciones del catálogo canónico (`/api/publicaciones/opciones`, que ya
 * consumen las páginas de contenido, así que no añade carga) y persiste la elección
 * por usuario. Por defecto ambos en "Todas" → no cambia el comportamiento inicial.
 *
 * Se monta DEBAJO del provider de marca: las líneas elegibles dependen de la marca
 * activa, y si la línea persistida deja de serlo, cae a "Todas".
 */
export function FiltrosContenidoProvider({ children }: { children: React.ReactNode }) {
  const { usuario } = useSesion();
  const usuarioId = usuario?.id ?? "";
  const { marcaActiva } = useMarcaActiva();

  // Catálogo de redes + líneas. Se cachea (mismo queryKey que las páginas), así se
  // resuelve una sola vez. Mientras carga, los selectores quedan con solo "Todas".
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    staleTime: Infinity,
  });
  const redes = React.useMemo<RedPublicacion[]>(
    () => opcionesQuery.data?.redes ?? [],
    [opcionesQuery.data],
  );
  const lineas = React.useMemo<LineaEditorialOpcion[]>(
    () => opcionesQuery.data?.lineas ?? [],
    [opcionesQuery.data],
  );

  // Estado inicial: preferencia persistida por usuario (o "Todas").
  const [red, setRed] = React.useState<string>(() =>
    usuarioId ? leerPersistido(claveRedActiva(usuarioId)) : FILTRO_TODOS,
  );
  const [linea, setLinea] = React.useState<string>(() =>
    usuarioId ? leerPersistido(claveLineaActiva(usuarioId)) : FILTRO_TODOS,
  );

  // Re-inicializa al cambiar de usuario (login distinto): cada quien arranca en SUS
  // filtros persistidos, no heredando los del usuario anterior.
  const refUsuario = React.useRef(usuarioId);
  React.useEffect(() => {
    if (refUsuario.current !== usuarioId) {
      refUsuario.current = usuarioId;
      setRed(usuarioId ? leerPersistido(claveRedActiva(usuarioId)) : FILTRO_TODOS);
      setLinea(usuarioId ? leerPersistido(claveLineaActiva(usuarioId)) : FILTRO_TODOS);
    }
  }, [usuarioId]);

  // Líneas elegibles: las de la marca activa + las globales (marca === ""). Con marca
  // activa null ("Todas") se muestran todas.
  const lineasElegibles = React.useMemo<LineaEditorialOpcion[]>(
    () => lineas.filter((l) => l.marca === "" || marcaActiva == null || l.marca === marcaActiva),
    [lineas, marcaActiva],
  );

  // Si la línea activa deja de pertenecer a la marca activa, se resetea a "Todas".
  React.useEffect(() => {
    if (linea !== FILTRO_TODOS && !lineasElegibles.some((l) => l.id === linea)) {
      setLinea(FILTRO_TODOS);
      if (usuarioId) guardarPersistido(claveLineaActiva(usuarioId), FILTRO_TODOS);
    }
  }, [lineasElegibles, linea, usuarioId]);

  const cambiarRed = React.useCallback(
    (id: string) => {
      setRed(id);
      if (usuarioId) guardarPersistido(claveRedActiva(usuarioId), id);
    },
    [usuarioId],
  );

  const cambiarLinea = React.useCallback(
    (id: string) => {
      setLinea(id);
      if (usuarioId) guardarPersistido(claveLineaActiva(usuarioId), id);
    },
    [usuarioId],
  );

  const valor = React.useMemo<ValorFiltrosContenido>(
    () => ({ red, linea, redes, lineasElegibles, cambiarRed, cambiarLinea }),
    [red, linea, redes, lineasElegibles, cambiarRed, cambiarLinea],
  );

  return (
    <FiltrosContenidoContexto.Provider value={valor}>{children}</FiltrosContenidoContexto.Provider>
  );
}

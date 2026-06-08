/**
 * ContenidosHub — pieza «Contenidos» del hub Investigación (Fase 1).
 *
 * Banco de piezas EVERGREEN (educativas/curiosas/atemporales): reportajes
 * internos y producciones propias que no caducan. Compone el banco EVERGREEN
 * existente (`TallerEvergreen`) sin reescribir su lógica; aquí solo le inyecta el
 * catálogo de marcas/redes (igual que hace hoy la página de Fuentes) y la
 * cabecera del hub.
 *
 * Fases posteriores fusionarán aquí el resto de superficies de contenido
 * evergreen; por ahora es un envoltorio fino para no perder función.
 */
import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { api } from "@/lib/api";
import type { RedPublicacion } from "@/types";

import { ORDEN_REDES } from "./publicaciones/meta";
import { TallerEvergreen } from "./fuentes/TallerEvergreen";

export default function ContenidosHub() {
  // Las marcas y redes viven en el catálogo de opciones de publicaciones (mismo
  // origen que usa la página de Fuentes para alimentar el banco EVERGREEN).
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  const opcionesRedes = React.useMemo<RedPublicacion[]>(
    () =>
      opcionesQuery.data?.redes ??
      ORDEN_REDES.map((id) => ({ id, nombre: id, limite: null })),
    [opcionesQuery.data],
  );

  return (
    <>
      <TallerEvergreen marcas={marcas} redes={opcionesRedes} />
    </>
  );
}

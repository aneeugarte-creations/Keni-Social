import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useSearchParams } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import type { RedPublicacion } from "@/types";

import { ORDEN_REDES } from "./publicaciones/meta";
import { CatalogoPresets } from "./fuentes/CatalogoPresets";
import { GestionFuentes } from "./fuentes/GestionFuentes";
// Salud del motor de ingesta de feeds: estado de los canales externos (feeds activos/
// con error, huecos, reactivar). Vive bajo "Externas".
import { SaludFeeds } from "./fuentes/SaludFeeds";
// Buzones del equipo (listas tipo portal/WhatsApp/corresponsales y Excel): la fuente
// INTERNA. Compone la página de Cajones del día.
import CajonesDia from "./CajonesDia";

/** Una clase de fuente (pestaña): Externas o Internas. */
type PestanaTipo = {
  valor: string;
  etiqueta: string;
};

// Solo hay DOS clases de fuente, y la barra lo refleja:
//   • Externas — lo que llega de fuera: feeds RSS (+ catálogo) y el estado del motor.
//   • Internas — lo que pone el equipo: buzones del día (Cajones). (Las aportaciones manuales
//     "Idea" e "Interno AMX" se mudaron a Contenidos, al banco de ideas evergreen.)
const PESTANAS_TIPO: PestanaTipo[] = [
  { valor: "externas", etiqueta: "Externas" },
  { valor: "internas", etiqueta: "Internas" },
];

/**
 * Página de Fuentes: ajustes de los canales de los que se alimentan Noticias y Contenidos.
 * Dos clases, dos pestañas:
 *   • Externas — feeds RSS (alta/edición con salud inline), catálogo y estado del motor.
 *   • Internas — buzones del equipo (Cajones) y aportes a mano (idea/interno).
 */
export default function Fuentes() {
  // Las marcas y redes viven en el catálogo de opciones de publicaciones.
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

  // Deep-link de pestaña: las rutas viejas del hub (cajones/agentes/eventos)
  // redirigen aquí con `?tab=` para abrir directamente su canal.
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get("tab");
  const tabInicial = PESTANAS_TIPO.some((p) => p.valor === tabParam)
    ? (tabParam as string)
    : "externas";

  return (
    <>
      <Tabs defaultValue={tabInicial} className="space-y-4">
        <TabsList>
          {PESTANAS_TIPO.map((p) => (
            <TabsTrigger key={p.valor} value={p.valor}>
              {p.etiqueta}
            </TabsTrigger>
          ))}
        </TabsList>
        {/* EXTERNAS: lo que llega de fuera. Feeds RSS (alta/edición con su salud
            inline) + catálogo para añadir de un clic + estado del motor de ingesta.
            (Agencias y Google Trends son señales externas; ver nota en el header.) */}
        <TabsContent value="externas" className="space-y-8">
          <GestionFuentes marcas={marcas} redes={opcionesRedes} />
          <CatalogoPresets marcas={marcas} />
          <SaludFeeds />
        </TabsContent>
        {/* INTERNAS: lo que pone el equipo. Buzones del día (listas tipo portal/WhatsApp/
            corresponsales y Excel), filtrados por la marca activa. Las aportaciones a mano
            ("Idea" e "Interno AMX") se mudaron a Contenidos, fusionadas con el generador de ideas. */}
        <TabsContent value="internas" className="space-y-8">
          <CajonesDia />
        </TabsContent>
      </Tabs>
    </>
  );
}

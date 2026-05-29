import { Globe, ListOrdered, Radar, Rss } from "lucide-react";
import { Outlet } from "react-router-dom";

import { TabsHub, type ItemTabHub } from "@/components/layout/TabsHub";

const TABS: ItemTabHub[] = [
  { ruta: "/investigacion/fuentes", etiqueta: "Fuentes", icono: Rss },
  { ruta: "/investigacion/termometro", etiqueta: "Termómetro", icono: Globe },
  { ruta: "/investigacion/radar", etiqueta: "Radar", icono: Radar },
  { ruta: "/investigacion/parrilla-dia", etiqueta: "Parrilla del día", icono: ListOrdered },
];

/**
 * Hub de Investigación: agrupa las tres fuentes de input para la generación
 * (RSS, panorama mundial y tendencias virales). Cada tab es una sub-ruta para
 * que se pueda compartir/refrescar y caer en el mismo sitio.
 */
export default function Investigacion() {
  return (
    <>
      <TabsHub items={TABS} etiquetaAria="Pestañas de Investigación" />
      <Outlet />
    </>
  );
}

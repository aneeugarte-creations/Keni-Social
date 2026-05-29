import { Outlet } from "react-router-dom";

import { TabsHub } from "@/components/layout/TabsHub";
import { TABS_INVESTIGACION } from "@/components/layout/hub-tabs";

/**
 * Hub de Investigación: agrupa las tres fuentes de input para la generación
 * (RSS, panorama mundial y tendencias virales). Cada tab es una sub-ruta para
 * que se pueda compartir/refrescar y caer en el mismo sitio. Las pestañas salen
 * del registro compartido `hub-tabs` (mismas que expande el sidebar).
 */
export default function Investigacion() {
  return (
    <>
      <TabsHub items={TABS_INVESTIGACION} etiquetaAria="Pestañas de Investigación" />
      <Outlet />
    </>
  );
}

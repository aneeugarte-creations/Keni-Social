import { Outlet } from "react-router-dom";

import { TabsHub } from "@/components/layout/TabsHub";
import { TABS_ANALITICAS } from "@/components/layout/hub-tabs";

/**
 * Hub de Analíticas: reúne los tres puntos de medición y reporte (rendimiento
 * orgánico, seguimiento de comercial con KPI y deck semanal de Claro Sports).
 * Las pestañas salen del registro compartido `hub-tabs` (mismas que expande el
 * sidebar).
 */
export default function Analiticas() {
  return (
    <>
      <TabsHub items={TABS_ANALITICAS} etiquetaAria="Pestañas de Analíticas" />
      <Outlet />
    </>
  );
}

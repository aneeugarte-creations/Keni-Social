import { Outlet } from "react-router-dom";

import { TabsHub } from "@/components/layout/TabsHub";
import { TABS_AGENTES } from "@/components/layout/hub-tabs";

/**
 * Hub de Agentes: layout que reúne el catálogo de agentes y el monitor de runs
 * (Actividad IA). El detalle individual `/agentes/:id` queda fuera de este
 * layout para ocupar toda la pantalla sin la subnav. Las pestañas salen del
 * registro compartido `hub-tabs` (mismas que expande el sidebar).
 */
export default function AgentesHub() {
  return (
    <>
      <TabsHub items={TABS_AGENTES} etiquetaAria="Pestañas de Agentes" />
      <Outlet />
    </>
  );
}

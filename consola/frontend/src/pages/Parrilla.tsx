import { Outlet } from "react-router-dom";

import { TabsHub } from "@/components/layout/TabsHub";
import { TABS_PARRILLA } from "@/components/layout/hub-tabs";

/**
 * Hub de Parrilla: une la vista de pendientes/tablero (antes /tareas) con el
 * planificador semanal/rota (antes /rota). Mismo dominio (eventos del equipo),
 * dos vistas complementarias. Las pestañas salen del registro compartido
 * `hub-tabs` (mismas que expande el sidebar).
 */
export default function Parrilla() {
  return (
    <>
      <TabsHub items={TABS_PARRILLA} etiquetaAria="Pestañas de Parrilla" />
      <Outlet />
    </>
  );
}

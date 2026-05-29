import { Outlet } from "react-router-dom";

import { TabsHub } from "@/components/layout/TabsHub";
import { TABS_REVISION } from "@/components/layout/hub-tabs";

/**
 * Hub de Revisión: agrupa los dos validadores previos a publicar (QA del copy
 * y verificación de autenticidad de imágenes/videos). Las pestañas salen del
 * registro compartido `hub-tabs` (mismas que expande el sidebar).
 */
export default function Revision() {
  return (
    <>
      <TabsHub items={TABS_REVISION} etiquetaAria="Pestañas de Revisión" />
      <Outlet />
    </>
  );
}

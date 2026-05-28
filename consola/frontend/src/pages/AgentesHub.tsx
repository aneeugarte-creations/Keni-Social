import { Activity, Bot } from "lucide-react";
import { Outlet } from "react-router-dom";

import { TabsHub, type ItemTabHub } from "@/components/layout/TabsHub";

const TABS: ItemTabHub[] = [
  // `end` para que el catálogo no quede activo cuando estás en /agentes/actividad.
  { ruta: "/agentes", etiqueta: "Agentes", icono: Bot, end: true },
  { ruta: "/agentes/actividad", etiqueta: "Actividad IA", icono: Activity },
];

/**
 * Hub de Agentes: layout que reúne el catálogo de agentes y el monitor de runs
 * (Actividad IA). El detalle individual `/agentes/:id` queda fuera de este
 * layout para ocupar toda la pantalla sin la subnav.
 */
export default function AgentesHub() {
  return (
    <>
      <TabsHub items={TABS} etiquetaAria="Pestañas de Agentes" />
      <Outlet />
    </>
  );
}

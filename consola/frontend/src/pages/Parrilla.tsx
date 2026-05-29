import { CalendarClock, ListTodo } from "lucide-react";
import { Outlet } from "react-router-dom";

import { TabsHub, type ItemTabHub } from "@/components/layout/TabsHub";

const TABS: ItemTabHub[] = [
  { ruta: "/parrilla/calendario", etiqueta: "Calendario", icono: CalendarClock },
  { ruta: "/parrilla/pendientes", etiqueta: "Pendientes", icono: ListTodo },
];

/**
 * Hub de Parrilla: une la vista de pendientes/tablero (antes /tareas) con el
 * planificador semanal/rota (antes /rota). Mismo dominio (eventos del equipo),
 * dos vistas complementarias.
 */
export default function Parrilla() {
  return (
    <>
      <TabsHub items={TABS} etiquetaAria="Pestañas de Parrilla" />
      <Outlet />
    </>
  );
}

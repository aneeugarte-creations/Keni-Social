import { Outlet } from "react-router-dom";

/**
 * Hub de Parrilla: une la vista de pendientes/tablero (antes /tareas) con el
 * planificador semanal/rota (antes /rota). Mismo dominio (eventos del equipo),
 * dos vistas complementarias. La navegación entre sub-pestañas vive ahora en el
 * sidebar (acordeón); el hub solo renderiza el contenido de la sub-ruta activa.
 */
export default function Parrilla() {
  return <Outlet />;
}

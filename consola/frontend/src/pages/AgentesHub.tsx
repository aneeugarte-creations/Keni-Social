import { Outlet } from "react-router-dom";

/**
 * Hub de Agentes: layout que reúne el catálogo de agentes y el monitor de runs
 * (Actividad IA). El detalle individual `/agentes/:id` queda fuera de este
 * layout para ocupar toda la pantalla sin la subnav. La navegación entre
 * sub-pestañas vive ahora en el sidebar (acordeón); el hub solo renderiza el
 * contenido de la sub-ruta activa.
 */
export default function AgentesHub() {
  return <Outlet />;
}

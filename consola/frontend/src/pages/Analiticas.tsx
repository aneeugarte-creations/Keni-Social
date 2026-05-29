import { Outlet } from "react-router-dom";

/**
 * Hub de Analíticas: reúne los tres puntos de medición y reporte (rendimiento
 * orgánico, seguimiento de comercial con KPI y deck semanal de Claro Sports).
 * La navegación entre sub-pestañas vive ahora en el sidebar (acordeón); el hub
 * solo renderiza el contenido de la sub-ruta activa.
 */
export default function Analiticas() {
  return <Outlet />;
}

import { Outlet } from "react-router-dom";

/**
 * Hub de Investigación: agrupa las fuentes de input para la generación
 * (RSS, panorama mundial, tendencias virales y la parrilla del día). Cada
 * sub-pestaña es una sub-ruta para que se pueda compartir/refrescar y caer en el
 * mismo sitio. La navegación entre ellas vive ahora en el sidebar (acordeón),
 * por eso el hub solo renderiza el contenido de la sub-ruta activa.
 */
export default function Investigacion() {
  return <Outlet />;
}

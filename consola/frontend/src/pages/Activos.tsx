import { Outlet } from "react-router-dom";

/**
 * Hub de Activos: agrupa los ACTIVOS reutilizables de producción que aceleran
 * armar piezas — plantillas de contenido por tipo de nota recurrente y la
 * biblioteca de medios interna (imágenes/clips aprobados, etiquetables). Ninguno
 * publica a redes (eso lo hace Metricool); son insumos para componer copy/piezas.
 *
 * La navegación entre sub-pestañas vive en el sidebar (acordeón), igual que el
 * resto de hubs; aquí solo se renderiza el contenido de la sub-ruta activa.
 */
export default function Activos() {
  return <Outlet />;
}

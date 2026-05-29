import { Outlet } from "react-router-dom";

/**
 * Hub de Revisión: agrupa los dos validadores previos a publicar (QA del copy
 * y verificación de autenticidad de imágenes/videos). La navegación entre
 * sub-pestañas vive ahora en el sidebar (acordeón); el hub solo renderiza el
 * contenido de la sub-ruta activa.
 */
export default function Revision() {
  return <Outlet />;
}

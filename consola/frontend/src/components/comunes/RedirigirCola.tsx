import { Navigate, useLocation } from "react-router-dom";

/**
 * Redirección a `/maquina/computo` (la cola por dentro), antigua casa «Workers»/Cola.
 * Preserva la query (`?proceso=investigacion|produccion`) para no romper los deep-links
 * prefiltrados de los cockpits ni los enlaces. Vive en su propio fichero (no en `router.tsx`)
 * para no romper el fast-refresh del módulo de rutas.
 */
export function RedirigirCola() {
  const { search } = useLocation();
  return <Navigate to={`/maquina/computo${search}`} replace />;
}

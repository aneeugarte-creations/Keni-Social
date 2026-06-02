import { Navigate, useParams } from "react-router-dom";

/**
 * Redirección legacy que PRESERVA el resto del path. Para una ruta `<vieja>/*`,
 * reapunta a `<a>/<resto>` (p. ej. `/investigacion/radar` → `/datos/investigacion/radar`).
 * Así una sola regla por hub cubre el hub y todas sus pestañas. Vive en su propio
 * fichero (no en `router.tsx`) para no romper el fast-refresh del módulo de rutas.
 */
export function RedirigirPrefijo({ a }: { a: string }) {
  const resto = useParams()["*"] ?? "";
  return <Navigate to={resto ? `${a}/${resto}` : a} replace />;
}

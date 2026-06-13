import { Navigate, useLocation } from "react-router-dom";

/**
 * Redirección legacy del antiguo Monitor (`/datos/produccion/monitor`, antes el hub
 * Producción·Monitor) a la nueva sección «Máquina» (fase 2A). El Monitor se RELOCALIZÓ:
 *   - la vista global del worker/cola es ahora `/maquina/cola` (Cola compartida),
 *   - la tira de etapas + el drawer de ajustes viven en el cockpit de Producción
 *     (`/maquina/produccion`), así que `?tab=ajustes` abre el drawer ALLÍ,
 *   - la antigua pestaña «Salud» (la infra) ya redirigía a `/sistema` (`?tab=salud`).
 *
 * Preserva los query params relevantes (`?proceso=` para prefiltrar la Cola). Vive en su
 * propio fichero (no en `router.tsx`) para no romper el fast-refresh del módulo de rutas.
 */
export function RedirigirMonitor() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  const tab = params.get("tab");

  // La infra (antigua pestaña «Salud») es página propia: /sistema.
  if (tab === "salud") return <Navigate to="/sistema" replace />;

  // Los ajustes de la máquina viven en el drawer del cockpit de Producción.
  if (tab === "ajustes") return <Navigate to="/maquina/produccion?tab=ajustes" replace />;

  // El resto (incl. `?proceso=investigacion|produccion`) cae en la Cola compartida,
  // preservando el prefiltro de proceso.
  params.delete("tab");
  const cola = params.toString();
  return <Navigate to={`/maquina/cola${cola ? `?${cola}` : ""}`} replace />;
}

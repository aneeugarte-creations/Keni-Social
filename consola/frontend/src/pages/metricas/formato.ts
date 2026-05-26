/**
 * Utilidades de formato es-MX para el dashboard de Métricas.
 *
 * Re-exporta desde `@/lib/formato` — módulo canónico compartido por toda la
 * consola — para mantener compatibilidad con importes existentes dentro de
 * `pages/metricas/` sin duplicar lógica.
 *
 * @deprecated Importa directamente desde `@/lib/formato` en código nuevo.
 */
export {
  costeUsd,
  duracion,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  variacion,
} from "@/lib/formato";

/**
 * Badge que indica la procedencia de los datos de Métricas: datos de MUESTRA
 * (ficticios, pendientes de credenciales reales) frente a datos REALES (de la API de cada red).
 *
 * Lee el campo `fuente` de la respuesta de métricas de forma DEFENSIVA: es
 * opcional (el backend lo añade en paralelo). Si llega `undefined`/`""` no se
 * renderiza nada, para no afirmar "real" cuando aún no lo sabemos.
 *
 * El único valor con significado especial es `"muestra"` (lo expone la fuente
 * de muestra como `nombre = "muestra"`); cualquier otro nombre se considera una
 * fuente real. La lógica vive en `./fuente` para no romper el fast-refresh.
 */
import { Badge } from "@/components/ui/badge";

import { esFuenteMuestra } from "./fuente";

export function BadgeFuente({
  fuente,
  className,
}: {
  /** Nombre de la fuente activa (`"muestra"`, `"meta"`, …). Opcional. */
  fuente: string | null | undefined;
  className?: string;
}) {
  // Defensivo: sin fuente no afirmamos nada (puede que el backend aún no la
  // exponga). No renderizamos badge para no dar una falsa sensación de "real".
  if (!fuente) return null;

  const muestra = esFuenteMuestra(fuente);
  return (
    <Badge
      variant={muestra ? "aviso" : "ok"}
      className={className}
      title={
        muestra
          ? "Datos de muestra: cifras ficticias para demostración, no reales."
          : "Datos reales tomados de la API de cada red."
      }
    >
      {muestra ? "Datos de muestra" : "Datos reales"}
    </Badge>
  );
}

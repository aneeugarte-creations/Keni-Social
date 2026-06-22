/**
 * Selector de RED único del dashboard de Métricas (cabecera, junto al de periodo).
 *
 * Single-select "Todas las redes" + cada red canónica. Escribe en `useVistaConfig.setRed`
 * (`null` = todas), que filtra TODA la página: cada sub-sección incluye la red en foco en
 * su consulta. Cada opción lleva un punto del color de su red (`coloresRed`) para anclar la
 * lectura cromática del resto de visualizaciones.
 */
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { nombreRed } from "@/lib/formato";

import { colorDe } from "./coloresRed";
import { useVistaConfig } from "./vistaConfig";

const RED_TODAS = "__todas__";

/** Redes en el orden de lectura del piloto (las más activas primero). */
const ORDEN_REDES = ["instagram", "youtube", "facebook", "tiktok", "x"];

/** Punto de color de una red (ancla cromática compartida con las gráficas). */
function PuntoRed({ red }: { red: string }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: colorDe(red) }}
    />
  );
}

/** Etiqueta legible de la red en foco (o "Todas las redes") para portadas y nombres. */
export function etiquetaRed(red: string | null): string {
  return red ? nombreRed(red) : "Todas las redes";
}

export function SelectorRed() {
  const red = useVistaConfig((s) => s.red);
  const setRed = useVistaConfig((s) => s.setRed);

  return (
    <Select
      value={red ?? RED_TODAS}
      onValueChange={(v) => setRed(v === RED_TODAS ? null : v)}
    >
      <SelectTrigger className="h-8 w-full text-xs sm:w-[170px]" aria-label="Red">
        <SelectValue placeholder="Red" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={RED_TODAS}>Todas las redes</SelectItem>
        {ORDEN_REDES.map((r) => (
          <SelectItem key={r} value={r}>
            <span className="inline-flex items-center gap-2">
              <PuntoRed red={r} />
              {nombreRed(r)}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

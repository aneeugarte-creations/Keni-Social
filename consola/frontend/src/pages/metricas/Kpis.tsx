/**
 * Fila de KPIs: nº de piezas publicadas + las métricas del total del reporte. Estilo
 * Vercel/Geist: etiqueta gris pequena + numero contenido, sin iconos ni acentos de color.
 */
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import type { TotalMetricas } from "@/types";

import { numeroCompleto } from "./formato";
import { METRICAS, valorMetrica } from "./metricas-meta";

export function Kpis({ total }: { total: TotalMetricas }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <TarjetaKpi
        variante="card"
        etiqueta="Piezas publicadas"
        valor={numeroCompleto(total.publicaciones)}
      />
      {METRICAS.map((m) => (
        <TarjetaKpi
          key={m.clave}
          variante="card"
          etiqueta={m.etiqueta}
          valor={m.compacto(valorMetrica(total, m.clave))}
          titulo={
            m.descripcion
              ? `${m.completo(valorMetrica(total, m.clave))} — ${m.descripcion}`
              : m.completo(valorMetrica(total, m.clave))
          }
        />
      ))}
    </div>
  );
}

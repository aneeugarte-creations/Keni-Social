/**
 * Fila de KPIs: nº de piezas publicadas + las métricas del total del reporte. Estilo
 * Vercel/Geist: etiqueta gris pequena + numero contenido, sin iconos ni acentos de color.
 *
 * Cada KPI lleva (cuando hay con qué) una insignia comparativa "vs periodo anterior":
 * se consulta `/metricas/comparar` con A = periodo inmediatamente anterior adyacente
 * (misma longitud, vía `periodoAnterior`) y B = el periodo visible. La MISMA forma de
 * queryKey que CompararPeriodos → caché compartida cuando ambos miran el mismo par.
 * La comparativa es ACCESORIA: mientras carga, si falla, si el periodo no tiene
 * anterior resoluble o si la métrica no viene en la respuesta, el KPI se pinta igual
 * que siempre, sin insignia y sin skeleton extra (nunca se bloquea por el delta).
 */
import { useQuery } from "@tanstack/react-query";
import * as React from "react";

import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { marcaParam } from "@/components/comunes/selectores";
import { api } from "@/lib/api";
import type { TotalMetricas } from "@/types";

import { MARCA_TODAS } from "./Controles";
import { InsigniaComparativa } from "./InsigniaComparativa";
import { numeroCompleto } from "./formato";
import { METRICAS, valorMetrica } from "./metricas-meta";
import { periodoAnterior } from "./rango";

export function Kpis({
  total,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  total: TotalMetricas;
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const rangoA = rangoActual ? periodoAnterior(rangoActual) : null;

  const { data } = useQuery({
    // MISMA forma que CompararPeriodos (["metricas","comparar",A,B,marca]): si la
    // sección de comparar mira el mismo par por defecto, comparten entrada de caché.
    queryKey: ["metricas", "comparar", rangoA, rangoActual, marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasComparar(
        { rango_a: rangoA!, rango_b: rangoActual, marca: marca_ },
        signal,
      ),
    enabled: Boolean(rangoActual && rangoA),
    staleTime: 5 * 60_000,
  });

  /** Insignia comparativa de una métrica, o nada si (aún) no hay comparativa. */
  function insigniaDe(metrica: string): React.ReactNode {
    const comp = data?.total.metricas.find((c) => c.metrica === metrica);
    if (!comp) return undefined;
    return (
      <InsigniaComparativa
        comp={comp}
        title={`vs periodo anterior (${data!.etiqueta_a})`}
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Sin delta a propósito: /metricas/comparar no emite `publicaciones`
          (no está en _METRICAS_CONTEO_COMPARABLES del backend, ver
          consola/src/keni_consola/api/metricas/reporte.py). */}
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
          insignia={insigniaDe(m.metrica)}
        />
      ))}
    </div>
  );
}

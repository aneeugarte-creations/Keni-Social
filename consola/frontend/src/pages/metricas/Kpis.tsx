/**
 * Fila de KPIs: nº de piezas publicadas + las métricas del total del reporte. Estilo
 * Vercel/Geist: etiqueta gris pequena + numero contenido, sin iconos ni acentos de color.
 *
 * Cada KPI lleva (cuando hay con qué) una insignia comparativa "vs periodo anterior":
 * se consulta `/metricas/comparar` con el par COMPARABLE que deriva `parComparable`
 * (rango.ts): A y B tienen SIEMPRE la misma duración. Para un mes EN CURSO se comparan
 * los días transcurridos contra los mismos días del mes anterior (1–10 jun vs 1–10
 * may) —comparar 10 días contra los 31 de mayo daba desplomes espurios— y la leyenda
 * bajo los KPIs explicita ese contexto. La MISMA forma de queryKey que
 * CompararPeriodos → caché compartida cuando ambos miran el mismo par.
 * La comparativa es ACCESORIA: mientras carga, si falla, si el periodo no tiene
 * par comparable (p. ej. un mes futuro, sin datos) o si la métrica no viene en la
 * respuesta, el KPI se pinta igual que siempre, sin insignia y sin skeleton extra
 * (nunca se bloquea por el delta y NUNCA se muestra un porcentaje espurio).
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
import { parComparable } from "./rango";

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
  // Par A/B de la MISMA duración (guarda de comparabilidad): para un mes en curso,
  // B son los días transcurridos y A los mismos días del mes anterior. null = no
  // hay comparación honesta posible (token irresoluble o periodo futuro).
  const par = rangoActual ? parComparable(rangoActual) : null;

  const { data } = useQuery({
    // MISMA forma que CompararPeriodos (["metricas","comparar",A,B,marca]): si la
    // sección de comparar mira el mismo par, comparten entrada de caché.
    queryKey: ["metricas", "comparar", par?.rangoA, par?.rangoB, marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasComparar(
        { rango_a: par!.rangoA, rango_b: par!.rangoB, marca: marca_ },
        signal,
      ),
    enabled: Boolean(par),
    staleTime: 5 * 60_000,
  });

  /** Insignia comparativa de una métrica, o nada si (aún) no hay comparativa. */
  function insigniaDe(metrica: string): React.ReactNode {
    const comp = data?.total.metricas.find((c) => c.metrica === metrica);
    if (!comp) return undefined;
    // El tooltip explicita CONTRA QUÉ se compara; para un periodo en curso, que la
    // comparación es de los días transcurridos (no del mes completo).
    const title = par?.enCurso
      ? `Periodo en curso: ${data!.etiqueta_b} vs ${data!.etiqueta_a}`
      : `vs periodo anterior (${data!.etiqueta_a})`;
    return <InsigniaComparativa comp={comp} title={title} />;
  }

  return (
    <div className="space-y-2">
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
      {/* Leyenda de comparabilidad: con el periodo en curso, las insignias comparan
          tramos de la MISMA duración (días transcurridos vs el tramo equivalente del
          periodo anterior), y aquí se dice de forma visible, no solo en el tooltip. */}
      {par?.enCurso && data && (
        <p className="text-xs text-muted-foreground" role="note">
          Periodo en curso: {data.etiqueta_b} vs {data.etiqueta_a}.
        </p>
      )}
    </div>
  );
}

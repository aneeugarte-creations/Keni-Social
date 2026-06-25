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
import type { ColumnaMeta } from "./columnasMeta";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";
import { InsigniaComparativa } from "./InsigniaComparativa";
import { numeroCompacto, numeroCompleto } from "./formato";
import { METRICAS, valorMetrica } from "./metricas-meta";
import { parComparable } from "./rango";
import { Seccion } from "./Seccion";

/** Catálogo de tarjetas configurables: "Piezas" + una por métrica del reporte. El id de
 * cada tarjeta de métrica es su `clave`; el de la tarjeta de conteo es "piezas". */
const COLUMNAS: ColumnaMeta[] = [
  { id: "piezas", etiqueta: "Piezas" },
  ...METRICAS.map((m) => ({ id: m.clave, etiqueta: m.etiqueta })),
];

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
  const red = useVistaConfig((s) => s.red);
  // Orden y visibilidad de las tarjetas (panel "Tarjetas"): se pintan SOLO las visibles,
  // en su orden; el grid reflowea solo al ocultar/reordenar.
  const cfg = useVistaConfig((s) => s.columnas["kpis"]) ?? {
    orden: COLUMNAS.map((c) => c.id),
    ocultas: [],
  };
  const visibles = columnasVisibles(
    COLUMNAS.map((c) => c.id),
    cfg,
  );
  // Par A/B de la MISMA duración (guarda de comparabilidad): para un mes en curso,
  // B son los días transcurridos y A los mismos días del mes anterior. null = no
  // hay comparación honesta posible (token irresoluble o periodo futuro).
  const par = rangoActual ? parComparable(rangoActual) : null;

  const { data } = useQuery({
    // MISMA forma que CompararPeriodos (["metricas","comparar",A,B,marca]): si la
    // sección de comparar mira el mismo par, comparten entrada de caché.
    queryKey: ["metricas", "comparar", par?.rangoA, par?.rangoB, marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasComparar(
        { rango_a: par!.rangoA, rango_b: par!.rangoB, marca: marca_, red: red ?? undefined },
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

  /** Tarjeta de una id visible: la de conteo ("piezas") o la de su métrica. */
  function tarjeta(id: string): React.ReactNode {
    if (id === "piezas") {
      // Sin delta a propósito: /metricas/comparar no emite `piezas`
      // (no está en _METRICAS_CONTEO_COMPARABLES del backend, ver
      // consola/src/keni_consola/api/metricas/reporte.py).
      return (
        <TarjetaKpi
          key="piezas"
          variante="card"
          etiqueta="Piezas publicadas"
          valor={numeroCompleto(total.piezas)}
        />
      );
    }
    // La cifra de cabecera de VOLUMEN son las impresiones (aditivas: veces que el contenido se
    // mostró). Cuando el reporte las trae, la tarjeta de "alcance" pasa a ser la de impresiones;
    // el alcance ÚNICO no es una cifra agregable de periodo y se lee como tendencia en su sección.
    // Sin impresiones en el reporte, la tarjeta se mantiene como alcance (degradación honesta).
    if (id === "alcance" && total.impresiones != null) {
      return (
        <TarjetaKpi
          key="impresiones"
          variante="card"
          etiqueta="Impresiones"
          valor={numeroCompacto(total.impresiones)}
          titulo={`${numeroCompleto(
            total.impresiones,
          )} — volumen total del periodo (veces que el contenido se mostró). El alcance único se lee como tendencia.`}
        />
      );
    }
    const m = METRICAS.find((x) => x.clave === id);
    if (!m) return null;
    // alcance puede ser null (el total no mide alcance de cuenta): se pinta "—", igual que
    // la tabla por red, en vez de un 0 falso.
    const valor = valorMetrica(total, m.clave);
    const compacto = valor === null ? "—" : m.compacto(valor);
    const completo = valor === null ? "—" : m.completo(valor);
    return (
      <TarjetaKpi
        key={m.clave}
        variante="card"
        etiqueta={m.etiqueta}
        valor={compacto}
        titulo={m.descripcion ? `${completo} — ${m.descripcion}` : completo}
        insignia={insigniaDe(m.metrica)}
      />
    );
  }

  return (
    <Seccion
      id="kpis"
      titulo="Resumen del periodo"
      tablaId="kpis"
      columnas={COLUMNAS}
      etiquetaCampos="Tarjetas"
    >
      <div className="space-y-2">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {visibles.map((id) => tarjeta(id))}
        </div>
        {/* Leyenda de comparabilidad: con el periodo en curso, las insignias comparan
            intervalos de la MISMA duración (días transcurridos vs el intervalo equivalente del
            periodo anterior), y aquí se dice de forma visible, no solo en el tooltip. */}
        {par?.enCurso && data && (
          <p className="text-xs text-muted-foreground" role="note">
            Periodo en curso: {data.etiqueta_b} vs {data.etiqueta_a}.
          </p>
        )}
      </div>
    </Seccion>
  );
}

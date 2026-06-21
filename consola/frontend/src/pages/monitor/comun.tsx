/**
 * Piezas COMPARTIDAS del Monitor para los dos loops (ADR 0011): Investigación y Producción
 * comparten cola y pool ÚNICOS; estos componentes leen el MISMO snapshot/serie
 * (`/api/actividad/cola*`) y lo presentan desglosado por proceso, sin inventar dos colas.
 */
import { Coins } from "lucide-react";
import * as React from "react";

import { CardTitle } from "@/components/ui/card";
import { costeUsd, numeroCompacto } from "@/lib/formato";
import { cn } from "@/lib/utils";
import type { ColaSerie, Proceso, ResultadoDia, ResultadoProceso } from "@/types";

/** Metadatos de presentación por proceso (color del segmento, etiqueta, tinte del texto). Es un
 *  mapa de color por MOTOR (investigación/producción), no un estado de trabajo: identifica el
 *  proceso en barras y gráficas, por eso NO va por `Badge`/`ChipEstado`. Reutilizado por Monitor,
 *  Cómputo y Economía. */
export const PROC_META: Record<Proceso, { etiqueta: string; barra: string; texto: string }> = {
  investigacion: { etiqueta: "Investigación", barra: "bg-sky-500/70", texto: "text-sky-600" },
  produccion: { etiqueta: "Producción", barra: "bg-emerald-500/70", texto: "text-emerald-600" },
};

const PROC_ORDEN: Proceso[] = ["investigacion", "produccion"];

const RES_PROC_VACIO: ResultadoProceso = { completados: 0, errores: 0, tokens: 0, coste_usd: 0 };

/** Resultados del día UTC `dia` (o ceros si ese día no tiene actividad real en la ventana). */
export function resultadoDelDia(serie: ColaSerie | undefined, dia: string): ResultadoDia | null {
  return serie?.resultados.find((r) => r.dia === dia) ?? null;
}

/** Total de tokens del día sumando ambos procesos (desde las generaciones reales, sin marcadores). */
export function tokensDelDia(res: ResultadoDia | null): number {
  if (!res?.por_proceso) return 0;
  return PROC_ORDEN.reduce((acc, p) => acc + (res.por_proceso?.[p]?.tokens ?? 0), 0);
}

/**
 * ECONOMÍA POR PROCESO del día: cuánto cuesta investigar vs producir. Sale de la serie (las
 * generaciones reales con sus métricas), que ya EXCLUYE los marcadores de etapa — así el desglose
 * cuadra con el gasto agregado del ledger y no con los marcadores a coste 0.
 */
export function DesgloseEconomiaProceso({
  res,
  soloProceso,
}: {
  res: ResultadoDia | null;
  /** Si se pasa, muestra SOLO ese proceso (monitor de Investigación); si no, los dos. */
  soloProceso?: Proceso;
}) {
  const procesos = soloProceso ? [soloProceso] : PROC_ORDEN;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {procesos.map((p) => {
        const rp = res?.por_proceso?.[p] ?? RES_PROC_VACIO;
        return (
          <span key={p} className="inline-flex items-center gap-1.5">
            <span className={cn("h-2 w-2 rounded-full", PROC_META[p].barra)} aria-hidden="true" />
            <span className={PROC_META[p].texto}>{PROC_META[p].etiqueta}</span>
            <span className="tabular-nums">
              {numeroCompacto(rp.tokens)} tok · {costeUsd(rp.coste_usd)} · {rp.completados} ok
              {rp.errores > 0 && <span className="text-destructive"> · {rp.errores} err</span>}
            </span>
          </span>
        );
      })}
    </div>
  );
}

/**
 * Mini-gráfico de barras por día: encolados (entrada) vs completados POR PROCESO + errores
 * (salida). Los marcadores de etapa NO cuentan (la serie ya los excluye): «ok» refleja trabajo
 * real, no auditoría. `soloProceso` recorta la barra a un único loop (monitor de Investigación).
 */
export function SerieProceso({
  serie,
  soloProceso,
}: {
  serie: ColaSerie;
  soloProceso?: Proceso;
}) {
  const procesos = soloProceso ? [soloProceso] : PROC_ORDEN;
  // Solo un proceso: el eje de días son los días con resultados reales (su throughput). Vista
  // completa: la unión de encolados (entrada) y resultados (salida) para alinear ambas barras.
  const dias = soloProceso
    ? serie.resultados.map((r) => r.dia).sort()
    : Array.from(
        new Set([...serie.encolados.map((e) => e.dia), ...serie.resultados.map((r) => r.dia)]),
      ).sort();

  // Para el máximo del eje: el día con más actividad (encolados o completados+errores del ámbito).
  const totalReal = (r: ResultadoDia) =>
    procesos.reduce(
      (acc, p) => acc + (r.por_proceso?.[p]?.completados ?? 0) + (r.por_proceso?.[p]?.errores ?? 0),
      0,
    );
  const maximo = Math.max(
    1,
    // En modo «solo un proceso» el eje NO escala con los encolados globales (que son del pool
    // entero, sobre todo producción): se ocultan y la barra mide solo el throughput de ese loop.
    ...(soloProceso ? [] : serie.encolados.map((e) => e.n)),
    ...serie.resultados.map((r) => totalReal(r)),
  );

  if (dias.length === 0) {
    return <p className="text-sm text-muted-foreground">Sin actividad en la ventana.</p>;
  }
  const porDia = new Map(serie.resultados.map((r) => [r.dia, r]));
  return (
    <div className="space-y-2">
      {dias.map((dia) => {
        const enc = soloProceso ? 0 : serie.encolados.find((e) => e.dia === dia)?.n ?? 0;
        const res = porDia.get(dia) ?? null;
        const okPorProc = procesos.map((p) => ({
          p,
          n: res?.por_proceso?.[p]?.completados ?? 0,
        }));
        const errores = res
          ? procesos.reduce((acc, p) => acc + (res.por_proceso?.[p]?.errores ?? 0), 0)
          : 0;
        const okTotal = okPorProc.reduce((acc, o) => acc + o.n, 0);
        return (
          <div key={dia} className="flex items-center gap-3 text-xs">
            <span className="w-20 shrink-0 tabular-nums text-muted-foreground">{dia.slice(5)}</span>
            <div className="flex h-4 flex-1 overflow-hidden rounded bg-muted">
              {!soloProceso && (
                <div
                  className="bg-amber-500/70"
                  style={{ width: `${(enc / maximo) * 100}%` }}
                  title={`${enc} encolados`}
                />
              )}
              {okPorProc.map((o) => (
                <div
                  key={o.p}
                  className={PROC_META[o.p].barra}
                  style={{ width: `${(o.n / maximo) * 100}%` }}
                  title={`${o.n} ${PROC_META[o.p].etiqueta} completados`}
                />
              ))}
              <div
                className="bg-destructive/70"
                style={{ width: `${(errores / maximo) * 100}%` }}
                title={`${errores} errores`}
              />
            </div>
            <span className="w-40 shrink-0 text-right tabular-nums text-muted-foreground">
              {!soloProceso && <span className="text-amber-600">{enc} enc</span>}
              {!soloProceso && " · "}
              {soloProceso ? (
                <>
                  {okTotal} ok
                </>
              ) : (
                okPorProc.map((o, i) => (
                  <React.Fragment key={o.p}>
                    {i > 0 && " · "}
                    <span className={PROC_META[o.p].texto}>{o.n}</span>
                  </React.Fragment>
                ))
              )}
              {errores > 0 && <span className="text-destructive"> · {errores} err</span>}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** Cabecera de Economía de tokens reutilizable (icono + título). */
export function TituloEconomia() {
  return (
    <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
      <Coins className="h-4 w-4 text-muted-foreground" />
      Economía de tokens
    </CardTitle>
  );
}

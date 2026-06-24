/**
 * CalculoScore — el «panel de señal» del detalle, en clave CALMA: contención tipográfica y aire.
 * El único elemento con presencia es el score (cifra grande, tabular); debajo, su veredicto de
 * corroboración, los APORTES al score como un hilo fino (el tramo de cada factor en el score
 * final) + la lista de factores con su aporte, y «¿por qué rankea así?» en frases editoriales.
 * Modelo v2: cada aporte es señal (0–1) × peso = mérito; mérito × confianza (corroboración) =
 * score. Vive solo en el detalle de la historia.
 */

import {
  calculoScore,
  estadoCorroboracion,
  factoresRanking,
} from "@/lib/noticias/ranking-editorial";
import { cn } from "@/lib/utils";
import type { Historia } from "@/types";

const ETIQUETA_SECCION =
  "text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground";

/** Opacidad del tramo naranja por posición: el mayor sólido, los siguientes atenuados. */
function tonoTramo(i: number): string {
  if (i === 0) return "bg-keni";
  if (i === 1) return "bg-keni/60";
  if (i === 2) return "bg-keni/40";
  return "bg-keni/25";
}

export function CalculoScore({ historia }: { historia: Historia }) {
  const { lineas, merito, confianza } = calculoScore(historia);
  const score = Math.round(historia.score * 100);
  const estado = estadoCorroboracion(historia);
  // Tramos del hilo: el aporte de cada factor al SCORE final (aporte × confianza), de mayor a
  // menor. Suman el score; el resto del 0–100 queda en gris (el track).
  const tramos = lineas
    .filter((l) => l.aporte > 0)
    .map((l) => ({ etiqueta: l.etiqueta, ancho: l.aporte * confianza }))
    .sort((a, b) => b.ancho - a.ancho);
  // Leyenda: todos los factores con su aporte al mérito; los de aporte 0, apagados al final.
  const leyenda = [...lineas].sort((a, b) => b.aporte - a.aporte);

  return (
    <div className="flex flex-col gap-7" data-testid="calculo-score">
      {/* 1 · Veredicto — la cifra manda */}
      <div>
        <div className="flex items-baseline gap-1.5">
          <span className="text-5xl font-medium leading-none tracking-tight tabular-nums">
            {score}
          </span>
          <span className="text-base font-normal tabular-nums text-muted-foreground/70">
            /100
          </span>
        </div>
        <p
          className={cn(
            "mt-3 inline-flex items-center gap-2 text-xs",
            estado.cautela
              ? "text-amber-700 dark:text-amber-400"
              : "text-emerald-700 dark:text-emerald-300",
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 shrink-0 rounded-full",
              estado.cautela ? "bg-amber-500" : "bg-emerald-500",
            )}
          />
          {estado.texto}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">Su sitio en el pool de hoy</p>
      </div>

      {/* 2 · Aportes al score — el hilo fino + la lista de factores */}
      {lineas.length > 0 && (
        <div>
          <p className={ETIQUETA_SECCION}>Aportes al score</p>
          <div className="mt-4 flex h-2 overflow-hidden rounded-full bg-muted">
            {tramos.map((t, i) => (
              <span
                key={t.etiqueta}
                className={cn("h-full", tonoTramo(i))}
                style={{ width: `${Math.round(t.ancho * 100)}%` }}
              />
            ))}
          </div>
          <ul className="mt-4">
            {leyenda.map((l, i) => (
              <li
                key={l.etiqueta}
                className={cn(
                  "flex items-baseline justify-between gap-4 py-1.5",
                  i > 0 && "border-t border-border/60",
                )}
              >
                <span
                  className={cn(
                    "text-[13px]",
                    i === 0 && l.aporte > 0 ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {l.etiqueta}
                </span>
                <span
                  className={cn(
                    "font-mono text-xs tabular-nums",
                    l.aporte > 0 ? "text-muted-foreground" : "text-muted-foreground/50",
                  )}
                >
                  {l.aporte.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
          <p
            className="mt-3 flex items-baseline justify-between gap-4 font-mono text-[11px] tabular-nums text-muted-foreground"
            data-testid="calculo-confianza"
          >
            <span>
              Mérito {merito.toFixed(2)} × confianza {confianza.toFixed(2)}
            </span>
            <span className="text-foreground">{(score / 100).toFixed(2)}</span>
          </p>
        </div>
      )}

      {/* 3 · ¿Por qué rankea así? */}
      <div>
        <p className={ETIQUETA_SECCION}>¿Por qué rankea así?</p>
        <ul
          className="mt-3 list-disc space-y-2 pl-4 text-[13px] leading-relaxed text-muted-foreground marker:text-muted-foreground/50"
          data-testid="factores-ranking"
        >
          {factoresRanking(historia).map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

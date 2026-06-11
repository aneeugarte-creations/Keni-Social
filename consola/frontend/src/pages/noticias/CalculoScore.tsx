/**
 * CalculoScore — la fórmula del ranking, línea a línea y LEGIBLE.
 *
 * Señal medida (0 a 1) × peso de la fórmula = aporte; la suma es el score. Lo usan el
 * pop-up del score en la tarjeta y el detalle de la historia (nada de tooltips kilométricos).
 */

import { calculoScore, factoresRanking } from "@/lib/noticias/ranking-editorial";
import type { Historia } from "@/types";

export function CalculoScore({ historia }: { historia: Historia }) {
  const { lineas, total } = calculoScore(historia);
  return (
    <div className="space-y-3" data-testid="calculo-score">
      <div className="space-y-1">
        <h4 className="text-sm font-semibold">¿Por qué rankea así?</h4>
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground" data-testid="factores-ranking">
          {factoresRanking(historia).map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      </div>
      {lineas.length > 0 && (
        <div className="space-y-1">
          <div className="rounded-md border bg-muted/30 px-3 py-2 font-mono text-[11px] leading-5">
            {lineas.map((l) => (
              <div key={l.etiqueta} className="flex justify-between gap-4 tabular-nums">
                <span>{l.etiqueta}</span>
                <span>
                  {l.senal.toFixed(2)} × {l.peso.toFixed(2)} = {l.aporte.toFixed(2)}
                </span>
              </div>
            ))}
            <div className="mt-1 flex justify-between gap-4 border-t pt-1 font-semibold tabular-nums">
              <span>Score</span>
              <span>
                {total.toFixed(2)} → {Math.round(historia.score * 100)}
              </span>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Señal (0-1) × peso = aporte; la suma es el score.
          </p>
        </div>
      )}
    </div>
  );
}

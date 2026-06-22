/**
 * CalculoScore — el «panel de señal» del detalle: el score como cifra grande, «¿por qué
 * rankea así?» en frases editoriales y el desglose como BARRAS (señal medida 0–1 × peso de
 * la fórmula = aporte; la suma es el score). Cada barra mide la señal; a su derecha, el
 * aporte ponderado. Vive solo en el detalle de la historia.
 */

import { calculoScore, factoresRanking } from "@/lib/noticias/ranking-editorial";
import type { Historia } from "@/types";

export function CalculoScore({ historia }: { historia: Historia }) {
  const { lineas } = calculoScore(historia);
  const score = Math.round(historia.score * 100);
  return (
    <div className="space-y-4" data-testid="calculo-score">
      <div>
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-semibold leading-none tracking-tight tabular-nums">
            {score}
          </span>
          <span className="text-sm text-muted-foreground">/ 100</span>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">Su sitio en el pool de hoy</p>
      </div>

      <div className="space-y-1.5">
        <h4 className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
          ¿Por qué rankea así?
        </h4>
        <ul
          className="list-disc space-y-1 pl-4 text-xs text-muted-foreground"
          data-testid="factores-ranking"
        >
          {factoresRanking(historia).map((f, i) => (
            <li key={i}>{f}</li>
          ))}
        </ul>
      </div>

      {lineas.length > 0 && (
        <div className="space-y-2.5">
          {lineas.map((l) => (
            <div
              key={l.etiqueta}
              className="grid grid-cols-[7rem_1fr_auto] items-center gap-2.5"
            >
              <span className="truncate text-xs">{l.etiqueta}</span>
              <span className="h-1.5 overflow-hidden rounded-full bg-muted">
                <span
                  className="block h-full rounded-full bg-foreground"
                  style={{ width: `${Math.round(Math.max(0, Math.min(1, l.senal)) * 100)}%` }}
                />
              </span>
              <span className="whitespace-nowrap font-mono text-[10px] tabular-nums text-muted-foreground">
                {l.senal.toFixed(2)} <span className="opacity-50">× {l.peso.toFixed(2)}</span>{" "}
                <span className="font-semibold text-foreground">{l.aporte.toFixed(2)}</span>
              </span>
            </div>
          ))}
          <p className="pt-0.5 text-[11px] text-muted-foreground">
            Señal (0–1) × peso = aporte; la suma es el score.
          </p>
        </div>
      )}
    </div>
  );
}

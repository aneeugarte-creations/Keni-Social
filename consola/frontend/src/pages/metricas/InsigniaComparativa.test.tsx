/**
 * Tests directos de la insignia comparativa: conteos en variación %, arranque desde
 * base 0 ("Nuevo", nunca "0.0 %"), engagement en PUNTOS (nunca variación relativa)
 * y degradación honesta cuando el dato no es calculable.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ComparativaMetrica } from "@/types";

import { InsigniaComparativa } from "./InsigniaComparativa";

function comp(parcial: Partial<ComparativaMetrica>): ComparativaMetrica {
  return {
    metrica: "visualizaciones",
    a: 0,
    b: 0,
    diferencia: 0,
    variacion_pct: 0,
    ...parcial,
  } as ComparativaMetrica;
}

describe("InsigniaComparativa", () => {
  it("conteo: variación relativa con signo y tooltip", () => {
    render(
      <InsigniaComparativa
        comp={comp({ a: 100, b: 139, diferencia: 39, variacion_pct: 39 })}
        title="vs periodo anterior (Mayo 2026)"
      />,
    );
    expect(screen.getByText("+39.0 %")).toBeInTheDocument();
    expect(screen.getByTitle("vs periodo anterior (Mayo 2026)")).toBeInTheDocument();
  });

  it("base 0 (a=0, b>0): badge «Nuevo», nunca un «0.0 %» que oculte el arranque", () => {
    render(
      <InsigniaComparativa
        comp={comp({ metrica: "interacciones", a: 0, b: 50, diferencia: 50, variacion_pct: 0 })}
      />,
    );
    expect(screen.getByText("Nuevo")).toBeInTheDocument();
    expect(screen.queryByText("0.0 %")).not.toBeInTheDocument();
  });

  it("engagement: diferencia en PUNTOS, jamás la variación relativa del porcentaje", () => {
    render(
      <InsigniaComparativa
        comp={comp({ metrica: "engagement_pct", a: 2.0, b: 2.4, diferencia: 0.4, variacion_pct: 20 })}
      />,
    );
    expect(screen.getByText("+0.4 pts")).toBeInTheDocument();
    expect(screen.queryByText(/\+20/)).not.toBeInTheDocument();
  });

  it("engagement sin diferencia calculable (null): no pinta nada", () => {
    const { container } = render(
      <InsigniaComparativa
        comp={comp({
          metrica: "engagement_pct",
          a: null as unknown as number,
          b: 2.4,
          diferencia: null as unknown as number,
          variacion_pct: null as unknown as number,
        })}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

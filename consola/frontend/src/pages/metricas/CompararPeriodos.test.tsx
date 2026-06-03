import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { CompararMetricas, OpcionesMetricas } from "@/types";

import { CompararPeriodos } from "./CompararPeriodos";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const OPCIONES: OpcionesMetricas = {
  marcas: [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro_sports", nombre: "Claro Sports" },
  ],
  rangos: [
    { id: "mes", etiqueta: "Este mes" },
    { id: "mes_cerrado", etiqueta: "Mes cerrado" },
  ],
};

const RESP: CompararMetricas = {
  marca: "",
  rango_a: "mes_cerrado",
  rango_b: "mes",
  etiqueta_a: "Mes cerrado",
  etiqueta_b: "Este mes",
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  total: {
    metricas: [
      { metrica: "visualizaciones", a: 1000, b: 1500, diferencia: 500, variacion_pct: 50 },
    ],
  },
  // `marca` ya viene resuelto del backend; el id `claro_sports` se resuelve por catálogo.
  por_marca: [
    {
      marca_id: "claro_sports",
      marca: "Claro Sports",
      comparativa: [
        { metrica: "visualizaciones", a: 400, b: 600, diferencia: 200, variacion_pct: 50 },
      ],
    },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CompararPeriodos", () => {
  it("usa el selector de tiempo (atajos · mes · personalizado) para AMBOS periodos", () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // Etiquetas claras Periodo A (origen) / Periodo B (comparado).
    expect(screen.getByText("Periodo A")).toBeInTheDocument();
    expect(screen.getByText("Periodo B")).toBeInTheDocument();

    // SelectorTiempo expone un combobox "Modo de tiempo" por cada periodo (A y B),
    // que el antiguo SelectorRango (solo presets) NO tenía. Dos periodos => dos
    // selectores de modo: es lo que habilita comparar periodos arbitrarios
    // (mes:AAAA-MM / rango:AAAA-MM-DD_AAAA-MM-DD), no solo preset vs preset.
    const modos = screen.getAllByLabelText("Modo de tiempo");
    expect(modos).toHaveLength(2);
  });

  it("hereda el rango visible como Periodo B (comparado) y consulta la comparativa", async () => {
    const espia = vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    // Periodo B parte del rango que se ve arriba ("mes"); A parte de otro distinto.
    await screen.findByText("Desglose por marca");
    const { rango_a, rango_b } = espia.mock.calls[0][0];
    expect(rango_b).toBe("mes");
    expect(rango_a).not.toBe("mes");
  });

  it("muestra el desglose por marca con el nombre legible (no el id crudo)", async () => {
    vi.spyOn(api, "metricasComparar").mockResolvedValue(RESP);
    renderConProviders(<CompararPeriodos opciones={OPCIONES} rangoActual="mes" />);

    expect(await screen.findByText("Desglose por marca")).toBeInTheDocument();
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    expect(screen.queryByText("claro_sports")).not.toBeInTheDocument();
  });
});

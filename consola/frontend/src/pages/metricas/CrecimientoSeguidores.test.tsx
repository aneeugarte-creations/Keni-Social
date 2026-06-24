import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { SerieSeguidores } from "@/types";

import { CrecimientoSeguidores } from "./CrecimientoSeguidores";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: SerieSeguidores = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  neto: 1234,
  neto_por_red: { instagram: 800, x: 434 },
  puntos: [
    { fecha: "2026-05-26", total: 10000, por_red: { instagram: 6000, x: 4000 } },
    { fecha: "2026-05-27", total: 10500, por_red: { instagram: 6300, x: 4200 } },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CrecimientoSeguidores", () => {
  it("destaca el total ACTUAL de seguidores y el neto como insignia", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue(RESP);
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    // El destacado es el total ACTUAL (último punto: 10 500), no el neto.
    expect(await screen.findByText("Seguidores totales")).toBeInTheDocument();
    // El total lleva el conteo exacto sin abreviar en su tooltip ("10,500 seguidores").
    expect(screen.getByTitle("10,500 seguidores")).toBeInTheDocument();
    // El neto del periodo viaja como insignia de variación con signo (un CONTEO, no un %).
    expect(screen.getByText("+1.2 k")).toBeInTheDocument();
    // etiquetas de red LEGIBLES (instagram → "Instagram"), nunca el id crudo.
    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.queryByText("instagram")).not.toBeInTheDocument();
  });

  it("desglosa las cifras EXACTAS por red en una tabla (inicio, actual, crecimiento, %)", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue(RESP);
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    const tabla = within(await screen.findByRole("table"));
    // La tabla trae su columna "Crecimiento" y una fila de totales.
    expect(tabla.getByText("Crecimiento")).toBeInTheDocument();
    expect(tabla.getByText("Total")).toBeInTheDocument();
    // Cifras EXACTAS con separador de miles (no abreviadas como el chart): stock por red.
    expect(tabla.getByText("6,000")).toBeInTheDocument();
    expect(tabla.getByText("6,300")).toBeInTheDocument();
    // Crecimiento absoluto (autoritativo: neto_por_red) con signo, y % sobre el inicio.
    expect(tabla.getByText("+800")).toBeInTheDocument();
    expect(tabla.getByText("+13.3 %")).toBeInTheDocument();
    // Totales del periodo al pie (10,000 → 10,500).
    expect(tabla.getByText("10,000")).toBeInTheDocument();
    expect(tabla.getByText("10,500")).toBeInTheDocument();
  });

  it("ofrece una alternativa textual del chart (role=img con el neto del periodo)", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue(RESP);
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    // El gráfico lleva un wrapper role="img" cuyo aria-label resume el neto con signo.
    expect(
      await screen.findByRole("img", { name: /seguidores del periodo: neto \+/i }),
    ).toBeInTheDocument();
  });

  it("dice con honestidad cuando la fuente no expone seguidores", async () => {
    vi.spyOn(api, "metricasSeguidores").mockResolvedValue({
      ...RESP,
      puntos: [],
      neto_por_red: {},
    });
    renderConProviders(<CrecimientoSeguidores marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/aún no hay datos de seguidores para este periodo/i),
    ).toBeInTheDocument();
  });
});

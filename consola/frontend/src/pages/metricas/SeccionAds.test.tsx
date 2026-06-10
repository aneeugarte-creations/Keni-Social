import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { AdsMetricas } from "@/types";

import { SeccionAds } from "./SeccionAds";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const RESP: AdsMetricas = {
  ads: [
    {
      nombre: "Campaña Mundial 2026",
      red: "facebook",
      impresiones: 250000,
      gasto: 12345,
      clics: 4200,
      moneda: "MXN",
      inicio: "2026-05-26",
      fin: "2026-06-01",
      es_post_impulsado: false,
    },
    {
      nombre: "Post impulsado noticias",
      red: "instagram",
      impresiones: 80000,
      gasto: 2500,
      clics: 900,
      moneda: "MXN",
      inicio: "2026-05-28",
      fin: "2026-06-01",
      es_post_impulsado: true,
    },
  ],
  total: {
    visualizaciones: 330000,
    gasto: 14845,
    clics: 5100,
    campanias: 2,
    moneda: "MXN",
  },
  etiqueta_rango: "Últimos 7 días",
  generado_en: "2026-06-02T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("SeccionAds", () => {
  it("pinta las campañas con cifras es-MX e Impresiones (no Vistas) como término", async () => {
    vi.spyOn(api, "metricasAds").mockResolvedValue(RESP);
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    // Espera al dato cargado (el título "Publicidad" ya se pinta durante la carga).
    expect(await screen.findByText("Campaña Mundial 2026")).toBeInTheDocument();
    expect(screen.getByText("Publicidad")).toBeInTheDocument();
    // En Ads el término correcto es "Impresiones" (KPI + columna), nunca "Vistas".
    expect(screen.getAllByText("Impresiones").length).toBeGreaterThan(0);
    expect(screen.queryByText("Vistas")).not.toBeInTheDocument();
    // KPI de impresiones totales: compacto visible, completo es-MX en el title.
    expect(screen.getByTitle("330,000")).toBeInTheDocument();
    // Gasto con separador de miles es-MX y la moneda de la fuente.
    expect(screen.getByText("14,845 MXN")).toBeInTheDocument();
    expect(screen.getByText("12,345 MXN")).toBeInTheDocument();
    // Las campañas con su red LEGIBLE (facebook -> "Facebook").
    expect(screen.getByText("Facebook")).toBeInTheDocument();
    expect(screen.queryByText("facebook")).not.toBeInTheDocument();
  });

  it("no renderiza la sección sin campañas en el periodo (no ensucia el dashboard)", async () => {
    const espia = vi.spyOn(api, "metricasAds").mockResolvedValue({
      ...RESP,
      ads: [],
      total: { visualizaciones: 0, gasto: 0, clics: 0, campanias: 0, moneda: "MXN" },
    });
    const { container } = renderConProviders(
      <SeccionAds marcaActual="__todas__" rangoActual="semana" />,
    );

    await vi.waitFor(() => expect(espia).toHaveBeenCalled());
    await vi.waitFor(() => expect(container).toBeEmptyDOMElement());
    expect(screen.queryByText("Publicidad")).not.toBeInTheDocument();
  });

  it("muestra un mensaje de error honesto si las campañas no cargan", async () => {
    vi.spyOn(api, "metricasAds").mockRejectedValue(new Error("boom"));
    renderConProviders(<SeccionAds marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText("No se pudieron cargar las campañas de Ads."),
    ).toBeInTheDocument();
  });
});

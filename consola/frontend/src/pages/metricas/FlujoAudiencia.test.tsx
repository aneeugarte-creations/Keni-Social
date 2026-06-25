import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import * as React from "react";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { FlujoAudiencia as FlujoAudienciaResp } from "@/types";

import { FlujoAudiencia } from "./FlujoAudiencia";

const RESP: FlujoAudienciaResp = {
  etiqueta_rango: "Últimos 7 días",
  generado_en: "2026-06-02T00:00:00",
  por_red: [
    // Facebook separa altas/bajas; TikTok solo da neto (altas/bajas null).
    { red: "facebook", altas: 1200, bajas: 300, neto: 900 },
    { red: "tiktok", altas: null, bajas: null, neto: -150 },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("FlujoAudiencia", () => {
  it("muestra altas, bajas y neto por red, con signo y color", async () => {
    vi.spyOn(api, "metricasAudiencia").mockResolvedValue(RESP);
    renderConProviders(<FlujoAudiencia marcaActual="__todas__" rangoActual="semana" />);

    const tabla = within(await screen.findByRole("table"));
    expect(tabla.getByText("Facebook")).toBeInTheDocument();
    expect(tabla.getByText("+1,200")).toBeInTheDocument(); // altas
    expect(tabla.getByText("−300")).toBeInTheDocument(); // bajas con signo menos
    expect(tabla.getByText("+900")).toBeInTheDocument(); // neto positivo
  });

  it("para una red que solo da neto (TikTok): altas/bajas como '—', neto siempre", async () => {
    vi.spyOn(api, "metricasAudiencia").mockResolvedValue(RESP);
    renderConProviders(<FlujoAudiencia marcaActual="__todas__" rangoActual="semana" />);

    const fila = (await screen.findByText("TikTok")).closest("tr");
    expect(fila).not.toBeNull();
    const celdas = within(fila as HTMLElement);
    // Altas y bajas no separadas → "—"; el neto (negativo) sí se muestra.
    expect(celdas.getAllByText("—").length).toBe(2);
    expect(celdas.getByText("−150")).toBeInTheDocument();
  });

  it("degrada con honestidad cuando no hay flujo de audiencia", async () => {
    vi.spyOn(api, "metricasAudiencia").mockResolvedValue({ ...RESP, por_red: [] });
    renderConProviders(<FlujoAudiencia marcaActual="__todas__" rangoActual="semana" />);

    expect(
      await screen.findByText(/no hay flujo de audiencia para este periodo/i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

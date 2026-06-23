import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { IngestaMetricas } from "@/types";

import { AlertaIngesta } from "./AlertaIngesta";
import { useVistaConfig } from "./vistaConfig";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

beforeEach(() => {
  useVistaConfig.getState().reset();
});

const CON_ALERTA: IngestaMetricas = {
  alertas: [
    {
      marca: "UnoTV",
      red: "facebook",
      formato: "feed_reel",
      ultima_pieza: "2026-05-30",
      dias_sin_piezas: 8,
      rezago_dias: 6,
    },
  ],
  etiqueta_rango: "Últimos 7 días",
  generado_en: "2026-06-08T00:00:00",
};

const SIN_ALERTAS: IngestaMetricas = {
  alertas: [],
  etiqueta_rango: "Últimos 7 días",
  generado_en: "2026-06-08T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("AlertaIngesta", () => {
  it("no renderiza nada cuando no hay canales estancados", async () => {
    const espia = vi.spyOn(api, "metricasIngesta").mockResolvedValue(SIN_ALERTAS);
    renderConProviders(<AlertaIngesta marcaActual="__todas__" rangoActual="semana" />);

    await vi.waitFor(() => expect(espia).toHaveBeenCalled());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("avisa del canal estancado con red y formato LEGIBLES", async () => {
    vi.spyOn(api, "metricasIngesta").mockResolvedValue(CON_ALERTA);
    renderConProviders(<AlertaIngesta marcaActual="__todas__" rangoActual="semana" />);

    const aviso = await screen.findByRole("status");
    expect(aviso).toHaveTextContent("La sincronización con Metricool parece estancada");
    // marca + red legible (facebook -> "Facebook") + formato legible (feed_reel -> "Reel").
    expect(aviso).toHaveTextContent("UnoTV");
    expect(aviso).toHaveTextContent("Facebook");
    expect(aviso).toHaveTextContent("Reel");
    expect(aviso).not.toHaveTextContent("feed_reel");
    // Días sin piezas y rezago frente al resto del feed.
    expect(aviso).toHaveTextContent("8 días");
    expect(aviso).toHaveTextContent("6 por detrás del resto");
  });

  it("no avisa de una red fuera del foco global (Facebook con foco en Instagram)", async () => {
    const espia = vi.spyOn(api, "metricasIngesta").mockResolvedValue(CON_ALERTA);
    useVistaConfig.getState().setRed("instagram");
    renderConProviders(<AlertaIngesta marcaActual="__todas__" rangoActual="semana" />);

    await vi.waitFor(() => expect(espia).toHaveBeenCalled());
    // La alerta es de Facebook; con foco en Instagram, no debe mostrarse nada.
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

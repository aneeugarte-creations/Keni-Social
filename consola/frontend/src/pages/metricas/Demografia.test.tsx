import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Demografia as DemografiaResp } from "@/types";

import { Demografia } from "./Demografia";
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

const RESP: DemografiaResp = {
  red: "instagram",
  distribuciones: {
    gender: [
      { clave: "M", valor: 62.5 },
      { clave: "F", valor: 37.5 },
    ],
    age: [{ clave: "25-34", valor: 41.2 }],
    postsTypes: [
      { clave: "reel", valor: 18 },
      { clave: "carrusel", valor: 7 },
    ],
  },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Demografia", () => {
  it("con una red en foco, pinta solo esa red con sus distribuciones legibles", async () => {
    useVistaConfig.getState().setRed("instagram");
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(screen.getByText("Demografía de la audiencia")).toBeInTheDocument();
    // Solo el panel de Instagram (sin panel de Facebook), con sus distribuciones legibles.
    expect(await screen.findByText("Instagram")).toBeInTheDocument();
    expect(screen.queryByText("Facebook")).not.toBeInTheDocument();
    // Las distribuciones aparecen cuando la consulta resuelve (el título y el panel son estáticos).
    expect(await screen.findByText("Género")).toBeInTheDocument();
    expect(screen.getByText("Edad")).toBeInTheDocument();
    expect(screen.getByText("Mezcla de formatos")).toBeInTheDocument();
  });

  it("sin foco de red, pinta un panel por cada red que expone demografía (IG y FB)", async () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    // Un panel por red demográfica: Instagram y Facebook, cada uno con su distribución.
    expect(await screen.findByText("Instagram")).toBeInTheDocument();
    expect(screen.getByText("Facebook")).toBeInTheDocument();
    // Cada panel resuelve su propia consulta: la distribución aparece una vez por red.
    await waitFor(() => expect(screen.getAllByText("Género")).toHaveLength(2));
  });

  it("degrada con honestidad cuando la red en foco no expone demografía", async () => {
    useVistaConfig.getState().setRed("instagram");
    vi.spyOn(api, "metricasDemografia").mockResolvedValue({ red: "instagram", distribuciones: {} });
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(
      await screen.findByText(/no expone demografía de audiencia/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Género")).not.toBeInTheDocument();
  });

  it("si el foco de red no incluye redes demográficas, lo dice sin consultar", async () => {
    useVistaConfig.getState().setRed("tiktok");
    const spy = vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcaActual="claro_sports" />);

    expect(
      await screen.findByText(/las redes en foco no exponen demografía/i),
    ).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });
});

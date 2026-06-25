import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { Demografia as DemografiaResp, MarcaDisponible } from "@/types";

import { Demografia } from "./Demografia";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const MARCAS: MarcaDisponible[] = [{ id: "claro_sports", nombre: "Claro Sports" }];

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
  it("pinta las distribuciones presentes con etiquetas legibles", async () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue(RESP);
    renderConProviders(<Demografia marcas={MARCAS} marcaActual="claro_sports" />);

    expect(screen.getByText("Demografía de la audiencia")).toBeInTheDocument();
    // Cada distribución del catálogo aparece como tarjeta con su etiqueta legible (se espera
    // a que la consulta resuelva: el título es estático y aparece ya en estado de carga).
    expect(await screen.findByText("Género")).toBeInTheDocument();
    expect(screen.getByText("Edad")).toBeInTheDocument();
    // La mezcla de formatos (postsTypes) tiene su propia etiqueta.
    expect(screen.getByText("Mezcla de formatos")).toBeInTheDocument();
  });

  it("degrada con honestidad cuando la red no expone demografía", async () => {
    vi.spyOn(api, "metricasDemografia").mockResolvedValue({ red: "instagram", distribuciones: {} });
    renderConProviders(<Demografia marcas={MARCAS} marcaActual="claro_sports" />);

    expect(
      await screen.findByText(/no expone demografía de audiencia/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Género")).not.toBeInTheDocument();
  });
});

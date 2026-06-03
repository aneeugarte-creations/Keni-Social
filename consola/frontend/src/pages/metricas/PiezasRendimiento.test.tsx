import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { OpcionesMetricas, PiezaRendimiento, PiezasRendimiento as Resp } from "@/types";

import { PiezasRendimiento } from "./PiezasRendimiento";

const OPCIONES: OpcionesMetricas = {
  marcas: [{ id: "unotv", nombre: "UnoTV" }],
  rangos: [{ id: "semana", etiqueta: "Últimos 7 días" }],
};

const PIEZA: PiezaRendimiento = {
  contenido_id: "c1",
  plataforma_id: "fb1",
  titulo: "Pieza publicada",
  marca: "unotv",
  marca_nombre: "UnoTV",
  red: "facebook",
  id_post_metricool: "m1",
  encontrado: true,
  visualizaciones: 50000,
  interacciones: 2000,
  engagement_pct: 4,
  url: "https://facebook.com/post/1",
  publicado: "2026-05-27",
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PiezasRendimiento", () => {
  it("enlaza el título de la pieza a su post real (nueva pestaña) cuando hay url", async () => {
    const resp: Resp = { marca: "", fuente: "muestra", total: 1, piezas: [PIEZA] };
    vi.spyOn(api, "metricasPiezasRendimiento").mockResolvedValue(resp);
    renderConProviders(<PiezasRendimiento opciones={OPCIONES} />);

    const enlace = await screen.findByRole("link", { name: /Pieza publicada/ });
    expect(enlace).toHaveAttribute("href", "https://facebook.com/post/1");
    expect(enlace).toHaveAttribute("target", "_blank");
  });

  it("no enlaza cuando la pieza no tiene url", async () => {
    const resp: Resp = {
      marca: "",
      fuente: "muestra",
      total: 1,
      piezas: [{ ...PIEZA, url: null }],
    };
    vi.spyOn(api, "metricasPiezasRendimiento").mockResolvedValue(resp);
    renderConProviders(<PiezasRendimiento opciones={OPCIONES} />);

    expect(await screen.findByText("Pieza publicada")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Pieza publicada/ })).not.toBeInTheDocument();
  });
});

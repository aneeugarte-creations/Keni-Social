import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import { numeroCompacto } from "@/lib/formato";
import type { DesgloseInteracciones as DesgloseResp } from "@/types";

import { DesgloseInteracciones } from "./DesgloseInteracciones";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const MARCAS = [{ id: "unotv", nombre: "UnoTV" }];

// `marca`/`red` llegan como IDS CRUDOS de la fuente; la UI los resuelve a nombre.
const RESP: DesgloseResp = {
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  celdas: [
    {
      marca: "unotv",
      red: "instagram",
      likes: 5000,
      comentarios: 300,
      compartidos: 120,
      guardados: 80,
      video_views: 90000,
      interacciones: 5500,
      visualizaciones: 90000,
      engagement_pct: 6.1,
      n_piezas: 10,
    },
  ],
  totales: {
    likes: 5000,
    comentarios: 300,
    compartidos: 120,
    guardados: 80,
    video_views: 90000,
    n_piezas: 10,
  },
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("DesgloseInteracciones", () => {
  it("muestra la tabla por marca×red LEGIBLE con la fila de totales", async () => {
    vi.spyOn(api, "metricasDesglose").mockResolvedValue(RESP);
    renderConProviders(
      <DesgloseInteracciones marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // marca (unotv → "UnoTV") y red (instagram → "Instagram") legibles, no el id crudo.
    // "UnoTV" aparece varias veces: una por cada red canónica (la real + las filas "—").
    expect((await screen.findAllByText("UnoTV")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.queryByText("instagram")).not.toBeInTheDocument();
    // fila de totales.
    expect(screen.getByText("Total")).toBeInTheDocument();
    // valores COMPLETOS (no compactados): likes = 5000 → "5,000" en celda y total.
    expect(screen.getAllByText("5,000").length).toBeGreaterThan(0);
    expect(screen.queryByText(/5\s*mil/i)).not.toBeInTheDocument();
    expect(screen.getAllByText("300").length).toBeGreaterThan(0);
  });

  it("ofrece una alternativa textual del chart (role=img con los totales por componente)", async () => {
    vi.spyOn(api, "metricasDesglose").mockResolvedValue(RESP);
    renderConProviders(
      <DesgloseInteracciones marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    const img = await screen.findByRole("img", {
      name: /Desglose de interacciones por marca y red/,
    });
    expect(img).toHaveAttribute(
      "aria-label",
      `Desglose de interacciones por marca y red: Me gusta ${numeroCompacto(5000)}, ` +
        "Comentarios 300, Compartidos 120, Guardados 80",
    );
  });

  it("ordena las celdas al clicar una cabecera de componente", async () => {
    const dos: DesgloseResp = {
      ...RESP,
      celdas: [
        { ...RESP.celdas[0], red: "instagram", likes: 1000 },
        { ...RESP.celdas[0], red: "facebook", likes: 9000 },
      ],
    };
    vi.spyOn(api, "metricasDesglose").mockResolvedValue(dos);
    renderConProviders(
      <DesgloseInteracciones marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    await screen.findByText("Total");
    const cabLikes = screen.getByRole("button", { name: /Me gusta/ });
    fireEvent.click(cabLikes); // desc -> Facebook (9000) primero
    const filasDatos = () =>
      screen
        .getAllByRole("row")
        .filter((f) => within(f).queryByText(/Instagram|Facebook/));
    expect(within(filasDatos()[0]).getByText("Facebook")).toBeInTheDocument();
    expect(cabLikes.closest("th")).toHaveAttribute("aria-sort", "descending");
  });

  it("dice con honestidad cuando no hay celdas", async () => {
    vi.spyOn(api, "metricasDesglose").mockResolvedValue({ ...RESP, celdas: [] });
    renderConProviders(
      <DesgloseInteracciones marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(
      await screen.findByText(/Aún no hay desglose de interacciones para este periodo/i),
    ).toBeInTheDocument();
  });
});

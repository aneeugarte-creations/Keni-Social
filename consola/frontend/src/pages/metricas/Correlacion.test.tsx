import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { CorrelacionSeguidores } from "@/types";

import { Correlacion } from "./Correlacion";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const NOTA = "Correlación, no causalidad: ganar seguidores depende de muchos factores.";

const MARCAS = [
  { id: "unotv", nombre: "UnoTV" },
  { id: "claro_sports", nombre: "Claro Sports" },
];

// `marca`/`red` llegan como IDS CRUDOS de la fuente; la UI los resuelve a nombre.
const RESP: CorrelacionSeguidores = {
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  fuente: "muestra",
  generado_en: "2026-06-02T00:00:00",
  nota: NOTA,
  items: [
    {
      marca: "unotv",
      red: "instagram",
      fecha: "2026-05-27",
      seguidores_ganados: 320,
      n_posts: 4,
      seguidores_por_post: 80,
      post_estrella: {
        id: "p1",
        titulo: "Gol de último minuto",
        engagement_pct: 9.4,
        url: "https://example.com/p1",
      },
    },
    {
      marca: "claro_sports",
      red: "x",
      fecha: "2026-05-28",
      seguidores_ganados: 10,
      n_posts: 0,
      seguidores_por_post: null,
      post_estrella: null,
    },
  ],
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Correlacion (seguidores vs publicación)", () => {
  it("renderiza la nota honesta y los items con marca legible y la pieza estrella enlazada", async () => {
    vi.spyOn(api, "metricasCorrelacion").mockResolvedValue(RESP);
    renderConProviders(
      <Correlacion marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // La nota (correlación ≠ causalidad) SIEMPRE visible.
    expect(await screen.findByText(NOTA)).toBeInTheDocument();
    // El item con su pieza estrella como enlace a la url.
    const estrella = screen.getByText("Gol de último minuto");
    const enlace = estrella.closest("a");
    expect(enlace).not.toBeNull();
    expect(enlace).toHaveAttribute("href", "https://example.com/p1");
    // marca (unotv → "UnoTV") y red (instagram → "Instagram") legibles, no el id crudo.
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("Instagram")).toBeInTheDocument();
    expect(screen.queryByText("instagram")).not.toBeInTheDocument();
    // El día sin posts no inventa ratio; claro_sports → "Claro Sports".
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay seguidores", async () => {
    vi.spyOn(api, "metricasCorrelacion").mockResolvedValue({ ...RESP, items: [] });
    renderConProviders(
      <Correlacion marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(await screen.findByText(/no expone seguidores/i)).toBeInTheDocument();
  });
});

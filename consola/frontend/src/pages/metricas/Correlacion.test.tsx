import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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
      fecha: "2026-05-27",
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
    // La red puede aparecer más de una vez (leyenda del scatter + celda de la tabla).
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getAllByText("Instagram").length).toBeGreaterThan(0);
    expect(screen.queryByText("instagram")).not.toBeInTheDocument();
    // El día sin posts no inventa ratio; claro_sports → "Claro Sports".
    expect(screen.getByText("Claro Sports")).toBeInTheDocument();
    // Seguidores ganados = CONTEO con signo ("+320"), NUNCA un porcentaje ("+320.0 %").
    expect(screen.getByText("+320")).toBeInTheDocument();
    expect(screen.queryByText("+320.0 %")).not.toBeInTheDocument();
    // Cabeceras en lenguaje del producto: «Piezas» y «Seg. por pieza» (no "post").
    expect(screen.getByText("Piezas")).toBeInTheDocument();
    expect(screen.getByText("Seg. por pieza")).toBeInTheDocument();
    expect(screen.queryByText("Posts")).not.toBeInTheDocument();
    expect(screen.queryByText("Seg./post")).not.toBeInTheDocument();
  });

  it("traduce el nombre técnico del ratio en la nota del backend a «Seg. por pieza»", async () => {
    const notaTecnica =
      "Correlación, no causalidad. 'seguidores_por_post' es un reparto indicativo.";
    vi.spyOn(api, "metricasCorrelacion").mockResolvedValue({ ...RESP, nota: notaTecnica });
    renderConProviders(
      <Correlacion marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(
      await screen.findByText(/«Seg\. por pieza» es un reparto indicativo/),
    ).toBeInTheDocument();
    expect(screen.queryByText(/'seguidores_por_post'/)).not.toBeInTheDocument();
  });

  it("pagina por día (un día por página) y navega entre días", async () => {
    const dosDias: CorrelacionSeguidores = {
      ...RESP,
      items: [
        { ...RESP.items[0], fecha: "2026-05-28", marca: "unotv", red: "instagram" },
        { ...RESP.items[1], fecha: "2026-05-27", marca: "claro_sports", red: "x" },
      ],
    };
    vi.spyOn(api, "metricasCorrelacion").mockResolvedValue(dosDias);
    renderConProviders(
      <Correlacion marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    // Primera página = día más reciente (2026-05-28 → UnoTV); el otro día no se ve.
    expect(await screen.findByText("UnoTV")).toBeInTheDocument();
    expect(screen.queryByText("Claro Sports")).not.toBeInTheDocument();
    // Conteo del día con plural correcto ("1 combinación de marca y red", no "marca·red").
    expect(screen.getByText(/1 combinación de marca y red · día 1 de 2/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Día más antiguo" }));
    expect(await screen.findByText("Claro Sports")).toBeInTheDocument();
    expect(screen.queryByText("UnoTV")).not.toBeInTheDocument();
  });

  it("dice con honestidad cuando no hay seguidores", async () => {
    vi.spyOn(api, "metricasCorrelacion").mockResolvedValue({ ...RESP, items: [] });
    renderConProviders(
      <Correlacion marcas={MARCAS} marcaActual="__todas__" rangoActual="semana" />,
    );

    expect(
      await screen.findByText(/aún no hay datos de seguidores para este periodo/i),
    ).toBeInTheDocument();
  });
});

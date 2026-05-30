import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Panel from "./Panel";

const PANEL = {
  metricas: {
    disponible: true,
    rango: "semana",
    fuente: "muestra",
    total: { visualizaciones: 12345, alcance: 67890, interacciones: 4321, engagement_pct: 6.4 },
    picos: [
      {
        marca: "UnoTV",
        direccion: "sube",
        variacion_vis_pct: 12.5,
        visualizaciones: 9999,
        pieza_titulo: "Gol de último minuto",
      },
    ],
  },
  cola: { total: 2 },
  proximas: {
    items: [
      {
        id: "p1",
        titulo: "Resumen de la jornada",
        marca: "unotv",
        marca_nombre: "UnoTV",
        red: "x",
        red_nombre: "X",
        fecha_programada: "2026-05-28T10:00",
        preparado_en: "",
      },
      {
        id: "p2",
        titulo: "Pieza ya vencida",
        marca: "unotv",
        marca_nombre: "UnoTV",
        red: "instagram",
        red_nombre: "Instagram",
        fecha_programada: "2026-05-27T08:00",
        preparado_en: "2026-05-27T08:00",
      },
    ],
    total: 2,
  },
  gating: {
    publicacion_real_activa: false,
    nota: "El posteo real a las plataformas está pendiente de #5/#8.",
  },
};

function stubFetch(panel: unknown = PANEL) {
  const fn = vi.fn(async (url: string | URL) => {
    if (String(url).includes("/api/panel")) {
      return new Response(JSON.stringify(panel), { status: 200 });
    }
    return new Response("{}", { status: 200 });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Panel (dashboard ligero)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra el resumen de métricas", async () => {
    stubFetch();
    renderConProviders(<Panel />);
    expect(await screen.findByText("Visualizaciones")).toBeInTheDocument();
  });

  it("cuenta las piezas que esperan revisión", async () => {
    stubFetch();
    renderConProviders(<Panel />);
    await screen.findByText(/cola de aprobación/i);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText(/piezas esperan revisión/i)).toBeInTheDocument();
  });

  it("lista las próximas programadas y marca la dry-run como lista", async () => {
    stubFetch();
    renderConProviders(<Panel />);
    expect(await screen.findByText("Resumen de la jornada")).toBeInTheDocument();
    expect(screen.getByText("Pieza ya vencida")).toBeInTheDocument();
    // La pieza vencida (con preparado_en) se marca como lista en dry-run.
    expect(screen.getByText("Lista (dry-run)")).toBeInTheDocument();
    expect(screen.getByText("Programada")).toBeInTheDocument();
  });

  it("avisa que el sistema no publica solo (gated por #5/#8)", async () => {
    stubFetch();
    renderConProviders(<Panel />);
    expect(await screen.findByText(/pendiente de #5\/#8/i)).toBeInTheDocument();
  });

  it("aguanta cuando las métricas no están disponibles", async () => {
    stubFetch({
      ...PANEL,
      metricas: { disponible: false, fuente: "muestra", total: null, picos: [] },
    });
    renderConProviders(<Panel />);
    expect(await screen.findByText(/métricas no están disponibles/i)).toBeInTheDocument();
  });
});

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
    nota: "El posteo real se hace vía Metricool y está gated por `KENI_PUBLICAR_REAL`.",
  },
};

// Cola de aprobación (`GET /api/aprobacion/cola`): query independiente del panel.
const COLA = {
  total: 2,
  cola: [
    {
      id: "pub-1",
      titulo: "Copy de la rueda de prensa",
      marca: "unotv",
      marca_nombre: "UnoTV",
      red: "instagram",
      red_nombre: "Instagram",
      enviado_a_revision_en: "2026-05-31T09:00",
    },
    {
      id: "pub-2",
      titulo: "Resumen del partido",
      marca: "claro-sports",
      marca_nombre: "Claro Sports",
      red: "x",
      red_nombre: "X",
      enviado_a_revision_en: "",
    },
  ],
};

function stubFetch(panel: unknown = PANEL, cola: unknown = COLA) {
  const fn = vi.fn(async (url: string | URL) => {
    const u = String(url);
    if (u.includes("/api/aprobacion/cola")) {
      return new Response(JSON.stringify(cola), { status: 200 });
    }
    if (u.includes("/api/panel")) {
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

  it("lista las piezas en revisión y cada una abre su revisión/aprobación", async () => {
    stubFetch();
    renderConProviders(<Panel />);
    const fila = await screen.findByText("Copy de la rueda de prensa");
    expect(screen.getByText("Resumen del partido")).toBeInTheDocument();
    // La pieza es un enlace que abre el tablero apuntando a ESA pieza (deep-link `?abrir=`).
    const enlace = fila.closest("a");
    expect(enlace).not.toBeNull();
    expect(enlace).toHaveAttribute("href", expect.stringContaining("abrir=pub-1"));
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

  it("aguanta cuando las métricas no están disponibles", async () => {
    stubFetch({
      ...PANEL,
      metricas: { disponible: false, fuente: "muestra", total: null, picos: [] },
    });
    renderConProviders(<Panel />);
    expect(await screen.findByText(/métricas no están disponibles/i)).toBeInTheDocument();
  });
});

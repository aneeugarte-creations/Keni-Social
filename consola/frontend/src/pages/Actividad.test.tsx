import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Actividad from "./Actividad";

const LISTA = {
  items: [
    {
      id: "g1",
      fuente: "generacion",
      tipo: "copy",
      etiqueta: "Resumen de la jornada",
      marca: "UnoTV",
      estado: "completado",
      fecha: "2026-05-28T10:00:00",
      metricas: { tokens: 12345, coste_usd: 0.038, duration_ms: 4200, num_turns: 3 },
      resultado_url: "/parrilla/pendientes",
    },
  ],
  total: 1,
};

const AGREGADOS = {
  total: { items: 7, coste_usd: 1.5, tokens: 98765 },
  por_tipo: [{ tipo: "copy", items: 4, coste_usd: 1.0, tokens: 60000 }],
  por_dia: [{ dia: "2026-05-28", items: 4, coste_usd: 1.0 }],
};

function stubFetch(lista: unknown = LISTA, agregados: unknown = AGREGADOS) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/actividad/agregados")) {
      return new Response(JSON.stringify(agregados), { status: 200 });
    }
    if (s.includes("/api/actividad")) {
      return new Response(JSON.stringify(lista), { status: 200 });
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

describe("Actividad (feed unificado de IA)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("muestra los KPIs de los agregados (items, coste, tokens)", async () => {
    stubFetch();
    renderConProviders(<Actividad />);
    expect(await screen.findByText("Actividad total")).toBeInTheDocument();
    expect(screen.getByText("Coste total")).toBeInTheDocument();
    // "Tokens" aparece como label de KPI y como cabecera de tabla: hay al menos uno.
    expect(screen.getAllByText("Tokens").length).toBeGreaterThan(0);
    // El total de items (7) aparece como valor del KPI.
    expect(screen.getByText("7")).toBeInTheDocument();
  });

  it("lista un ítem del feed con su etiqueta y badge de fuente", async () => {
    stubFetch();
    renderConProviders(<Actividad />);
    expect(await screen.findByText("Resumen de la jornada")).toBeInTheDocument();
    // Badge de fuente (Generación) y de tipo (copy) — copy aparece también en "Por tipo".
    expect(screen.getAllByText("Generación").length).toBeGreaterThan(0);
    expect(screen.getByText("Completado")).toBeInTheDocument();
  });

  it("ofrece 'Ver resultado' en un ítem completado con resultado_url", async () => {
    stubFetch();
    renderConProviders(<Actividad />);
    expect(await screen.findByText("Resumen de la jornada")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ver resultado/ })).toBeInTheDocument();
  });

  it("ofrece 'Ver en vivo' en una generación en curso (item D)", async () => {
    const enCurso = {
      items: [
        {
          id: "g2",
          fuente: "generacion",
          tipo: "copy",
          etiqueta: "En curso",
          marca: "UnoTV",
          estado: "ejecutando",
          fecha: "2026-05-28T11:00:00",
          metricas: { tokens: null, coste_usd: null, duration_ms: null, num_turns: null },
          resultado_url: null,
        },
      ],
      total: 1,
    };
    stubFetch(enCurso);
    renderConProviders(<Actividad />);
    expect(await screen.findByText("En curso")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Ver en vivo/ })).toBeInTheDocument();
  });

  it("muestra el estado vacío honesto cuando no hay actividad", async () => {
    stubFetch(
      { items: [], total: 0 },
      { total: { items: 0, coste_usd: 0, tokens: 0 }, por_tipo: [], por_dia: [] },
    );
    renderConProviders(<Actividad />);
    expect(await screen.findByText(/aún no hay actividad ia/i)).toBeInTheDocument();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Actividad from "./Actividad";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";

// Actividad lee la marca activa global (filtro por marca). En test no hay provider, así que
// stubeamos el hook a "todas las marcas" (igual patrón que el resto de páginas con marca global).
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => ({ marcaActiva: null, marcaPrimaria: null }),
}));

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
      resultado_url: "/operacion/feed/lista",
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

  it("lista un ítem del feed con su etiqueta, tipo y estado", async () => {
    stubFetch();
    renderConProviders(<Actividad />);
    expect(await screen.findByText("Resumen de la jornada")).toBeInTheDocument();
    // Ya no hay badge de fuente (todo es generación): queda el de tipo (etiqueta "Copy",
    // también en la tabla "Por tipo") y el de estado.
    expect(screen.getAllByText("Copy").length).toBeGreaterThan(0);
    expect(screen.getByText("Completado")).toBeInTheDocument();
  });

  it("la fila con resultado_url es la acción principal (clicable, sin botón aparte)", async () => {
    stubFetch();
    renderConProviders(<Actividad />);
    const fila = (await screen.findByText("Resumen de la jornada")).closest("tr");
    expect(fila).toHaveAttribute("role", "button");
    // Ya no hay columna de acciones con su botón.
    expect(screen.queryByRole("button", { name: /Ver resultado/ })).toBeNull();
  });

  it("la fila de una generación en curso es clicable (item D)", async () => {
    const enCurso = {
      items: [
        {
          id: "g2",
          fuente: "generacion",
          tipo: "copy",
          etiqueta: "Copy en curso",
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
    const fila = (await screen.findByText("Copy en curso")).closest("tr");
    expect(fila).toHaveAttribute("role", "button");
    expect(screen.queryByRole("button", { name: /Ver en vivo/ })).toBeNull();
  });

  it("muestra la etiqueta legible del tipo (insumos → Cajones del día)", async () => {
    const listaInsumos = {
      items: [
        {
          id: "g2",
          fuente: "generacion",
          tipo: "insumos",
          etiqueta: "Cajón portal · 2026-06-05",
          marca: "",
          estado: "completado",
          fecha: "2026-06-05T08:00:00",
          metricas: { tokens: 1000, coste_usd: 0.001, duration_ms: 800, num_turns: 1 },
          resultado_url: "/datos/investigacion/cajones",
        },
      ],
      total: 1,
    };
    const agregadosInsumos = {
      total: { items: 1, coste_usd: 0.001, tokens: 1000 },
      por_tipo: [{ tipo: "insumos", items: 1, coste_usd: 0.001, tokens: 1000 }],
      por_dia: [{ dia: "2026-06-05", items: 1, coste_usd: 0.001 }],
    };
    stubFetch(listaInsumos, agregadosInsumos);
    renderConProviders(<Actividad />);
    // La tabla y el desglose deben mostrar "Cajones del día", no "insumos".
    const labels = await screen.findAllByText("Cajones del día");
    expect(labels.length).toBeGreaterThan(0);
    // El raw tipo NO debe aparecer como texto visible.
    expect(screen.queryByText("insumos")).toBeNull();
  });

  it("etiquetaTipoGeneracion devuelve label para todos los tipos conocidos", () => {
    expect(etiquetaTipoGeneracion("copy")).toBe("Copy");
    expect(etiquetaTipoGeneracion("rss")).toBe("RSS");
    expect(etiquetaTipoGeneracion("imagen")).toBe("Imagen");
    expect(etiquetaTipoGeneracion("insumos")).toBe("Cajones del día");
    // Tipos retirados NO tienen etiqueta legacy: caen al raw (fallback).
    expect(etiquetaTipoGeneracion("investigacion")).toBe("investigacion");
    expect(etiquetaTipoGeneracion("import-calendario")).toBe("Importar calendario");
    // Fallback para tipos desconocidos
    expect(etiquetaTipoGeneracion("desconocido")).toBe("desconocido");
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

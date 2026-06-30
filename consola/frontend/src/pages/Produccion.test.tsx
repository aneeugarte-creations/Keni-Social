import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Produccion from "./Produccion";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";

// Producción lee la marca activa global (filtro por marca). En test no hay provider, así que
// stubeamos el hook a "todas las marcas" (igual patrón que el resto de páginas con marca global).
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => ({ marcaActiva: null, marcaPrimaria: null }),
}));

// Una run del pipeline + un trabajo SUELTO (clase "actividad"), como los sirve el feed
// unificado `GET /api/pipelines`.
const RUN = {
  clase: "run",
  id: "c1",
  titulo: "Cómo gana la FIFA",
  marca: "unotv",
  marca_nombre: "UnoTV",
  origen: "pipeline",
  creado: "2026-06-10T10:00:00",
  actualizado: "2026-06-10T10:05:00",
  estado_global: "pendiente",
  etapa_actual: "aprobar",
  etapas: [
    { clave: "fusionar", nombre: "Fusionar", estado: "ok", detalle: "2 fuentes", ts: "", es_ia: true },
    { clave: "redactar", nombre: "Redactar", estado: "ok", detalle: "1/1", ts: "", es_ia: true },
    { clave: "aprobar", nombre: "Aprobar", estado: "pendiente", detalle: "", ts: "", es_ia: false },
  ],
  verificacion: null,
  cluster: null,
  metricas: { items: 2, tokens: 5000, coste_usd: 0.05, duration_ms: 12000 },
  piezas: [],
};

const SUELTA = {
  clase: "actividad",
  id: "g1",
  titulo: "Resumen de la jornada",
  marca: "unotv",
  marca_nombre: "UnoTV",
  origen: "generacion",
  tipo: "insumos",
  creado: "2026-06-10T09:00:00",
  actualizado: "2026-06-10T09:01:00",
  estado_global: "ok",
  etapa_actual: "",
  etapas: [
    { clave: "trabajo", nombre: "insumos", estado: "ok", detalle: "", ts: "", es_ia: true },
  ],
  verificacion: null,
  cluster: null,
  metricas: { items: 1, tokens: 12345, coste_usd: 0.038, duration_ms: 4200 },
  piezas: [],
  resultado_url: "/operacion/investigacion/fuentes",
};

// Un tema FUTURO: pipeline del tablero aún sin trabajar (`futuro: true`), va al final del feed
// atenuado y rotulado «En cola».
const FUTURO = {
  clase: "run",
  id: "f1",
  titulo: "Tema en cola del tablero",
  marca: "unotv",
  marca_nombre: "UnoTV",
  origen: "pipeline",
  creado: "2026-06-09T10:00:00",
  actualizado: "2026-06-09T10:00:00",
  estado_global: "pendiente",
  etapa_actual: "fusionar",
  futuro: true,
  etapas: [
    { clave: "fusionar", nombre: "Fusionar", estado: "pendiente", detalle: "", ts: "", es_ia: true },
  ],
  verificacion: null,
  cluster: null,
  piezas: [],
};

const LISTA = {
  pipelines: [RUN, SUELTA],
  paginacion: { total: 2, limite: 20, desplazamiento: 0 },
  totales: { items: 3, tokens: 17345, coste_usd: 0.088, duration_ms: 16200 },
  futuros_total: 0,
  futuros_mostrados: 0,
};

const AGREGADOS = {
  total: { items: 7, coste_usd: 1.5, tokens: 98765, duration_ms: 360000 },
  por_tipo: [{ tipo: "copy", items: 4, coste_usd: 1.0, tokens: 60000 }],
  por_dia: [{ dia: "2026-06-10", items: 4, coste_usd: 1.0 }],
};

function stubFetch(lista: unknown = LISTA, agregados: unknown = AGREGADOS) {
  const fn = vi.fn(async (url: string | URL) => {
    const s = String(url);
    if (s.includes("/api/actividad/agregados")) {
      return new Response(JSON.stringify(agregados), { status: 200 });
    }
    if (s.includes("/api/pipelines")) {
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

describe("Producción (feed unificado: runs del pipeline + actividad suelta)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("es la pestaña Actividad del hub: solo el feed/traza, sin economía ni título propio", async () => {
    stubFetch();
    renderConProviders(<Produccion />);
    // Espera al feed para asegurar el render completo.
    expect(await screen.findByText("Cómo gana la FIFA")).toBeInTheDocument();
    // Los KPIs de economía (Trabajos IA / Coste total / Tiempo de cómputo) viven en /maquina/economia.
    expect(screen.queryByText("Trabajos IA")).toBeNull();
    expect(screen.queryByText("Coste total")).toBeNull();
    // El enlace «Economía de tokens → Agentes» desapareció: la economía es una pestaña hermana.
    expect(screen.queryByRole("link", { name: /Econom[ií]a de tokens/i })).toBeNull();
  });

  it("ya NO monta el embudo del backlog (embalse del tablero): es un conteo por etapa en Contexto", async () => {
    stubFetch();
    renderConProviders(<Produccion />);
    await screen.findByText("Cómo gana la FIFA");
    expect(screen.queryByText("Embalse del tablero (antes de la cola)")).toBeNull();
  });

  it("pinta un tema FUTURO atenuado con su badge «En cola» y «+N más en cola» al final", async () => {
    stubFetch({
      pipelines: [RUN, FUTURO],
      paginacion: { total: 2, limite: 20, desplazamiento: 0 },
      futuros_total: 35,
      futuros_mostrados: 30,
    });
    renderConProviders(<Produccion />);
    // El tema futuro se rotula «En cola» y su tarjeta queda atenuada (opacity-60).
    expect(await screen.findByText("En cola")).toBeInTheDocument();
    const tarjeta = screen.getByText("Tema en cola del tablero").closest(".opacity-60");
    expect(tarjeta).not.toBeNull();
    // Resumen de los futuros que no caben en el cap (35 - 30 = 5).
    expect(screen.getByText("+5 más en cola")).toBeInTheDocument();
  });

  it("junto a los filtros solo va el CONTEO del feed", async () => {
    stubFetch();
    renderConProviders(<Produccion />);
    expect(await screen.findByText(/2 items/i)).toBeInTheDocument();
    // El sumatorio global (totales.tokens = 17345) ya NO se pinta arriba: sobraba.
    expect(screen.queryByText(/17.3\s*k tok/i)).toBeNull();
  });

  it("pinta una RUN del pipeline como tarjeta con su tira de etapas y sus métricas", async () => {
    stubFetch();
    renderConProviders(<Produccion />);
    expect(await screen.findByText("Cómo gana la FIFA")).toBeInTheDocument();
    expect(screen.getByText("Fusionar")).toBeInTheDocument();
    expect(screen.getByText("Aprobar")).toBeInTheDocument();
    // Métricas de la run en la tarjeta (tokens compactos, 5000 → "5 k").
    expect(screen.getByText(/5\s*k tok/i)).toBeInTheDocument();
  });

  it("pinta un trabajo SUELTO como tarjeta de UNA etapa con el nombre legible de su tipo", async () => {
    stubFetch();
    renderConProviders(<Produccion />);
    expect(await screen.findByText("Resumen de la jornada")).toBeInTheDocument();
    // La etapa única lleva la etiqueta legible del tipo (insumos → Cajones del día), no el raw.
    expect(screen.getAllByText("Cajones del día").length).toBeGreaterThan(0);
    expect(screen.queryByText("insumos")).toBeNull();
  });

  it("la tarjeta de un trabajo suelto (generación) es clicable; abre su detalle in/out", async () => {
    stubFetch();
    renderConProviders(<Produccion />);
    const tarjeta = (await screen.findByText("Resumen de la jornada")).closest('[role="button"]');
    expect(tarjeta).not.toBeNull();
  });

  it("etiquetaTipoGeneracion devuelve label para todos los tipos conocidos", () => {
    expect(etiquetaTipoGeneracion("copy")).toBe("Redactar");
    expect(etiquetaTipoGeneracion("rss")).toBe("RSS");
    expect(etiquetaTipoGeneracion("imagen")).toBe("Imagen");
    expect(etiquetaTipoGeneracion("insumos")).toBe("Cajones del día");
    expect(etiquetaTipoGeneracion("import-calendario")).toBe("Importar calendario");
    expect(etiquetaTipoGeneracion("sugerir-hashtags")).toBe("Keywords");
    expect(etiquetaTipoGeneracion("carrusel")).toBe("Carrusel");
    // Fallback para tipos desconocidos
    expect(etiquetaTipoGeneracion("desconocido")).toBe("desconocido");
  });

  it("muestra el estado vacío honesto cuando no hay producción", async () => {
    stubFetch(
      { pipelines: [], paginacion: { total: 0, limite: 20, desplazamiento: 0 } },
      { total: { items: 0, coste_usd: 0, tokens: 0, duration_ms: 0 }, por_tipo: [], por_dia: [] },
    );
    renderConProviders(<Produccion />);
    expect(await screen.findByText(/aún no hay producción/i)).toBeInTheDocument();
  });
});

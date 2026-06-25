/**
 * Tests del dashboard de Métricas (página integradora).
 *
 * Cubre:
 *   1. El cuerpo del dashboard pinta sin avisos de demostración (no existen en la app).
 *   2. Deep-link del periodo: `?periodo=` válido (preset del backend o token
 *      `mes:`/`rango:`) inicializa el rango de la consulta del reporte.
 *   3. `?periodo=` inválido cae al primer rango disponible.
 *
 * Los hijos pesados (gráficas, tablas con queries propias) se mockean a stubs
 * vacíos: aquí se prueba la ORQUESTACIÓN de la página, no cada sección.
 */

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MarcaActivaContexto,
  type ValorMarcaActiva,
} from "@/hooks/marca-activa-contexto";
import * as apiMod from "@/lib/api";
import type { OpcionesMetricas, ReporteMetricas } from "@/types";

import Metricas from "./Metricas";
import { useVistaConfig } from "./metricas/vistaConfig";

// ── Stubs de los hijos pesados (queries/gráficas propias) ────────────────────

vi.mock("./metricas/TendenciaDiaria", () => ({ TendenciaDiaria: () => null }));
vi.mock("./metricas/AnalisisNarrativo", () => ({ AnalisisNarrativo: () => null }));
vi.mock("./metricas/DistribucionEngagement", () => ({ DistribucionEngagement: () => null }));
vi.mock("./metricas/PanoramaPiezas", () => ({ PanoramaPiezas: () => null }));
vi.mock("./metricas/PiezasConsolidada", () => ({ PiezasConsolidada: () => null }));
vi.mock("./metricas/CompararPeriodos", () => ({ CompararPeriodos: () => null }));
vi.mock("./metricas/EvolucionRedes", () => ({ EvolucionRedes: () => null }));
vi.mock("./metricas/Correlacion", () => ({ Correlacion: () => null }));
vi.mock("./metricas/Crosstab", () => ({ Crosstab: () => null }));
vi.mock("./metricas/DesgloseInteracciones", () => ({ DesgloseInteracciones: () => null }));
vi.mock("./metricas/CrecimientoSeguidores", () => ({ CrecimientoSeguidores: () => null }));
vi.mock("./metricas/GraficaPorSerie", () => ({ GraficaPorSerie: () => null }));
vi.mock("./metricas/MetricaPorCategoria", () => ({ MetricaPorCategoria: () => null }));
vi.mock("./metricas/SeccionAds", () => ({ SeccionAds: () => null }));
// Marcador para comprobar que una sección oculta NO monta su contenido.
vi.mock("./metricas/GraficaMarcas", () => ({
  GraficaMarcas: () => <div data-testid="grafica-marcas" />,
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const OPCIONES: OpcionesMetricas = {
  marcas: [{ id: "uno_tv", nombre: "UnoTV" }],
  rangos: [
    { id: "semana", etiqueta: "Últimos 7 días" },
    { id: "mes", etiqueta: "Últimos 30 días" },
  ],
};

function reporte(fuente: string): ReporteMetricas {
  return {
    rango: "semana",
    // Distintivo a propósito: no coincide con las etiquetas del selector de rangos.
    etiqueta_rango: "Corte de prueba (1–7 jun)",
    marca: "Todas",
    fuente,
    total: {
      visualizaciones: 1000,
      alcance: 800,
      interacciones: 50,
      engagement_pct: 5,
      piezas: 10,
    },
    // Dos marcas y dos redes CON datos: así se muestran las secciones por marca/por red
    // (un desglose por una dimensión con un solo valor se omite a propósito).
    cuentas: [
      { marca: "UnoTV", marca_id: "uno_tv", visualizaciones: 700, alcance: 500, interacciones: 35, engagement_pct: 5 },
      { marca: "Claro Sports", marca_id: "claro_sports", visualizaciones: 300, alcance: 200, interacciones: 15, engagement_pct: 5 },
    ],
    por_red: [
      { red: "instagram", visualizaciones: 600, alcance: 400, interacciones: 30, engagement_pct: 5 },
      { red: "youtube", visualizaciones: 400, alcance: null, interacciones: 20, engagement_pct: 5 },
    ],
    cobertura_redes: [],
    generado_en: "2026-06-10T12:00:00Z",
  };
}

// ── Arnés ─────────────────────────────────────────────────────────────────────

function valorMarcaActiva(marcaActiva: string | null): ValorMarcaActiva {
  return {
    marcaActiva,
    marcaPrimaria: marcaActiva,
    enMarcaPrimaria: true,
    esMultiMarca: false,
    puedeTodas: true,
    marcasParaSwitch: [],
    nombreActiva: marcaActiva,
    cambiarMarca: vi.fn(),
    volverAPrimaria: vi.fn(),
  };
}

function renderMetricas(ruta = "/metricas", marcaActiva: string | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MarcaActivaContexto.Provider value={valorMarcaActiva(marcaActiva)}>
        <MemoryRouter initialEntries={[ruta]}>
          <Metricas />
        </MemoryRouter>
      </MarcaActivaContexto.Provider>
    </QueryClientProvider>,
  );
}

// ── Stubs de API ──────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
let mockReporte: any;

beforeEach(() => {
  vi.spyOn(apiMod.api, "metricasOpciones").mockResolvedValue(OPCIONES);
  mockReporte = vi
    .spyOn(apiMod.api, "metricasReporte")
    .mockResolvedValue(reporte("metricool"));
  vi.spyOn(apiMod.api, "metricasIngesta").mockResolvedValue({
    alertas: [],
    etiqueta_rango: "Corte de prueba (1–7 jun)",
    generado_en: "2026-06-10T12:00:00Z",
  });
  // El control de Vistas guardadas (cabecera) lista al montar; sin datos en estos tests.
  vi.spyOn(apiMod.api, "vistas").mockResolvedValue({ vistas: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
  // La config de vista es un singleton global: restáurala para no contaminar otros tests.
  useVistaConfig.getState().reset();
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("Metricas · cuerpo del dashboard", () => {
  it("pinta el cuerpo sin avisos de datos de muestra (no existen en la app)", async () => {
    renderMetricas();

    // "Detalle por red" es una sección REAL (no mockeada): confirma que el cuerpo montó.
    expect(await screen.findByText("Detalle por red")).toBeInTheDocument();
    expect(screen.queryByText("Corte de prueba (1–7 jun)")).not.toBeInTheDocument();
    expect(screen.queryByText(/datos de muestra/i)).not.toBeInTheDocument();
  });

  it("muestra el contenido de una sección visible (toggle inline)", async () => {
    renderMetricas();

    // Visible por defecto: su contenido está montado y NO hay botón "Mostrar".
    expect(await screen.findByTestId("grafica-marcas")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Mostrar Comparativa por marca" }),
    ).not.toBeInTheDocument();
  });

  it("oculta una sección dejando su título + botón Mostrar, sin montar su contenido", async () => {
    useVistaConfig.getState().setSeccionVisible("marca-comparativa", false);
    renderMetricas();

    // El resto del dashboard sigue ahí.
    expect(await screen.findByText("Detalle por red")).toBeInTheDocument();
    // La sección oculta NO desaparece: conserva su título y ofrece "Mostrar" para restaurarla
    // in situ (no hay panel macro). Y su contenido NO se monta (ni se consulta).
    expect(screen.getByText("Comparativa por marca")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Mostrar Comparativa por marca" }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("grafica-marcas")).not.toBeInTheDocument();
  });
});

describe("Metricas · periodo en la URL (?periodo=)", () => {
  it("inicializa el rango desde ?periodo= cuando es un preset del backend", async () => {
    renderMetricas("/metricas?periodo=mes");

    await waitFor(() => {
      expect(mockReporte).toHaveBeenCalledWith(
        expect.objectContaining({ rango: "mes" }),
        expect.anything(),
      );
    });
  });

  it("acepta tokens mes:/rango: válidos aunque no estén en los presets", async () => {
    renderMetricas("/metricas?periodo=mes:2026-05");

    await waitFor(() => {
      expect(mockReporte).toHaveBeenCalledWith(
        expect.objectContaining({ rango: "mes:2026-05" }),
        expect.anything(),
      );
    });
  });

  it("cae al primer rango disponible cuando ?periodo= no es válido", async () => {
    renderMetricas("/metricas?periodo=basura");

    await waitFor(() => {
      expect(mockReporte).toHaveBeenCalledWith(
        expect.objectContaining({ rango: "semana" }),
        expect.anything(),
      );
    });
    expect(mockReporte).not.toHaveBeenCalledWith(
      expect.objectContaining({ rango: "basura" }),
      expect.anything(),
    );
  });
});

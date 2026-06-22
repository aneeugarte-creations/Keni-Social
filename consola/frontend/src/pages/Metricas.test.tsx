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
vi.mock("./metricas/MetricaPorLinea", () => ({ MetricaPorLinea: () => null }));
vi.mock("./metricas/SeccionAds", () => ({ SeccionAds: () => null }));
vi.mock("./metricas/GraficaMarcas", () => ({ GraficaMarcas: () => null }));

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
    cuentas: [],
    por_red: [],
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

    expect(await screen.findByText("Por marca")).toBeInTheDocument();
    expect(screen.queryByText("Corte de prueba (1–7 jun)")).not.toBeInTheDocument();
    expect(screen.queryByText(/datos de muestra/i)).not.toBeInTheDocument();
  });

  it("oculta una sección cuando la config la marca como no visible", async () => {
    useVistaConfig.getState().setSeccionVisible("por-marca", false);
    renderMetricas();

    // El resto del dashboard sigue ahí; solo desaparece la sección oculta y su encabezado.
    expect(await screen.findByText("Por red")).toBeInTheDocument();
    expect(screen.queryByText("Por marca")).not.toBeInTheDocument();
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

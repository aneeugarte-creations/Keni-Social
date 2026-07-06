/**
 * Tests del diálogo «Descargar PDF» de una campaña: parte con todo activado, la persona ajusta
 * secciones y piezas, y la descarga recibe justo esa configuración. La rasterización se mockea
 * (`descargarPdfCampania`): aquí se prueba la lógica de selección, no el PDF binario.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { AnaliticaCampania, ComparativaKpi, PiezaCampania } from "@/types";

import { DialogoDescargarPdf } from "./DialogoDescargarPdf";
import { descargarPdfCampania } from "./exportarPdfCampania";

vi.mock("./exportarPdfCampania", () => ({
  descargarPdfCampania: vi.fn().mockResolvedValue(undefined),
}));

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const COMP: ComparativaKpi = { actual: 0, anterior: 0, delta: 0, variacion_pct: null };

function pieza(id: string, visualizaciones: number): PiezaCampania {
  return {
    id,
    red: "instagram",
    marca: "UnoTV",
    titulo: `Pieza ${id}`,
    publicado: "2026-06-10T00:00:00Z",
    visualizaciones,
    visualizaciones_pagadas: 0,
    interacciones: 100,
    engagement_pct: 4.2,
    url: `https://example.com/${id}`,
    formato: "reel",
    por_cross_post: false,
    es_inorganico: false,
  };
}

function datos(piezas: PiezaCampania[]): AnaliticaCampania {
  return {
    campania: {
      id: "c1",
      marcas: ["uno_tv"],
      marcas_nombres: ["UnoTV"],
      nombre: "Mundial 2026",
      hashtags: ["Mundial2026"],
      etiqueta_web: "",
      precio_venta: 0,
      margen_objetivo_pct: 40,
      activa: true,
      fecha_creacion: "2026-06-01T00:00:00Z",
      fecha_actualizacion: "2026-06-01T00:00:00Z",
    },
    rango: "mes",
    periodo: { desde: "2026-05-26", hasta: "2026-06-25" },
    fuente: "metricool",
    kpis: { visualizaciones: 500000, interacciones: 23000, engagement_pct: 4.6, piezas: piezas.length, alcance: null },
    comparativa: { visualizaciones: COMP, interacciones: COMP, engagement_pct: COMP, piezas: COMP },
    tendencia: { puntos: [] },
    desglose_red: [],
    cross_posts: 0,
    inorganico: { visualizaciones: 0, gasto: 0, clics: 0, campanias: 0, moneda: "MXN" },
    piezas,
    generado_en: "2026-06-25T12:00:00Z",
  };
}

function montar(piezas: PiezaCampania[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DialogoDescargarPdf
        abierto
        datos={datos(piezas)}
        periodoEtiqueta="junio 2026"
        ocultarAds={false}
        tokenEnlace={null}
        enlacePrevia={null}
        onCerrar={() => {}}
      />
    </QueryClientProvider>,
  );
}

describe("DialogoDescargarPdf", () => {
  it("arranca con todas las piezas marcadas y descarga con la config por defecto (null = todas)", async () => {
    montar([pieza("a", 300), pieza("b", 200)]);

    // Contador de la cabecera de piezas: 2/2 seleccionadas.
    expect(screen.getByText("Piezas · 2/2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Descargar PDF" }));

    await waitFor(() =>
      expect(descargarPdfCampania).toHaveBeenCalledWith(
        expect.anything(),
        expect.objectContaining({
          // Selección completa -> null (comportamiento de hoy, con "+N más" si excede el tope).
          piezasSeleccionadas: null,
          secciones: { kpis: true, tendencia: true, desgloseRed: true, piezas: true },
        }),
      ),
    );
  });

  it("«Ninguna» deja la selección vacía y la pasa como Set vacío a la descarga", async () => {
    montar([pieza("a", 300), pieza("b", 200)]);

    fireEvent.click(screen.getByRole("button", { name: "Ninguna" }));
    expect(screen.getByText("Piezas · 0/2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Descargar PDF" }));

    await waitFor(() => expect(descargarPdfCampania).toHaveBeenCalled());
    const arg = vi.mocked(descargarPdfCampania).mock.calls.at(-1)?.[1];
    expect(arg?.piezasSeleccionadas).toBeInstanceOf(Set);
    expect(arg?.piezasSeleccionadas?.size).toBe(0);
  });

  it("apagar una sección la pasa como false a la descarga", async () => {
    montar([pieza("a", 300)]);

    fireEvent.click(screen.getByRole("checkbox", { name: "Tendencia diaria" }));
    fireEvent.click(screen.getByRole("button", { name: "Descargar PDF" }));

    await waitFor(() => expect(descargarPdfCampania).toHaveBeenCalled());
    const arg = vi.mocked(descargarPdfCampania).mock.calls.at(-1)?.[1];
    expect(arg?.secciones).toEqual({ kpis: true, tendencia: false, desgloseRed: true, piezas: true });
  });

  it("deseleccionar una pieza la excluye del Set enviado", async () => {
    montar([pieza("a", 300), pieza("b", 200)]);

    // La lista de piezas tiene un checkbox por pieza (aria-label = título); se desmarca "Pieza a".
    fireEvent.click(screen.getByRole("checkbox", { name: "Pieza a" }));
    expect(screen.getByText("Piezas · 1/2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Descargar PDF" }));

    await waitFor(() => expect(descargarPdfCampania).toHaveBeenCalled());
    const arg = vi.mocked(descargarPdfCampania).mock.calls.at(-1)?.[1];
    // Selección parcial -> Set con solo la pieza que quedó marcada.
    expect(arg?.piezasSeleccionadas).toBeInstanceOf(Set);
    expect(arg?.piezasSeleccionadas?.size).toBe(1);
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { HistoricoPieza, PiezaListado, PiezasListado } from "@/types";

import { ListaPiezas } from "./ListaPiezas";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

function pieza(over: Partial<PiezaListado>): PiezaListado {
  return {
    id: "p1",
    plataforma: "facebook",
    titulo: "Pieza A",
    publicado: "2026-05-20",
    visualizaciones: 1000,
    interacciones: 50,
    engagement_pct: 5,
    url: "https://facebook.com/post/a",
    likes: 40,
    comentarios: 5,
    compartidos: 3,
    guardados: 2,
    video_views: 900,
    tiempo_medio_vis_s: 12,
    clics_enlace: 10,
    formato: "reel",
    cuenta: "unotv",
    rendimiento_relativo: 1.2,
    linea: "Virales",
    ...over,
  };
}

// Dos piezas EL MISMO día (una página): para render, orden y filtro por título.
const MISMO_DIA: PiezaListado[] = [
  pieza({ id: "p1", titulo: "Gol de último minuto", visualizaciones: 1000, linea: "Virales" }),
  pieza({ id: "p2", titulo: "Noticia local", visualizaciones: 5000, linea: null }),
];

// Dos piezas en DÍAS distintos: para la paginación por día.
const DOS_DIAS: PiezaListado[] = [
  pieza({ id: "pA", titulo: "Pieza reciente", publicado: "2026-05-21" }),
  pieza({ id: "pB", titulo: "Pieza antigua", publicado: "2026-05-20" }),
];

function resp(over: Partial<PiezasListado> = {}): PiezasListado {
  return {
    rango: "mes",
    etiqueta_rango: "Últimos 30 días",
    marca: "",
    periodo: { desde: "2026-05-03", hasta: "2026-06-02" },
    fuente: "muestra",
    piezas: MISMO_DIA,
    total: MISMO_DIA.length,
    generado_en: "2026-06-02T00:00:00",
    ...over,
  };
}

const HISTORICO_VACIO: HistoricoPieza = { pieza_id: "p2", puntos: [], velocidad: null };

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("ListaPiezas", () => {
  it("muestra las piezas del día con 'Plataforma · Línea' (línea null -> 'Sin línea')", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp());
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);

    // Ambas son del mismo día -> una sola página las muestra.
    expect(await screen.findByText("Gol de último minuto")).toBeInTheDocument();
    expect(screen.getByText("Noticia local")).toBeInTheDocument();
    // Subtítulo: plataforma + línea (ya NO el formato). null -> "Sin línea".
    expect(screen.getByText(/Facebook · Virales/)).toBeInTheDocument();
    expect(screen.getByText(/Facebook · Sin línea/)).toBeInTheDocument();
    // Pie del listado (único): "N piezas · M días".
    expect(screen.getByText(/2 piezas · 1 días/)).toBeInTheDocument();
  });

  it("ordena por vistas (desc por defecto; toggle a asc al clicar)", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp());
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);
    await screen.findByText("Gol de último minuto");

    // Por defecto vistas desc: Noticia local (5000) va primero.
    let filas = screen.getAllByRole("button", { name: /Ver detalle de/ });
    expect(within(filas[0]).getByText("Noticia local")).toBeInTheDocument();

    // Al clicar "Vistas" alterna a asc: Gol (1000) pasa a primera.
    fireEvent.click(screen.getByRole("button", { name: /^Vistas/ }));
    filas = screen.getAllByRole("button", { name: /Ver detalle de/ });
    expect(within(filas[0]).getByText("Gol de último minuto")).toBeInTheDocument();
  });

  it("filtra por título con el buscador", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp());
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);
    await screen.findByText("Gol de último minuto");

    fireEvent.change(screen.getByLabelText("Buscar piezas por título"), {
      target: { value: "noticia" },
    });
    expect(screen.queryByText("Gol de último minuto")).not.toBeInTheDocument();
    expect(screen.getByText("Noticia local")).toBeInTheDocument();
    expect(screen.getByText(/1 de 2 piezas/)).toBeInTheDocument();
  });

  it("pagina por día: empieza por el más reciente y navega al anterior", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(
      resp({ piezas: DOS_DIAS, total: DOS_DIAS.length }),
    );
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);

    // Primera página = día más reciente (2026-05-21).
    expect(await screen.findByText("Pieza reciente")).toBeInTheDocument();
    expect(screen.queryByText("Pieza antigua")).not.toBeInTheDocument();
    expect(screen.getByText(/día 1 de 2/)).toBeInTheDocument();

    // Avanzar al día más antiguo.
    fireEvent.click(screen.getByRole("button", { name: "Día más antiguo" }));
    expect(await screen.findByText("Pieza antigua")).toBeInTheDocument();
    expect(screen.queryByText("Pieza reciente")).not.toBeInTheDocument();
    expect(screen.getByText(/día 2 de 2/)).toBeInTheDocument();
  });

  it("abre el detalle al clicar una fila", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp());
    const espia = vi
      .spyOn(api, "metricasPiezaHistorico")
      .mockResolvedValue(HISTORICO_VACIO);
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);
    await screen.findByText("Noticia local");

    fireEvent.click(screen.getByRole("button", { name: /Ver detalle de "Noticia local"/ }));

    // El modal abre y carga el histórico por id de la pieza clicada.
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(espia).toHaveBeenCalledWith({ id: "p2" }, expect.anything()));
  });
});

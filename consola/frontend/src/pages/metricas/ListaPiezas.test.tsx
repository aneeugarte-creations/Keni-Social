import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { HistoricoPieza, PiezaMetrica, PiezasListado } from "@/types";

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

function pieza(over: Partial<PiezaMetrica>): PiezaMetrica {
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
    ...over,
  };
}

const PIEZAS: PiezaMetrica[] = [
  pieza({ id: "p1", titulo: "Gol de último minuto", visualizaciones: 1000, engagement_pct: 3 }),
  pieza({ id: "p2", titulo: "Noticia local", visualizaciones: 5000, engagement_pct: 8 }),
];

function resp(over: Partial<PiezasListado> = {}): PiezasListado {
  return {
    rango: "mes",
    etiqueta_rango: "Últimos 30 días",
    marca: "",
    periodo: { desde: "2026-05-03", hasta: "2026-06-02" },
    fuente: "muestra",
    piezas: PIEZAS,
    total: PIEZAS.length,
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
  it("renderiza todas las piezas del periodo con red/formato legibles", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp());
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);

    expect(await screen.findByText("Gol de último minuto")).toBeInTheDocument();
    expect(screen.getByText("Noticia local")).toBeInTheDocument();
    // Red + formato traducidos.
    expect(screen.getAllByText(/Facebook · Reel/).length).toBeGreaterThan(0);
    expect(screen.getByText("2 de 2 piezas")).toBeInTheDocument();
  });

  it("ordena por vistas al clicar la cabecera", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp());
    renderConProviders(<ListaPiezas marcaActual="__todas__" rangoActual="mes" />);
    await screen.findByText("Gol de último minuto");

    // Por defecto se ordena por fecha (ambas iguales aquí); al clicar "Vistas" desc,
    // la de 5000 (Noticia local) va primero.
    fireEvent.click(screen.getByRole("button", { name: /^Vistas/ }));
    // Las filas de datos son botones ("Ver detalle de …"); la primera debe ser la
    // de mayor vistas (Noticia local, 5000) tras ordenar desc.
    const filas = screen.getAllByRole("button", { name: /Ver detalle de/ });
    expect(within(filas[0]).getByText("Noticia local")).toBeInTheDocument();
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
    expect(screen.getByText("1 de 2 piezas")).toBeInTheDocument();
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

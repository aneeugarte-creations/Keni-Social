import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { HistoricoPieza, MarcaDisponible, PiezaListado, PiezasListado } from "@/types";

import { PiezasConsolidada } from "./PiezasConsolidada";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const MARCAS: MarcaDisponible[] = [
  { id: "unotv", nombre: "UnoTV" },
  { id: "claro_sports", nombre: "Claro Sports" },
];

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

function resp(piezas: PiezaListado[]): PiezasListado {
  return {
    rango: "mes",
    etiqueta_rango: "Últimos 30 días",
    marca: "",
    periodo: { desde: "2026-05-03", hasta: "2026-06-02" },
    fuente: "muestra",
    piezas,
    total: piezas.length,
    generado_en: "2026-06-02T00:00:00",
  };
}

const HISTORICO_VACIO: HistoricoPieza = { pieza_id: "p2", puntos: [], velocidad: null };

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const MISMO_DIA: PiezaListado[] = [
  pieza({ id: "p1", titulo: "Gol de último minuto", visualizaciones: 1000, linea: "Virales" }),
  pieza({ id: "p2", titulo: "Noticia local", visualizaciones: 9000, linea: null }),
];

describe("PiezasConsolidada", () => {
  it("muestra 'Plataforma · Línea' y la tira de estadísticas (media/mediana)", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);

    expect(await screen.findByText("Gol de último minuto")).toBeInTheDocument();
    expect(screen.getByText(/Facebook · Virales/)).toBeInTheDocument();
    expect(screen.getByText(/Facebook · Sin línea/)).toBeInTheDocument();
    // Stats del conjunto filtrado: 2 piezas; vistas media (5K) y mediana (5K) presentes.
    expect(screen.getByText("Piezas")).toBeInTheDocument();
    expect(screen.getByText("Vistas media · mediana")).toBeInTheDocument();
    expect(screen.getByText("Engagement mediana")).toBeInTheDocument();
  });

  it("ordena por vistas (desc por defecto): la más vista va primero", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Gol de último minuto");
    const filas = screen.getAllByRole("button", { name: /Ver detalle de/ });
    expect(within(filas[0]).getByText("Noticia local")).toBeInTheDocument(); // 9000 vistas
  });

  it("filtra por título con el buscador", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Gol de último minuto");

    fireEvent.change(screen.getByLabelText("Buscar piezas por título"), {
      target: { value: "noticia" },
    });
    expect(screen.queryByText("Gol de último minuto")).not.toBeInTheDocument();
    expect(screen.getByText("Noticia local")).toBeInTheDocument();
  });

  it("pagina por día: arranca por el más reciente y navega al anterior", async () => {
    const dosDias = [
      pieza({ id: "pA", titulo: "Pieza reciente", publicado: "2026-05-21" }),
      pieza({ id: "pB", titulo: "Pieza antigua", publicado: "2026-05-20" }),
    ];
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(dosDias));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);

    expect(await screen.findByText("Pieza reciente")).toBeInTheDocument();
    expect(screen.queryByText("Pieza antigua")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Día más antiguo" }));
    expect(await screen.findByText("Pieza antigua")).toBeInTheDocument();
    expect(screen.queryByText("Pieza reciente")).not.toBeInTheDocument();
  });

  it("en vista agregada muestra todas las marcas recibidas (sin filtro propio de marca)", async () => {
    // La marca la manda el switch global: la tabla ya no tiene filtro de marca y
    // pinta cuanto devuelve la API (aquí, dos marcas mezcladas).
    const mezcla = [
      pieza({ id: "u1", titulo: "De UnoTV", cuenta: "unotv" }),
      pieza({ id: "c1", titulo: "De Claro", cuenta: "claro_sports" }),
    ];
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(mezcla));
    renderConProviders(
      <PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />,
    );
    expect(await screen.findByText("De Claro")).toBeInTheDocument();
    expect(screen.getByText("De UnoTV")).toBeInTheDocument();
    // No hay control de filtrado por marca en la tabla.
    expect(screen.queryByLabelText("Filtrar por marca")).not.toBeInTheDocument();
  });

  it("abre el detalle al clicar una fila", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    const espia = vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(HISTORICO_VACIO);
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Noticia local");

    fireEvent.click(screen.getByRole("button", { name: /Ver detalle de "Noticia local"/ }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(espia).toHaveBeenCalledWith({ id: "p2" }, expect.anything()));
  });
});

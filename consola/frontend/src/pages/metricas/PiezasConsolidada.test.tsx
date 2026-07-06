import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { HistoricoPieza, MarcaDisponible, PiezaListado, PiezasListado } from "@/types";

import { PiezasConsolidada } from "./PiezasConsolidada";
import { TABLA_PIEZAS } from "./columnasMeta";
import { useVistaConfig } from "./vistaConfig";

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
    alcance: 8000,
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
    categoria: "Virales",
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

afterEach(() => {
  vi.restoreAllMocks();
  // La config de vista es un singleton global: restáurala para no contaminar otros tests.
  useVistaConfig.getState().reset();
});

const MISMO_DIA: PiezaListado[] = [
  pieza({ id: "p1", titulo: "Gol de último minuto", visualizaciones: 1000, categoria: "Virales" }),
  pieza({ id: "p2", titulo: "Noticia local", visualizaciones: 9000, categoria: null }),
];

/** Filas de DATOS de la tabla (las que tienen celdas `td`), en orden de pintado.
 *  Modelo item-first: cada fila es un `tr` accionable (role="button"), no role="row";
 *  las seleccionamos directamente del DOM (los `tr` con celdas dentro del `tbody`). */
function filasDatos() {
  return Array.from(document.querySelectorAll<HTMLTableRowElement>("tbody tr")).filter(
    (f) => f.querySelectorAll("td").length > 0,
  );
}

describe("PiezasConsolidada", () => {
  it("muestra 'Plataforma · Línea' y la tira de estadísticas (promedio/mediana)", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);

    expect(await screen.findByText("Gol de último minuto")).toBeInTheDocument();
    expect(screen.getByText(/Facebook · Virales/)).toBeInTheDocument();
    expect(screen.getByText(/Facebook · Sin categoría/)).toBeInTheDocument();
    // Stats del conjunto filtrado: 2 piezas; vistas promedio (5K) y mediana (5K) presentes.
    expect(screen.getByText("Piezas")).toBeInTheDocument();
    expect(screen.getByText("Vistas promedio")).toBeInTheDocument();
    expect(screen.getByText("Vistas mediana")).toBeInTheDocument();
    expect(screen.getByText("Engagement (agregado)")).toBeInTheDocument();
    expect(screen.getByText("Engagement mediana")).toBeInTheDocument();
  });

  it("ordena por vistas (desc por defecto): la más vista va primero", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Gol de último minuto");
    expect(within(filasDatos()[0]).getByText("Noticia local")).toBeInTheDocument(); // 9000 vistas
  });

  it("muestra columnas de comentarios/compartidos/guardados/clics y ordena por ellas", async () => {
    const datos = [
      pieza({ id: "a", titulo: "Pocos comentarios", comentarios: 2 }),
      pieza({ id: "b", titulo: "Muchos comentarios", comentarios: 99 }),
    ];
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(datos));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Muchos comentarios");

    // El número de comentarios se ve y la columna de clics a enlace (tráfico web
    // fusionado) está presente como cabecera ordenable.
    expect(screen.getByText("99")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clics a enlace" })).toBeInTheDocument();

    // Orden por comentarios (clic en columna nueva = desc): la de más comentarios primero.
    // Nombre EXACTO "Comentarios" (la cabecera); los botones de fila contienen el título.
    fireEvent.click(screen.getByRole("button", { name: "Comentarios" }));
    expect(within(filasDatos()[0]).getByText("Muchos comentarios")).toBeInTheDocument();
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

  it("el día es una columna ordenable más (no el eje); pagina de 20 en 20", async () => {
    const dosDias = [
      pieza({ id: "pA", titulo: "Pieza reciente", publicado: "2026-05-21", visualizaciones: 1000 }),
      pieza({ id: "pB", titulo: "Pieza antigua", publicado: "2026-05-20", visualizaciones: 2000 }),
    ];
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(dosDias));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);

    // Ambas piezas en la MISMA página (20 por página), ya no separadas por día.
    expect(await screen.findByText("Pieza reciente")).toBeInTheDocument();
    expect(screen.getByText("Pieza antigua")).toBeInTheDocument();

    // Orden por defecto = Vistas desc → la más vista (la antigua, 2000) va primero,
    // aunque sea de un día anterior: la página 1 es el top del rango, no de un día.
    expect(within(filasDatos()[0]).getByText("Pieza antigua")).toBeInTheDocument();

    // El día es una columna ordenable: al ordenar por "Día" (clic = desc) manda la fecha.
    fireEvent.click(screen.getByRole("button", { name: "Día" }));
    expect(within(filasDatos()[0]).getByText("Pieza reciente")).toBeInTheDocument();
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

  it("abre el detalle con click izquierdo sobre la fila (modelo item-first)", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    const espia = vi.spyOn(api, "metricasPiezaHistorico").mockResolvedValue(HISTORICO_VACIO);
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Noticia local");

    // La fila es el control accionable (role="button"); su click izquierdo abre el detalle.
    const fila = filasDatos().find((f) => within(f).queryByText("Noticia local"));
    expect(fila).toBeDefined();
    expect(fila).toHaveAttribute("role", "button");
    fireEvent.click(fila!);
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(espia).toHaveBeenCalledWith({ id: "p2" }, expect.anything()));
  });

  it("'Abrir en la red' vive en el menú contextual (click derecho), no como icono suelto", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Noticia local");

    // Ya no hay icono/enlace suelto "Abrir la pieza en la red" en la fila.
    expect(screen.queryByLabelText("Abrir la pieza en la red")).not.toBeInTheDocument();

    const fila = filasDatos().find((f) => within(f).queryByText("Noticia local"))!;
    fireEvent.contextMenu(fila);
    expect(await screen.findByRole("menuitem", { name: "Abrir en la red" })).toBeInTheDocument();
  });

  it("las columnas opcionales (Me gusta/Reproducciones/Tiempo medio/Alcance) están OCULTAS por defecto", async () => {
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(MISMO_DIA));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Gol de último minuto");

    // Sin config guardada: las cabeceras opcionales no se pintan (la tabla no se sobrecarga).
    expect(screen.queryByRole("columnheader", { name: "Me gusta" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Reproducciones" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Tiempo medio" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Alcance" })).not.toBeInTheDocument();
  });

  it("al activar las columnas opcionales aparecen con su valor (tiempo como duración)", async () => {
    // Activa las 4 opcionales en la config de vista (lo que hace el editor de columnas).
    useVistaConfig.getState().setColumnas(TABLA_PIEZAS, {
      orden: [
        "pieza",
        "publicado",
        "visualizaciones",
        "engagement_pct",
        "comentarios",
        "compartidos",
        "guardados",
        "clics_enlace",
        "likes",
        "video_views",
        "tiempo_medio_vis_s",
        "alcance",
      ],
      ocultas: [],
    });
    const datos = [
      pieza({ id: "x", titulo: "Con granulares", likes: 4300, video_views: 55000, tiempo_medio_vis_s: 95, alcance: 120000 }),
    ];
    vi.spyOn(api, "metricasPiezasListado").mockResolvedValue(resp(datos));
    renderConProviders(<PiezasConsolidada marcaActual="__todas__" rangoActual="mes" marcas={MARCAS} />);
    await screen.findByText("Con granulares");

    // Cabeceras presentes.
    expect(screen.getByRole("columnheader", { name: "Me gusta" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Reproducciones" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Tiempo medio" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Alcance" })).toBeInTheDocument();
    // Valores: compactos es-MX para conteos; el tiempo medio como duración legible (95s → "1m 35s").
    expect(screen.getByText("4.3 k")).toBeInTheDocument();
    expect(screen.getByText("55 k")).toBeInTheDocument();
    expect(screen.getByText("1m 35s")).toBeInTheDocument();
    expect(screen.getByText("120 k")).toBeInTheDocument();
  });
});

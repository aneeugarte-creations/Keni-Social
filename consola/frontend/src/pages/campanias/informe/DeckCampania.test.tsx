/**
 * Tests del deck del PDF "testigo" de una campaña. Render puro (sin canvas/html-to-image,
 * eso lo cubre la guarda de `exportarPdfCampania.test.ts`): aquí se prueba que cada lámina
 * pinta lo que debe, respeta el modo cliente y degrada quien no tiene enlace público.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AnaliticaCampania, ComparativaKpi, PiezaCampania } from "@/types";

import { clavePieza } from "../formato";

import { DeckCampania, piezasParaTabla } from "./DeckCampania";

const COMP_SUBE: ComparativaKpi = { actual: 600, anterior: 400, delta: 200, variacion_pct: 50 };
const COMP_VACIA: ComparativaKpi = { actual: 0, anterior: 0, delta: 0, variacion_pct: null };

function pieza(id: string, visualizaciones: number, visualizacionesPagadas: number): PiezaCampania {
  return {
    id,
    red: "instagram",
    marca: "UnoTV",
    titulo: `Pieza ${id}`,
    publicado: "2026-06-10T00:00:00Z",
    visualizaciones,
    visualizaciones_pagadas: visualizacionesPagadas,
    interacciones: 100,
    engagement_pct: 4.2,
    url: `https://example.com/${id}`,
    formato: "reel",
    por_cross_post: false,
    es_inorganico: false,
  };
}

function datosBase(piezas: PiezaCampania[]): AnaliticaCampania {
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
    comparativa: {
      visualizaciones: COMP_SUBE,
      interacciones: COMP_SUBE,
      engagement_pct: COMP_VACIA,
      piezas: COMP_VACIA,
    },
    tendencia: {
      puntos: [
        { fecha: "2026-06-01", visualizaciones: 1000, interacciones: 50 },
        { fecha: "2026-06-02", visualizaciones: 2000, interacciones: 80 },
      ],
    },
    desglose_red: [
      { red: "instagram", piezas: 5, visualizaciones: 300000, interacciones: 12000, likes: 9000, comentarios: 500, compartidos: 300, guardados: 200, engagement_pct: 4.1 },
    ],
    cross_posts: 0,
    inorganico: { visualizaciones: 0, gasto: 0, clics: 0, campanias: 0, moneda: "MXN" },
    piezas,
    generado_en: "2026-06-25T12:00:00Z",
  };
}

describe("DeckCampania · portada y KPIs", () => {
  it("pinta el nombre de la campaña, sus marcas y hashtags", () => {
    render(<DeckCampania datos={datosBase([])} periodoEtiqueta="junio 2026" ocultarAds={false} />);

    expect(screen.getByText("Mundial 2026")).toBeInTheDocument();
    expect(screen.getByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("#Mundial2026")).toBeInTheDocument();
  });

  it("muestra el crecimiento de un KPI comparado y 'n/d' cuando el alcance no se mide", () => {
    render(<DeckCampania datos={datosBase([])} periodoEtiqueta="junio 2026" ocultarAds={false} />);

    // Vistas e interacciones comparten el mismo comparativo de prueba (+50 %): ambas tarjetas
    // pintan el badge.
    expect(screen.getAllByText("+50.0 %").length).toBe(2);
    expect(screen.getByText("n/d")).toBeInTheDocument();
  });
});

describe("DeckCampania · tabla de piezas y modo cliente", () => {
  it("suma lo pagado a lo orgánico en modo cliente (ocultarAds)", () => {
    render(
      <DeckCampania
        datos={datosBase([pieza("p1", 1000, 500)])}
        periodoEtiqueta="junio 2026"
        ocultarAds
      />,
    );

    // 1000 orgánicas + 500 pagadas fundidas = 1500 -> compactado "1.5K" (es-MX).
    expect(screen.getByText(/1[.,]5\s?K/i)).toBeInTheDocument();
  });

  it("avisa cuántas piezas quedan fuera cuando hay más del tope de la lámina", () => {
    const piezas = Array.from({ length: 20 }, (_, i) => pieza(`p${i}`, 1000 - i, 0));
    render(<DeckCampania datos={datosBase(piezas)} periodoEtiqueta="junio 2026" ocultarAds={false} />);

    expect(screen.getByText(/\+ 6 piezas más/)).toBeInTheDocument();
  });
});

describe("piezasParaTabla", () => {
  it("sin selección (null): ordena por vistas, corta al tope y reporta el resto", () => {
    const piezas = Array.from({ length: 20 }, (_, i) => pieza(`p${i}`, 1000 - i, 0));
    const { piezas: mostradas, restantes } = piezasParaTabla(datosBase(piezas), false, null);

    expect(mostradas).toHaveLength(14);
    expect(restantes).toBe(6);
    // Ordenadas por vistas efectivas desc: la primera es la de más vistas.
    expect(mostradas[0].visualizaciones).toBe(1000);
  });

  it("con selección: solo las elegidas, sin corte y sin resto", () => {
    const piezas = Array.from({ length: 20 }, (_, i) => pieza(`p${i}`, 1000 - i, 0));
    const datos = datosBase(piezas);
    // Elige 16 piezas concretas (más que el tope de una lámina): tienen que salir todas.
    const claves = new Set(datos.piezas.slice(0, 16).map((p, i) => clavePieza(p, i)));
    const { piezas: mostradas, restantes } = piezasParaTabla(datos, false, claves);

    expect(mostradas).toHaveLength(16);
    expect(restantes).toBe(0);
  });

  it("selección vacía: no muestra ninguna pieza", () => {
    const piezas = Array.from({ length: 5 }, (_, i) => pieza(`p${i}`, 100, 0));
    const { piezas: mostradas } = piezasParaTabla(datosBase(piezas), false, new Set());
    expect(mostradas).toHaveLength(0);
  });
});

describe("DeckCampania · secciones y paginación", () => {
  it("apaga una sección y su lámina desaparece del deck", () => {
    const { rerender } = render(
      <DeckCampania datos={datosBase([])} periodoEtiqueta="junio 2026" ocultarAds={false} />,
    );
    expect(screen.getByText("Desglose por red")).toBeInTheDocument();

    rerender(
      <DeckCampania
        datos={datosBase([])}
        periodoEtiqueta="junio 2026"
        ocultarAds={false}
        secciones={{ kpis: true, tendencia: true, desgloseRed: false, piezas: true }}
      />,
    );
    expect(screen.queryByText("Desglose por red")).not.toBeInTheDocument();
    // Otras secciones siguen ahí.
    expect(screen.getByText("Resultados del periodo")).toBeInTheDocument();
  });

  it("con más de una lámina de piezas seleccionadas, pinta la cabecera de la tabla por página", () => {
    const piezas = Array.from({ length: 20 }, (_, i) => pieza(`p${i}`, 1000 - i, 0));
    const datos = datosBase(piezas);
    const seleccion = new Set(datos.piezas.map((p, i) => clavePieza(p, i)));
    render(
      <DeckCampania
        datos={datos}
        periodoEtiqueta="junio 2026"
        ocultarAds={false}
        piezasSeleccionadas={seleccion}
      />,
    );

    // 20 seleccionadas -> 2 láminas de piezas (14 + 6): la cabecera "Publicación" sale dos veces.
    expect(screen.getAllByText("Publicación")).toHaveLength(2);
    // Sin nota de "+N más": todas las elegidas salen.
    expect(screen.queryByText(/piezas más en el periodo/)).not.toBeInTheDocument();
  });
});

describe("DeckCampania · desglose por red y enlace público", () => {
  it("pinta el desglose por red con su nombre legible", () => {
    render(<DeckCampania datos={datosBase([])} periodoEtiqueta="junio 2026" ocultarAds={false} />);

    expect(screen.getByText("Instagram")).toBeInTheDocument();
  });

  it("sin enlace público, no pinta la lámina de cierre", () => {
    render(<DeckCampania datos={datosBase([])} periodoEtiqueta="junio 2026" ocultarAds={false} />);

    expect(screen.queryByAltText("Código QR del informe")).not.toBeInTheDocument();
  });

  it("con enlace público, cierra con un QR clicable hacia esa URL", () => {
    const url = "https://social.kenitech.io/c/abc123";
    render(
      <DeckCampania
        datos={datosBase([])}
        periodoEtiqueta="junio 2026"
        ocultarAds={false}
        enlace={{ url, qrDataUrl: "data:image/gif;base64,xyz" }}
      />,
    );

    const enlace = screen.getByText(url).closest("a");
    expect(enlace).not.toBeNull();
    expect(enlace?.getAttribute("data-pdf-enlace")).toBe(url);
    expect(screen.getByAltText("Código QR del informe")).toHaveAttribute("src", "data:image/gif;base64,xyz");
  });
});

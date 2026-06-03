import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import * as React from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api } from "@/lib/api";
import type { AnaliticaPiezas, OpcionesMetricas, PiezaMetrica } from "@/types";

import { PiezasAnalitica } from "./PiezasAnalitica";

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
});

const OPCIONES: OpcionesMetricas = {
  marcas: [{ id: "unotv", nombre: "UnoTV" }],
  rangos: [{ id: "semana", etiqueta: "Últimos 7 días" }],
};

// `cuenta` y `plataforma` llegan como IDS CRUDOS de la fuente: la UI los resuelve a
// nombre legible (catálogo de marcas + mapa de redes), no los muestra tal cual.

const ESTADISTICAS = {
  n: 3,
  media: 5.5,
  mediana: 5,
  p25: 3,
  p75: 8,
  minimo: 1,
  maximo: 10,
  desviacion: 2,
};

const PIEZA_TOP: PiezaMetrica = {
  id: "p1",
  plataforma: "instagram",
  titulo: "Gol de último minuto",
  publicado: "2026-05-27",
  visualizaciones: 120000,
  interacciones: 8000,
  engagement_pct: 6.7,
  url: "https://example.com/p1",
  likes: 5000,
  comentarios: 300,
  compartidos: 120,
  guardados: 80,
  video_views: 90000,
  tiempo_medio_vis_s: 12,
  clics_enlace: 40,
  formato: "reel",
  cuenta: "unotv",
  rendimiento_relativo: 2.3,
};

// Pieza con desglose parcialmente null: no debe inventar 0 (distingue 0 de sin dato).
const PIEZA_PEOR: PiezaMetrica = {
  ...PIEZA_TOP,
  id: "p2",
  titulo: "Nota floja",
  engagement_pct: 0.4,
  likes: null,
  comentarios: null,
  compartidos: null,
  guardados: null,
  rendimiento_relativo: null,
  cuenta: "unotv",
  // Riqueza barata ausente: la UI no debe inventar 0 ni pintar el campo.
  tiempo_medio_vis_s: null,
  clics_enlace: null,
};

const RESP: AnaliticaPiezas = {
  cuenta: null,
  rango: "semana",
  etiqueta_rango: "Últimos 7 días",
  periodo: { desde: "2026-05-26", hasta: "2026-06-01" },
  total: 2,
  fuente: "muestra",
  engagement: ESTADISTICAS,
  visualizaciones: ESTADISTICAS,
  top: [PIEZA_TOP],
  peores: [PIEZA_PEOR],
  distribucion: [{ etiqueta: "0–5 %", inicio: 0, fin: 5, n: 1 }],
  generado_en: "2026-06-02T00:00:00",
};

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("PiezasAnalitica (enriquecida)", () => {
  it("muestra marca·red LEGIBLE, el badge de rendimiento relativo y el desglose granular", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue(RESP);
    renderConProviders(<PiezasAnalitica opciones={OPCIONES} rangoActual="semana" />);

    expect(await screen.findByText("Gol de último minuto")).toBeInTheDocument();
    // (a) marca (`cuenta`=unotv → "UnoTV") + red (instagram → "Instagram"): legibles,
    //     NUNCA el id crudo "unotv · instagram".
    expect(screen.getAllByText("UnoTV · Instagram").length).toBeGreaterThan(0);
    expect(screen.queryByText(/unotv · instagram/)).not.toBeInTheDocument();
    // (b) badge de rendimiento relativo cuando no es null.
    expect(screen.getByText(/2\.3× mediana de vistas de su red/)).toBeInTheDocument();
    // (c) desglose granular legible: cada chip lleva el nombre como tooltip (title)
    //     y el valor. Comentarios = 300, sin compactar.
    const chipComentarios = document.querySelector('[title="Comentarios"]');
    expect(chipComentarios?.textContent).toContain("300");
    // (d) riqueza barata: clics a enlace y tiempo de visualización cuando != null.
    const chipClics = document.querySelector('[title="Clics al enlace"]');
    expect(chipClics?.textContent).toContain("40");
    const chipTiempo = document.querySelector('[title="Tiempo medio de visualización"]');
    expect(chipTiempo?.textContent).toContain("12s");
    // (e) el título ENLAZA al post real (nueva pestaña) cuando hay url.
    const enlace = screen.getByRole("link", { name: /Gol de último minuto/ });
    expect(enlace).toHaveAttribute("href", "https://example.com/p1");
    expect(enlace).toHaveAttribute("target", "_blank");
  });

  it("no inventa desglose, badge ni riqueza cuando la fuente no los expone (null)", async () => {
    vi.spyOn(api, "metricasPiezas").mockResolvedValue({
      ...RESP,
      top: [PIEZA_PEOR],
      peores: [],
    });
    renderConProviders(<PiezasAnalitica opciones={OPCIONES} rangoActual="semana" />);

    expect(await screen.findByText("Nota floja")).toBeInTheDocument();
    // sin rendimiento_relativo -> no hay badge "× mediana de vistas".
    expect(screen.queryByText(/mediana de vistas de su red/)).not.toBeInTheDocument();
    // clics_enlace/tiempo null -> no se pintan los chips (sin 0 falso).
    expect(document.querySelector('[title="Clics al enlace"]')).toBeNull();
    expect(document.querySelector('[title="Tiempo medio de visualización"]')).toBeNull();
  });
});
